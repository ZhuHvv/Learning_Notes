# async   await 与协程调度

> 所属分类：Python / Async / FastAPI  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

`async def` 定义协程函数，调用后得到 coroutine object；`await` 在等待尚未完成的 I/O 或 Future 时暂停当前 Task，把线程交还事件循环。asyncio 是协作式并发，不等于自动多线程或 CPU 并行。

## 2. 原理性解释

- coroutine object 只有被 `await`、包装为 Task，或交给框架调度后才开始执行；
- Task 是事件循环中的协程包装，不是 OS 线程；
- 真正的切换发生在尚未完成的 awaitable 处，已完成的 awaitable 可能立即返回；
- `async def` 内的同步数据库、文件、网络或 CPU 计算仍会阻塞事件循环；
- Task 取消是协作式请求，异常和资源清理仍需显式处理；
- `gather`、Semaphore、Queue、timeout 分别解决聚合、并发度、生产消费和时间边界问题。

### `async` 定义可暂停函数，`await` 才可能交出控制权

```python
async def fetch_document(doc_id: str):
    data = await http_get(f"/documents/{doc_id}")
    return data

coro = fetch_document("doc-1")  # 尚未执行函数体
document = await coro            # 此时开始推进
```

coroutine object 通常只能完整 await 一次；再次执行要重新调用协程函数。`async def` 中出现 `yield` 时，得到的是异步生成器，应通过 `async for` / `anext()` 消费，而不是直接 await。

### Task、取消与异常

`asyncio.create_task()` 把协程注册到当前事件循环，让调用方可以继续执行其他逻辑，但不会新建线程。应保留 Task 引用，通过 `await task` 或 `task.exception()` 获取异常；取消时调用 `task.cancel()` 后继续 await，让 `finally` 有机会清理。

`cancel()` 通常在 Task 下一次到达可取消挂起点时注入 `CancelledError`。若协程长时间执行同步代码，取消也无法及时生效。

### 同步阻塞函数与 `to_thread`

```python
parsed = await asyncio.to_thread(parse_large_file, path)
```

`to_thread` 适合暂时无法替换的同步文件 I/O、网络 SDK 或短时同步库调用。默认线程池容量有限；外层 Task 被取消通常不能强制停止已运行的线程函数；CPU 密集纯 Python 代码还受 GIL 影响，通常应评估进程池或外部 worker。跨线程使用数据库 Session、client 和可变对象前必须确认线程安全。

### `gather` 与结果顺序

`asyncio.gather()` 并发推进多个 awaitable，结果按传入顺序排列，不按完成顺序。默认情况下，一个异常会传播给等待者，但其他 awaitable 不会仅因此被 `gather` 自动全部取消。`return_exceptions=True` 会把异常放进结果列表，调用方仍须逐项处理。

需要按完成顺序处理或只取首个完成任务时，见 `035_asyncio.wait、done_pending_与_FIRST_COMPLETED.md`。

### Semaphore：并发度不是 QPS

`asyncio.Semaphore(3)` 表示同一进程、同一实例的受限区域内最多三个协程同时执行。它不限制每秒请求数、不设置单请求超时，也不提供跨进程全局配额。QPS 需要速率限制器，超时需要客户端 timeout / `wait_for`，服务级配额需要网关、Redis 或队列。

许可只应包住真正稀缺的外部 I/O。`asyncio.BoundedSemaphore` 可在重复释放超过初始值时报错，但两者都不保证精确公平排队。

### Queue、timeout 与背压

有界 `asyncio.Queue(maxsize=N)` 配合 `await put()` 可在队列满时暂停生产者，把消费压力反向传递。无界 Queue 或持续 `put_nowait()` 不会形成容量背压，消息可能积压内存。

`task_done()` / `join()` 用于追踪入队工作是否全部处理；`put_nowait()` / `get_nowait()` 在满/空时抛 `QueueFull` / `QueueEmpty`。

`asyncio.wait_for(awaitable, timeout)` 超时后会取消内部 awaitable，等待清理后抛 `TimeoutError`，因此实际耗时可能略超过 timeout。短 timeout 轮询只会周期性醒来检查状态，不会自动生成心跳。

### 异步生成器的逐级背压

异步生成器在 `yield` 时交出值并保存局部状态，直到上层请求下一个值才从 `yield` 后继续。上层消费慢会限制生成器前进；但若生成器前还有无界 Queue，生产者仍可先积压，背压就没有传到源头。

## 3. 机制流程

1. 调用协程函数，创建 coroutine object；
2. `await` 或 `create_task` 将其交给事件循环；
3. Task 执行到未完成 awaitable 时挂起；
4. 事件循环推进其他就绪 Task；
5. I/O/Future 完成后，原 Task 恢复；
6. 调用方收集结果、处理异常，必要时取消剩余 Task；
7. Queue、Semaphore 和 timeout 在对应边界控制流量与资源。

### 协程调度流程

```text
事件循环运行 Task A
  ↓ A 遇到未完成的 await I/O，挂起
运行 Task B
  ↓ B 遇到 await Queue/Semaphore，挂起
I/O 完成，A 重新进入 ready 队列
  ↓
事件循环恢复 A 的 await 后续代码
```

## 4. 类比理解

事件循环像一个服务员：点单后不会堵在厨房门口，而是服务其他桌；厨房通知菜好了，再回来继续。线程池像把无法异步化的工作交给另一组员工；Semaphore 像只有三个工位；有界 Queue 像容量有限的取餐台。

## 5. 应用举例 / 代码或伪代码

```python
import asyncio

async def fetch_all(urls: list[str]) -> list[bytes]:
    semaphore = asyncio.Semaphore(3)

    async def fetch_one(url: str) -> bytes:
        async with semaphore:
            return await asyncio.wait_for(http_get(url), timeout=5)

    return await asyncio.gather(*(fetch_one(url) for url in urls))
```

生产者/消费者示例：

```python
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
```

## 6. 你在讨论中的理解推进

你已从“`async` 就是异步”推进到完整执行模型：协程只是待执行对象，Task 由事件循环推进，真正切换取决于挂起点；同步阻塞要显式隔离，并发聚合、并发度、速率、超时和背压是不同的工程边界。
