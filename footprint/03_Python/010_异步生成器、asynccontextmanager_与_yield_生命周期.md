# 异步生成器、asynccontextmanager 与 yield 生命周期

> 学习层级：进阶  
> 前置知识：[Semaphore、Queue 与异步背压](009_Semaphore、Queue_与异步背压.md)  
> 后续阅读：[FastAPI 请求参数、Depends 与生命周期](011_FastAPI_请求参数、Depends_与生命周期.md)

## 1. 普通异步生成器由消费者推进

`async def` 中出现 `yield` 时，函数返回的是异步生成器，不是普通 coroutine：

```python
async def stream_events():
    yield "started"
    await save_checkpoint()
    yield "checkpoint_saved"
```

异步生成器通过 `async for` 或 `anext()` 消费，不能直接 `await`：

```python
async for event in stream_events():
    print(event)
```

生成器在 `yield` 时交出值并保存局部状态，直到上层请求下一个值才从 `yield` 后继续。所以上例交出 `"started"` 时，`save_checkpoint()` 尚未执行。

若事件名称承诺“checkpoint 已保存”，就应先保存再发送该事件；否则应准确命名为 `stage_output_ready` 等只描述当前事实的名称。

## 2. `@asynccontextmanager` 使用进入/退出协议

`@asynccontextmanager` 把异步生成器适配成异步上下文管理器：

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

被装饰的异步生成器在一次上下文使用中必须恰好执行一次 `yield`：

- 没有 yield 到值：进入上下文失败；
- yield 多次：退出上下文失败；
- yield 前：资源初始化，对应 `__aenter__` 阶段；
- yield 的值：绑定给 `as` 变量；
- yield 后：对应 `__aexit__` 阶段；
- `finally`：保证正常退出和异常路径都执行清理。

## 3. 异常会在 `yield` 位置重新注入

```python
async with db_conn() as conn:
    await run_query(conn)
```

业务代码若抛出异常，退出协议会把异常重新抛入异步生成器的 `yield` 位置。因此可以在上下文管理器中观察异常，但不应无意吞掉它；资源释放应放进 `finally`。

不要把清理只写在普通 `return` 后面，因为异常路径可能直接跳过。

## 4. 生命周期流程

```text
调用 manager()，创建上下文管理器
  ↓
进入 async with，推进到 yield
  ↓
把资源交给 as 变量并执行业务
  ↓
业务正常结束或抛出异常
  ↓
从 yield 位置继续，执行 finally
  ↓
释放资源并退出
```

单个上下文管理器实例通常是一次性的；需要再次进入时，应重新调用工厂创建新实例。

## 5. FastAPI lifespan 示例

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

这类结构常用于应用启动/关闭阶段的数据库连接池、模型、HTTP client 和消息系统连接。

`@asynccontextmanager` 与 FastAPI 的 yield 依赖都建立在上下文管理思想上，但前者是 Python 标准库协议，后者还受 FastAPI 请求作用域和响应生命周期控制。

## 6. 类比

普通异步生成器像逐页交付文档：读者请求下一页，作者才继续。异步上下文管理器像借会议室：进入时开门开灯，离开时无论会议是否正常结束，都要关灯锁门。
