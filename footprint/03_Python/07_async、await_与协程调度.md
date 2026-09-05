# 03.07 async、await 与协程调度

> 学习层级：中级  
> 前置知识：函数、异常、迭代器与上下文管理器基础  
> 后续阅读：[Task 聚合、取消、超时与 asyncio.wait](08_Task_聚合、取消、超时与_asyncio.wait.md)

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

## 6. 从 `await` 到恢复：Coroutine、Task、Future 与事件循环

事件循环不会根据函数名或“它正在查数据库”自动抢占任务。`asyncio` 是**协作式调度**：只有当前协程执行到可等待对象，且该对象尚未完成时，Task 才会挂起。

```text
Task 驱动 coroutine 执行
  ↓
执行到 await awaitable
  ↓
awaitable 已完成？ ── 是 → 立即取得结果并继续
  │
  否
  ↓
Task 保存等待关系并注册 Future 的完成回调
  ↓
当前 coroutine 挂起；事件循环运行 ready 队列中的其他 Task
```

可把三者分工记成：

| 对象 | 保存什么 | 负责什么 |
| --- | --- | --- |
| Coroutine | 局部变量、调用帧、当前暂停位置 | 可以暂停、恢复的函数执行现场 |
| Task | 对 coroutine 的调度包装与取消/结果状态 | 驱动 coroutine，并在可运行时进入 ready 队列 |
| Future | 一个尚未或已经得到的结果及回调 | 在结果完成时唤醒等待它的 Task |

例如：

```python
async def fetch_user():
    request_id = "r-1"
    user = await client.get_user()
    return request_id, user
```

若 `client.get_user()` 返回的 Future 尚未完成，协程会在 `await` 处保存 `request_id` 和恢复位置，而不是从头重跑。网络结果到达后，Future 变为完成状态，回调把对应 Task 放回 ready 队列；事件循环再次驱动它时，`await` 表达式得到 `user`，随后继续执行 `return`。

概念化伪代码如下，意在说明状态关系，而非 CPython 源码：

```python
class Task:
    def step(self, value=None):
        awaited = self.coroutine.send(value)
        if not awaited.done():
            awaited.add_done_callback(self.wakeup)

    def wakeup(self, future):
        loop.call_soon(self.step, future.result())
```

网络、异步数据库等 I/O 的“结果到了”通常来自操作系统的就绪/完成通知机制：Linux 常见 `epoll`，macOS/BSD 常见 `kqueue`，Windows 常见 IOCP。事件循环在没有 ready Task 时等待这些事件；驱动程序读取并解析结果后调用类似 `future.set_result(result)` 的逻辑，进而恢复等待者。Linux 中从 Socket 就绪通知到 `epoll_wait()` 返回的细节见 [Linux epoll：Socket、就绪通知、实例与多线程模型](../07_Backend_Deploy_Network/13_Linux_epoll_Socket_就绪通知与多线程等待.md)。

## 7. 不能等待的 CPU 代码不会被自动切走

```python
async def cpu_bound():
    total = 0
    for item in huge_items:
        total += transform(item)  # 长时间没有真正的挂起点
    return total
```

即使函数写成 `async def`，它仍会持续占用事件循环线程。`await` 只是一个**可能**的挂起点：等待对象如果已经完成，也可以同步返回。CPU 密集工作应优先缩短单次执行时间、使用进程池/外部 worker，或采用适合的原生/GPU 实现；不要把任意循环中机械插入 `await asyncio.sleep(0)` 当作性能方案。

## 8. 理解检查

- 调用 `async def` 后得到的是什么？
- 哪些 `await` 会真正让当前 Task 挂起？
- Task 与线程有什么区别？
- 为什么同步数据库查询仍会阻塞异步服务？
- 协程对象、Task 和异步生成器分别如何被消费？
- Future 完成后，为什么协程能从原来的 `await` 后继续，而不是从函数开头重跑？
- 为什么 CPU 密集协程即使写了 `async def` 也可能饿死其他 Task？

### 本次技术讨论来源

- [async/await 的作用与 asyncio 底层调度](https://chatgpt.com/share/6a89c1a1-f2c8-83ec-a347-3c4228b6116d)
