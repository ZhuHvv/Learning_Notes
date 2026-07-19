# FastAPI UploadFile：流式读取 vs bytes

> 所属分类：Python / Async / FastAPI  
> 修订版本：v11 审查修订版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

FastAPI UploadFile 适合大文件流式读取；bytes 会把整个文件读入内存。


## 2. 原理性解释

- UploadFile 提供文件名、类型和异步 read。
- 大文件应分块读取。
- bytes 简单但内存峰值高。
- RAG 上传要保存 source metadata。

### UploadFile 与 bytes 的差别主要是内存占用和读取时机

`bytes` 会把整个上传文件一次性读入内存，适合小文件；`UploadFile` 底层使用 SpooledTemporaryFile，可以分块读取，大文件会落盘，适合流式处理。你讨论的 RAG 附件接口中，如果用户上传 PDF、Word、长文本，直接 bytes 容易造成内存峰值过高。

```python
async def upload(file: UploadFile):
    while chunk := await file.read(1024 * 1024):
        process(chunk)
```

## 3. 机制流程

1. multipart 上传。
2. UploadFile 包装。
3. 分块读取。
4. 保存/解析。
5. 切分入库。

### 上传文件处理流程

```text
客户端 multipart/form-data 上传
  ↓
FastAPI 封装为 UploadFile
  ↓
按 chunk 读取 / 保存临时文件
  ↓
文本提取 / 切分 / embedding
  ↓
写入向量库或附件上下文
```

使用 UploadFile 时要注意：读取过一次后文件指针会移动；如果后续还要读，需要 `await file.seek(0)`。

## 4. 类比理解

bytes 像整箱书搬上桌，UploadFile 像一本本拿出来处理。

## 5. 应用举例 / 代码或伪代码

```python
import os

@app.post("/upload")
async def upload(file: UploadFile):
    # 1) 不要直接把用户可控的 filename 当路径用（路径穿越风险），先做 basename/白名单处理
    # 2) async 端点内用同步 open/write 写大文件会阻塞事件循环，生产建议 aiofiles 或线程池
    safe_name = os.path.basename(file.filename or "upload.bin")
    with open(os.path.join("uploads", safe_name), "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
```

## 6. 你在讨论中的理解推进

你问流式读取和 bytes 区别；核心是内存占用和适用文件大小。

