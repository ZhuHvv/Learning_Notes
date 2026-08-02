# 04.07 Go 并发模型：goroutine、channel、select 与 Context

> 所属主线：Go 并发  
> 难度：基础  
> 前置知识：函数、接口与错误处理  
> 后续知识：Goroutine 调度、Channel、Context 与 Mutex

## 1. 先区分三个概念

- **并发（concurrency）**：多个任务的生命周期重叠，系统在它们之间推进工作。
- **并行（parallelism）**：多个任务在同一时刻由多个 CPU 核心真正执行。
- **异步（asynchrony）**：调用方启动任务后不原地等待，通过结果、回调或事件在之后获知完成状态。

Go 没有 Python 风格的 `async` / `await` 关键字。Go 通常用以下机制组合表达并发和异步：

- `go` 启动 goroutine；
- `channel` 传递数据和同步信号；
- `select` 同时等待多个 channel 事件；
- `context.Context` 传递取消、deadline 和请求生命周期；
- `WaitGroup`、`errgroup` 等等待任务完成并汇总错误；
- `sync.Mutex`、`sync/atomic` 保护共享内存。

## 2. Python async/await 与 Go 的差异

Python `asyncio` 通常以事件循环和协作式让出为中心：

```text
async 函数创建协程
  → await 遇到等待点时让出控制权
  → 事件循环推进其他协程
  → I/O 完成后恢复原协程
```

Go 以 goroutine 和运行时调度为中心：

```text
go f() 创建 goroutine
  → Go runtime 将 goroutine 调度到 OS 线程
  → channel / mutex / syscall / network poller 使任务等待或唤醒
  → select / WaitGroup / Context 组织协作与退出
```

| 对比点 | Python async/await | Go goroutine 模型 |
|---|---|---|
| 并发单元 | coroutine | goroutine |
| 启动方式 | 调用 async 函数并交给事件循环 | `go f()` |
| 常见让出点 | `await` | channel、锁、I/O、运行时抢占等 |
| 等待多个任务 | `gather` / `wait` | `select` / WaitGroup / errgroup |
| 取消 | task cancel / timeout | `context.Context` |
| 常见执行模型 | 单线程事件循环 | M:N 调度，可使用多个 OS 线程 |

## 3. 一条完整的并发控制链

```text
请求进入 Handler
  → 启动 goroutine 并发执行可独立任务
  → channel / errgroup 汇总结果和错误
  → select 同时等待结果、超时或退出信号
  → Context 将取消传播给 DB / HTTP / RPC
  → Mutex / atomic 保护必须共享的内存状态
  → worker pool / semaphore 限制并发规模
```

这条链路中的组件不能互相替代：

- goroutine 解决“任务如何并发执行”；
- channel 解决“任务如何通信和同步”；
- Context 解决“整条调用链何时停止”；
- Mutex 解决“共享内存如何互斥访问”；
- WaitGroup 只等待完成，不限制并发；
- worker pool 或 semaphore 才负责限制同时运行数量。

## 4. 三种常见形态

### 4.1 Fire-and-forget

调用方启动后台任务后立即继续。它仍然需要错误记录、退出策略和服务关闭时的收尾，不能把 `go func()` 当作任务系统。

### 4.2 启动后等待结果

任务在 goroutine 中执行，调用方通过单元素 channel、WaitGroup 或 errgroup 等待。若需要超时，应同时把 Context 传进任务，让“放弃等待”和“停止工作”保持一致。

### 4.3 等待多个事件

`select` 可以同时等待结果 channel、`ctx.Done()`、ticker 或其他信号。已关闭 channel 会永久读就绪，因此循环中必须检查 `ok` 或把关闭的 channel 置为 `nil`。

## 5. 选择工具

| 需求 | 优先考虑 |
|---|---|
| 启动一个独立任务 | goroutine |
| 传递数据或所有权 | channel |
| 等待多个事件 | `select` |
| 等待一组任务全部完成 | WaitGroup |
| 首个错误触发整组取消 | errgroup + Context |
| 限制并发数量 | worker pool / semaphore |
| 保护同一进程内共享状态 | Mutex / RWMutex / atomic |
| 跨服务异步削峰、重试和持久化 | 消息队列或任务系统 |

## 6. 常见误区

- Go 没有 `async/await`，不代表不支持异步。
- `go f()` 只负责启动，不会自动传播错误或等待结束。
- 请求结束不会自动杀死手动创建的所有 goroutine；任务必须监听 Context。
- channel 不是所有并发场景的必需品；共享状态、完成等待和错误汇总各有更合适的工具。
- goroutine 很轻，但栈、调度、下游连接和任务积压仍有成本。
- 并发不一定并行，异步也不等于更快。

## 7. 后续阅读

1. Goroutine 数量、调度与性能边界
2. Channel 关闭、方向限制与 `select` 读就绪
3. Context：取消、超时与值传递
4. `sync.Mutex`、`TryLock` 与锁模型
