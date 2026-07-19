# Go Context：取消、超时与值传递

> 所属分类：Go / Gin / Runtime  
> 修订版本：v9 昨日今日增量版  
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

