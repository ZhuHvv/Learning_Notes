# async   await 与协程调度

> 所属分类：Python / Async / FastAPI  
> 修订版本：v6 Kafka 补全融合版  
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

**async   await 与协程调度** 在 Python 工程中通常关系到“运行时行为”而不是语法表面：

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

## 11. 针对 `async   await 与协程调度` 的专项排查

Python 服务中很多问题不是语法错，而是运行时行为与预期不一致。排查 **async   await 与协程调度** 时建议看：

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

# 练习：把涉及 async   await 与协程调度 的函数包一层 safe_call，观察错误到底在哪里发生。
```

### 面试表达模板

回答 `async   await 与协程调度` 时，可以按“它改变了什么运行时行为 → 什么时候执行 → 和同步写法有什么差异 → 项目中如何排错”来组织。
