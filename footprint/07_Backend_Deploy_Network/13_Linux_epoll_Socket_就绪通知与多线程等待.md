# 07.13 Linux epoll：Socket、就绪通知、实例与多线程模型

> 来源：整理自共享对话《介绍 IO 多路复用》及后续关于 epoll 实例的讨论。本文保留概念修正、内核对象关系、通知链、CPU 调度、多线程例子和实例选型，合并重复解释。Linux 内核结构会随版本调整，字段和伪代码只用于说明主线，不应视为稳定 ABI。

## 1. 总体性概念

epoll 是 Linux 的 **readiness（就绪）通知机制**，不是一个在后台轮询 Socket 的线程，也不是异步 IO 请求的完成队列。

必须先分开三个概念：

| 概念 | 示例 | 负责什么 |
|---|---|---|
| IO 资源 | TCP Socket | 保存连接状态和尚未被应用消费的数据 |
| 就绪事件 | `fd7 + EPOLLIN` | 表示 fd 在某个时刻满足可读条件 |
| IO 操作 | `recv(fd7, ...)` | 真正从 Socket 中消费字节并产生读取结果 |

因此：

- `epoll_wait()` 返回“哪些 fd 可能可以做 IO”，不返回 Socket 数据；
- `recv()` 才真正读取并消费数据；
- ready 事件没有数据所有权，不会为某个线程预留数据；
- 调用 `epoll_wait()` 的线程负责等待事件，但谁最后执行 `recv()` 由用户态线程模型决定；
- 唤醒只把线程从 Sleeping 变为 Runnable，线程仍要等待调度器分配 CPU。

epoll 以 **实例** 为状态边界：

```text
epoll instance
├─ interest list  注册并关注哪些 fd
├─ ready list     哪些注册对象当前就绪
└─ wait queue     哪些线程正在等待这个实例
```

但是“以实例为单位”不表示每个 epoll 实例有一个内核线程在运行。`epoll_create1()` 创建内核实例并返回引用它的 `epfd`；线程调用 `epoll_wait(epfd, ...)` 时，才进入该实例获取事件或睡眠。

一句话模型：**epoll 实例是公告栏，Socket 保存数据，`epoll_wait()` 看公告，`recv()` 才取数据。**

## 2. 原理性解释

### 2.1 Socket 是通信端点，fd 是进程内句柄

Socket 是操作系统维护的网络通信端点。一个 TCP Socket 至少要关联：

- 本地和对端 IP、端口；
- TCP 状态、序列号、窗口和拥塞控制状态；
- 应用尚未读取的数据；
- 等待该 Socket 状态变化的线程或通知机制。

Socket 不是“网络连接这根线”，而是本机对连接一端的抽象和状态容器。

```text
fd = 7
  ↓
进程 fd table
  ↓
struct file
  ↓
struct socket
  ↓
struct sock
```

`7` 不是 Socket 本身，只是当前进程文件描述符表中的索引。关闭 fd 后，同一个数字可以被另一个对象复用；`dup()` 产生的不同 fd 又可能引用同一个 open file description。

理解 Linux 网络栈时可以先采用以下分工：

- `struct socket`：更接近 `socket()`、`bind()`、`listen()`、`accept()`、`send()`、`recv()` 等用户 API；
- `struct sock`：保存协议状态、接收队列、发送状态、等待/通知关系等网络栈数据。

### 2.2 Socket 接收队列保存的是字节数据

把实现细节适当简化后，Socket 的接收数据可以理解为由 `sk_buff`（简称 skb）组成的队列：

```text
sk_receive_queue
      ↓
[skb1] ⇄ [skb2] ⇄ [skb3]
```

`sk_buff` 主要描述报文数据及其元信息；实际字节可以位于线性缓冲区、内存页或页面分片中。TCP 还存在乱序队列、报文合并等机制，因此“一个 skb 就是一条应用消息”并不成立。

```text
网卡收包
  ↓ DMA
内存中的报文数据
  ↓
驱动和网络栈构造/关联 skb
  ↓
Ethernet → IP → TCP
  ↓
找到对应 struct sock
  ↓
把数据纳入该 Socket 的接收状态/队列
```

