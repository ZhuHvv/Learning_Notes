# Channel 关闭、只读通道与 select 读就绪

> 所属分类：Go / Gin / Runtime  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Channel 是 Go 中 goroutine 之间通信和同步的核心机制。今天你围绕 channel 问了几个非常关键的问题：

- 为什么 channel 需要关闭？
- 只读 channel 要怎么写入数据？
- 传参时变成只读 channel，是不是类似切片底层数组不变？
- `select` 读取未关闭 channel 和已关闭 channel 时为什么表现不同？
- 什么叫“读就绪”？

核心结论：**关闭 channel 的意义不是释放内存，而是向接收方广播“不会再有新数据”。只读 channel 只是编译期方向限制，不是创建一个新的底层队列。关闭后的 channel 读操作永远立即就绪。**

## 2. 原理性解释

### 2.1 Channel 为什么需要关闭

关闭 channel 的主要目的是通知接收方：发送端已经不会再发送数据。

```go
v, ok := <-ch
if !ok {
    // channel 已关闭且数据已读完
}
```

关闭不是必须的。只有当接收方需要知道“数据结束”时，才需要关闭。典型场景是：

- `for v := range ch` 需要在 channel 关闭后结束循环。
- 多个 worker 等待任务，关闭 jobs channel 表示不再有新任务。
- 生产者完成后通知消费者退出。

不需要关闭的场景：

- channel 只在局部使用，双方都自然退出。
- 通过 context 取消控制退出。
- 接收方不依赖 close 判断结束。

### 2.2 关闭 channel 的规则

- 通常由发送方关闭 channel。
- 不要由接收方关闭 channel，因为接收方不知道是否还有其他发送者。
- 已关闭的 channel 不能再发送数据，发送会 panic。
- 已关闭的 channel 可以继续读取，直到缓冲区读空。
- 读空后继续读会得到零值和 `ok=false`。

```go
close(ch)

v, ok := <-ch
// ok == false 表示 channel 已关闭且没有剩余数据
```

### 2.3 只读 channel 的本质

只读 channel 类型是 `<-chan T`，它表示当前变量或参数只能接收，不能发送。

```go
func consumer(ch <-chan int) {
    v := <-ch      // 可以读
    // ch <- 1     // 编译错误：不能向只读 channel 发送
}
```

这并不是新建了一个底层 channel。它更像是：同一个 channel 被传入函数时，函数拿到的是一个“只读视角”。

你用切片类比是合理的：

```text
slice 传参：复制 slice header，但底层数组相同
channel 传参：复制 channel 值，但底层 hchan 相同
```

区别在于：切片的只读不是类型系统强制的，而 channel 可以通过 `<-chan T` 或 `chan<- T` 做方向限制。

### 2.4 select 中的“读就绪”

对 channel 的读取是否“就绪”，可以理解为：**这个读取操作是否可以立即完成而不阻塞。**

读取操作在以下情况下就绪：

1. channel 中已有数据。
2. 有发送者正在等待发送。
3. channel 已经关闭。

读取操作在以下情况下不就绪：

1. channel 没有数据。
2. channel 没有关闭。
3. 没有发送者正在发送。

因此：

```go
select {
case v := <-ch:
    fmt.Println(v)
default:
    fmt.Println("no data")
}
```

- 如果 `ch` 未关闭且没有数据：走 `default`。
- 如果 `ch` 已关闭：`case v := <-ch` 永远就绪，会读到零值。

## 3. 机制流程

### 3.1 生产者关闭 channel，消费者 range 退出

```text
生产者发送数据
  ↓
消费者读取数据
  ↓
生产者 close(ch)
  ↓
消费者读完缓冲区
  ↓
range 自动结束
```

```go
go func() {
    defer close(ch)
    for i := 0; i < 3; i++ {
        ch <- i
    }
}()

for v := range ch {
    fmt.Println(v)
}
```

### 3.2 未关闭空 channel + select default

```text
select 检查 ch 是否可读
  ↓
ch 无数据、未关闭、无发送者
  ↓
读取不就绪
  ↓
执行 default
```

### 3.3 已关闭 channel + 无限循环

```text
close(ch)
  ↓
for 循环进入 select
  ↓
读取已关闭 channel 立即就绪
  ↓
读到零值
  ↓
下一轮仍然立即就绪
  ↓
无限打印零值
```

这就是你问的：**为什么循环外关闭 ch 会一直循环，而不关闭则不会一直读 case。**

正确写法应检查 `ok`：

```go
for {
    select {
    case v, ok := <-ch:
        if !ok {
            fmt.Println("channel closed")
            return
        }
        fmt.Println(v)
    default:
        fmt.Println("no data")
        time.Sleep(100 * time.Millisecond)
    }
}
```

