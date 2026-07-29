# Go Context：请求取消、超时与值传递

> 所属主线：Go 并发与请求生命周期  
> 难度：进阶  
> 前置知识：Channel、`select` 与请求处理  
> 后续知识：并发任务组、SSE 和 gRPC 调用

## 1. 总体性概念

Go Context 用于请求链路中的取消、超时和少量元数据传递；它代表一次生命周期，不应长期放结构体字段。


## 2. 原理性解释

- 父 context 取消会传播到子 context。
- Done channel 关闭表示取消。
- WithTimeout 要 defer cancel。
- WithValue 只放请求范围元数据。
- ctx 应作为函数第一个参数显式传递。

### Context 是请求范围的取消信号与元数据载体

Go 的 `context.Context` 主要用于跨 API 边界传递取消、超时、deadline 和少量请求范围值。把请求 Context 放进长期存活的结构体，容易持有过期 Context，导致误取消、资源泄漏或语义混乱；它的生命周期通常应和一次请求或操作绑定。

```go
ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
defer cancel()
rows, err := db.QueryContext(ctx, query)
```

## 3. 机制流程

1. 请求生成 ctx。
2. 传给 DB/RPC/goroutine。
3. 超时或断开。
4. Done 关闭。
5. 下游退出。

### 取消传播流程

```text
客户端断开 / 超时 / 手动 cancel
  ↓
ctx.Done() 关闭
  ↓
数据库查询、HTTP 请求、goroutine select 感知取消
  ↓
释放资源并返回 ctx.Err()
```

`context.WithValue` 只适合请求范围元数据，例如 request id、trace id、用户身份；不要用它传业务依赖，如 db、logger、config。

## 4. 类比理解

Context 像任务通行证，任务结束通行证失效。

## 5. 应用举例 / 代码或伪代码

```go
func Query(ctx context.Context, db *sql.DB) error {
    ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
    defer cancel()
    return db.QueryRowContext(ctx, "select 1").Err()
}
```

### HTTP 下游调用继承超时

```go
func fetchWithTimeout(parent context.Context, url string) ([]byte, error) {
    ctx, cancel := context.WithTimeout(parent, 2*time.Second)
    defer cancel()

    req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
    if err != nil {
        return nil, err
    }

    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()

    return io.ReadAll(resp.Body)
}
```

子调用的 deadline 不应晚于父请求允许的时间。设置本地超时时应同时考虑上游剩余预算，而不是每一层都重新获得完整超时。

### 携带取消原因

需要区分“谁取消、为什么取消”时，可使用 `context.WithCancelCause`：

```go
ctx, cancel := context.WithCancelCause(parent)
cancel(errQuotaExceeded)

if cause := context.Cause(ctx); cause != nil {
    log.Printf("cancel cause: %v", cause)
}
```

`ctx.Err()` 仍返回 `context.Canceled` 或 `context.DeadlineExceeded`；`context.Cause` 用于读取更具体的原因。

## 6. 使用边界

- Context 表达取消、deadline 和请求级元数据，不负责承载可选参数或业务依赖。
- Context 可以放进短生命周期、语义明确的对象，但一般 API 不应把请求 Context 长期存入结构体字段。
- Context 取消只是发出信号；下游代码若不监听 `Done` 或不调用支持 Context 的 API，工作不会自动停止。
