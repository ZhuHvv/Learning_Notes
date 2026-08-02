# 04.11 sync.Mutex：Lock、TryLock 与锁模型

> 所属主线：Go 并发  
> 难度：进阶  
> 前置知识：Goroutine、Channel 与共享状态  
> 后续知识：运行时内存、跨进程并发控制

## 1. 总体性概念

`sync.Mutex` 是 Go 中最常见的互斥锁，用于保护共享数据在同一时刻只被一个 goroutine 访问临界区。本篇同时区分 `Lock()`、`TryLock()`、悲观锁与乐观锁。

核心结论：

- `Lock()`：拿不到锁就阻塞等待，适合绝大多数互斥场景。
- `TryLock()`：尝试拿锁，拿不到立即返回 `false`，适合少数“不值得等待”的场景。
- 悲观锁：先锁住再操作，默认冲突会发生。
- 乐观锁：先不锁，提交时检查版本/CAS，默认冲突较少。

## 2. 原理性解释

### 2.1 Mutex 解决什么问题

多个 goroutine 同时读写共享变量可能出现数据竞争：

```go
counter++
```

这行代码不是原子操作，它大致包含：

```text
读取 counter
  ↓
加 1
  ↓
写回 counter
```

如果两个 goroutine 同时执行，就可能丢失更新。`Mutex` 的作用是在临界区外加一把锁：

```go
mu.Lock()
counter++
mu.Unlock()
```

### 2.2 Lock 的语义

`Lock()` 的含义是：

- 如果锁空闲，当前 goroutine 获取锁并继续执行。
- 如果锁已被持有，当前 goroutine 阻塞等待。
- 等锁释放后，runtime 唤醒等待者之一。

它适合需要强一致地修改共享状态的场景。

### 2.3 TryLock 的语义

`TryLock()` 的含义是：

- 如果锁空闲，获取锁并返回 `true`。
- 如果锁已被持有，不阻塞，立即返回 `false`。

它不是用来替代 `Lock()` 的常规工具。滥用 `TryLock()` 容易造成：

- 忙等：循环 TryLock 消耗 CPU。
- 逻辑丢失：拿不到锁就跳过任务，可能漏处理。
- 复杂分支：系统状态变得难以推理。

### 2.4 悲观锁与乐观锁

悲观锁认为冲突很常见，所以先加锁再操作：

```text
加锁 → 读取 → 修改 → 写回 → 解锁
```

乐观锁认为冲突较少，所以先读取和计算，提交时检查数据有没有被别人改过：

```text
读取值和版本号 → 计算新值 → 提交时检查版本号 → 成功写入或重试
```

Go 中的 `sync.Mutex` 是典型悲观锁。`atomic.CompareAndSwap` 或数据库 `version` 字段更新是典型乐观锁思想。

## 3. 机制流程

### 3.1 Lock 保护临界区

```text
goroutine A 调用 Lock
  ↓
进入临界区修改共享数据
  ↓
goroutine B 调用 Lock，发现锁被占用
  ↓
B 阻塞等待
  ↓
A Unlock
  ↓
B 获得锁继续执行
```

### 3.2 TryLock 非阻塞尝试

```text
调用 TryLock
  ├─ 成功：进入临界区，最后 Unlock
  └─ 失败：立即返回 false，执行降级逻辑
```

### 3.3 乐观锁 CAS 流程

```text
读取旧值 old
  ↓
根据 old 计算 new
  ↓
CAS(old, new)
  ├─ 成功：说明期间没人改过
  └─ 失败：说明发生冲突，重新读取或返回失败
```

## 4. 类比理解

- 悲观锁像进房间前先锁门，别人只能在门外等。
- 乐观锁像多人编辑文档，提交时检查版本是否还是你打开时的版本；如果版本变了，就让你重新合并。
- `TryLock` 像试着推门：门开就进去，门锁着就不等，直接做别的事。

## 5. 应用举例 / 代码或伪代码

### 5.1 Mutex 的标准用法

```go
type Counter struct {
    mu sync.Mutex
    n  int
}

func (c *Counter) Inc() {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.n++
}

func (c *Counter) Value() int {
    c.mu.Lock()
    defer c.mu.Unlock()
    return c.n
}
```

### 5.2 TryLock 的适合场景：避免重复启动后台任务

```go
type Refresher struct {
    mu sync.Mutex
}

func (r *Refresher) Refresh() {
    if !r.mu.TryLock() {
        // 已经有刷新任务在运行，本次直接跳过
        return
    }
    defer r.mu.Unlock()

    doRefresh()
}
```

这个场景中，跳过一次刷新是可以接受的，所以 `TryLock` 合理。

### 5.3 错误示例：忙等 TryLock

```go
for !mu.TryLock() {
    // 空循环会浪费 CPU，不推荐
}
defer mu.Unlock()
```

