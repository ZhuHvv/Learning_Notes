# Go error、panic 与 recover

> 所属分类：Go / Gin / Runtime  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Go 用 error 显式处理可预期错误；panic 表示严重异常；recover 只能在 defer 中捕获同 goroutine 的 panic。


## 2. 原理性解释

- error 是普通返回值。
- panic 会执行 defer 并中断当前 goroutine。
- recover 必须在 defer 中调用。
- HTTP 服务常用 recover 中间件兜底。
- 业务错误不要滥用 panic。

### error、panic、recover 对应不同级别的异常处理

Go 鼓励显式返回 error 处理可预期错误，例如数据库查不到、参数非法。panic 适合不可恢复的程序错误，例如数组越界、初始化配置严重缺失。recover 只能在 defer 中捕获同 goroutine 的 panic，常用于 HTTP 中间件防止单个请求打崩进程。

```go
defer func() {
    if r := recover(); r != nil { log.Println(r) }
}()
```

## 3. 机制流程

1. 函数返回 error。
2. 调用方检查。
3. 严重异常 panic。
4. defer recover 记录日志。

### 错误处理流程

```text
业务可预期失败 → return error → handler 转 HTTP 状态码
程序不变量被破坏 → panic
  ↓
defer recover 捕获
  ↓
记录堆栈 + 返回 500 + 服务继续运行
```

不要用 panic 代替业务错误，也不要 recover 后静默吞掉问题；至少要记录日志和 trace id。

## 4. 类比理解

error 是红灯提示，panic 是设备冒烟，recover 是紧急断电。

## 5. 应用举例 / 代码或伪代码

```go
defer func() {
    if r := recover(); r != nil {
        log.Printf("panic: %v", r)
    }
}()
```

## 6. 你在讨论中的理解推进

你在 Gin ErrorHandler 中接触错误边界；常规业务用 error，recover 只兜底。

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

**Go error、panic 与 recover** 在 Go 后端中通常要和 Handler、Context、goroutine、连接池、日志与错误处理一起看：

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

## 11. 针对 `Go error、panic 与 recover` 的专项排查

Go 后端的关键不是只写出能跑的代码，而是保证请求生命周期、资源释放和并发安全。检查 **Go error、panic 与 recover** 时：

- **请求路径**：请求从 router 到 middleware，再到 handler，最后到 service/dao，链路是否清楚。
- **Context 传播**：数据库、Redis、RPC 调用是否使用同一个请求 context 或带超时 context。
- **错误处理**：错误是返回、包装、记录，还是 panic；是否有统一错误响应。
- **并发安全**：共享 map、连接池、全局对象是否存在竞争或生命周期问题。

### 小型练习

```go
func withTimeout(r *http.Request) (context.Context, context.CancelFunc) {
    return context.WithTimeout(r.Context(), 2*time.Second)
}

// 练习：检查与 Go error、panic 与 recover 有关的外部调用是否都接收 ctx。
```

### 面试表达模板

讲 `Go error、panic 与 recover` 时，可以结合 Gin/Context/DB/中间件说明它在一次 HTTP 请求中的位置，而不是只讲语言特性本身。