## 4. 类比理解

Channel 像一个传送带：

- 有数据：可以立刻拿。
- 没数据但传送带还开着：你要等。
- 传送带关了：你立刻知道“不会再有东西”，所以读取操作也算立即完成。
- 只读 channel：像别人只给你“取货口”，不给你“放货口”。

## 5. 应用举例 / 代码或伪代码

### 5.1 只读 channel 用于限制消费者权限

```go
func producer() <-chan int {
    ch := make(chan int)
    go func() {
        defer close(ch)
        for i := 0; i < 5; i++ {
            ch <- i
        }
    }()
    return ch // 返回只读 channel，外部只能读
}

func main() {
    ch := producer()
    for v := range ch {
        fmt.Println(v)
    }
}
```

### 5.2 发送专用 channel 用于限制生产者权限

```go
func sendOnly(ch chan<- int) {
    ch <- 1
    // <-ch // 编译错误：不能从只写 channel 读取
}
```

### 5.3 select + default 的非阻塞读取

```go
func tryRecv(ch <-chan int) (int, bool) {
    select {
    case v, ok := <-ch:
        if !ok {
            return 0, false
        }
        return v, true
    default:
        return 0, false
    }
}
```

### 5.4 避免关闭 channel 后 select 空转

```go
for ch != nil {
    select {
    case v, ok := <-ch:
        if !ok {
            ch = nil // nil channel 永远不会就绪，可避免重复读关闭 channel
            continue
        }
        fmt.Println(v)
    }
}
```

## 6. 你在讨论中的理解推进

- 起点：你问 channel 为什么需要关闭。
- 推进：你理解 close 的核心不是释放资源，而是告诉接收方“不会再有数据”。
- 进一步：你用切片类比理解只读 channel，抓住了“传参复制的是描述符/视图，底层对象不变”的关键。
- 修正：只读 channel 不能写入，不是因为底层没有写能力，而是当前变量的类型禁止写。
- 深化：你通过 `select + default` 的例子理解了“读就绪”：已关闭 channel 的读取永远立即完成，所以会导致循环持续执行 case。

## 7. 常见误区与排查思路

- **误区 1：channel 必须关闭。** 只有接收方需要结束信号时才需要关闭。
- **误区 2：关闭 channel 是释放内存。** close 是通信语义，不是手动释放内存。
- **误区 3：接收方可以随便 close。** 多发送者场景中接收方关闭很容易导致 send on closed channel。
- **误区 4：关闭 channel 后读取会阻塞。** 实际上关闭 channel 的读取永远就绪。
- **排查：select 循环 CPU 飙高。** 检查是否不断读取已关闭 channel，且没有 `ok` 判断或将 channel 置 nil。

## 8. 关联知识点

- Goroutine 数量、调度与性能边界
- Go Context：取消、超时与值传递
- Go SSE：text event-stream 与流式响应
- sync.Mutex Lock、TryLock 与锁模型

## 9. 复习检查问题

- close(channel) 的真正作用是什么？
- 为什么关闭后的 channel 读取会立即返回？
- `<-chan T` 和 `chan<- T` 分别限制什么？
- `select` 中 default 的执行条件是什么？
- 如何避免关闭 channel 后无限循环读取零值？

## 10. 更细的工程拆解

在真实项目中，channel 常用于 worker pool、超时控制、异步结果汇总、后台任务退出。

### 多 worker 处理任务

```go
func worker(id int, jobs <-chan Job, wg *sync.WaitGroup) {
    defer wg.Done()
    for job := range jobs {
        handle(job)
    }
}

func run(jobsList []Job) {
    jobs := make(chan Job)
    var wg sync.WaitGroup

    for i := 0; i < 5; i++ {
        wg.Add(1)
        go worker(i, jobs, &wg)
    }

    for _, job := range jobsList {
        jobs <- job
    }
    close(jobs) // 告诉 worker 没有更多任务

    wg.Wait()
}
```

### 结合 ctx 退出

```go
func loop(ctx context.Context, ch <-chan Event) {
    for {
        select {
        case <-ctx.Done():
            return
        case e, ok := <-ch:
            if !ok {
                return
            }
            handle(e)
        }
    }
}
```

## 11. 针对 `Channel 关闭、只读通道与 select 读就绪` 的专项排查

- 是否由唯一发送方关闭 channel？
- 消费者是否检查 `ok`？
- `range ch` 是否能等到 close，否则会永久阻塞？
- `select` 中 default 是否导致忙轮询，需要 sleep/ticker 或阻塞等待？
- 是否误把只读 channel 理解为新建了一个 channel？
