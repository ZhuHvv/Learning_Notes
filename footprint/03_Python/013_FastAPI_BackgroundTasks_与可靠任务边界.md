# FastAPI BackgroundTasks 与可靠任务边界

> 学习层级：进阶  
> 前置知识：[FastAPI UploadFile、File 与 Form](012_FastAPI_UploadFile、File_与_Form.md)  
> 后续阅读：[状态模型、ORM、JSONB 与持久化边界](014_状态模型、ORM、JSONB_与持久化边界.md)

## 1. BackgroundTasks 的定位

FastAPI `BackgroundTasks` 用于在响应返回后执行同一应用进程中的小型后续工作：

```python
from fastapi import BackgroundTasks

def write_audit_log(document_id: str) -> None:
    ...

@app.post("/documents/{document_id}")
async def create_document(document_id: str, tasks: BackgroundTasks):
    tasks.add_task(write_audit_log, document_id)
    return {"accepted": True}
```

它适合发送简单通知、追加审计记录等短任务，但不是持久化任务队列。

## 2. 它不提供哪些保证

`BackgroundTasks` 默认不提供：

- 跨进程持久化；
- 自动重试和退避；
- 定时调度；
- 任务去重；
- 崩溃恢复；
- 多服务器统一消费；
- 独立扩缩容和任务积压治理。

响应成功只说明请求处理完成并登记了进程内后台工作，不必然证明后台任务最终成功。

## 3. 同步、异步与 CPU 边界

普通 `def` 后台任务可以由框架在线程池中执行。若把任务写成 `async def`，其中却调用长时间同步 I/O 或 CPU 计算，仍可能阻塞事件循环。

- 小型同步 I/O：使用普通 `def`，或显式隔离到线程池；
- 原生异步 I/O：使用 `async def` 并完整 await；
- CPU 密集任务：使用进程池或外部 worker；
- 需要可靠重试、持久化和独立扩缩容：使用消息队列与任务 worker。

线程池容量有限，也不能把不具备线程安全保证的 Session 或 client 随意跨线程使用。

## 4. 不要复用即将清理的请求资源

yield 依赖会按自身 scope 退出，后台任务不应依赖请求结束后可能已经关闭的数据库 Session、文件流或连接。

更稳妥的做法是只向后台任务传递稳定标识：

```python
def process_document(document_id: str) -> None:
    with create_new_session() as session:
        document = session.get(Document, document_id)
        ...
```

后台任务内部创建并释放自己的资源，而不是接收请求阶段产生的 ORM 对象或 Session。

## 5. 何时升级为任务队列

满足任一条件时，应认真评估外部 worker：

- 任务不能因 Web 进程重启而丢失；
- 需要重试、死信、延迟或定时执行；
- CPU 或耗时会明显影响 Web 实例；
- 任务量需要独立扩缩容；
- 需要查看状态、进度和失败原因；
- 任务可能跨多个服务协作。

常见流程：

```text
HTTP 请求
  ↓
写入业务记录 / Outbox
  ↓
提交消息或任务 ID
  ↓
Worker 独立执行
  ↓
记录成功、失败、重试与可观测信息
```

## 6. 可观测性

无论使用 BackgroundTasks 还是外部队列，都应记录：

- task/job ID；
- 业务对象 ID；
- 开始、结束与耗时；
- 重试次数；
- 异常堆栈；
- 幂等键或去重信息；
- 最终状态。

否则“响应已发送”很容易被误解为“后台工作已经完成”。