所谓“写入 Socket buffer”，本质是网络栈把新收到的数据及其描述对象纳入这个 Socket 管理的数据结构。

### 2.3 `recv()` 读取的是 TCP 字节流

```c
char buf[4096];
ssize_t n = recv(fd, buf, sizeof(buf), 0);
```

一次 `recv()` 不对应一个 skb，也不对应一次 `send()`。它可能跨多个 skb 复制，也可能只消费其中一部分：

```text
内核队列： ["Hello "] ["World"] ["!!!"]
recv(..., 8) → 用户缓冲区得到 "Hello Wo"
```

原因是 TCP 向应用提供 **byte stream（字节流）**，而不是消息边界稳定的 packet stream。

### 2.4 状态由修改者主动通知，不靠独立观察者轮询

不存在一个独立观察者持续检查每个 Socket。修改状态的执行路径本身知道状态刚被修改，因此会主动触发通知。

```c
// 概念化伪代码，不对应稳定内核 API
enqueue_received_data(sk, skb);
sk->sk_data_ready(sk);
```

这与条件变量模型相似：生产者执行 `queue.put(data)` 后主动调用 `condition.notify()`。不是另一个线程发现队列变化，而是修改队列的人顺手发出通知。

### 2.5 四种数据结构必须分清

| 数据结构 | 主要内容 | 目的 |
|---|---|---|
| Socket receive queue | skb / 接收数据 | 保存应用还没读取的数据 |
| Socket wait queue | `wait_queue_entry` 等等待项 | 记录谁关心 Socket 状态变化 |
| epoll interest list | `epitem` 注册项，Linux 中以红黑树管理 | 记录该实例长期关注哪些对象和事件 |
| epoll ready list | 已就绪的 `epitem` | 供该实例上的 `epoll_wait()` 获取事件 |

此外，epoll 实例本身还有等待队列，用于保存阻塞在这个实例上的 `epoll_wait()` 调用者。

```text
Socket
├─ receive queue     ← 数据
└─ wait queue        ← 状态变化通知关系
        │
        ▼
      epoll instance
      ├─ interest list / rbr ← 长期注册集合
      ├─ rdllist             ← 当前 ready 集合
      └─ wq                  ← 等待该实例的线程
```

最常见的混淆是把 receive queue、Socket wait queue 和 epoll ready list 都叫成“事件队列”。它们保存的对象和职责完全不同。

### 2.6 `epitem`、`eppoll_entry` 与回调

当用户执行：

```c
epoll_ctl(epfd, EPOLL_CTL_ADD, fd7, &event);
```

内核需要在 `epfd` 指向的实例中记录“我关心 fd7 的哪些事件”。一条注册记录可以抽象为：

```c
struct epitem {
    /* 被关注的 file/fd 身份 */
    /* 用户注册的事件掩码 */
    /* 所属 eventpoll 实例 */
    /* interest list 中的树节点 */
    /* ready list 中的链表节点 */
};
```

同一个 `epitem` 同时有两个身份：

- 在注册集合中回答“这个实例是否注册过该对象”；
- 在 ready list 中表示“这个已注册对象现在可能就绪”。

Socket 等待队列需要挂入等待项，而 `epitem` 表达的是 epoll 注册关系。Linux 使用 `eppoll_entry` 把二者连接起来：

```text
epitem
   ▲
   │ base
eppoll_entry
   │ wait.func = ep_poll_callback
   ▼
Socket wait queue
```

Socket 状态变化并唤醒等待队列时，`ep_poll_callback()` 可以沿这条关系找到对应 `epitem` 和所属 epoll 实例，把注册项放入该实例的 ready list，并唤醒等待这个实例的线程。

### 2.7 interest list 为什么使用红黑树

epoll 要管理大量长期注册项，`EPOLL_CTL_ADD`、`MOD`、`DEL` 都需要高效查找、插入和删除。Linux 使用红黑树实现有界的 `O(log N)` 操作。

注册身份不是单独的 fd 数字，而是 fd number 与 open file description 的组合。原因包括：

```text
close(7) 前：fd7 → file A
close(7) 后：fd7 → file B

dup 后：
fd7 ─┐
     ├─→ 同一个 open file description
fd8 ─┘
```

