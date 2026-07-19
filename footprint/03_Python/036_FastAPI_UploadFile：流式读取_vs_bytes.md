# FastAPI UploadFile：流式读取 vs bytes

> 所属分类：Python / Async / FastAPI  
> 修订版本：v11 审查修订版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

FastAPI 根据路径模板、函数签名、类型注解和 `Depends` / `File` / `Form` 等标记建立 HTTP 请求边界。`UploadFile` 使用 spooled file，适合大文件和分块处理；`bytes` 通常把整个文件读入内存，适合小文件。

## 2. 原理性解释

- 路径模板中的同名参数通常来自 path，其他简单参数通常来自 query；
- Pydantic 模型参数通常来自 JSON body，进入 handler 前已验证；
- `Depends` 表示由 FastAPI 构建和管理请求级依赖图；
- `File` / `Form` 表示 `multipart/form-data`；
- `UploadFile` 减少大文件内存峰值，但不会把后续同步文件操作自动异步化；
- `BackgroundTasks` 不是持久化任务队列；
- Pydantic 校验、JSON Schema、OpenAPI 和数据库 schema 属于不同层。

### Handler 参数来源与 Depends 生命周期

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

这里 `project_id` 来自 path，`preview` 来自 query，`request` 来自 JSON body，`user_id` 来自依赖系统。生成器依赖可表达：

```text
创建资源 → yield 给 handler → 响应生命周期结束 → finally 清理
```

FastAPI 可以在线程池执行同步依赖，但注入后的同步 ORM Session 不会变成异步 Session。`async def` 中直接执行同步查询、SDK 或文件复制仍会阻塞事件循环。应完整使用异步驱动，或在确认线程安全后把完整同步事务隔离到线程池。

### UploadFile、File 与 Form

```python
file: UploadFile = File(...)
collection: str = Form(...)
```

`...` 表示必填。JSON body 与 File/Form 不能按普通方式混用，因为一个请求只有一个 `Content-Type`。需要结构化元数据时，可拆为 form 字段，或把 JSON 文本放入 form 后显式解析和校验。

读取会移动文件指针，重读前使用 `await file.seek(0)`。还应校验大小、MIME、扩展名、内容签名和保存路径，不能直接把用户可控文件名当路径。

### BackgroundTasks 的真实边界

`BackgroundTasks` 在响应发送后执行任务，但不提供跨进程持久化、重试、调度或崩溃恢复。异步后台函数中的同步调用仍可能占用事件循环。短同步 I/O 可评估线程池，CPU 密集任务适合进程池或外部 worker，需要可靠重试和独立扩缩容时应使用任务队列。

### Pydantic、JSON Schema 与 OpenAPI

1. Pydantic 由模型建立运行时校验器；
2. 同一模型可生成 JSON Schema；
3. FastAPI 把 JSON Schema 组合进 OpenAPI，用于文档和客户端生成。

字段的 description/example 主要是文档元数据，不会自动形成业务约束。请求模型负责阻止不可信输入；`response_model` 还能过滤、验证和序列化输出。流式响应没有一次性完整 body，应在每个事件包帧前验证事件模型。

JSON Schema、数据库表结构和 Agent 输出 schema 都可能被简称为 schema，但不会自动等价。Pydantic 的类型边界详见 `037_可变默认参数与_default_factory.md`。

### 包导出、ORM relationship 与 JSONB

`__init__.py` 可重新导出名字并用 `__all__` 声明公共 API；现代 Python 还支持 namespace package，因此“没有它就绝对不能导入”并不普遍成立。导入路径是否有效还取决于包安装方式、启动目录和 `PYTHONPATH`。

SQLAlchemy `Column` 描述数据库列，`relationship()` 描述 Python 对象导航。ORM `cascade` 与数据库外键 `ON DELETE CASCADE` 属于不同层。

JSONB 应接收由 dict/list/标量组成的 JSON-compatible 对象。若先把 dict `json.dumps()` 再作为对象写入，保存的是 JSON 字符串值；JSONB 也不会自动校验业务字段。Queue、Task、Session 和连接等运行时资源不能直接持久化。

## 3. 机制流程

1. FastAPI 解析 path、query、body、依赖或 multipart；
2. Pydantic 验证请求模型；
3. 依赖系统创建请求级资源；
4. Handler 分块读取、保存或处理 UploadFile；
5. 返回值按响应契约序列化；
6. 依赖退出阶段释放资源；
7. 可靠长任务交给独立 worker，而不是依赖进程内 BackgroundTasks。

### 上传文件处理流程

```text
客户端 multipart/form-data
  ↓
FastAPI 解析 File / Form，构造 UploadFile
  ↓
校验大小、名称、类型和权限
  ↓
在线程池或异步文件 API 中保存
  ↓
解析、切分或进入后台任务
```

## 4. 类比理解

函数签名像收件窗口的表格规则；Depends 像窗口内部申请并归还临时设备；`bytes` 像整箱资料一次搬上桌，`UploadFile` 像从临时仓库分批取用。

## 5. 应用举例 / 代码或伪代码

```python
import asyncio
import shutil
from pathlib import Path
from typing import Annotated

from fastapi import File, Form, UploadFile

UPLOAD_DIR = Path("uploads")

def copy_file(source, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        shutil.copyfileobj(source, output, length=1024 * 1024)

@app.post("/documents")
async def upload_document(
    file: Annotated[UploadFile, File()],
    collection: Annotated[str, Form()],
):
    safe_name = Path(file.filename or "upload.bin").name
    destination = UPLOAD_DIR / safe_name
    await file.seek(0)
    await asyncio.to_thread(copy_file, file.file, destination)
    return {"collection": collection, "filename": safe_name}
```

## 6. 你在讨论中的理解推进

你从“UploadFile 与 bytes 的内存差异”推进到完整请求边界：参数来源、依赖生命周期、同步阻塞、后台任务可靠性、Pydantic/OpenAPI 分层，以及 ORM/JSONB 的持久化边界。
