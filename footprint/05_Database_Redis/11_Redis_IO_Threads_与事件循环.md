# 05.11 Redis IO Threads 与事件循环

Redis 的网络处理以 **非阻塞 Socket、I/O 多路复用和 Reactor 事件分发**为基础。`ae` 是 Redis 自己的事件库：等待连接就绪、调用已注册的处理函数，并调度到期的时间事件。普通核心命令主要由主线程串行执行，网络处理的线程分工则取决于版本和配置。

本文先以普通 TCP 连接、未启用多线程 I/O 的经典路径解释机制，再以 Redis 7.2 和 8.0 对比线程分工。通用 I/O 原理见 [IO 模型与多路复用](../07_Backend_Deploy_Network/14_IO模型与多路复用：select、poll、epoll.md)，这里集中说明 Redis 如何组织这些机制。

## 1. Reactor 与各层职责

Reactor 是一种事件驱动的 I/O 处理模型：**等待就绪通知，再分发给处理函数执行实际操作**。它本身不限定线程数量。

| 层次 | 职责 | Redis 中的对应部分 |
|---|---|---|
| 非阻塞 Socket | 暂时不能读写时及时返回，不一直等待某个连接 | 客户端连接；读写仍需处理 `EAGAIN`、EOF 和错误 |
| I/O 多路复用 | 集中等待多个 fd 的就绪状态 | Linux 通常用 `epoll`，其他平台可用 `kqueue` 等 |
| 事件循环与分发 | 维护事件注册关系，取得就绪结果后调用回调 | `ae` 事件库 |
| 事件处理函数 | 接收连接、读取请求、推进命令处理、发送响应 | 连接处理、读处理、写处理等回调 |

`epoll` 是 `ae` 使用的底层机制，不负责替 Redis 读取完整请求或执行命令。非阻塞 Socket 也不意味着线程永不休眠：没有立即可做的工作时，线程可以在 `epoll_wait` 中统一等待网络事件或超时。

常见 Reactor 组织方式包括单 Reactor 单线程、单 Reactor 加业务线程池，以及主 Reactor 接收连接、多个子 Reactor 处理连接 I/O。**经典 Redis 属于单 Reactor 单线程；Redis 6/7 的 I/O 工作线程不能直接等同于各自拥有事件循环的子 Reactor。**