内核实现中可用类似 `(file *, fd)` 的键建立稳定顺序；`file *` 的地址大小只用于树的排序，没有业务含义。

哈希表也可以被设计成注册集合，因此红黑树不是 epoll 理论上的必然要求。Linux 选择红黑树，是因为它具有稳定的最坏情况复杂度，不依赖哈希冲突质量，也不需要哈希表扩容。

ready 集合的主要需求则是“就绪时放入，等待者顺序取得”，不以随机查找为主，因此使用链表更合适。红黑树负责长期注册管理，等待队列、回调和 ready list 负责实时事件通知。

### 2.8 epoll fd 与 epoll 实例的关系

`epoll_create1()` 会创建一个新的内核 epoll 实例，并返回引用它的文件描述符。需要区分：

- 多个线程使用同一个 `epfd`：操作同一个实例；
- `dup(epfd)` 或 `fork()` 后继承该 open file description：不同 fd/进程仍可能引用同一个实例；
- 分别调用两次 `epoll_create1()`：得到两个相互独立的实例。

一个线程也可以持有多个 epoll fd，但一次阻塞的 `epoll_wait(epfd, ...)` 只等待参数指定的那个实例。

## 3. 机制流程

### 3.1 注册管理路径

```text
epoll_ctl(ADD / MOD / DEL)
  ↓
在指定 epoll 实例中定位或创建 epitem
  ↓
维护该实例的 interest list（Linux 使用红黑树）
  ↓
ADD 时建立目标对象 wait queue 到 epoll 回调的联系
```

另一个线程可以在某线程阻塞于 `epoll_wait()` 时向同一实例注册 fd；新 fd 变为就绪后，可以唤醒正在等待该实例的线程。

### 3.2 数据到达与就绪通知路径

```text
TCP 收到数据
  ↓
Socket 接收状态发生变化
  ↓
修改状态的网络栈代码主动发出 data-ready 通知
  ↓
wake up Socket wait queue
  ↓
ep_poll_callback()
  ↓
找到该 Socket 在某个 epoll 实例中的 epitem
  ↓
把 epitem 放入这个实例的 ready list
  ↓
wake up 这个实例自己的 wait queue
  ↓
阻塞在该实例上的 epoll_wait() 线程变为 Runnable
```

如果同一个目标 fd 被注册到多个 epoll 实例，它会与每个实例分别建立注册和通知关系，因此多个实例都可能收到就绪通知。

### 3.3 `epoll_wait()`、线程睡眠与 CPU 调度

没有 ready 事件时：

```text
线程 T 调用 epoll_wait(epfd)
  ↓
进入 epfd 对应的 epoll 实例
  ↓
检查该实例的 ready list
  ↓
没有事件，把 T 登记为该实例的等待者
  ↓
T：Running → Sleeping
  ↓
调度器让 CPU 运行其他线程
```

CPU 不会替该线程执行一个用户态 `while` 循环去扫描所有 Socket；调用线程真正睡眠。

事件到达后：

```text
fd7 变为 readable
  ↓
epitem(fd7) 进入实例的 ready list
  ↓
T：Sleeping → Runnable
  ↓
等待 Linux Scheduler 选择
  ↓
T 获得 CPU，从 epoll_wait() 内继续运行
  ↓
内核把 ready 事件复制到 events[]
  ↓
epoll_wait() 返回事件数量
```

`wake_up()` 不等于线程立即运行，只是让它重新具备被调度的资格。

### 3.4 `epoll_wait()` 与 `recv()` 返回不同结果

```c
struct epoll_event events[128];
int n = epoll_wait(epfd, events, 128, -1);

for (int i = 0; i < n; ++i) {
    int fd = events[i].data.fd;
    if (events[i].events & EPOLLIN) {
        ssize_t nr = recv(fd, buf, sizeof(buf), 0);
        /* nr / buf 才是读取结果 */
    }
}
```

- `epoll_wait()` 返回：取得多少个就绪事件，并填充 `events[]`；
- `events[i]` 表示：某个 fd 满足哪些就绪条件；
- `recv()` 返回：本次实际读取的字节数，数据写入用户缓冲区。

