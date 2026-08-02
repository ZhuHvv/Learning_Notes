# 03.12 FastAPI UploadFile、File 与 Form

> 学习层级：进阶  
> 前置知识：[FastAPI 请求参数与依赖](11_FastAPI_请求参数、Depends_与生命周期.md)  
> 后续阅读：[FastAPI BackgroundTasks 与可靠任务边界](13_FastAPI_BackgroundTasks_与可靠任务边界.md)

## 1. `bytes` 与 `UploadFile`

接收上传文件时：

- `bytes`：FastAPI 读取完整文件并把内容放入内存，适合明确受限的小文件；
- `UploadFile`：底层使用 spooled file，小于阈值时留在内存，超过阈值后转存磁盘，适合较大文件及分块处理。

`UploadFile` 还提供文件名、内容类型和文件对象等元数据，并提供异步的 `read`、`write`、`seek`、`close` 方法。FastAPI 会在线程池中执行底层文件方法，但把 `file.file` 直接传给同步库时，后续行为仍由该同步库决定。

## 2. `File`、`Form` 与请求 Content-Type

```python
from typing import Annotated
from fastapi import File, Form, UploadFile

async def upload(
    file: Annotated[UploadFile, File()],
    collection: Annotated[str, Form()],
):
    ...
```

`File` 和 `Form` 表示请求使用 `multipart/form-data`。旧式声明中的 `File(...)` / `Form(...)` 里，`...` 表示必填。

一个请求体采用 multipart 后，不能再按普通 `application/json` body 的方式同时解析 Pydantic JSON 模型。需要结构化元数据时，可以：

- 把字段逐项声明为 form；
- 把 JSON 文本作为一个 form 字段，再显式解析并通过 Pydantic 校验；
- 把元数据与文件上传拆成不同请求。

## 3. 文件指针与分块读取

读取会移动文件指针。若同一个上传文件需要重新读取：

```python
await file.seek(0)
```

分块读取示例：

```python
async def consume_upload(file: UploadFile) -> int:
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        await process_chunk(chunk)
    return total
```

`UploadFile` 能降低一次性内存峰值，但只有下游也按块处理时，整个链路才是真正的流式处理。

## 4. 上传安全边界

不能只相信客户端提供的 `filename` 和 `content_type`。应根据风险校验：

- 总大小和分块累计大小；
- MIME 类型；
- 扩展名；
- 文件内容签名；
- 用户权限和配额；
- 保存目录与最终路径；
- 重名覆盖和并发写入；
- 解压炸弹、恶意文档等格式风险。

`Path(filename).name` 可以去掉当前平台识别的父目录，但跨平台分隔符、名称碰撞和业务授权仍需单独处理。生产代码通常应生成服务端唯一文件名，并把原始名称仅作为元数据保存。

## 5. 保存上传文件

```python
import asyncio
import shutil
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import File, Form, UploadFile

UPLOAD_DIR = Path("uploads")

def copy_file(source, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        shutil.copyfileobj(source, output, length=1024 * 1024)

@app.post("/documents")
async def upload_document(
    file: Annotated[UploadFile, File()],
    collection: Annotated[str, Form()],
):
    suffix = Path(file.filename or "").suffix.lower()
    destination = UPLOAD_DIR / f"{uuid4().hex}{suffix}"

    await file.seek(0)
    await asyncio.to_thread(copy_file, file.file, destination)

    return {
        "collection": collection,
        "original_filename": file.filename,
        "stored_filename": destination.name,
    }
```

示例使用 `"xb"` 防止意外覆盖，但完整系统仍需实现大小、内容、权限和失败清理。

## 6. 上传处理流程

```text
客户端 multipart/form-data
  ↓
FastAPI 构造 File / Form / UploadFile
  ↓
校验权限、大小、名称、类型和内容
  ↓
分块保存或处理
  ↓
持久化元数据或投递后续任务
  ↓
关闭临时资源并返回明确结果
```

`bytes` 像把整箱资料一次搬到桌上；`UploadFile` 像从临时仓库分批取用。
