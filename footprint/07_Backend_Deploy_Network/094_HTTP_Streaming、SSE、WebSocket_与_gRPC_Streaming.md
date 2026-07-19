# HTTP Streaming、SSE、WebSocket 与 gRPC Streaming

> 所属分类：Backend / Deploy / Network  
> 修订版本：v11  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

HTTP Streaming、SSE、WebSocket、gRPC Streaming 都能流式传输，但方向和场景不同：SSE 单向，WebSocket 双向，gRPC 适合服务间强类型流。


## 2. 原理性解释

- SSE 基于 HTTP，适合 token 推送。
- WebSocket 适合双向实时。
- gRPC streaming 适合服务间。
- 代理缓冲和断线取消必须处理。

### 四种流式技术的核心差异是方向、协议和适用场景

HTTP Streaming 是泛称；SSE 是 HTTP 上的服务端到客户端事件流；WebSocket 是全双工长连接；gRPC Streaming 是基于 HTTP/2 的强类型流。SSE 区别于普通 HTTP Streaming 的关键特性：浏览器 EventSource 会自动重连，并通过 `Last-Event-ID` 请求头实现断点续传。LLM 输出 token 通常 SSE 足够；多人实时协作或游戏状态同步更适合 WebSocket；服务间强类型流式调用适合 gRPC streaming。

gRPC 共有四种调用模式：

- **unary**：一请求一响应，等价于普通 RPC，适合常规查询/写入。
- **server streaming**：一个请求换服务端一串响应，适合结果推送、大列表分批下发。
- **client streaming**：客户端连续发送多条消息后服务端汇总返回一次，适合日志/指标批量上报。
- **bidirectional streaming**：双向独立流，适合实时对话、双向同步等持续交互场景。

```text
SSE: server → client
WebSocket: client ↔ server
gRPC stream: typed service stream
```

## 3. 机制流程

1. 建立请求/连接。
2. 服务端持续产生事件。
3. 按协议发送。
4. 客户端增量处理。
5. 断线重连或取消。

### LLM 流式输出流程

```text
前端发起请求
  ↓
后端调用 LLM stream API
  ↓
每收到一个 token/chunk
  ↓
写入 SSE data 帧并 flush
  ↓
前端 EventSource 追加显示
```

如果后端内部框架节点不 yield token，只在结束后返回 state，那么即使 LLM 支持 stream，用户仍看不到实时输出。

## 4. 类比理解

SSE 是广播，WebSocket 是电话，gRPC streaming 是企业专线。

## 5. 应用举例 / 代码或伪代码

```text
SSE:
event: message
data: hello

WebSocket: client <-> server
gRPC stream: typed messages over HTTP/2
```

## 6. 你在讨论中的理解推进

你多次比较 HTTP、SSE、WebSocket；关键是区分传输流、模型 token 流和应用状态。