如果 Socket 中有 `"Hello"`，`epoll_wait()` 只会报告类似 `fd7 + EPOLLIN`，不会返回 `"Hello"`。

ready 也不是承诺或所有权：

```text
Socket fd7 receive queue："Hello"

T1：recv(fd7) → 取走 "Hello"
T2：recv(fd7) → EAGAIN（非阻塞模式）
```

“fd7 ready”只表示在事件产生或检查的那个时刻满足可读条件。调度、其他线程读取、连接关闭等状态变化都可能发生在真正 `recv()` 前。

### 3.5 多个线程共享一个 epoll 实例

```text
                 epoll A
       interest list / ready list
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
       T1        T2         T3
 epoll_wait  epoll_wait  epoll_wait
```

多个线程操作的是同一份内核状态：

- 共享一份 interest list；
- 共享一份 ready list；
- 任一线程通过 `epoll_ctl()` 修改注册集合，其他线程都会受到影响；
- 多个线程共同消费这个实例的 ready 事件流，而不是各自得到一份独立副本；
- 某个线程忙时，其他线程仍可取得事件，任务分配比较动态；
- 同一连接可能先后落到不同线程，连接状态同步和缓存局部性更复杂。

对于以 `EPOLLET` 标记的目标 fd，如果多个线程阻塞在同一个 epoll fd 上，一次就绪变化通常只唤醒其中一个等待者，以减少惊群。

不能把这条规则扩展成“任何模式下永远只有一个线程看到 fd7”。在 LT 模式下，只要可读条件仍然成立，fd 还可能在后续 `epoll_wait()` 中继续被报告；即便使用 ET，也必须避免其他代码路径并发操作同一连接。

共享同一实例的影响：

- 每个目标 fd 通常只注册一次，注册对象和内核内存开销相对少；
- Worker 可以动态竞争 ready 任务，负载分配直接；
- 多线程会竞争共享的 epoll 和连接状态；
- 同一个连接可能被不同 Worker 处理，CPU Cache 局部性较弱；
- 一般要配合连接状态机、锁、任务归属或 `EPOLLONESHOT` 保证同一连接不会被并发处理。

### 3.6 每个线程使用不同 epoll 实例并划分 fd

```text
Thread 1                     Thread 2
   │                            │
epoll A                      epoll B
├─ fd1                       ├─ fd2
├─ fd4                       ├─ fd5
└─ fd7                       └─ fd8
```

epoll A 和 B 分别拥有独立的 interest list、ready list 和 wait queue。如果 fd7 只注册在 epoll A 中，它的事件通常只交给 Thread 1，形成明确的连接归属：

```text
fd7 → epoll A → Thread 1
fd8 → epoll B → Thread 2
```

这种模型的影响：

- 同一连接通常只由固定 Event Loop 处理，协议状态更容易维护；
- 不需要围绕每个连接频繁加锁；
- epoll 实例之间没有共享 ready list 的竞争，CPU Cache 局部性更好；
- 每个实例和每条注册记录仍会占用内核资源；
- 可能发生负载不均，例如 Thread 1 的连接很忙而 Thread 2 很空闲；
- 连接迁移需要从旧实例移除，再交给新线程注册，线程间交接更复杂；
- 每个 Event Loop 还要独立维护任务队列、定时器和连接状态。

这种“一线程 + 一 epoll 实例 + 一组归属连接”的模型常用于多 Reactor 服务器。

### 3.7 同一个目标 fd 注册到多个 epoll 实例

```text
               Socket fd7
                /       \
               /         \
          epoll A       epoll B
             │             │
            T1            T2
```

Linux 允许同一个目标 fd 注册到不同 epoll 实例。默认情况下，fd7 就绪后，两个实例都会收到事件。但被复制的是就绪通知，不是 Socket 数据：

```text
fd7 receive queue = "Hello"

epoll A → fd7 readable → T1
epoll B → fd7 readable → T2

T1：recv(fd7) → "Hello"
T2：recv(fd7) → EAGAIN
```

其影响包括：

