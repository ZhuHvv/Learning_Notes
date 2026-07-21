# @asynccontextmanager 与 yield 生命周期

> 所属分类：Python / Async / FastAPI  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

`@asynccontextmanager` 用异步生成器定义上下文管理器：`yield` 前初始化，`yield` 的值交给 `as` 变量，退出上下文时执行 `yield` 后的清理。

## 2. 原理性解释

- 函数内部必须包含一次生命周期分界用的 `yield`；
- 进入 `async with` 时执行到 `yield`；
- 正常退出或业务代码抛错时，生成器都会继续到 `finally`；
- 普通异步生成器由 `async for` / `anext()` 请求下一个值，而上下文管理器由进入/退出协议推进；
- 执行到 `yield` 时，后面的 checkpoint、日志或清理尚未执行。

### `@asynccontextmanager` 把“进入/退出资源生命周期”写成一个 async generator

`yield` 前面的代码对应 `__aenter__`，`yield` 后面的清理对应 `__aexit__`。业务代码在上下文中抛出的异常会在 `yield` 位置重新注入生成器，因此清理逻辑应放进 `finally`。

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def db_conn():
    conn = await open_db()
    try:
        yield conn
    finally:
        await conn.close()
```

普通异步生成器也在 `yield` 处暂停：若代码先 `yield` 一个“阶段完成”事件，再保存 checkpoint，事件交给上层时 checkpoint 尚未执行。只有上层继续消费，生成器才从 `yield` 后推进。严格协议应先保存再发 `checkpoint_saved`，或准确命名为 `stage_output_ready`。

## 3. 机制流程

1. 调用上下文函数，创建异步生成器；
2. 进入 `async with`，执行初始化；
3. 推进到 `yield`，把资源交给业务代码；
4. 业务代码正常结束或抛出异常；
5. 退出协议继续推进生成器；
6. `finally` 释放资源。

### 生命周期流程

```text
async with manager():
  ↓ 执行 yield 前逻辑
获得资源并执行业务
  ↓ 正常结束或异常
执行 yield 后 / finally 清理
```

FastAPI 中常用于应用启动/关闭阶段的数据库连接池、模型、HTTP client 和消息系统连接。不要把清理只写在普通 `return` 后面，否则异常路径可能跳过。

## 4. 类比理解

像借会议室：进入时开门开灯，把房间交给你；离开时无论会议是否正常结束，都关灯锁门。

## 5. 应用举例 / 代码或伪代码

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = await create_http_client()
    try:
        yield
    finally:
        await app.state.client.aclose()

app = FastAPI(lifespan=lifespan)
```

## 6. 你在讨论中的理解推进

你从“yield 只有被消费才执行后续逻辑”推进到两种协议的区别：普通异步生成器由上层逐次取值驱动，`@asynccontextmanager` 则由 `async with` 的进入和退出驱动初始化与清理。
