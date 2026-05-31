# Go Context：取消、超时与值传递

> 所属分类：Go / Gin / Runtime  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Go Context 用于请求链路中的取消、超时和少量元数据传递；它代表一次生命周期，不应长期放结构体字段。


## 2. 原理性解释

- 父 context 取消会传播到子 context。
- Done channel 关闭表示取消。
- WithTimeout 要 defer cancel。
- WithValue 只放请求范围元数据。
- ctx 应作为函数第一个参数显式传递。

### Context 是请求范围的取消信号与元数据载体

Go 的 `context.Context` 主要用于跨 API 边界传递取消、超时、deadline 和少量请求范围值。你问“Context 放在结构体字段里不是也能接收关闭信号吗？”问题在于 context 的生命周期应跟请求/操作绑定，放进长期结构体容易持有过期 context，导致误取消、资源泄漏或语义混乱。

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

## 6. 你在讨论中的理解推进

你追问放结构体也能接收 Done；关键是结构体生命周期通常长于一次请求。

## 7. 常见误区与排查思路

- 只背名词，不知道它在完整链路中的输入、输出和失败模式。
- 只看正常路径，忽略异常、超时、权限、重复和可观测性。
- 把相邻概念混用，导致设计或排查时定位错误。

## 8. 关联知识点

- 回到 00_总体索引.md 查看上下游知识点。
- 结合 00_总体知识网络图.md 理解跨模块关系。

## 9. 复习检查问题

- 它解决的核心问题是什么？
- 它的输入、输出和中间状态分别是什么？
- 它在真实项目中最容易出错的边界条件是什么？
- 它和上游、下游知识点如何连接？

## 10. 更细的工程拆解

**Go Context：取消、超时与值传递** 在 Go 后端中通常要和 Handler、Context、goroutine、连接池、日志与错误处理一起看：

1. **入口**：HTTP/RPC 请求进入 Handler 或 Middleware。
2. **依赖**：DB、Redis、Logger、Service 通常通过闭包、结构体或依赖注入传入。
3. **控制**：Context 负责超时、取消和跨函数传递请求级信息。
4. **退出**：错误要被明确返回或集中处理，goroutine 要避免泄露。

### 最小服务骨架

```go
type App struct {
    DB     *sql.DB
    Logger *log.Logger
}

func (a *App) Handler(w http.ResponseWriter, r *http.Request) {
    ctx := r.Context()
    if err := a.DB.PingContext(ctx); err != nil {
        http.Error(w, "db unavailable", http.StatusServiceUnavailable)
        return
    }
    w.WriteHeader(http.StatusOK)
}
```

### 工程落地要点

- 能通过参数传递的依赖，不要到处使用全局变量。
- 对外部 IO 使用 `context.WithTimeout`，否则请求取消后后端仍可能继续消耗资源。
- 中间件适合做认证、日志、错误收集、跨域和限流，不适合塞入复杂业务逻辑。

## 11. 针对 `Go Context：取消、超时与值传递` 的专项排查

Go 后端的关键不是只写出能跑的代码，而是保证请求生命周期、资源释放和并发安全。检查 **Go Context：取消、超时与值传递** 时：

- **请求路径**：请求从 router 到 middleware，再到 handler，最后到 service/dao，链路是否清楚。
- **Context 传播**：数据库、Redis、RPC 调用是否使用同一个请求 context 或带超时 context。
- **错误处理**：错误是返回、包装、记录，还是 panic；是否有统一错误响应。
- **并发安全**：共享 map、连接池、全局对象是否存在竞争或生命周期问题。

### 小型练习

```go
func withTimeout(r *http.Request) (context.Context, context.CancelFunc) {
    return context.WithTimeout(r.Context(), 2*time.Second)
}

// 练习：检查与 Go Context：取消、超时与值传递 有关的外部调用是否都接收 ctx。
```

### 面试表达模板

讲 `Go Context：取消、超时与值传递` 时，可以结合 Gin/Context/DB/中间件说明它在一次 HTTP 请求中的位置，而不是只讲语言特性本身。
