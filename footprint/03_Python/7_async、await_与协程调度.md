# 03.07 async、await 与协程调度

> 学习层级：中级  
> 前置知识：函数、异常、迭代器与上下文管理器基础  
> 后续阅读：[Task 聚合、取消、超时与 asyncio.wait](8_Task_聚合、取消、超时与_asyncio.wait.md)

## 1. 协程不是线程

`async def` 定义协程函数。调用协程函数会得到 coroutine object，但此时函数体通常还没有开始执行：

```python
async def fetch_document(doc_id: str):
    data = await http_get(f"/documents/{doc_id}")
    return data

coro = fetch_document("doc-1")  # 创建协程对象
document = await coro            # 开始推进协程
```

协程对象需要被 `await`、包装成 Task，或交给框架调度。一个 coroutine object 通常只能完整 await 一次；需要重新执行时应重新调用协程函数。

Task 是事件循环对协程的调度包装，不是 OS 线程。asyncio 实现的是协作式并发，不会自动带来 CPU 并行。

## 2. `await` 是可能的控制权交接点

Task 执行到尚未完成的 awaitable 时会挂起，把线程交还事件循环；事件循环随后推进其他就绪 Task。若 awaitable 已经完成，`await` 可能立即返回，并不保证每次都发生切换。

```text
事件循环运行 Task A
  ↓ A 等待尚未完成的 I/O
Task A 挂起，事件循环运行 Task B
  ↓
I/O 完成，Task A 重新进入 ready 队列
  ↓
事件循环恢复 Task A 的 await 后续代码
```

因此，`async` 的关键不是函数名字，而是调用链中是否存在真正可挂起的异步操作。

## 3. `async def` 内仍可能阻塞

下面这些同步工作不会因为写在 `async def` 中就自动异步化：

- 同步数据库驱动；
- 同步文件读写；
- 同步网络 SDK；
- 长时间 CPU 计算。

它们会占用事件循环线程，使其他请求或 Task 无法及时运行。暂时无法替换的同步 I/O 可以评估 `asyncio.to_thread()`；其线程安全、取消和 CPU 边界见下一篇。

## 4. 协程、Task 与异步生成器

- coroutine：通常通过 `await` 得到一个最终结果；
- Task：让事件循环独立推进某个协程，并允许调用方保留引用、取消或等待；
- async generator：`async def` 中使用 `yield`，通过 `async for` 或 `anext()` 逐个消费，不能直接 `await`。

异步生成器和 `@asynccontextmanager` 的生命周期见[异步生成器与 asynccontextmanager](10_异步生成器、asynccontextmanager_与_yield_生命周期.md)。

## 5. 最小并发示例

```python
import asyncio

async def worker(name: str, delay: float) -> str:
    await asyncio.sleep(delay)
    return f"{name} done"

async def main() -> None:
    first = asyncio.create_task(worker("A", 0.2))
    second = asyncio.create_task(worker("B", 0.1))

    print(await first)
    print(await second)

asyncio.run(main())
```

两个 Task 可以在彼此等待时交错推进。最终打印顺序由代码中 await 的顺序决定，不一定等于任务完成顺序。

## 6. 理解检查

- 调用 `async def` 后得到的是什么？
- 哪些 `await` 会真正让当前 Task 挂起？
- Task 与线程有什么区别？
- 为什么同步数据库查询仍会阻塞异步服务？
- 协程对象、Task 和异步生成器分别如何被消费？