- 每个 epoll 实例都有一条独立注册记录和 ready 状态；
- 每次注册都会增加内核对象、等待关系和内存开销；
- 默认可能产生重复通知和惊群；
- 多线程仍竞争同一份 Socket 数据；
- 对普通已连接 Socket，通常不应这样设计。

Linux 4.5 起可以在 `EPOLL_CTL_ADD` 时使用 `EPOLLEXCLUSIVE`。当多个 epoll 实例以该模式注册同一个目标 fd 时，唤醒事件会交给一个或多个 exclusive 实例，而不是默认交给全部实例，用于减少某些场景的惊群。

需要注意：

- `EPOLLEXCLUSIVE` 只可在 `EPOLL_CTL_ADD` 时设置；
- 可与它组合的事件标志受限制；
- 已以 `EPOLLEXCLUSIVE` 注册的 `(epfd, fd)` 不能再用普通 `EPOLL_CTL_MOD` 修改；
- 如果同一目标 fd 同时存在 exclusive 和非 exclusive 注册，所有非 exclusive 实例仍会收到事件，并且至少一个 exclusive 实例也会收到；
- 它减少无效唤醒，但不会复制 Socket 数据，也不会自动解决用户态连接状态并发。

### 3.8 三种 epoll 实例模型对比

| 模型 | interest/ready 状态 | 事件交付 | 连接状态 | 主要影响 |
|---|---|---|---|---|
| 多线程共享一个 epoll | 全部共享 | Worker 共同消费一条 ready 事件流 | 需要额外保证同一连接不被并发处理 | 动态负载分配直接，但共享竞争和状态同步复杂 |
| 每线程一个 epoll，fd 分区 | 每个实例独立 | fd 通常只交给所属 Event Loop | 连接归属清晰 | 局部性好，但可能负载不均、迁移复杂 |
| 同一 fd 注册到多个 epoll | 每个实例都有注册和 ready 状态 | 默认多个实例都收到通知 | 仍竞争同一份 Socket 数据 | 重复通知、惊群和额外内核开销 |

选择的关键不是“epoll 数量越多越快”，而是连接所有权、负载均衡、状态同步和缓存局部性的权衡。

### 3.9 多线程等待同一 IO 资源的实际形态

#### 多线程 `accept()` 同一个监听 Socket

```c
void *worker(void *arg) {
    for (;;) {
        int client_fd = accept(listen_fd, NULL, NULL);
        handle(client_fd);
    }
}
```

同一进程的线程共享 fd 表，多个 Worker 可以同时阻塞在同一个 `listen_fd` 上：

```text
                   listen_fd
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
      T1              T2              T3
   accept()         accept()         accept()
```

三次握手完成后，新连接进入监听 Socket 的 accept queue。某个线程取走一个完整新连接，获得新的 `client_fd`。

这种竞争比多个线程读取同一 TCP 连接合理，因为 accept queue 中的 Connection A、B、C 天然可以独立分配；同一连接里的 TCP 字节流不适合被多个线程随意切分消费。

#### 多线程 `epoll_wait()` 同一个 epoll 实例

线程直接等待的是同一个 epoll 实例，并共同消费该实例的 ready 事件。监听 fd ready 后，某个 Worker 可以醒来执行 `accept()`。这对应 3.5 的共享实例模型。

#### 多线程 `recv()` 同一个连接 Socket

操作系统允许两个线程阻塞读取同一个 TCP Socket，但它们竞争消费同一份字节流：

```text
Socket 字节流：ABCDEFGHIJ

一种可能结果：
T1 → ABCDE
T2 → FGHIJ
```

结果依赖调度时序，容易破坏应用协议解析，因此工程上通常避免这样设计。

#### 监听 Socket 的多实例分发

如果希望每个 Event Loop 使用独立 epoll，可以选择：

- 一个 acceptor 接收连接，再把 `client_fd` 分发给目标 Event Loop 注册；
- 多个 epoll 实例注册同一个监听 fd，并根据需要使用 `EPOLLEXCLUSIVE` 减少惊群；
- 使用 `SO_REUSEPORT`，让每个 Worker 拥有自己的监听 Socket 和 epoll 实例，由内核在监听 Socket 之间分配新连接。

