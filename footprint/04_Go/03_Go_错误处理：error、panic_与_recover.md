# 04.03 Go 错误处理：error、panic 与 recover

> 所属主线：Go 错误处理  
> 难度：入门  
> 前置知识：函数返回值、接口与 `defer`  
> 后续知识：HTTP 错误边界、并发任务错误传播

## 1. 总体性概念

Go 用 error 显式处理可预期错误；panic 表示严重异常；recover 只能在 defer 中捕获同 goroutine 的 panic。


## 2. 原理性解释

- error 是普通返回值。
- panic 会停止当前函数的正常流程，并沿当前 goroutine 的调用栈执行 `defer`。
- 如果 panic 一直没有被 recover，最终会终止整个程序，而不只是结束当前 goroutine。
- recover 必须由同一 goroutine 的延迟函数直接调用才有效。
- HTTP 服务常用 recover 中间件兜底。
- 业务错误不要滥用 panic。

### error、panic、recover 对应不同级别的异常处理

Go 鼓励显式返回 error 处理可预期错误，例如数据库查不到、参数非法。panic 适合程序无法继续维持正确性的情况，例如数组越界或关键初始化失败。recover 只能在同一 goroutine 的延迟函数中捕获 panic，常用于 HTTP 中间件隔离单个请求中的异常。

```go
defer func() {
    if r := recover(); r != nil { log.Println(r) }
}()
```

普通错误需要保留上下文，同时支持调用方判断根因：

```go
if err != nil {
    return fmt.Errorf("load user %s: %w", id, err)
}

if errors.Is(err, sql.ErrNoRows) {
    // 转换为“用户不存在”等领域错误
}
```

- 使用 `%w` 包装错误链；
- 使用 `errors.Is` 判断链中的特定错误；
- 使用 `errors.As` 提取链中的特定错误类型；
- 不要依赖完整错误字符串做程序分支。

## 3. 机制流程

1. 下层返回或包装 error。
2. 调用方用 `errors.Is/As` 分类并决定重试、转换或继续返回。
3. 程序不变量被破坏时才 panic。
4. 边界层通过 `defer` + `recover` 记录堆栈并隔离故障。

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

## 6. 使用边界

- 业务可预期失败：返回 `error`。
- 包内部为简化深层控制流而使用 panic：必须在包边界转换回 `error`。
- HTTP/RPC 边界：recover 后记录堆栈、请求标识并返回统一错误；不要静默吞掉 panic。
- 后台 goroutine：需要在该 goroutine 内部设置 recover，其他 goroutine 无法替它捕获 panic。
