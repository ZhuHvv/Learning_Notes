# FastAPI 请求参数、Depends 与生命周期

> 学习层级：进阶  
> 前置知识：[异步生成器与 asynccontextmanager](010_异步生成器、asynccontextmanager_与_yield_生命周期.md)、[Pydantic 数据模型](004_dataclass、TypedDict_与_Pydantic.md)  
> 后续阅读：[FastAPI UploadFile、File 与 Form](012_FastAPI_UploadFile、File_与_Form.md)

## 1. FastAPI 从函数签名建立请求边界

FastAPI 根据路径模板、函数签名、类型注解和 `Depends`、`File`、`Form` 等标记决定数据来源：

```python
@app.post("/projects/{project_id}/reports")
async def create_report(
    project_id: str,
    request: CreateReportRequest,
    preview: bool = False,
    user_id: str = Depends(get_current_user),
):
    ...
```

通常：

- `project_id` 与路径模板同名，来自 path；
- `preview` 是简单类型且不在路径中，来自 query；
- `request` 是 Pydantic 模型，来自 JSON body；
- `user_id` 由依赖系统提供。

这是常用默认规则，不应靠猜测复杂签名；需要明确边界时应使用 `Path`、`Query`、`Body`、`Depends`、`File` 和 `Form` 等声明。

## 2. `Depends` 构建请求级依赖图

依赖可以继续依赖其他依赖。FastAPI 负责解析依赖图、复用同一次请求中的依赖结果，并按正确顺序执行进入和退出逻辑。

普通返回式依赖：

```python
async def get_current_user(token: str = Header()):
    return await verify_token(token)
```

yield 依赖：

```python
async def get_session():
    session = create_session()
    try:
        yield session
    finally:
        await session.close()
```

当前 FastAPI 对 yield 依赖提供两种主要作用域：

- `Depends(scope="request")`：默认值，退出代码在响应发送后运行；
- `Depends(scope="function")`：路径操作函数返回后、响应发送前运行退出代码。

子依赖的作用域还必须满足生命周期嵌套关系。流式响应是否仍需使用资源，会直接影响作用域选择。

## 3. 同步依赖不会把资源变成异步

FastAPI 可以在线程池中执行同步依赖或同步路径操作函数，但注入后的同步 ORM Session 不会因此变成异步 Session。

在 `async def` handler 中直接运行同步数据库查询、SDK 调用或文件复制，仍会阻塞事件循环。通常应选择以下一种完整边界：

- 全链路使用异步驱动；
- 把完整同步事务放进线程池，并确认其中对象的线程安全；
- 对 CPU 密集或可靠长任务使用进程池或外部 worker。

不要把同一个同步 Session 在事件循环线程和线程池之间随意传递。

## 4. Pydantic、JSON Schema 与 OpenAPI 分层

1. Pydantic 根据模型创建运行时验证和序列化规则；
2. 模型可以生成 JSON Schema；
3. FastAPI 把这些 schema 组合进 OpenAPI；
4. OpenAPI 可用于交互文档和客户端生成。

字段的 `description` 和 `example` 主要服务文档，不会自动产生业务约束。请求模型用于阻止不可信输入进入业务代码；`response_model` 还能过滤、验证和序列化输出。

`StreamingResponse` 等流式响应没有一次性完整的 body，无法只靠最终 `response_model` 约束整个流。若使用 SSE、JSONL 等流式协议，应在每个事件编码前验证事件模型。

JSON Schema、数据库表结构和 Agent 输出 schema 不会自动等价。必须为每层明确：

- 谁生成；
- 谁验证；
- 失败如何处理；
- 是否允许额外字段或类型转换。

## 5. 请求处理流程

```text
匹配路由
  ↓
解析 path / query / header / body
  ↓
构建并执行依赖图
  ↓
Pydantic 验证输入
  ↓
执行 handler
  ↓
按响应契约序列化
  ↓
根据依赖 scope 执行退出和清理
```

函数签名像收件窗口的表格规则；依赖系统像窗口内部申请并归还临时设备。