## 4. 类比理解

把 epoll 实例理解成公告栏：

```text
Socket fd7、fd8、fd9
       │ 状态变化
       ▼
┌─────────────────────┐
│ epoll 公告栏        │
│ fd7 readable        │
│ fd9 writable        │
└─────────────────────┘
       │ epoll_wait
       ▼
     Thread
```

公告栏只保存“谁可能可以读写”，不保存 `"Hello"` 数据，也不记录“这个 Socket 原来属于哪个线程”。

不同实例模型可以类比为：

- 多线程共享一个 epoll：多个工作人员共同看同一块公告栏、领取同一批任务；
- 每线程一个 epoll：每人有自己的公告栏，连接先被分区，再只投递到所属公告栏；
- 同一 fd 注册多个 epoll：同一条提醒复制到多块公告栏，但仓库里的货物仍只有一份。

所以多个线程可以看到同一个“可读事实”，但不会各自得到一份相同数据。`epoll_wait()` 是看公告，`recv()` 才是去仓库取货。

## 5. 应用举例 / 代码或伪代码

### 5.1 常见服务器线程模型

#### 单线程 Reactor

```text
Event Loop
  ├─ epoll_wait()
  ├─ recv(fd)
  ├─ 处理事件
  └─ 再次 epoll_wait()
```

连接归属简单，但耗时业务会阻塞整个循环。

#### Event Loop 负责 IO，Worker 负责业务

```text
epoll_wait
  ↓
Event Loop 执行 recv / 协议解析
  ↓
业务任务队列
  ↓
Worker Pool 执行业务计算、数据库访问等
```

这种模型不让多个 Worker 同时读取同一连接。每个 Event Loop 可以拥有独立 epoll 实例和一组归属连接。

#### 多个 Worker 共享一个 epoll 实例

```text
                     epoll A
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
     Worker1        Worker2        Worker3
```

Worker 共同取得 ready 事件。需要用连接状态机、锁或 `EPOLLONESHOT` 防止同一连接被并发处理。

#### Event Loop 分发 ready fd，Worker 执行 IO

```text
epoll_wait → fd7 ready → 任务队列 → Worker3 → recv(fd7)
```

必须保证同一个 fd 同一时刻只有一个 Worker 处理。常见手段包括连接归属、每个 fd 固定到一个 Event Loop、锁和 `EPOLLONESHOT`。

### 5.2 `EPOLLONESHOT` 的处理边界

```text
fd7 ready
  ↓
一个 Worker 得到事件
  ↓
fd7 在该 epoll 实例中暂时 disabled
  ↓
Worker 独占处理并读到 EAGAIN
  ↓
epoll_ctl(MOD) rearm
```

`EPOLLONESHOT` 解决的是事件交付后的串行处理问题。它不会自动加用户态锁，也不会阻止代码通过其他 fd 或其他 epoll 实例访问同一个 open file description。

### 5.3 最小非阻塞 epoll 循环

下面代码只展示关键边界，不含 accept、错误分类、半关闭、写缓冲、背压和连接生命周期管理：

```c
int epfd = epoll_create1(EPOLL_CLOEXEC);

// fd 应先设为 O_NONBLOCK
struct epoll_event ev = {
    .events = EPOLLIN | EPOLLET,
    .data.fd = fd,
};
epoll_ctl(epfd, EPOLL_CTL_ADD, fd, &ev);

struct epoll_event events[128];
char buf[4096];

for (;;) {
    int n = epoll_wait(epfd, events, 128, -1);
    if (n < 0) {
        if (errno == EINTR) continue;
        /* 处理致命错误 */
        break;
    }

    for (int i = 0; i < n; ++i) {
        int ready_fd = events[i].data.fd;

        if (events[i].events & (EPOLLERR | EPOLLHUP)) {
            /* 查询/处理连接错误和关闭 */
        }

        if (events[i].events & EPOLLIN) {
            for (;;) {
                ssize_t nr = recv(ready_fd, buf, sizeof(buf), 0);
                if (nr > 0) {
                    /* 消费 nr 字节 */
                    continue;
                }
                if (nr == 0) {
                    /* 对端有序关闭 */
                    break;
                }
                if (errno == EINTR) continue;
                if (errno == EAGAIN || errno == EWOULDBLOCK) break;
                /* 其他读取错误 */
                break;
            }
        }
    }
}
```