实现入口：[Redis 7.2 ae.c](https://github.com/redis/redis/blob/7.2/src/ae.c)、[ae_epoll.c](https://github.com/redis/redis/blob/7.2/src/ae_epoll.c)。

## 2. ae 事件循环怎样工作

### 2.1 先注册事件和回调

`ae` 不是额外的线程，而是一套由线程执行的事件处理代码及其状态。经典模型由主线程运行 `aeMain`，不断调用 `aeProcessEvents`。

注册文件事件时，要指定 fd、关注的事件和处理函数。例如：

| 对象 | 事件 | 后续处理 |
|---|---|---|
| 监听 Socket | `AE_READABLE` | 接收已经可以被 `accept` 的连接 |
| 客户端 Socket | `AE_READABLE` | 读取数据、处理输入缓冲区 |
| 仍有响应待发送的 Socket | `AE_WRITABLE` | 继续写出剩余响应 |
| 定时任务 | 到达截止时间 | 执行维护回调，决定是否再次调度 |

这里的“文件事件”按 fd 抽象命名，不是磁盘文件变化通知；网络关闭和错误也可能映射为读写事件，需要处理函数通过实际操作识别，不存在一个通用的 `AE_CLOSE` 事件。

### 2.2 注册表与就绪表各存什么

以 Redis 7.2 的 `aeEventLoop` 为例：

| 成员 | 内容 |
|---|---|
| `events[fd]` | 已注册的事件类型、读写回调及上下文；不是“未就绪连接表” |
| `fired[i]` | 本轮多路复用返回的就绪 fd 和事件类型；不是请求数据或命令队列 |
| `timeEventHead` | 时间事件链表 |
| `apidata` | epoll 等平台实现的状态 |
| `beforesleep`、`aftersleep` | 等待前后的处理钩子 |

例如本轮 `fired` 包含 A 可读、B 可写，事件循环就从 `events[A]` 和 `events[B]` 中取得相应回调并依次调用。`events` 保存注册关系，下一轮继续使用；`fired` 表示本轮报告的结果。

字段定义见 [Redis 7.2 ae.h](https://github.com/redis/redis/blob/7.2/src/ae.h)。

### 2.3 一轮循环的主要顺序

以下省略异常和特殊标志分支，展示 Redis 7.2 主事件循环的常规路径：

```text
aeMain 持续调用 aeProcessEvents
  ↓
beforeSleep：处理等待前的工作，例如待发送响应和待处理 I/O
  ↓
根据最近的时间事件计算等待上限；有立即工作时可以不等待
  ↓
aeApiPoll → epoll_wait：取得就绪事件，填入 fired
  ↓
afterSleep
  ↓
遍历 fired，根据 events[fd] 调用相应读写回调
  ↓
processTimeEvents：处理已经到期的时间事件
  ↓
下一轮
```

事件循环在文件事件分发部分直接调用回调，不应把概念性的“处理文件事件”写成源码中一定存在的 `processFileEvents()`。Redis 6/7 的批量 I/O 处理由 `beforeSleep` 等实际路径组织，也不是统一在时间事件后调用一个 `processIOThreads()`。

同一 fd 同时可读、可写时，Redis 7.2 通常先处理读事件，但 `AE_BARRIER` 可改变该顺序。不同连接之间也不保证严格按请求发出或到达的时间执行。

时间事件回调返回 `AE_NOMORE` 表示不再调度；返回延迟毫秒数则安排下一次运行。Redis 7.2 用单调时钟字段 `when` 记录到期时间，不能混用旧版 `when_sec`、`when_ms` 结构。

`serverCron` 是主要的周期性维护入口，模块也可使用定时器。基础 `hz` 默认是 10，但动态频率与实际执行负载会影响调度，不能理解为严格每 100 ms 执行一次。长回调会延迟后续网络事件和时间事件。

依据：[ae.c](https://github.com/redis/redis/blob/7.2/src/ae.c)、[server.c](https://github.com/redis/redis/blob/7.2/src/server.c)、[Redis 7.2 配置](https://github.com/redis/redis/blob/7.2/redis.conf)。

## 3. 一次请求的完整路径

下面以 `GET user:1` 为例。监听 Socket 接收新连接，客户端 Socket 承担连接建立后的数据交换；两者不要混为一谈。

1. **接收连接**：监听 Socket 就绪，Redis 调用 `accept` 取得客户端 Socket，设置非阻塞模式、初始化客户端状态，并注册读处理。
2. **读取请求**：客户端 Socket 可读后，读处理函数通过连接层读取字节，放入客户端输入缓冲区 `querybuf`。
3. **解析命令**：按 RESP 协议识别命令及参数。数据不完整时保留缓冲区和解析状态，继续处理其他工作；完整命令才进入执行流程。
4. **执行命令**：经过必要检查，主线程执行查询，生成响应并放入客户端输出缓冲区。
5. **尝试发送**：Redis 在待写处理路径中尝试发送响应，不必先注册可写事件才能进行第一次写入。
6. **处理剩余响应**：若本轮未写完，保存剩余数据和发送进度，监听可写事件后继续发送；全部写完后取消不再需要的写监听。

连接初始化见[客户端管理](https://redis.io/docs/latest/develop/reference/clients/)；读写处理可沿 Redis 7.2 的 `readQueryFromClient`、`processInputBuffer`、`handleClientsWithPendingWrites`、`writeToClient`、`sendReplyToClient` 阅读 [networking.c](https://github.com/redis/redis/blob/7.2/src/networking.c)。

### 3.1 区分两层缓冲区

```text
请求：客户端 → 内核 Socket 接收缓冲区 → Redis 输入缓冲区 → 协议解析
响应：命令结果 → Redis 输出缓冲区 → 内核 Socket 发送缓冲区 → 客户端
```

- **可读不等于完整请求到齐**：TCP 是字节流，一次读取可能只有半条命令，也可能包含多条命令。RESP 提供长度与分隔信息来确定边界；EOF、错误也需要处理。
- **可写不等于客户端已经读取**：通常表示本机发送缓冲区有可用空间；写调用仍可能短写或返回错误。
- **写出成功不等于客户端业务处理成功**：通常只是本机内核接受了相应数据，之后还要经过网络传输和客户端读取。

请求边界见 [RESP 规范](https://redis.io/docs/latest/develop/reference/protocol-spec/)，系统调用与就绪语义见 [IO 模型与多路复用](../07_Backend_Deploy_Network/14_IO模型与多路复用：select、poll、epoll.md)。

### 3.2 为什么按需监听可写

Redis 7.2 的 Linux epoll 适配没有设置 `EPOLLET`，采用水平触发 LT：只要就绪条件持续满足，后续等待仍可报告该事件。因此，没有响应待发送时不应持续监听可写，避免反复收到没有实际工作可做的通知。

`epoll_wait` 从内核就绪集合取得事件，不是每次遍历保存注册项的红黑树查找就绪连接。Redis 再把返回结果转换为 `fired` 中的 fd 和 mask。底层机制见 [Linux epoll](../07_Backend_Deploy_Network/13_Linux_epoll_Socket_就绪通知与多线程等待.md)，Redis 的注册标志见 [ae_epoll.c](https://github.com/redis/redis/blob/7.2/src/ae_epoll.c)。

## 4. 单线程与 IO Threads 的版本边界

“单线程”主要描述普通核心命令的执行路径，不能理解为 Redis 整个进程只有一个线程。后台释放、AOF 刷盘等有各自的任务机制，RDB 保存、AOF 重写还会涉及子进程。Redis 4.0 的 `UNLINK` 先摘除键，再按条件把内存回收交给后台；它不是网络多线程的起点。[UNLINK](https://redis.io/docs/latest/commands/unlink/)

### 4.1 Redis 6/7 以 7.2 为例

Redis 6.0 引入可选的网络 I/O 线程。7.2 中各线程主要执行主线程分发的一批 I/O 工作：

```text
主线程收集待处理客户端
  → 分配一批读或写工作，主线程也处理其中一部分
  → 等待其他 I/O 线程完成本批工作
  → 主线程继续执行命令或完成写后处理
```

读和写是分别组织的阶段。启用多线程读取时，I/O 线程可以读取并预解析请求，普通命令仍回到主线程执行；不能说“解析始终只在主线程”。客户端较少或连接类型不适用时，也可能走主线程处理路径。[Redis 7.2 networking.c](https://github.com/redis/redis/blob/7.2/src/networking.c)

| 配置 | Redis 7.2 中的含义 |
|---|---|
| `io-threads 1` | 默认仅由主线程处理网络 I/O |
| `io-threads 4` | 配置总数为 4，包含主线程，不是额外创建 4 个工作线程 |
| `io-threads-do-reads no` | 默认值；开启 I/O 线程后，仅分担写侧工作 |
| `io-threads-do-reads yes` | 在 I/O 线程启用时，允许分担读取和协议解析 |

例如同时设置 `io-threads 4` 和 `io-threads-do-reads yes` 可以演示多线程读写，但不代表适合所有部署；线程协作有成本，是否获益取决于瓶颈。Redis 7.2 的该 I/O 线程模式不支持 TLS。[Redis 7.2 配置](https://github.com/redis/redis/blob/7.2/redis.conf)

### 4.2 Redis 8.0 的独立事件循环

Redis 8.0 重构了 I/O 线程实现：启用后，各 I/O 工作线程拥有自己的 `aeEventLoop`，处理分配给它们的连接，并通过队列与通知机制和主线程交接。读取、协议解析、写出可以由这些线程承担，需要执行的普通命令交回主线程。

`io-threads > 1` 即启用新的线程模式，`io-threads-do-reads` 仅为兼容保留，不再控制读取；8.0 的 I/O 线程也支持 TLS。但并非所有连接都移入工作线程：复制、Pub/Sub、MONITOR 等特殊客户端在 8.0 有主线程处理限制。

所以，“所有 ae 事件循环都在主线程”以及“Redis 6 以后始终使用同一种线程协作流程”都不准确。不要把 I/O 并行误解为普通键值命令并行执行。

依据：[Redis 8.0 iothread.c](https://github.com/redis/redis/blob/8.0/src/iothread.c)、[配置定义](https://github.com/redis/redis/blob/8.0/src/config.c)、[TLS 说明](https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/#limitations)。

## 5. 性能与容易混淆的阻塞

Redis 可以维护大量连接，是因为多路复用和非阻塞处理不要求每个连接占用一个等待线程。内存数据结构和串行访问核心数据也减少了一部分开销，但不意味着 CPU、网络或磁盘永远不会成为瓶颈。

| 情况 | 实际影响 |
|---|---|
| 主线程执行耗时命令、长 Lua 脚本或昂贵的大 key 操作 | 占用命令执行时间，拖慢后续请求；增加 I/O 线程不能直接解决 |
| `BLPOP` 等待空列表 | 记录客户端的等待状态，主线程继续服务其他客户端；数据到来或超时后推进响应 |
| `epoll_wait` 休眠 | 等待连接就绪或超时，是没有立即工作时的正常等待 |
| 客户端读取响应很慢 | 输出缓冲区可能积压；具体限制和断开策略取决于客户端类型与配置 |

Lua 脚本执行期间的原子性指相对于其他客户端命令不被交错执行，不代表运行出错时会自动回滚已经完成的写入。[脚本原子执行](https://redis.io/docs/latest/develop/programmability/eval-intro/)

排查延迟时先区分慢命令、CPU、网络、输出积压、持久化或 fork 等原因，再判断是否需要 I/O 多线程或分片。参考[延迟诊断](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/)、[BLPOP](https://redis.io/docs/latest/commands/blpop/)、[客户端输出限制](https://redis.io/docs/latest/develop/reference/clients/#output-buffer-limits)。

## 6. 复习自检

- **ae 与 epoll 的关系？** ae 负责注册、分发和定时调度，epoll 提供底层就绪等待；调用它们的是线程。
- **一次可读就能执行命令吗？** 先读取并解析，只有完整命令才能进入执行流程。
- **主线程在执行命令 A 时，B 的数据还能到达吗？** 可以进入内核接收缓冲区；经典模型下 B 的读取和命令处理需要等待主线程，启用 I/O 线程后部分网络工作可并行。
- **单线程是否意味着多条命令自动组成原子操作？** 否。例如客户端分开发出的 GET、SET 之间仍可能插入其他客户端命令，需要按业务使用原子命令、脚本或事务机制。

相关笔记：[Linux epoll 的就绪通知与多线程等待](../07_Backend_Deploy_Network/13_Linux_epoll_Socket_就绪通知与多线程等待.md)、[Redis 限流与 Lua 原子操作](10_Redis_限流与_Lua_原子操作.md)、[Redis 总笔记](../../Redis/Redis.md)。
