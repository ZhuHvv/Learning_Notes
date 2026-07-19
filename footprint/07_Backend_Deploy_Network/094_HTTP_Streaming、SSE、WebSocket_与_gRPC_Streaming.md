# HTTP Streaming、SSE、WebSocket 与 gRPC Streaming

> 所属分类：Backend / Deploy / Network  
> 修订版本：v11  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

HTTP Streaming 是分块响应的泛称；SSE 是 HTTP 上的服务端单向事件流；WebSocket 是全双工长连接；gRPC Streaming 是服务间的强类型单向或双向流。框架响应流、SSE 应用帧和底层网络发送属于不同层。

## 2. 原理性解释

- SSE 适合 token、进度和事件推送，EventSource 支持自动重连和 Last-Event-ID；
- WebSocket 适合持续双向交互；
- gRPC 有 unary、server streaming、client streaming、bidirectional streaming；
- `StreamingResponse` 迭代上游 chunk，但不会自动把 dict 变成 SSE；
- 原生 EventSource 只能 GET，POST 流需用 fetch 等客户端读取；
- 响应头发出后，流中异常通常不能再改 HTTP 状态；
- 反向代理、压缩和客户端可能缓冲 chunk；
- 无界 Queue 会切断端到端背压。

### 四种流式技术的核心差异是方向、协议和适用场景

```text
HTTP Streaming：response body 分块发送
SSE：server → client 的文本事件
WebSocket：client ↔ server 的消息连接
gRPC Streaming：typed service stream
```

LLM token 推送通常 SSE 足够；多人协作、游戏和实时控制更适合 WebSocket；服务间强类型流式调用适合 gRPC。选型还要考虑认证、客户端生态、重连、代理支持和消息契约。

### StreamingResponse 与生成器对象

对于异步 iterable，ASGI 层可抽象为：

```text
发送 response.start
async for chunk in content:
    发送 response.body(more_body=True)
发送最终 body(more_body=False)
```

异步生成器函数必须调用后得到生成器对象再传入：`StreamingResponse(event_stream(), ...)`。同步 iterable 通常由 Starlette 在线程池中迭代。

框架提交 chunk 不保证浏览器立即看到。生产环境要检查代理 buffering、压缩、缓存头、空闲超时和客户端缓冲。

### SSE 帧、POST 与错误

```text
event: progress
id: 42
data: {"percent":50}

```

空行（`\n\n`）结束一帧。`text/event-stream` 只设置 Content-Type，不会自动添加 `event:` / `data:`。序列化与包帧责任应固定在一层，避免重复 `json.dumps` 或重复前缀。

原生 EventSource 只发 GET；POST JSON 流通常用 `fetch` 读取 response body 并自行解析 SSE。`[DONE]` 是应用约定，不是 SSE 标准；也可以发送结构化 `event: done`。

响应开始后发生异常，应通过 error 事件或断开表达。客户端必须同时处理建连前 HTTP 错误、建连后 error、缺少完成事件的断开和重连去重。客户端断开会取消流 Task，但已进入 `to_thread` 的同步函数通常不能被强制停止，上游 SDK 仍需 timeout。

### 背压链路

```text
数据源 → Queue → async generator → StreamingResponse → 代理 → 客户端
```

生成器受上层消费速度约束，但若前面是无界 Queue，生产者仍可持续积压。端到端背压需要有界 Queue、`await put()`、可取消生产者、连接缓冲限制，以及对慢客户端的等待、合并、丢弃或断开策略。

## 3. 机制流程

1. 客户端建立 GET SSE、POST 流、WebSocket 或 gRPC 连接；
2. 上游模型/任务产生 token、进度、工具或错误事件；
3. 应用验证事件并序列化；
4. 传输层按 SSE/WebSocket/gRPC 协议发送；
5. 客户端增量处理；
6. 完成、异常或断开时取消上游并释放资源；
7. 必要时按 event ID 重连、续传和去重。

### LLM 流式输出流程

```text
模型 token/chunk 流
  ↓
应用事件流（token/tool/progress/error/done）
  ↓
SSE / WebSocket / gRPC 传输流
  ↓
客户端增量渲染
```

模型支持 streaming 不代表用户必然实时看到；中间工作流必须及时暴露事件，HTTP 层必须包帧，代理也不能无限缓冲。

## 4. 类比理解

SSE 像广播，WebSocket 像电话，gRPC Streaming 像企业专线。`StreamingResponse` 是传送带，SSE 帧是传送带上每个包裹的标签。

## 5. 应用举例 / 代码或伪代码

```python
import asyncio
import json
from fastapi import Request
from fastapi.responses import StreamingResponse

def sse(event: str, data: dict, event_id: int) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\nid: {event_id}\ndata: {payload}\n\n"

async def generate_events(request: Request):
    for step in range(1, 6):
        if await request.is_disconnected():
            return
        await asyncio.sleep(0.2)
        yield sse("progress", {"step": step, "total": 5}, step)
    yield sse("done", {"ok": True}, 6)

@app.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request):
    return StreamingResponse(
        generate_events(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
```

## 6. 你在讨论中的理解推进

你从 HTTP、SSE、WebSocket 的表面比较推进到完整分层：模型 token 流、应用事件流、协议帧和网络发送并非同一概念；实时性还取决于包帧、缓冲、取消和背压。
