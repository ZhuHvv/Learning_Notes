# @asynccontextmanager 与 yield 生命周期

> 所属分类：Python / Async / FastAPI  
> 修订版本：v9 昨日今日增量版  
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

