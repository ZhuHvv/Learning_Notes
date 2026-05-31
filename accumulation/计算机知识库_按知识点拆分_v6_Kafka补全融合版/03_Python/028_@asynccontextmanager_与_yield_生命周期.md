# @asynccontextmanager 与 yield 生命周期

> 所属分类：Python / Async / FastAPI  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

@asynccontextmanager 用异步生成器定义上下文管理器；yield 前初始化，yield 后清理。


## 2. 原理性解释

- 函数内部必须包含 yield。
- 进入 async with 执行 yield 前代码。
- yield 的值交给 as 变量。
- 退出 async with 执行 finally 清理。

### `@asynccontextmanager` 把“进入/退出资源生命周期”写成一个 async generator

`yield` 前面的代码对应 `__aenter__`，`yield` 后面的 `finally` 对应 `__aexit__`。你之前说“yield 返回生成器只有被消费时才执行具体逻辑”，在 contextmanager 场景下可以理解为：只有进入 `async with` 时，yield 前的初始化逻辑才执行；离开 `async with` 时，yield 后的清理逻辑才执行。

```python
@asynccontextmanager
async def lifespan(app):
    app.state.db = await connect_db()
    try:
        yield
    finally:
        await app.state.db.close()
```

## 3. 机制流程

1. 调用上下文函数。
2. 进入 `__aenter__`。
3. 初始化资源。
4. 业务使用资源。
5. 退出时清理。

### 生命周期流程

```text
async with manager():
  ↓ 调用 manager，执行 yield 前逻辑
获得资源
  ↓ 执行业务代码
正常结束或异常
  ↓ 执行 yield 后 / finally 清理逻辑
```

在 FastAPI 中常用于应用启动/关闭资源管理，例如数据库连接池、模型加载、HTTP client、消息队列连接。不要把清理逻辑写在普通 return 后面，因为异常时可能无法执行。

## 4. 类比理解

像借会议室：开门开灯、交给你用、最后关灯锁门。

## 5. 应用举例 / 代码或伪代码

```python
@asynccontextmanager
async def db_conn():
    conn = await open_db()
    try:
        yield conn
    finally:
        await conn.close()

async with db_conn() as db:
    await db.query("select 1")
```

## 6. 你在讨论中的理解推进

你说 yield 只有被消费才执行逻辑；这里对应 async with 进入/退出生命周期。

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

**@asynccontextmanager 与 yield 生命周期** 在 Python 工程中通常关系到“运行时行为”而不是语法表面：

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

## 11. 针对 `@asynccontextmanager 与 yield 生命周期` 的专项排查

Python 服务中很多问题不是语法错，而是运行时行为与预期不一致。排查 **@asynccontextmanager 与 yield 生命周期** 时建议看：

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

# 练习：把涉及 @asynccontextmanager 与 yield 生命周期 的函数包一层 safe_call，观察错误到底在哪里发生。
```

### 面试表达模板

回答 `@asynccontextmanager 与 yield 生命周期` 时，可以按“它改变了什么运行时行为 → 什么时候执行 → 和同步写法有什么差异 → 项目中如何排错”来组织。
