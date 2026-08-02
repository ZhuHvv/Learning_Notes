# 04.08 Goroutine：数量、调度与性能边界

> 所属主线：Go 并发  
> 难度：进阶  
> 前置知识：Go 异步与并发模型  
> 后续知识：Channel、Context、Mutex 与并发任务组

## 1. 总体性概念

Goroutine 是 Go 语言中由运行时管理的轻量级并发执行单元。它比操作系统线程更轻，但并不等于“没有成本”。

核心问题是：**goroutine 数量是不是越多越好，会不会影响性能？** 结论是：goroutine 可以大量创建，但数量必须由任务类型、阻塞情况、内存占用、调度开销和下游资源容量共同决定。

## 2. 原理性解释

Go 运行时使用 **M:N 调度模型**：

- `G`：goroutine，代表待执行任务。
- `M`：machine，可以理解为操作系统线程。
- `P`：processor，运行时调度资源，数量通常受 `GOMAXPROCS` 控制。

```text
很多 G（goroutine）
  ↓ 由 Go runtime 调度
少量 M（OS thread） + 若干 P（调度上下文）
  ↓
CPU 核心执行
```

Goroutine 的初始栈很小，会按需增长，所以它适合高并发 I/O 场景。但它仍然有成本：

1. **栈内存成本**：每个 goroutine 都要维护栈、状态和调度信息。
2. **调度成本**：goroutine 过多时，runtime 要在大量 G 中挑选可运行任务。
3. **上下文切换成本**：虽然比线程轻，但频繁切换仍然会消耗 CPU。
4. **下游资源成本**：例如数据库连接池只有 20 个连接，开 10 万个 goroutine 也不能让数据库同时处理 10 万个请求。
5. **CPU 型任务受核心数限制**：CPU 密集型任务并不是 goroutine 越多越快，最终仍受 CPU 核数与 `GOMAXPROCS` 限制。

因此，Go 并发的关键不是“开多少 goroutine”，而是：

- I/O 型任务：可以开较多 goroutine，但要限制下游资源并发。
- CPU 型任务：goroutine 数量通常接近 CPU 核数或略高。
- 长生命周期任务：必须关注退出条件，避免 goroutine 泄露。

## 3. 机制流程

### 3.1 创建与调度流程

```text
调用 go func()
  ↓
创建 G，并放入本地或全局运行队列
  ↓
P 从队列取出可运行 G
  ↓
M 执行该 G
  ↓
G 阻塞 / 让出 / 结束
  ↓
runtime 调度其他 G
```

### 3.2 I/O 阻塞时的调度

当 goroutine 等待网络 I/O 时，Go runtime 会尽量把它挂起，当前线程可继续执行其他 goroutine。这样能让少量线程支撑大量连接。

```text
G1 发起网络读
  ↓
G1 等待数据，进入阻塞/等待状态
  ↓
M 不必一直空等，继续运行 G2/G3
  ↓
网络数据就绪
  ↓
G1 被重新放回可运行队列
```

### 3.3 CPU 密集型任务的限制

如果任务是大量计算，goroutine 无法凭空增加 CPU：

```text
10000 个计算型 goroutine
  ↓
最终仍只能由有限 CPU 核心执行
  ↓
过多 goroutine 反而增加调度成本
```

## 4. 类比理解

Goroutine 像“很多张任务单”，OS 线程像“真正干活的工人”，CPU 核心像“工作台”。任务单可以很多，但工作台和工人有限。I/O 型任务经常在等外部结果，所以多排一些任务单能提高利用率；CPU 型任务一直占用工作台，任务单太多只会增加排队和调度负担。

## 5. 应用举例 / 代码或伪代码

### 5.1 不受控制地创建 goroutine：容易压垮下游

```go
for _, id := range ids {
    go func(id int) {
        // 如果 ids 有几十万，并且每个都访问 DB，可能瞬间打爆连接池或数据库。
        queryDatabase(id)
    }(id)
}
```

### 5.2 使用信号量限制并发

```go
var wg sync.WaitGroup
sem := make(chan struct{}, 20) // 最多同时 20 个任务访问下游资源

for _, id := range ids {
    wg.Add(1)
    sem <- struct{}{} // 获取并发名额

    go func(id int) {
        defer wg.Done()
        defer func() { <-sem }() // 释放名额

        queryDatabase(id)
    }(id)
}

wg.Wait()
```

### 5.3 Worker Pool：固定 goroutine 数量处理大量任务

```go
func worker(id int, jobs <-chan int, results chan<- string) {
    for job := range jobs {
        results <- fmt.Sprintf("worker %d processed job %d", id, job)
    }
}

func main() {
    jobs := make(chan int)
    results := make(chan string)

    for i := 0; i < 10; i++ { // 固定 10 个 worker
        go worker(i, jobs, results)
    }

    go func() {
        for j := 0; j < 1000; j++ {
            jobs <- j
        }
        close(jobs)
    }()

    for i := 0; i < 1000; i++ {
        fmt.Println(<-results)
    }
}
```