在 Edge-Triggered 模式下，处理者通常要一直读取到 `EAGAIN`，否则剩余数据可能不会再次产生预期的边沿通知。

### 5.4 工程选型建议

一般可以按下面的顺序选择：

1. 希望连接状态简单、减少锁和提高 Cache 局部性：优先“一 Event Loop 一 epoll 实例，连接分区”。
2. 希望多个 Worker 动态竞争 ready 任务：可以共享一个 epoll 实例，但必须明确单连接串行处理机制。
3. 同一个已连接 Socket 注册到多个实例：通常避免，因为通知会重复，数据不会复制。
4. 多 Worker 接收新连接：可以使用独立 acceptor 分发、`EPOLLEXCLUSIVE` 或 `SO_REUSEPORT`，三者解决问题的层级不同。

生产实现还要处理：

- 写就绪和用户态发送缓冲；
- 背压与内存上限；
- fd 关闭、复用及过期事件；
- ET/LT 选择；
- 多线程连接归属和跨线程任务投递；
- 定时器、超时、取消和资源回收；
- epoll 实例、注册 watch 数量和内核内存限制。

## 6. 你在讨论中的理解推进

这组讨论依次补齐了以下拼图：

1. **线程与 epoll**：epoll 不是监听线程；调用 `epoll_wait()` 的线程在无事件时睡眠。
2. **CPU 调度**：IO ready 后线程只是进入 Runnable 队列，不会立刻执行。
3. **事件与数据**：`epoll_wait()` 返回就绪事实，`recv()` 才产生并消费 IO 结果。
4. **数据归属**：多个线程可能看到同一就绪事实，但 Socket 数据只有一份，先读取者先消费。
5. **实际并发**：多线程竞争监听 Socket 的 `accept()` 合理；随意竞争同一连接的 `recv()` 通常不合理。
6. **实例边界**：每个 epoll 实例独立维护注册集合、ready 集合和等待线程；实例本身不会主动运行。
7. **线程模型**：共享一个实例意味着共同消费一条 ready 事件流；不同实例并划分 fd 意味着建立连接归属。
8. **重复监听**：同一 fd 注册到多个实例会复制通知而不会复制数据，可能产生惊群和竞争。
9. **工程约束**：连接归属、`EPOLLONESHOT`、`EPOLLEXCLUSIVE`、独立 acceptor 和 `SO_REUSEPORT` 都是在控制不同层面的并发分发。

复习时可以用两句话自检：

> 多个线程可能看到同一个 IO 就绪事实，但不会各自得到一份相同的 IO 结果。

> 共享同一个 epoll 是共同消费一条就绪事件流；使用不同 epoll 并划分 fd，是每个线程维护自己的事件流和连接所有权。

## 7. 常见误区与排查思路

### 7.1 常见误区

- **epoll 有一个内核监听线程。** 没有；网络栈在修改 Socket 状态的路径上触发通知，`epoll_wait()` 的调用线程负责睡眠和取事件。
- **epoll 实例会自己运行。** 实例只保存状态，必须由线程调用 `epoll_wait()` 才会等待和取得事件。
- **`epoll_wait()` 返回网络数据。** 它返回就绪事件，数据由后续 `recv()` 获取。
- **曾经调用 `recv()` 的线程拥有该 Socket。** epoll 不记录最初是谁发起 IO，连接归属是用户态架构约束。
- **ready 事件会为线程保留数据。** 不会；其他线程可能先消费数据，非阻塞 IO 必须处理 `EAGAIN`。
- **多个线程共享一个 epoll 会各自得到一份事件副本。** 它们共享 ready 状态；ET 下一个就绪变化通常只唤醒一个 waiter，LT 下持续就绪又可能被后续调用继续观察。
- **不同 epoll 实例监听同一 Socket，就有多份 Socket 数据。** 只有通知被分别投递，底层数据仍然只有一份。
- **epoll 通过红黑树扫描 ready fd。** 红黑树主要维护 interest list；实时通知依靠等待队列、回调和 ready list。
- **一次 `recv()` 对应一个网络包或一次 `send()`。** TCP 是字节流，读取边界不等于 skb、IP 包或发送调用边界。
- **多个线程等待同一 fd 一定不合理。** 多线程竞争监听 fd 的 `accept()` 是经典分发方式；竞争读取同一已连接 Socket 则通常难以维护协议状态。
- **epoll 实例越多性能越高。** 多实例减少共享竞争并改善归属，但也带来负载不均、连接迁移和独立状态管理成本。
- **`EPOLLONESHOT` 或 `EPOLLEXCLUSIVE` 自动解决所有并发问题。** 前者控制单实例事件 rearm，后者减少多实例等待同一目标 fd 的惊群；二者都不能替代完整的用户态连接状态机。

