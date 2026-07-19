# async   await 与协程调度

> 所属分类：Python / Async / FastAPI  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

async 定义协程函数，await 在等待 I/O 时把控制权还给事件循环；异步是协作式调度，不等于自动多线程。


## 2. 原理性解释

- async def 调用后返回 coroutine。
- 只有 await/create_task/事件循环驱动才执行。
- await 遇到 I/O 可挂起当前协程。
- CPU 密集任务会阻塞事件循环。

### `async` 定义可暂停函数，`await` 才交出控制权

你已经形成了正确理解：`async def` 只是把函数变成协程函数，调用后得到 coroutine 对象；真正让事件循环有机会调度其它任务的是 `await`。当 await 的对象正在等待 IO、网络、sleep 等非 CPU 阻塞操作时，当前协程挂起，事件循环可以运行其它协程。

```python
async def fetch():
    data = await http_get()  # 这里让出控制权
    return data
```

如果在 async 函数里直接执行 CPU 密集循环或同步阻塞 IO，不写 await，事件循环仍然会被卡住。

## 3. 机制流程

1. 创建协程。
2. 事件循环调度。
3. await I/O 时挂起。
4. 其他任务运行。
5. I/O 完成后恢复。

### 协程调度流程

```text
事件循环启动
  ↓
运行协程 A
  ↓ A 遇到 await IO，挂起
运行协程 B
  ↓ B 遇到 await sleep，挂起
IO 完成，A 变为 ready
  ↓
事件循环恢复 A 的 await 后续代码
```

```python
async def main():
    tasks = [asyncio.create_task(fetch(i)) for i in range(10)]
    results = await asyncio.gather(*tasks)
```

并发不等于并行：asyncio 主要适合 IO 并发，不适合直接加速 CPU 密集计算。

## 4. 类比理解

像服务员点菜后不堵在厨房门口等，而是去服务别桌。

## 5. 应用举例 / 代码或伪代码

```python
async def fetch(i):
    await asyncio.sleep(1)
    return i

results = await asyncio.gather(*(fetch(i) for i in range(3)))
```

## 6. 你在讨论中的理解推进

你已理解 async 只是定义协程，await 才让出执行权。