如果必须等待，直接使用 `Lock()` 更合适。

### 5.4 乐观锁：atomic CAS

```go
var count int64

func IncCAS() {
    for {
        old := atomic.LoadInt64(&count)
        newVal := old + 1
        if atomic.CompareAndSwapInt64(&count, old, newVal) {
            return
        }
        // CAS 失败说明中间被别人改过，重新读取再试
    }
}
```

### 5.5 数据库乐观锁：version 字段

```sql
UPDATE product
SET stock = stock - 1,
    version = version + 1
WHERE id = ?
  AND stock > 0
  AND version = ?;
```

如果影响行数为 0，说明版本已变化或库存不足，需要重试或返回失败。

## 6. 常见误区与排查思路

- **误区 1：TryLock 比 Lock 更高级。** TryLock 只是非阻塞语义，适用场景更窄。
- **误区 2：加了锁就一定安全。** 必须保证所有访问共享变量的路径都使用同一把锁。
- **误区 3：defer Unlock 会天然让锁变慢。** `defer` 的性能通常不是主要问题；真正要检查的是函数是否在不必要的工作完成后才返回，导致临界区过大。需要提前释放锁时，应缩小受锁保护的代码块。
- **误区 4：乐观锁不需要处理失败。** 乐观锁的核心就是检测冲突后的重试或失败返回。
- **排查：死锁。** 检查是否 Lock 后某条路径没有 Unlock，或多把锁顺序不一致。

## 7. 关联知识点

- Goroutine：数量、调度与性能边界
- Channel：关闭、方向限制与 select 读就绪
- Go Context：请求取消、超时与值传递
- B+树索引、复合索引与最左前缀
- Redis 限流与 Lua 原子操作

## 8. 复习检查问题

- `Lock()` 和 `TryLock()` 的行为差异是什么？
- 什么场景适合 TryLock？什么场景不适合？
- 悲观锁和乐观锁分别假设什么？
- CAS 为什么可能失败？失败后应该怎么处理？

## 9. 更细的工程拆解

### 9.1 互斥锁保护 map

Go 的普通 map 并发写不安全：

```go
type SafeMap struct {
    mu sync.RWMutex
    m  map[string]string
}

func (s *SafeMap) Get(k string) (string, bool) {
    s.mu.RLock()
    defer s.mu.RUnlock()
    v, ok := s.m[k]
    return v, ok
}

func (s *SafeMap) Set(k, v string) {
    s.mu.Lock()
    defer s.mu.Unlock()
    s.m[k] = v
}
```

读多写少时可以用 `RWMutex`，允许多个读者同时进入，但写者仍然互斥。

### 9.2 与 Redis Lua 的类比

Go 进程内共享变量可以用 Mutex；跨进程共享资源不能只靠本地 Mutex。比如多个服务实例同时扣库存，需要数据库事务、Redis Lua、分布式锁或消息队列串行化。

```lua
-- Redis Lua：检查库存并扣减，保证脚本内原子执行
local stock = tonumber(redis.call('GET', KEYS[1]))
if stock <= 0 then
  return 0
end
redis.call('DECR', KEYS[1])
return 1
```

## 10. 专项排查

- 临界区是否过大，导致锁竞争严重？
- 是否存在 Lock 后提前 return 没有 Unlock？
- 是否所有访问共享状态的路径都受同一把锁保护？
- 是否误用 TryLock 导致任务被静默跳过？
- 是否把进程内锁误当成分布式锁使用？

## 11. 面试与项目表达补充

在面试或项目复盘中，可以这样表达这个知识点：

```text
我会先判断共享资源的范围：如果只是单进程内的 map、计数器或缓存结构，优先使用 Mutex/RWMutex 或 atomic；如果资源跨多个服务实例，就不能只靠本地锁，而要考虑数据库事务、Redis Lua、分布式锁或消息队列串行化。
Lock 适合必须等待一致结果的场景；TryLock 适合拿不到锁也可以跳过或降级的场景。乐观锁适合冲突少、重试成本可控的场景；悲观锁适合冲突多、必须强互斥的场景。
```

### 选择锁模型的判断表

| 场景 | 推荐方式 | 原因 |
|---|---|---|
| 单进程内共享 map | `sync.RWMutex` | 读多写少，保护内存数据结构 |
| 单进程计数器 | `atomic` 或 `Mutex` | 简单数值可用 CAS，复杂状态用锁 |
| 请求内避免重复刷新 | `TryLock` | 刷新中则跳过，避免阻塞请求 |
| 数据库库存扣减 | 事务 / version 乐观锁 | 多实例共享数据，本地锁无效 |
| Redis 计数扣减 | Lua 原子脚本 | 多命令合并为服务端原子执行 |

这也解释了为什么并发控制不是一个单独 API 问题，而是要结合“共享资源在哪里、冲突概率多高、失败后能否重试、是否跨进程”一起判断。