### 7.2 排查顺序

```text
确认目标 fd 是否非阻塞
→ 确认它注册在哪个 epoll 实例、事件掩码是什么
→ 确认是否被重复注册到多个实例
→ 确认等待线程是共享实例还是每线程独立实例
→ 确认 ET 是否读/写到 EAGAIN
→ 确认 ONESHOT 是否正确 rearm
→ 确认同一连接是否可能被多个线程并发处理
→ 检查 fd 关闭、dup、复用和过期事件
→ 检查负载分区、跨线程投递和背压
```

## 8. 关联知识点

- [Redis IO Threads 与事件循环](../05_Database_Redis/11_Redis_IO_Threads_与事件循环.md)：事件循环与 IO 线程的分工。
- [HTTP Streaming、SSE、WebSocket 与 gRPC Streaming](07_HTTP_Streaming、SSE、WebSocket_与_gRPC_Streaming.md)：上层流式协议与底层 TCP 字节流。
- [Go 并发模型：goroutine、channel、select 与 Context](../04_Go/07_Go_并发模型：goroutine、channel、select_与_Context.md)：调度、事件等待和任务归属。

## 9. 复习检查问题

- epoll 实例保存哪些状态？为什么说它不会自己运行？
- `epoll_wait()` 与 `recv()` 的返回结果有什么区别？
- Socket receive queue、Socket wait queue、interest list 和 ready list 分别保存什么？
- 数据到达后，`ep_poll_callback()` 如何把 Socket 状态变化传递到某个 epoll 实例？
- 为什么 interest list 使用红黑树，而 ready 集合更适合链表？
- 一个 epoll 实例被多个线程等待时，它们共享什么、竞争什么？
- 每线程一个 epoll 且 fd 分区有什么优势和代价？
- 同一目标 fd 注册到多个 epoll 实例后，通知和数据分别会发生什么？
- `EPOLLONESHOT` 与 `EPOLLEXCLUSIVE` 分别解决哪一层问题？
- 为什么多个线程竞争 `accept()` 比竞争同一连接的 `recv()` 更合理？
- ET 模式为什么通常要读写到 `EAGAIN`？
- 独立 acceptor、`EPOLLEXCLUSIVE` 和 `SO_REUSEPORT` 的分发位置有什么不同？

## 10. 参考资料

- [共享对话：介绍 IO 多路复用](https://chatgpt.com/share/6a89bf2e-5db8-83ec-abfc-e955dede66bb)
- [epoll(7) — Linux manual page](https://man7.org/linux/man-pages/man7/epoll.7.html)
- [epoll_create(2) — Linux manual page](https://man7.org/linux/man-pages/man2/epoll_create.2.html)
- [epoll_ctl(2) — Linux manual page](https://man7.org/linux/man-pages/man2/epoll_ctl.2.html)
- [epoll_wait(2) — Linux manual page](https://man7.org/linux/man-pages/man2/epoll_wait.2.html)
- [Linux kernel: fs/eventpoll.c](https://github.com/torvalds/linux/blob/master/fs/eventpoll.c)
- [Linux kernel: include/net/sock.h](https://github.com/torvalds/linux/blob/master/include/net/sock.h)
- [Linux kernel: include/linux/skbuff.h](https://github.com/torvalds/linux/blob/master/include/linux/skbuff.h)
