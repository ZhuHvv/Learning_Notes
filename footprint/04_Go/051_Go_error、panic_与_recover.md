# Go error、panic 与 recover

> 所属分类：Go / Gin / Runtime  
> 修订版本：v9 昨日今日增量版  
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

