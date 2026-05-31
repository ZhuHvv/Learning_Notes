# asyncio.wait、done pending 与 FIRST COMPLETED

> 所属分类：Python / Async / FastAPI  
> 修订版本：v6 Kafka 补全融合版  
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

## 7. 常见误区与排查思路

- 只背名词，不知道它在完整链路中的输入、输出和失败模式。
- 只看正常路径，忽略异常、超时、权限、重复和可观测性。
- 把相邻概念混用，导致设计或排查时定位错误。

## 8. 关联知识点

- 回到 00_总体索引.md 查看上下游知识点。
- 结合 00_总体知识网络图.md 理解跨模块关系。

## 9. 复习检查问题

- 它解决的核心问题是什么？
- 它的输入、输出和中间状态分别是什么？
- 它在真实项目中最容易出错的边界条件是什么？
- 它和上游、下游知识点如何连接？

## 10. 更细的工程拆解

**asyncio.wait、done pending 与 FIRST COMPLETED** 在 Python 工程中通常关系到“运行时行为”而不是语法表面：

1. **生命周期**：对象、协程、文件流、上下文管理器分别什么时候创建、挂起、恢复、释放。
2. **阻塞点**：网络 IO、文件 IO、数据库查询、模型调用是异步服务最常见的等待来源。
3. **错误传播**：异常是直接抛出、被 task 包装，还是在日志中被吞掉，会决定排障难度。
4. **可观测性**：日志、trace id、结构化 JSON 输出能把一次请求的执行路径串起来。

### 最小调试骨架

```python
import asyncio
import logging

logging.basicConfig(filename="app.log", level=logging.INFO)

async def run_step(name, coro):
    logging.info("start step=%s", name)
    try:
        result = await coro
        logging.info("done step=%s result=%r", name, result)
        return result
    except Exception:
        logging.exception("failed step=%s", name)
        raise

# 用法：await run_step("retrieve", retriever(query))
```

### 工程落地要点

- 写 FastAPI/RAG/Agent 服务时，先明确哪些函数必须是 async，哪些只是普通 CPU 计算。
- 不要把大文件一次性读入内存，能流式就流式；不要在事件循环里跑长时间 CPU 任务。
- 对生成器、上下文管理器和 task，都要明确“谁负责消费、谁负责关闭、异常从哪里冒出”。

## 11. 针对 `asyncio.wait、done pending 与 FIRST COMPLETED` 的专项排查

Python 服务中很多问题不是语法错，而是运行时行为与预期不一致。排查 **asyncio.wait、done pending 与 FIRST COMPLETED** 时建议看：

- **是否真的被执行**：生成器、协程、上下文管理器经常只有在被消费/await/进入时才执行。
- **是否阻塞事件循环**：异步函数内部如果跑 CPU 密集循环，仍然会卡住其他请求。
- **异常是否被吞掉**：后台 task、日志函数、try/except 都可能让错误不再显式暴露。
- **资源是否关闭**：文件、数据库连接、上传流和 session 都需要明确生命周期。

### 小型练习

```python
async def safe_call(name, func, *args, **kwargs):
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        print(f"[{name}] failed:", repr(e))
        raise

# 练习：把涉及 asyncio.wait、done pending 与 FIRST COMPLETED 的函数包一层 safe_call，观察错误到底在哪里发生。
```

### 面试表达模板

回答 `asyncio.wait、done pending 与 FIRST COMPLETED` 时，可以按“它改变了什么运行时行为 → 什么时候执行 → 和同步写法有什么差异 → 项目中如何排错”来组织。
