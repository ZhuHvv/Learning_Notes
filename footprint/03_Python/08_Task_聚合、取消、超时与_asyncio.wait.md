# 03.08 Task 聚合、取消、超时与 asyncio.wait

> 学习层级：中级到进阶  
> 前置知识：[async、await 与协程调度](07_async、await_与协程调度.md)  
> 后续阅读：[Semaphore、Queue 与异步背压](09_Semaphore、Queue_与异步背压.md)

## 1. 创建 Task 后要管理它的结果

`asyncio.create_task()` 把协程注册到当前事件循环，使调用方可以继续执行其他逻辑。它不会创建新线程。多个 awaitable 的聚合入口是 `asyncio.gather()`。

```python
task = asyncio.create_task(fetch_document("doc-1"))
result = await task
```

应保留重要 Task 的引用，并通过 `await task`、`task.result()` 或 `task.exception()` 观察结果。若任务抛错却始终无人获取异常，程序可能产生“Task exception was never retrieved”等警告。

## 2. `gather` 聚合多个 awaitable

```python
results = await asyncio.gather(
    fetch_document("doc-1"),
    fetch_document("doc-2"),
)
```

- 多个 awaitable 会并发推进；
- 返回结果按传入顺序排列，不按完成顺序；
- 默认情况下，第一个异常会传播给等待 `gather` 的调用方；
- 其他 awaitable 不会仅因为其中一个异常传播而被自动全部取消；
- `return_exceptions=True` 会把异常放入结果列表，调用方仍需逐项处理。

若需要结构化地保证同组任务共同结束或取消，也可以根据项目 Python 版本评估 `asyncio.TaskGroup`。

## 3. 取消是协作式请求

```python
task.cancel()
try:
    await task
except asyncio.CancelledError:
    pass
```

`cancel()` 通常在 Task 下一次到达可取消挂起点时注入 `CancelledError`。若协程长时间运行同步代码，取消无法及时生效。

调用 `cancel()` 后继续 await，才能让任务执行 `finally` 清理，并确认取消已经完成。清理代码通常不应无意吞掉 `CancelledError`。

## 4. `wait_for` 为单个等待设置时间边界

```python
result = await asyncio.wait_for(http_get(url), timeout=5)
```

超时后，`wait_for` 会取消内部 awaitable，并等待其取消清理，然后抛出 `TimeoutError`。因此实际墙钟时间可能略超过配置的 timeout。

短 timeout 的循环只会周期性唤醒检查状态，不会自动产生应用层心跳。客户端超时、业务截止时间、重试次数和心跳协议应分别设计。

## 5. `asyncio.wait` 返回 done/pending 快照

当前 Python 中，`asyncio.wait()` 接收 Task 或 Future；Python 3.11 起不再允许直接传入 coroutine object。因此先显式创建 Task：

```python
tasks = {
    asyncio.create_task(worker("A", 0.2)),
    asyncio.create_task(worker("B", 0.1)),
}

done, pending = await asyncio.wait(
    tasks,
    return_when=asyncio.FIRST_COMPLETED,
)
```

`asyncio.wait(FIRST_COMPLETED)` 常用来表达“任一任务完成就返回”。`done` 是返回时刻已经完成的一组 Task，可能同时包含多个；`pending` 仍在运行。后续完成的任务不会自动加入原来的 `done` 集合。

`asyncio.wait` 自身的 timeout 到期时不会抛 `TimeoutError`，也不会自动取消 pending；它只是返回当时的两个集合。

## 6. 按完成顺序处理全部任务

循环使用 `FIRST_COMPLETED`：

```python
pending = set(tasks)

while pending:
    done, pending = await asyncio.wait(
        pending,
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in done:
        try:
            handle(await task)
        except Exception as exc:
            handle_error(exc)
```

也可以使用 `asyncio.as_completed()` 表达“谁先完成就先处理谁”：

```python
for awaitable in asyncio.as_completed(tasks):
    result = await awaitable
    handle(result)
```

`await task` 只能取得这个 task 的结果，不会顺带收集其他 Task。

## 7. 只要第一个结果并取消其余任务

```python
done, pending = await asyncio.wait(
    tasks,
    return_when=asyncio.FIRST_COMPLETED,
)

first_task = next(iter(done))

for task in pending:
    task.cancel()

try:
    first_result = await first_task
finally:
    # 即使 first_task 抛错，也等待其余任务完成取消和 finally 清理。
    await asyncio.gather(*pending, return_exceptions=True)
    await asyncio.gather(*(done - {first_task}), return_exceptions=True)
```

两个 `gather` 用于观察 `done` 中同时完成的其他 Task，并等待 pending 的取消和资源清理。实际业务还应决定如何记录这些异常，而不是只用 `return_exceptions=True` 静默忽略。

`FIRST_COMPLETED` 的语义像比赛中第一个人到终点就通知裁判；其他选手仍在跑，不会因为通知已经发出而自动退赛。

## 8. `to_thread` 的适用边界

```python
parsed = await asyncio.to_thread(parse_large_file, path)
```

适合暂时无法替换的同步文件 I/O、同步网络 SDK 或短时同步库调用，但要注意：

- 默认线程池容量有限；
- 外层 Task 被取消通常不能强制停止已经运行的线程函数；
- CPU 密集的纯 Python 代码仍受 GIL 影响，通常应评估进程池或外部 worker；
- 跨线程使用数据库 Session、client 和可变对象前必须确认线程安全。
