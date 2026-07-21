# Go SSE：text event-stream 与流式响应

> 所属分类：Go / Gin / Runtime  
> 修订版本：v11 审查修订版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Go SSE 通过 text/event-stream、持续写入 data 行并 Flush，实现服务端到客户端单向流式响应。


## 2. 原理性解释

- SSE 是单向推送。
- 需要设置响应头和 no-cache。
- 每条消息以空行结束。
- 必须 Flush。
- 应监听 request context 处理断开。

### SSE 是 HTTP 上的服务端单向事件流

SSE 通过 `Content-Type: text/event-stream` 保持 HTTP 响应不断开，服务端按事件格式持续写入数据。它适合 LLM token 流、任务进度、日志推送等服务端到客户端的单向流。和 WebSocket 相比，SSE 更简单，但不适合高频双向通信。

```text
event: message
data: hello

```

## 3. 机制流程

1. 客户端请求。
2. 服务端设置 SSE 头。
3. 写 event/data。
4. flush。
5. 客户端增量渲染。

### Go SSE Handler 流程

```go
func stream(c *gin.Context) {
    c.Header("Content-Type", "text/event-stream")
    c.Header("Cache-Control", "no-cache")
    flusher, _ := c.Writer.(http.Flusher)
    for msg := range ch {
        fmt.Fprintf(c.Writer, "data: %s\n\n", msg)
        flusher.Flush()
    }
}
```

工程上要处理客户端断开、心跳、缓冲区阻塞和反向代理超时，否则流式接口会在部署后表现不稳定。

## 4. 类比理解

普通 HTTP 像整桌菜上齐，SSE 像做好一道上一道。

## 5. 应用举例 / 代码或伪代码

```go
func Stream(c *gin.Context) {
    c.Header("Content-Type", "text/event-stream")
    flusher := c.Writer.(http.Flusher)
    for token := range tokens {
        fmt.Fprintf(c.Writer, "data: %s\n\n", token)
        flusher.Flush()
    }
}
```

## 6. 你在讨论中的理解推进

你多次追问 SSE 与状态更新；SSE 可以提前展示 token，但不等于状态已提交。