### 5.4 结合 Context 防止 goroutine 泄露

长生命周期 goroutine 必须有明确退出条件，常见做法是在循环中同时监听业务 channel 和 `ctx.Done()`。完整代码统一放在 [Channel：关闭、方向限制与 select 读就绪](09_Channel：关闭、方向限制与_select_读就绪.md) 的“结合 ctx 退出”小节，Context 的传播规则则见后续 Context 专题。

### 5.5 Fire-and-forget 后台任务

```go
go func() {
    if err := doBackgroundWork(); err != nil {
        logger.Error("background work failed", "err", err)
    }
}()
```

调用方虽然不等待结果，但任务仍然需要：

- 明确由进程、服务还是请求控制生命周期；
- 记录或上报错误；
- 在服务关闭时停止接收新任务并等待已有任务结束；
- 必要时从请求 Context 派生独立、有限时长的后台 Context，避免请求结束后任务被意外取消或无限运行。

### 5.6 WaitGroup：等待完成，不限制并发

```go
var wg sync.WaitGroup

for _, task := range tasks {
    task := task
    wg.Add(1)
    go func() {
        defer wg.Done()
        process(task)
    }()
}

wg.Wait()
```

`WaitGroup` 只统计任务是否完成。如果 `tasks` 很大，仍应结合 worker pool 或 semaphore 控制同时运行数量。

### 5.7 errgroup：请求链路中的任务组

```go
g, ctx := errgroup.WithContext(ctx)

g.Go(func() error {
    return callA(ctx)
})
g.Go(func() error {
    return callB(ctx)
})

if err := g.Wait(); err != nil {
    return err
}
```

`errgroup` 将“等待、首个错误和取消传播”组合在一起。任一任务返回错误后，其他任务可通过派生 Context 感知取消；但下游函数仍必须真正监听该 Context。

## 6. 常见误区与排查思路

- **误区 1：goroutine 越多越快。** CPU 型任务可能变慢，I/O 型任务也会受下游资源限制。
- **误区 2：goroutine 很轻，所以不用管退出。** 没有退出条件的 goroutine 会泄露。
- **误区 3：WaitGroup 能控制并发。** `WaitGroup` 只能等待完成，不能限制同时运行数量；限制并发要用 semaphore、worker pool 或连接池。
- **排查 1：看 goroutine 数量。** 可通过 `runtime.NumGoroutine()` 或 pprof 观察。
- **排查 2：看阻塞点。** 大量 goroutine 堵在 channel、mutex、网络 I/O、数据库连接池上，说明瓶颈不在 goroutine 创建本身。

## 7. 关联知识点

- Go Context：请求取消、超时与值传递
- Channel：关闭、方向限制与 select 读就绪
- sync.Mutex：Lock、TryLock 与锁模型
- HTTP Streaming、SSE、WebSocket 与 gRPC Streaming

## 8. 复习检查问题

- Goroutine 为什么比线程轻？它是否完全没有成本？
- I/O 型任务和 CPU 型任务的 goroutine 数量设计有什么区别？
- `WaitGroup` 和并发控制有什么区别？
- 如何发现 goroutine 泄露？

## 9. 更细的工程拆解

真实后端中，goroutine 通常出现在：

1. HTTP 请求处理：每个请求由 net/http 启动 goroutine 处理。
2. 后台任务：定时任务、异步消费、日志写入。
3. 并发调用：同时请求多个下游服务。
4. 流式输出：SSE/WebSocket 长连接维护。

### 并发调用多个下游服务

```go
func Aggregate(ctx context.Context, userID string) (*Result, error) {
    ctx, cancel := context.WithTimeout(ctx, 800*time.Millisecond)
    defer cancel()

    type item struct {
        name string
        val  any
        err  error
    }

    ch := make(chan item, 3)

    go func() { v, err := getProfile(ctx, userID); ch <- item{"profile", v, err} }()
    go func() { v, err := getOrders(ctx, userID);  ch <- item{"orders", v, err} }()
    go func() { v, err := getScore(ctx, userID);   ch <- item{"score", v, err} }()

    res := &Result{}
    for i := 0; i < 3; i++ {
        select {
        case <-ctx.Done():
            return nil, ctx.Err()
        case it := <-ch:
            if it.err != nil {
                return nil, it.err
            }
            res.Set(it.name, it.val)
        }
    }
    return res, nil
}
```

## 10. 专项排查

- goroutine 数量是否持续增长但不下降？可能泄露。
- 是否创建了大量永久阻塞在 channel receive/send 上的 goroutine？
- 是否将 CPU 型任务拆成过多 goroutine，导致调度开销过高？
- 是否没有根据 DB/Redis/RPC 下游容量限制并发？
- 是否缺少 `ctx.Done()` 退出分支？
- 是否只用了 WaitGroup 等待，却没有限制任务创建速度？
- 并发调用存在首错即取消需求时，是否更适合使用 errgroup？
