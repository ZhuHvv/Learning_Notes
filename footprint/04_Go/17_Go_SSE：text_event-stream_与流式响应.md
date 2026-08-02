# 04.17 Go SSE：text/event-stream 与流式响应

> 所属主线：Go 流式应用  
> 难度：深入  
> 前置知识：HTTP Handler、Channel 与 Context  
> 后续知识：Eino 流式模型与 Agent 事件

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
    c.Header("X-Accel-Buffering", "no")

    flusher, ok := c.Writer.(http.Flusher)
    if !ok {
        c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{
            "error": "streaming unsupported",
        })
        return
    }

    ctx := c.Request.Context()
    for {
        select {
        case <-ctx.Done():
            return
        case msg, ok := <-ch:
            if !ok {
                return
            }
            fmt.Fprintf(c.Writer, "data: %s\n\n", msg)
            flusher.Flush()
        }
    }
}
```

工程上要处理客户端断开、心跳、缓冲区阻塞和反向代理超时，否则流式接口会在部署后表现不稳定。`X-Accel-Buffering: no` 常用于提示 Nginx 不缓冲该响应，但仍需结合实际代理配置验证。

## 4. 类比理解

普通 HTTP 像整桌菜上齐，SSE 像做好一道上一道。

## 5. 协议与工程边界

- 一条事件由若干字段行组成，并以空行结束；多行数据应拆成多个 `data:` 行。
- `Flush` 只把当前缓冲内容向下游推进，不保证浏览器已渲染，也不代表数据库或任务状态已经提交。
- SSE 是服务端到客户端的单向通道；高频双向通信通常更适合 WebSocket。
- 客户端断开后，Handler 应通过请求 Context 退出，并继续把取消信号传给模型、数据库或其他生产者。
- 若生产速度长期高于网络发送速度，需要有界队列、丢弃/合并策略或背压设计，不能让内存无限积压。
