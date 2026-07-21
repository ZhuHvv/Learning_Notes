# asyncio.wait、done pending 与 FIRST COMPLETED

> 所属分类：Python / Async / FastAPI  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

asyncio.wait 返回 done/pending；FIRST_COMPLETED 在任意任务完成时返回，pending 不会自动取消。


## 2. 原理性解释

- done 是返回时刻已完成任务快照。
- pending 任务仍在运行。
- `await task` 只能取得该 task 结果。
- 需要 pending 结果就继续 await；不需要就 cancel。

### `asyncio.wait(FIRST_COMPLETED)` 返回的是“此刻已完成的一批任务”

你之前问：第一个任务完成时返回 done/pending 后，后续 `for task in done: result = await task` 能不能得到之后完成任务的结果？答案是不能。`done` 是 wait 返回瞬间已经完成的集合；`pending` 里的任务仍在继续，但不会自动出现在这个 done 集合里，除非你再次 wait 或 await 它们。

```python
done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
for t in done:
    print(await t)  # 只取已经完成的任务
```

## 3. 机制流程

1. 创建 tasks。
2. wait FIRST_COMPLETED。
3. 处理 done。
4. 取消或继续等待 pending。

### FIRST_COMPLETED 典型流程

```python
pending = set(tasks)
while pending:
    done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
    for task in done:
        result = await task
        handle(result)
```

如果你的目标是“谁先完成就先处理谁”，可以循环 wait；如果目标是“拿到第一个结果就取消其它任务”，要显式 cancel pending。

## 4. 类比理解

像比赛第一个人到终点就通知你，其他人还在跑。

## 5. 应用举例 / 代码或伪代码

```python
done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
for t in done:
    print(await t)
for t in pending:
    t.cancel()
```

## 6. 你在讨论中的理解推进

你问 `for task in done` 能否得到之后完成任务；答案是不能，pending 要继续等待。

