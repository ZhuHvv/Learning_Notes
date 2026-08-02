# Semaphore、Queue 与异步背压

> 学习层级：进阶
> 前置知识：[Task 聚合、取消、超时与 asyncio.wait
> ](008\_Task\_%E8%81%9A%E5%90%88%E3%80%81%E5%8F%96%E6%B6%88%E3%80%81%E8%B6%85%E6%97%B6%E4%B8%8E\_asyncio.wait.md)后续阅读：[异步生成器与 asynccontextmanager
> 
> ](10_%E5%BC%82%E6%AD%A5%E7%94%9F%E6%88%90%E5%99%A8%E3%80%81asynccontextmanager_%E4%B8%8E_yield_%E7%94%9F%E5%91%BD%E5%91%A8%E6%9C%9F.md)

## 1. Semaphore 限制并发度

`asyncio.Semaphore(3)` 表示同一进程、同一个 Semaphore 实例保护的区域内，最多有三个协程同时进入：

```python
semaphore = asyncio.Semaphore(3)

async def fetch_one(url: str) -> bytes:
    async with semaphore:
        return await http_get(url)
```

它限制的是同时在途的工作数量，不是：

- 每秒请求数（QPS）；
- 单请求超时；
- 跨进程或跨机器的全局配额；
- 外部服务的可靠重试策略。

QPS 需要速率限制器，超时需要客户端 timeout 或 `wait_for`，服务级全局配额通常需要网关、Redis 或消息队列。

许可应尽量只包住真正稀缺的外部 I/O。`asyncio.BoundedSemaphore` 能在释放次数超过初始值时报错，但 Semaphore 与 BoundedSemaphore 都不保证精确公平排队。

## 2. Queue 连接生产者和消费者

```python
queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=100)
```

通用形式可以记为 `asyncio.Queue(maxsize=N)`。有界 Queue 配合 `await queue.put(item)` 可以在队列满时暂停生产者，把消费压力反向传递。无界 Queue 或持续使用 `put_nowait()` 不会形成容量背压，消息可能不断积压内存。

常用方法：

- `await put()`：队列满时等待；
- `put_nowait()`：队列满时抛 `QueueFull`；
- `await get()`：队列空时等待；
- `get_nowait()`：队列空时抛 `QueueEmpty`；
- `task_done()`：表示某个取出的条目处理完毕；
- `join()`：等待所有已入队工作都被标记为完成。

## 3. 生产者/消费者示例

```python
import asyncio

queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=100)

async def producer(items: list[str]) -> None:
    for item in items:
        await queue.put(item)
    await queue.put(None)

async def consumer() -> None:
    while True:
        item = await queue.get()
        try:
            if item is None:
                return
            await handle(item)
        finally:
            queue.task_done()

async def main(items: list[str]) -> None:
    producer_task = asyncio.create_task(producer(items))
    consumer_task = asyncio.create_task(consumer())

    await producer_task
    await queue.join()
    await consumer_task
```

该示例只有一个消费者，因此一个结束哨兵就够了。若有多个消费者，必须为每个消费者设计明确的停止协议。

`task_done()` 必须与成功 `get()` 的次数匹配；遗漏会使 `join()` 永远等待，重复调用则会抛 `ValueError`。

## 4. 背压必须传回源头

异步生成器会在 `yield` 处暂停，只有上层请求下一个值时才继续，因此慢消费者可以限制生成器前进。

但若数据源与生成器之间还有一个无界 Queue，生产者仍能先把大量数据塞进内存，生成器的背压并没有真正传回源头：

```
快速生产者 → 无界 Queue（持续积压）→ 异步生成器 → 慢消费者
```

有效背压需要从消费端一直贯穿到生产端，包括：

- 有界缓冲区；
- 可等待的写入；
- 合理的并发上限；
- 超时、取消和过载策略。

## 5. 组合并发度与时间边界

```python
import asyncio

async def fetch_all(urls: list[str]) -> list[bytes]:
    semaphore = asyncio.Semaphore(3)

    async def fetch_one(url: str) -> bytes:
        async with semaphore:
            return await asyncio.wait_for(http_get(url), timeout=5)

    return await asyncio.gather(*(fetch_one(url) for url in urls))
```

这里：

- `gather` 负责聚合结果；
- Semaphore 负责同时在途的请求数量；
- `wait_for` 负责单次等待的时间边界。

三者解决不同问题，不能互相替代。

## 6. 共享容器不等于并发协议

在单事件循环中，一次不包含 `await` 的普通 list 修改不会在中间切换 Task，但多步骤“检查后写入”仍可能跨越 await，也不是事务。线程、多进程或多个服务实例之间更不能依赖这一特性。

需要共享状态时，应明确使用 Queue、锁、不可变消息、数据库事务或其他符合实际部署模型的机制。
