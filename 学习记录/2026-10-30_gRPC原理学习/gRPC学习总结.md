# gRPC 学习总结：从远程调用到 grpc-go 底层实现

整理日期：2026-10-30。

本文汇总本次讨论，按知识之间的依赖重新组织，保留提问中的关键疑惑，并把后续源码核对后的结论合并到对应位置。贯穿示例是：**进程 A 调用进程 B 的 `UserService.GetUser`，根据用户 ID 获取用户资料。**

概念部分讲通用 gRPC；实现部分固定为 **grpc-go v1.85.0**，提交 `c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7`，使用原生 `grpc.Server.Serve` 路径。其他语言、旧版 Go 实现和 `ServeHTTP` 路径不能直接套用这里的协程结构与函数名。

本文中的 Go / Proto 代码用于解释接口和执行关系，省略部分工程配置，不是一套已经编译运行的示例工程。`GetUser` 是教学接口，生成代码结构通过官方 `Greeter.SayHello` 示例核对。

## 阅读入口

建议先读第 1～5 节建立主线，再读调用治理，最后结合图阅读实现。

- [1. 整体地图](#overview)
- [2. Proto、Protobuf 与生成代码](#proto)
- [3. 地址、Channel、连接与 Stub](#channel)
- [4. 一次普通调用，以及网络上的数据](#wire)
- [5. 四种调用方式与流式通信](#streaming)
- [6. Deadline、取消与业务结果](#deadline)
- [7. 错误状态、重试与幂等](#retry)
- [8. 服务发现与负载均衡](#discovery)
- [9. Metadata 与拦截器](#interceptor)
- [10. 流量控制、背压与缓冲](#flowcontrol)
- [11. Keepalive、健康检查与优雅停机](#lifecycle)
- [12. Go 代码如何接上框架](#generated)
- [13. 实现中的对象与协程](#runtime)
- [14. 沿一次 Unary 看完整实现](#implementation)
- [15. TCP 队头阻塞及缓解](#hol)
- [16. 讨论中的疑惑与准确结论](#questions)
- [17. 学习进度与后续顺序](#progress)
- [18. 源码与资料索引](#sources)

已有实现图与说明：

| 文件 | 用途 |
| --- | --- |
| [实现说明入口](index.html) | 在一页中切换三张图，阅读逐步说明与源码证据 |
| [01 对象与生命周期](01-objects.html) | 区分 Stub、Channel、连接、调用尝试、底层流与缓冲 |
| [02 双端收发架构](02-runtime.html) | 看请求和响应如何穿过协程、队列、连接 |
| [03 一次成功 Unary 的时序](03-sequence.html) | 看调度、解码、业务执行与最终状态的先后关系 |

HTML 图可用浏览器打开。图经过结构、源码引用和浏览器自动检查；这些检查不代表运行过真实 RPC 或做过性能测试。

<a id="overview"></a>

## 1. 整体地图

### 1.1 先把各层的职责分开

| 名称 | 回答的问题 | 在本例中的作用 |
| --- | --- | --- |
| RPC | 怎样跨进程调用一个操作？ | A 调用 B 的 `GetUser` |
| gRPC | 哪个框架落实这套调用机制？ | 接口生成、调用管理、传输、状态、流式调用等 |
| `.proto` | 接口和消息结构如何声明？ | 定义 `GetUser` 以及请求、响应类型 |
| Protobuf | 消息对象如何编码为字节？ | 编码用户 ID 与用户资料 |
| HTTP/2 | 调用如何组织成流和帧？ | 请求头、DATA、响应头、Trailers，多流复用 |
| TCP | 字节如何可靠、有序地到达对端？ | 提供连接上的双向有序字节传输 |
| TLS | 如何保护传输并验证对端身份？ | 常见部署中位于 HTTP/2 和 TCP 之间 |

本文默认讨论 **gRPC + Protobuf + HTTP/2 + TCP** 这条常见路径。Protobuf 是默认消息编码方式，不是 gRPC 所有实现和配置唯一可能的编码方式。

RPC 与 HTTP 不在同一个抽象层：RPC 描述调用方式，HTTP 可以承担它的传输。使用 HTTP 并不意味着一定是 REST。

### 1.2 最初的 HTTP handler 类比哪里成立

最初的理解是：把内容放进 HTTP 请求体，发给目标服务，再根据请求地址路由到 handler。

这个理解抓住了主要方向。对应到 gRPC：

```text
A 组装请求对象
  → Stub 携带方法路径发起调用
  → 框架编码消息并通过 HTTP/2 发送
  → B 根据服务名和方法名查找注册的 handler
  → 框架解码请求
  → 业务方法处理
  → 框架把响应和最终状态传回 A
```

要补上的内容有三类：

1. 调用接口、消息编解码、服务注册等通常由生成代码和框架衔接。
2. 一条连接可以承载许多并发 RPC，每次调用有自己的流状态。
3. 远程调用还需要处理超时、取消、故障、最终状态和可能重复执行的问题。

**函数式的调用接口没有消除网络的不确定性。**

<a id="proto"></a>

## 2. Proto、Protobuf 与生成代码

### 2.1 `message` 与 `service / rpc` 各自定义什么

```proto
syntax = "proto3";

package user.v1;
option go_package = "example.com/demo/gen/user/v1;userv1";

message GetUserRequest {
  int64 user_id = 1;
}

message GetUserReply {
  int64 user_id = 1;
  string name = 2;
}

service UserService {
  rpc GetUser(GetUserRequest) returns (GetUserReply);
}
```

| 声明 | 含义 |
| --- | --- |
| `message GetUserRequest` | 请求数据有哪些字段 |
| `message GetUserReply` | 响应数据有哪些字段 |
| `service UserService` | 一组可远程调用的方法 |
| `rpc GetUser(...) returns (...)` | 方法名、请求类型、响应类型及是否流式 |

以前只用 Protobuf 时，可能只写了消息结构，自己负责网络协议、路由和发送。现在声明 `service / rpc`，还把“哪些方法可以调用”交给工具生成接口。

`.proto` 可以只定义消息，也可以定义服务；消息可以拆到其他文件再 `import`。**不要求每个文件都同时拥有消息和服务。**

`rpc` 声明本身不会建立连接或发送数据。它是接口描述，实际行为来自代码生成器和运行时框架。[Protobuf 服务定义说明](https://protobuf.dev/programming-guides/proto3/#services)

### 2.2 两类生成代码

Go 中常见的生成分工是：

| 工具 | 常见产物 | 职责 |
| --- | --- | --- |
| `protoc-gen-go` | `*.pb.go` | 消息类型、字段信息及 Protobuf 运行时所需代码 |
| `protoc-gen-go-grpc` | `*_grpc.pb.go` | 客户端接口和 Stub、服务端接口、注册函数、方法描述与适配 handler |

开发者仍要写业务方法，也要提供目标地址、凭据等运行配置。

### 2.3 Proto 通常不放 B 的部署地址

接口契约与部署位置是两个问题。同一个 `UserService` 可以部署在本机、测试环境或多个生产实例上，接口无需随 IP 变化。

```text
.proto：调用什么方法、用什么消息
配置 / 服务发现：这个服务在哪里
Channel：如何连接、选择和管理目标
```

<a id="channel"></a>

## 3. 地址、Channel、连接与 Stub

### 3.1 A 如何知道 B 在哪里

A 创建 Channel 时提供目标字符串，例如：

```go
// 本机教学示例：使用明文凭据连接本地服务。
conn, err := grpc.NewClient(
    "localhost:50051",
    grpc.WithTransportCredentials(insecure.NewCredentials()),
)
if err != nil {
    return err
}
defer conn.Close()

client := userv1.NewUserServiceClient(conn)

ctx, cancel := context.WithTimeout(context.Background(), time.Second)
defer cancel()

reply, err := client.GetUser(ctx, &userv1.GetUserRequest{UserId: 123})
if err != nil {
    return err
}
fmt.Println(reply.Name)
```

目标也可以是 `dns:///user-service.example:50051` 等逻辑名称。解析器将名称变成地址集合，后续由 Channel 的连接管理和负载均衡机制使用。

实际部署使用与服务端相匹配的 TLS / 身份配置；上面的明文设置仅说明本地调用结构。

### 3.2 Channel 是长期逻辑对象，不等于一条 TCP 连接

grpc-go 中，面向用户的 Channel 通常由 `*grpc.ClientConn` 表示。

```text
ClientConn
  ├─ 目标与解析器
  ├─ 负载均衡策略、picker、连接状态
  ├─ 连接到 B1 的 transport
  └─ 连接到 B2 的 transport（是否存在取决于策略和状态）
```

一个 Channel 在不同时间可能关联零条、一条或多条实际连接。连接可能建立、断开、重建或因空闲等原因释放，Channel 对象可以继续存在。

因此，对“Channel 是长连接还是每次请求才建连接”的回答应分两层：

- **使用方式**：通常长期复用 Channel 和 Stub，多次 RPC 复用已经可用的连接。
- **建连时机**：取决于 API 和状态。此版本 `grpc.NewClient` 本身不做网络 I/O，首次使用等动作可触发连接；创建成功不代表已连上服务。

旧示例中的 `grpc.Dial / DialContext` 与 `NewClient` 的启动行为有差异，不能混为一谈。[固定版本客户端创建说明](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/Documentation/anti-patterns.md)

### 3.3 为什么一个 Channel 能承载多个 RPC

常见情况下，多次调用选中同一个 HTTP/2 连接；每次调用尝试使用不同的 HTTP/2 Stream。

```text
同一个 Channel
  └─ 同一个 HTTP/2 连接
       ├─ Stream 1：GetUser(123)
       ├─ Stream 3：GetUser(456)
       └─ Stream 5：其他方法调用
```

图中的 ID 仅作示意，关键是同一连接内用 Stream ID 区分调用。并发流数仍受对端设置和框架资源限制，不能理解成无限并发。

### 3.4 一个 service 是否需要一个 Stub

生成代码通常为每个 Proto `service` 提供对应的客户端类型。例如 `UserServiceClient` 与 `OrderServiceClient`。

但要分清“类型”和“实例”：

- 一个 Stub 实例包含该 service 的多个方法，不必为每个方法创建 Stub。
- 同一个 Stub 可以复用并并发发起多个 RPC。
- 不同 service 的 Stub 可以共用一个 Channel，前提是该目标实际提供这些服务。
- 同一 service 也可以有多个 Stub 实例，使用相同或不同 Channel。

**Stub 持有调用接口，不等于独占连接。**

<a id="wire"></a>

## 4. 一次普通调用，以及网络上的数据

### 4.1 先看完整逻辑闭环

```text
A 的业务代码
  → client.GetUser(ctx, request)
  → 客户端 Stub
  → ClientConn.Invoke
  → 选择连接、创建本次调用的流
  → 编码请求并发送
  → B 接收请求头，按服务与方法路由
  → B 解码请求并执行 GetUser
  → B 编码响应，发送最终 gRPC 状态
  → A 解码响应并检查最终状态
  → 返回 reply 或 error
```

### 4.2 方法名如何变成路由

本例的完整方法路径是：

```text
/user.v1.UserService/GetUser
```

它来自 Proto 的 package、service 和方法名，作为 HTTP/2 的 `:path` 发送。常见请求还包含 `:method = POST`、`content-type = application/grpc` 等信息。

服务端注册表建立“服务名 / 方法名 → 适配 handler → 业务实现”的对应关系。运行时不是根据路径在磁盘里寻找某个 Proto 文件。

### 4.3 从对象到字节的层次

```text
GetUserRequest 对象
  ↓ Protobuf 编码
消息内容字节
  ↓ 可选压缩，再加 gRPC 消息前缀
[1 字节压缩标志][4 字节消息长度][N 字节内容]
  ↓ 放进 HTTP/2 DATA 帧，可拆分
带 Stream ID 的 HTTP/2 帧
  ↓ 可选 TLS
TCP 字节流
```

4 字节长度使用大端序；启用单条消息压缩时，该长度描述压缩后的消息内容字节数。接收方依次做逆向处理。

必须分清三种边界：

- 一条 Protobuf / gRPC 消息可以跨多个 DATA 帧。
- 一个 DATA 帧也可能带有多条消息的数据，或者消息的一部分。
- TCP 分段边界既不等于帧边界，也不等于消息边界。

长度前缀帮助接收方在连续数据中恢复消息边界，不能把一次底层 `Read` 当成一条完整消息。

以上消息格式、方法路径和终止状态约定见 [gRPC over HTTP/2 协议](https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-HTTP2.md)；本次接收解析实现见 [rpc_util.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/rpc_util.go#L783)。

### 4.4 HEADERS、DATA 与 Trailers

一次常见成功 Unary 可以概括为：

```text
A → B：请求 HEADERS
A → B：请求 DATA，最后结束请求发送方向
B → A：响应 HEADERS
B → A：响应 DATA
B → A：Trailers，带 grpc-status，结束响应方向
```

Trailers 在 HTTP/2 上也是末尾的头部块，通常由 HEADERS 帧承载；它不是额外定义的一种“TRAILERS 帧”。头部块较大时还涉及 CONTINUATION，图中省略这一分帧细节。

错误响应可能只有终止头部而没有业务响应消息。HTTP 状态、收到一条 DATA、解码出一个对象，都不能单独替代最终 gRPC 状态的检查。

<a id="streaming"></a>

## 5. 四种调用方式与流式通信

### 5.1 讨论中的几个 Stream 不在同一层

| 术语 | 含义 |
| --- | --- |
| TCP 字节流 | 一条连接在每个方向上有序传输的字节序列 |
| HTTP/2 Stream | HTTP/2 连接中带 ID 的独立逻辑交换，具有自己的状态 |
| gRPC 流式调用 | 一次 RPC 允许某个方向发送多条业务消息 |
| grpc-go Stream 对象 | 框架提供或维护的调用状态与 Send / Recv 接口 |

普通 Unary 也会使用 HTTP/2 Stream。“是不是流式 RPC”取决于接口是否允许多条消息，不取决于底层有没有 Stream。

一次调用尝试的请求和响应通常使用**同一个双向 HTTP/2 Stream**。客户端和服务端分别持有自己的本地对象，靠连接与 Stream ID 对应，不能理解成跨进程共用同一块内存。

### 5.2 四种调用形态

下面的 `Request / Response` 是示意类型：

| 调用方式 | Proto 方法形式 | 成功路径上的消息关系 | 例子 |
| --- | --- | --- | --- |
| Unary | `rpc Get(Request) returns (Response)` | 一条请求 → 一条响应 | 查询用户 |
| 服务端流 | `rpc Watch(Request) returns (stream Response)` | 一条请求 → 多条响应 | 订阅用户状态 |
| 客户端流 | `rpc Upload(stream Request) returns (Response)` | 多条请求 → 一条响应 | 上传分片后汇总 |
| 双向流 | `rpc Chat(stream Request) returns (stream Response)` | 两个方向都可多条消息 | 持续交互 |

“多条”表示可持续发送消息的接口形态，不要求实际至少发送两条；错误结束时也可能没有响应消息。[gRPC 调用类型](https://grpc.io/docs/what-is-grpc/core-concepts/)

### 5.3 流式调用持续的是什么

```text
建立一次 Chat 调用
  A → B：消息 A1
  A → B：消息 A2
  B → A：消息 B1
  A → B：消息 A3
  B → A：消息 B2
  ……
结束这次调用
```

每次 `Send` 通常是在既有调用中追加一条消息，不是再次调用远程方法、创建新 RPC。每次成功 `Recv` 获得一条解码后的业务消息，不是任意长度的 TCP 数据。

双向流的两个方向可以独立推进，不要求 A 发一条就必须等 B 回一条。每个方向内部保序；请求与响应怎样对应，需要业务协议定义。

### 5.4 为什么两个协程操作同一个 Stream

因为业务代码把**同一次流式方法调用返回的 Stream 对象**交给了两个协程：

```go
// 结构示意：错误处理和取消协调应由实际程序补全。
stream, err := client.Chat(ctx)
if err != nil {
    return err
}

go sendLoop(stream) // 此协程独占发送方向。
recvLoop(stream)    // 当前协程独占接收方向。
```

共用同一个 Stub 不是共用 Stream 的原因：

```text
同一个 client
  ├─ 第一次 Chat(ctx) → streamA
  └─ 第二次 Chat(ctx) → streamB
```

`streamA`、`streamB` 是两次不同调用，可以复用同一连接。

### 5.5 Send / Recv 的并发边界

grpc-go 支持一个协程发送、另一个协程接收同一个流，但不能让多个协程同时 `SendMsg`，也不能让多个协程同时 `RecvMsg`。`CloseSend` 也不应与 `SendMsg` 并发。

多生产者需要一个发送协程来汇聚消息；接收后若交给工作池并行处理，业务完成顺序可能发生变化，需要自行维护顺序约束。[固定版本并发说明](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/Documentation/concurrency.md)、[Stream 接口约束](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/stream.go#L93)

### 5.6 半关闭、EOF 与结束

- 客户端 `CloseSend` 表示自己不再发送请求消息，仍可以继续接收响应。
- 服务端读到请求方向的 EOF，不代表它不能再发送响应。
- 客户端接收方向正常完成时通常得到 `io.EOF`；非 OK 状态以错误返回。
- `CloseSend` 成功不证明整个 RPC 成功，应继续处理接收结果和最终状态。

流式调用需要明确退出与取消协调。如果发送或接收一侧结束后让另一侧永久等待，就可能泄漏协程和调用资源。应消费终止结果，或取消调用 context，让未完成的等待退出。

<a id="deadline"></a>

## 6. Deadline、取消与业务结果

### 6.1 为什么 RPC 要有时间预算

```go
ctx, cancel := context.WithTimeout(parentCtx, 800*time.Millisecond)
defer cancel()
reply, err := client.GetUser(ctx, request)
```

Timeout 是一段时长，Deadline 是截止时刻。该预算约束整次调用可能经历的等待和处理，包括选连接、发送、服务端执行、接收，以及同一次调用内的重试等待，不能只理解成“B 的业务函数最多跑多久”。

gRPC 默认并不为每次调用自动设置合适的业务 deadline。调用链 A → B → C 中，B 应沿用传入的 context，必要时再缩短预算；在 B 内随意改用 `context.Background()` 会切断上游取消和时间约束。[Deadline 指南](https://grpc.io/docs/guides/deadlines/)

### 6.2 取消如何影响服务端

取消会通过框架的流关闭、协议通知与 context 传播机制影响对端及本地等待。服务端业务应把 context 传入数据库、下游 RPC 等支持取消的接口，或在长期循环中检查 `ctx.Done()`。

**取消不会强行杀死任意 Go 协程，也不会自动撤销已经完成的副作用。**

### 6.3 超时不等于业务没有成功

```text
B 完成扣款并提交数据库
  → 响应在返回途中丢失或延迟
  → A 的 deadline 到期
  → A 看见 DeadlineExceeded
```

A 只知道自己没有在预算内取得成功结果，不能据此断言 B 没执行。

| A 能证明的事实 | 对业务结果的含义 |
| --- | --- |
| 明确在发送前失败 | 这次尝试通常没有到达业务处理，但需结合具体路径 |
| 已收到明确业务拒绝 | 按该业务接口定义解释 |
| 发送后超时、断线或响应丢失 | 可能未执行、执行中，也可能已提交 |

写操作要靠业务请求 ID、幂等处理和结果查询解决这种不确定性。

<a id="retry"></a>

## 7. 错误状态、重试与幂等

### 7.1 看 gRPC 状态，不只看 HTTP 200

gRPC 通过状态码描述 RPC 结果。Go 的 Unary 调用通常返回 `reply, err`，可用 `status.Code(err)` 判断错误类型。

| 常见状态 | 常见语义 | 处理方向 |
| --- | --- | --- |
| `OK` | RPC 成功完成 | 使用响应 |
| `InvalidArgument` | 请求参数有误 | 修正参数 |
| `NotFound` | 目标资源不存在 | 按业务语义处理 |
| `Unauthenticated` | 缺少或无效身份凭据 | 修复身份认证 |
| `PermissionDenied` | 身份无权执行操作 | 处理授权问题 |
| `ResourceExhausted` | 配额或资源耗尽 | 限速、退避或调整资源 |
| `Unavailable` | 当前无法完成调用，常见于临时不可用 | 满足业务安全条件时考虑重试 |
| `DeadlineExceeded` | 超过截止时间 | 判断预算及结果是否未知 |
| `Canceled` | 调用取消 | 分清谁取消、为什么取消 |
| `Internal` | 内部错误 | 排查服务或协议处理问题 |

这些是解释方向，不是只靠一个状态码就能确定故障发生位置的规则。连接提前断开时，客户端也可能本地生成状态，未必收到服务端 Trailers。[固定版本状态码定义](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/codes/codes.go)

### 7.2 重试要分框架机制和业务语义

框架可以在满足条件时创建新的 attempt，并重放可重试的调用数据。是否重试受透明重试条件、配置策略、状态码、次数、退避、调用是否已提交给应用等约束。

不能推导为“所有错误都会自动重试”，也不能推导为“配置重试后业务一定只执行一次”。没有显式配置重试策略时，仍可能有受限的透明重试。收到响应头等事件会限制后续框架重试；长流断开后的业务续传尤其需要额外协议。[gRPC 重试说明](https://grpc.io/docs/guides/retry/)

重试源码中的 `committed` 表示该尝试已不能再按这套机制重试，与“数据库事务已经提交”不是同一种状态。连接重建也只恢复传输可用性，不保证中断的调用已恢复或从未执行。

### 7.3 幂等让重复请求具有可控制的结果

以创建订单为例：

```text
A 第一次调用：CreateOrder(request_id=R123)
  → B 创建订单成功，保存 R123 对应结果
  → A 未收到响应
A 重试：CreateOrder(request_id=R123)
  → B 识别已处理的 R123，返回既有结果
```

请求 ID 应稳定标识这次业务操作，跨重试保持一致。服务端需要让去重记录与业务状态变更具备可靠的一致性，例如利用数据库唯一约束和事务；仅在内存里记一个标记不能应对进程崩溃。

HTTP/2 Stream ID 只在一条连接内标识传输流。重试会建立新的传输流；换到另一连接时，Stream ID 的数值甚至可能相同。因此它不能代替跨尝试保持稳定的业务幂等 ID。

<a id="discovery"></a>

## 8. 服务发现与负载均衡

### 8.1 名称解析和请求选择是两件事

```text
目标名 user-service
  → resolver 得到 B1、B2、B3
  → Channel / balancer 管理连接状态
  → picker 为新调用尝试选择可用 transport
  → 该尝试绑定选定连接上的一个流
```

Resolver 回答“有哪些候选地址”，负载均衡策略回答“本次使用哪个候选”。服务发现系统还可能更新地址集合或提供服务配置。[名称解析指南](https://grpc.io/docs/guides/custom-name-resolution/)

### 8.2 `pick_first` 与 `round_robin`

| 策略 | 可用于理解的行为 |
| --- | --- |
| `pick_first` | 选定一个可用连接持续承载调用；不会因为有多个地址就把每次 RPC 轮流分散 |
| `round_robin` | 在就绪的可用后端连接之间轮转选择新调用 |

具体建连和切换细节随版本实现变化。多地址解析、策略注册和服务配置都要配合；“用了 gRPC”不等于已经启用了客户端轮询负载均衡。[固定版本负载均衡示例](https://github.com/grpc/grpc-go/tree/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/examples/features/load_balancing)

### 8.3 一次长流不会逐条消息重新选择后端

一次流式调用建立后，其底层流绑定某条连接。之后的每条消息沿这条流传输，不会因为 picker 轮询就突然发给另一台服务器。

连接故障后的重试或业务重连会建立新流，不能描述成原 Stream 无缝迁移。恢复订阅、断点续传或游标位置需要业务协议配合。

### 8.4 长连接和四层负载均衡

若外部四层负载均衡按 TCP 连接选择后端，一条连接中的所有 HTTP/2 流通常都会到达同一个后端。一个客户端长期只用一条连接，可能造成请求集中。

应先区分问题属于服务发现、客户端策略还是代理层的分配粒度，再考虑客户端负载均衡、能理解 gRPC 的代理或经过测量的连接隔离。无需因为看到“长连接”就默认给每次 RPC 新建连接。

<a id="interceptor"></a>

## 9. Metadata 与拦截器

### 9.1 业务消息和调用附加信息

请求消息保存接口业务字段，例如 `user_id`。Metadata 常用于认证信息、追踪信息和其他跨方法的调用属性，通过 HTTP/2 头部传输。

```go
// 给下游调用附加追踪信息，业务请求类型不必因此增加字段。
ctx = metadata.AppendToOutgoingContext(ctx, "x-request-id", requestID)
reply, err := client.GetUser(ctx, request)
```

服务端通过 incoming metadata 读取。业务字段与 Metadata 没有绝对禁止交叉的语法限制，划分依据是接口语义和用途。应用自定义 Metadata 不应占用保留的 `grpc-` 前缀。[Metadata 指南](https://grpc.io/docs/guides/metadata/)

普通 `context.WithValue` 中的值不会自动跨网络传输。框架处理 outgoing Metadata、deadline 等明确支持的内容；服务端据此建立自己的 context，客户端和服务端并不共用同一个 context 对象。身份凭据也可以使用专门的 Call Credentials 接口，不必全部塞进自定义拦截器。

### 9.2 “类似 Gin 中间件”这个类比成立

拦截器把日志、认证、授权、指标等公共逻辑包在调用链外层：

```text
拦截器 A 前置
  → 拦截器 B 前置
    → 业务 handler
  ← 拦截器 B 后置
← 拦截器 A 后置
```

它可以调用下一层继续，也可以直接返回错误，终止后续处理。客户端和服务端有不同接口；Unary 与 streaming 也有不同拦截器类型。[拦截器指南](https://grpc.io/docs/guides/interceptors/)

### 9.3 类比的精确边界

- 客户端 Unary interceptor 包围一次调用，不是围住每个 TCP 包。
- 此版本生成的服务端 Unary handler 先通过 `dec` 得到请求对象，再调用 Unary interceptor；不能说所有拦截器都在解码前运行。
- 流式拦截器面向流的创建或处理；要观察每次 `SendMsg / RecvMsg`，通常需要包装 Stream 接口。
- 客户端流式方法返回 Stream 时，整条流一般还没结束，因此不能把“创建流返回”当成“流式 RPC 完成”。

这些差异解释了为什么 Gin 类比有帮助，但不能把 Gin 的生命周期原样搬过来。

<a id="flowcontrol"></a>

## 10. 流量控制、背压与缓冲

### 10.1 为什么发送不能永远快于接收

假设 B 每秒产生 10 万条结果，A 每秒只能处理 1 万条。如果无限接收并存入内存，积压会持续增长。

背压是把下游处理能力不足传回上游，让生产或发送受到限制。gRPC 的读写与底层流控是其中一部分，应用自己的队列设计也是其中一部分。

`Send` 成功通常只表示框架接受了这次发送，不能据此确认对端已收到、已消费或已执行。发送过快时，发送调用也可能等待。[gRPC 流控说明](https://grpc.io/docs/guides/flow-control/)

### 10.2 三个容易混淆的限制

| 机制 | 粒度 | 作用 |
| --- | --- | --- |
| 本地 `writeQuota` | 单个传输流的本地待发量 | 限制应用持续向本地发送路径堆积数据 |
| HTTP/2 Stream 窗口 | 一个流的发送方向 | 限制该流可继续发送多少 DATA |
| HTTP/2 Connection 窗口 | 整条连接的发送方向 | 限制连接上所有流合计可继续发送多少 DATA |

writer 在实际写 DATA 时需要同时满足流窗口与连接窗口。流控额度主要限制 DATA，不能说窗口归零后连 PING、WINDOW_UPDATE 等控制帧也必须停发。

某一流窗口不足，其他有额度的流仍可能发送；连接窗口不足时，所有流的 DATA 都受限。底层 socket 写入阻塞也会影响这条连接上的其他流。

**Unary 的 DATA 同样受 HTTP/2 流控约束。** 流式调用让应用更频繁地感受到背压，但底层机制并非只存在于 streaming API。[HTTP/2 流控规范](https://www.rfc-editor.org/rfc/rfc9113.html#section-5.2)、[固定版本流控实现](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/internal/transport/flowcontrol.go)

### 10.3 应用队列也要受控

```text
容易积压：Recv 很快 → 无限队列 → 慢消费者

可传播背压：Recv → 有界队列 → 消费者
                       队列满后等待，进而减慢继续接收
```

框架不能替应用约束任意自建容器。也不能机械理解成“每 Recv 一条就立即发一个 WINDOW_UPDATE”，实际额度更新有字节统计、阈值和批量处理。

grpc-go 在连接级和流级接收额度上做了区分，避免仅因某条流的业务消费缓慢就无必要地拖住其他流；这不意味着不同流完全没有共享资源影响。

### 10.4 双向流也可能产生应用死锁

如果 A、B 都先大量发送，发送被背压阻塞，而双方都打算“全部发完再开始接收”，就可能互相等待。解决方向是设计独立的发送和接收推进、有限缓冲与明确的退出规则。

<a id="lifecycle"></a>

## 11. Keepalive、健康检查与优雅停机

### 11.1 三个问题分别由什么处理

| 机制 | 关注点 | 不能证明什么 |
| --- | --- | --- |
| Deadline | 这一次调用最多等到什么时候 | 超时不证明业务没有提交 |
| Keepalive | 连接上的协议通信是否仍然通畅 | PING 成功不证明数据库或业务可用 |
| Health Check | 服务是否声明自己可接收业务请求 | 返回健康不保证之后每次调用都成功 |

### 11.2 Keepalive

gRPC 的 Keepalive 常通过 HTTP/2 PING / ACK 探测连接。它与操作系统 TCP keepalive 是不同层的机制。

配置需要客户端、服务端和代理共同匹配。过于频繁的 PING 可能被服务端拒绝，并触发带 `too_many_pings` 信息的 GOAWAY。Keepalive 也不能替长流恢复业务进度。[Keepalive 指南](https://grpc.io/docs/guides/keepalive/)

### 11.3 健康检查

标准 gRPC 健康服务提供 `Check` 和持续观察状态的 `Watch`，常见状态包括 `SERVING` 与 `NOT_SERVING`。

框架提供协议和实现，业务仍要决定什么条件算健康，并更新状态。仅注册健康服务，不会自动替你判断数据库、依赖或业务容量。

客户端自动健康检查与负载均衡行为还依赖显式配置和所选策略，不能认为所有 Channel 默认都会按健康状态避开后端。[健康检查指南](https://grpc.io/docs/guides/health-checking/)

### 11.4 优雅停机

目标是在停止接收新请求的同时，给已有请求留出完成机会：

```text
通知流量入口 / 健康系统该实例准备退出
  → 停止接受新连接与新调用，现有连接进入排空
  → 等待正在执行的调用结束
  → 到达退出上限后强制关闭剩余调用
  → 清理资源并退出
```

实例摘除和健康状态传播存在延迟，因此不能假设宣布退出后瞬间就没有新请求。HTTP/2 GOAWAY 参与连接排空，包含最后处理的 Stream ID 等信息。它不是把所有已建立 RPC 迁移到新服务器的指令；既有流可能继续完成，新调用由客户端选择其他可用路径。

grpc-go 的 `GracefulStop` 会等待调用结束；若长期流一直不退出，等待也可能持续。通常由应用设置退出期限，并用 `Stop` 作为到期后的强制终止手段。不要让数据库等资源早于仍在使用它们的 handler 被关闭。[优雅停机指南](https://grpc.io/docs/guides/graceful-shutdown/)、[固定版本 Stop / GracefulStop](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/server.go#L1670)

<a id="generated"></a>

## 12. Go 代码如何接上框架

### 12.1 Stub 是强类型适配层

生成客户端的核心关系可以简化成：

```go
type userServiceClient struct {
    cc grpc.ClientConnInterface
}

func (c *userServiceClient) GetUser(
    ctx context.Context,
    in *GetUserRequest,
    opts ...grpc.CallOption,
) (*GetUserReply, error) {
    out := new(GetUserReply)
    // 传入完整方法路径和输入输出对象；网络逻辑由框架承担。
    err := c.cc.Invoke(ctx, "/user.v1.UserService/GetUser", in, out, opts...)
    if err != nil {
        return nil, err
    }
    return out, nil
}
```

这段是概念化简；真实生成代码可能增加静态方法等调用选项。它没有为每个方法手写 socket、HTTP/2 帧或 Protobuf 解码流程。

### 12.2 注册业务实现

```go
type userServer struct {
    userv1.UnimplementedUserServiceServer
}

func (s *userServer) GetUser(
    ctx context.Context,
    req *userv1.GetUserRequest,
) (*userv1.GetUserReply, error) {
    // 这里只展示接口衔接；真实查询应使用 ctx 并处理业务错误。
    return &userv1.GetUserReply{UserId: req.UserId, Name: "Alice"}, nil
}

// 以下片段位于启动函数中。
lis, err := net.Listen("tcp", ":50051")
if err != nil {
    return err
}
server := grpc.NewServer()
userv1.RegisterUserServiceServer(server, &userServer{})
return server.Serve(lis)
```

注册函数把服务描述、方法适配函数和实现对象交给框架。请求到来后，框架查表找到生成 handler，handler 解码并调用 `userServer.GetUser`。

这里 `grpc.Server`、Proto 中的 `service UserService`、业务实现对象 `userServer` 是三个不同概念。一个 `grpc.Server` 可注册多个 service。

### 12.3 并发请求不会自动得到不同业务对象

通常启动时注册一个 `&userServer{...}`，多个请求的 handler 会并发调用它的方法。框架不会因为每 RPC 有自己的处理协程，就自动复制这个实现对象。

| 数据 | 处理原则 |
| --- | --- |
| 方法内部新建的局部请求变量 | 通常属于本次调用 |
| `userServer` 上共享的 map、计数器、可变缓存 | 需要锁、原子操作或其他并发设计 |
| Stub / ClientConn | 框架支持并发使用 |
| 同一个请求 / 响应消息对象 | 不应在发送或框架使用期间并发修改 |

生成接口与注册结构见 [官方 Greeter 生成代码](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/examples/helloworld/helloworld/helloworld_grpc.pb.go#L42)。

<a id="runtime"></a>

## 13. 实现中的对象与协程

实现开始混乱的主要原因，是把**对象、执行者、数据格式和调用阶段**放进了同一条层级链。应分别问四个问题：

| 维度 | 要回答的问题 |
| --- | --- |
| 对象与生命周期 | 谁持有这份状态，它存在多久？ |
| 执行者 | 哪个 goroutine 正在执行这段代码？ |
| 数据形式 | 当前处理的是消息对象、字节块还是 HTTP/2 帧？ |
| 阶段与完成条件 | 入队、写出、解码、最终成功分别保证什么？ |

### 13.1 对象关系

| 对象 | 粒度 | 主要职责 |
| --- | --- | --- |
| 生成 Stub | 可长期复用 | 强类型方法入口，引用 `ClientConnInterface` |
| `ClientConn` | 逻辑 Channel | 解析、连接管理、负载均衡与调用入口 |
| `http2Client / http2Server` | 一条连接的 transport | 连接状态、活动流表、收发机制 |
| `clientStreamWrapper / clientStream` | 一次逻辑 RPC | 调用选项、context、发送接收及重试相关状态 |
| `csAttempt` | 一次调用尝试 | 关联选中的 transport 与底层流 |
| `transport.ClientStream / ServerStream` | 连接中的一个流 | Stream ID、头部、状态、接收缓冲等 |
| `recvBuffer` | 每个传输流 | 暂存接收字节块与终止事件 |
| `controlBuf` | 每条连接 | 供 writer 消费的数据与控制任务 |

`recvBuffer` 内部可以使用 Go channel 和 backlog，但 **Go channel、gRPC Channel、HTTP/2 Stream 是三件不同的东西**。

重试时逻辑 RPC 可以继续，但会换 attempt 与底层传输流。不存在把原来连接上的 Stream 原封不动搬到另一连接的行为。

### 13.2 主要执行者

下面的 G 名称是图中的教学标签，不是 Go 源码变量名。

| 标签 | 粒度 | 负责什么 |
| --- | --- | --- |
| `G-call` | 本次客户端业务调用的协程 | 调 Stub、编码请求、等待并解码响应、继续调用后代码 |
| `G-cw` | 客户端每连接主要写循环 | 发送调度、窗口控制、拆帧与写连接 |
| `G-cr` | 客户端每连接主要读循环 | 从连接读 HTTP/2 帧，按 Stream ID 分发 |
| `G-sr` | 服务端每连接主要读循环 | 读取帧、创建流、投递数据与调度处理 |
| `G-rpc` | 服务端每 RPC 的处理任务 | 路由、读取并解码请求、执行拦截器和业务、提交响应 |
| `G-sw` | 服务端每连接主要写循环 | 调度并写出响应帧与控制帧 |

“每连接一读一写”描述的是这条原生 transport 路径的主要 I/O 循环。框架还可能有连接管理、保活、控制回调等其他协程；不能把进程总协程数算成每连接恰好两个。

服务端默认调度独立处理 goroutine，也有可选 worker 配置。客户端同步 Unary 调用中，Stub、Invoke、SendMsg、RecvMsg 通常沿原调用协程执行，不是每一层都自动新建协程。

### 13.3 对早先理解的精确修正

原来的概括是：“一个连接有读取协程，读取和组装 Stream 数据，再放进上层读取协程的缓冲区。”

更准确的版本是：

> 连接 reader 读取 HTTP/2 帧，根据 Stream ID 将 DATA 字节块投递到对应 Stream 的接收缓冲。调用 `RecvMsg` 的协程从该缓冲读字节，解析 gRPC 消息边界、解压和反序列化。缓冲属于 Stream，不属于某个 goroutine。

reader 确实需要恢复 HTTP/2 帧，但“恢复帧”和“组装完整 gRPC 消息”是不同层次，后者在消费该流的读取路径完成。

配图：[对象图](01-objects.html)、[双端架构图](02-runtime.html)。

<a id="implementation"></a>

## 14. 沿一次 Unary 看完整实现

本节从连接已经可用开始，展开单次成功调用。重试、首次建连、TLS 握手不插入主线，以免混淆。

### 14.1 第一步：调用 Stub，进入 Invoke

```text
G-call
  → client.GetUser(ctx, request)
  → ClientConn.Invoke(..., 完整方法路径, request, reply)
  → 客户端 Unary interceptor（如配置）
  → 内部 invoke
  → newClientStream
```

调用创建 RPC 相关状态，经 picker 选择 transport，创建本次 attempt 的底层流，并提交请求 HEADERS。创建流不等于新建 TCP 连接。

源码：[call.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/call.go#L29)、[attempt 选连接与建流](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/stream.go#L602)。

### 14.2 第二步：G-call 编码并提交发送

```text
G-call.SendMsg(request)
  → 编码 / 可选压缩
  → gRPC 消息前缀 + 内容
  → 调用 transport 写入接口
  → 在内部获取本流本地 writeQuota
  → 把内部发送任务放入连接 controlBuf
```

这里的内部 `dataFrame` 项还可能在 writer 中被拆成多个真正的 HTTP/2 DATA 帧。`SendMsg` 并不意味着调用者直接独占 socket 写入完整消息。

普通 Unary 发送唯一请求时会结束客户端发送方向，但接收方向继续存在。发送成功不等于对端已接收或业务已执行。

源码：[客户端发送入口](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/internal/transport/http2_client.go#L1143)。

### 14.3 第三步：客户端 writer 调度并写帧

`G-cw` 的 `loopyWriter` 消费连接任务，维护各流待发送数据和活动队列，结合连接 / 流窗口决定哪些 DATA 可以继续发送，再写入连接。

```text
Stream 1 待发数据 ─┐
Stream 3 待发数据 ─┼→ writer 调度 → 有序的连接字节
Stream 5 待发数据 ─┘
```

多个 Stream 的帧可以交错出现；某条流的消息字节仍必须按该流顺序交付。多路复用不是让多个协程随意同时往 socket 写不带边界的字节。

源码：[loopyWriter](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/internal/transport/controlbuf.go#L661)。

### 14.4 第四步：服务端读请求头，建流并提前调度

服务端的连接读取循环 `HandleStreams` 按帧类型处理数据。

收到有效请求 HEADERS 后，`operateHeaders` 建立 `ServerStream`，记录路径、Metadata、deadline 等，加入活动流表，再触发处理调度。

**请求体还没到齐时，服务端处理任务就可以开始。** 但“处理任务开始”只表示可以路由并等待消息，不代表业务方法已有完整请求可用。

后续 DATA 根据 Stream ID 找到该流，放入其 `recvBuffer`。reader 不负责执行 `GetUser`，也不在此处把 Protobuf 字节变成业务对象。

源码：[服务端 HEADERS 处理](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/internal/transport/http2_server.go#L377)、[默认 RPC 调度](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/server.go#L1089)。

### 14.5 第五步：G-rpc 路由、解码并调用业务

固定版本的概念调用链是：

```text
handleStream
  → 拆分完整方法路径
  → 在 s.services 的服务 / 方法描述中查找
  → processRPC
  → wrapUnaryHandler 包装的处理器
  → 生成的 _UserService_GetUser_Handler
  → dec(request)
  → 服务端 RecvMsg
  → Unary interceptor
  → userServer.GetUser
```

本版本注册时把 Unary 适配到统一处理路径，因此不能拿旧版 `processUnaryRPC` 函数名直接描述这里的实现。

`RecvMsg` 从本流缓冲读取 5 字节消息前缀及 N 字节内容，按需等待更多数据，然后解压、解码。本版本 Unary 路径还会确认请求方向 EOF、没有第二条请求，才让生成 handler 继续执行拦截器与业务。

所以：

```text
HEADERS 到达 → 可建流 / 调度
完整请求及结束条件满足 → Unary 业务才可执行
```

源码：[注册与方法包装](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/server.go#L789)、[wrapUnaryHandler / processRPC](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/server.go#L1281)、[服务端 RecvMsg](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/stream.go#L1932)。

### 14.6 第六步：响应消息和最终状态分别提交

成功路径上，业务返回响应对象后，服务端 `SendMsg` 编码响应并交给发送队列；统一处理路径再通过 `WriteStatus` 提交最终状态。

```text
G-rpc：响应对象 → 编码 → 发送任务
G-rpc：最终 OK / 错误 → 状态任务
G-sw ：按协议顺序写响应头、DATA、终止 Trailers
```

响应消息与最终状态是两个概念：服务端可能返回错误而没有业务响应；客户端也可能收到某些数据后才得知最终失败。

源码：[最终状态发送](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/server.go#L1494)。

### 14.7 第七步：客户端 reader 分类分发

`G-cr` 从连接读取帧，用活动流表找到 `transport.ClientStream`：

| 输入 | 主要处理 |
| --- | --- |
| 响应 HEADERS | 记录 Metadata / 压缩信息等，通知等待头部的路径 |
| DATA | 向对应 `recvBuffer` 投递消息内容字节块 |
| 终止 Trailers | 保存最终 status / trailer，再投递 EOF 并完成终止通知 |
| 流或连接错误 | 进入相应关闭、取消和错误传播路径 |

并不是所有帧都作为业务数据塞进一个队列，也不是 reader 解码后直接调用客户端后续业务代码。

源码：[客户端 reader](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/internal/transport/http2_client.go#L1726)、[关闭流时保存状态](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/internal/transport/http2_client.go#L981)。

### 14.8 第八步：G-call 解码响应，确认最终结果

客户端 `invoke` 在发送请求后调用 `RecvMsg(reply)`。仍是 `G-call` 沿调用栈执行：

```text
等待本流头部 / 数据
  → 读取消息前缀和正文
  → 解压 / Unmarshal 到 reply
  → Unary 包装层继续确认没有第二条响应
  → 检查流的最终状态
  → 返回到 Stub
  → GetUser 返回给业务代码
```

成功 Unary 要求恰好一条响应且最终状态为 OK。只解码出第一条消息还不能确定成功；第二条响应、缺少正常响应或最终非 OK 状态都会影响结果。

源码：[Unary 客户端包装层](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/stream.go#L207)。

### 14.9 谁在等待，谁推进它

| 等待位置 | 等待者 | 常见推进或终止方式 |
| --- | --- | --- |
| 选连接 / 建流 | G-call | 可用 transport / 流资源出现，或错误、取消、deadline |
| 本地发送额度 | G-call 或 G-rpc | writer 消耗数据后补额度，或流关闭 |
| 实际 DATA 发送 | writer 管理的待发任务 | 窗口更新、网络可写或错误关闭 |
| 完整消息接收 | G-call 或 G-rpc | reader 投递更多字节 / 终止事件 |
| 最终状态 | 客户端 G-call | Trailers、流错误、连接错误或取消 |
| 数据库 / 下游调用 | 服务端业务协程 | 依赖完成、错误，或依赖配合取消 |

等待通常会挂起 goroutine，并不等于忙循环或持续独占一个操作系统线程。连接 reader 也可能等待网络和框架资源，不能笼统说它“永远不阻塞”。

完整时序见 [03 一次成功 Unary](03-sequence.html)。

<a id="hol"></a>

## 15. TCP 队头阻塞及缓解

### 15.1 丢失的不只是“某个 Stream 的前段”

同一 TCP 连接上，多个 HTTP/2 Stream 的帧混合进入一个有序字节序列：

```text
TCP 序列： [Stream 1 数据] [Stream 3 数据] [Stream 1 数据] [Stream 5 数据]
                              ↑ 对应的某段 TCP 数据丢失
```

TCP 需要先补齐前面的缺口，才把后续连续字节交给上层。即使后面的字节属于其他 HTTP/2 Stream，也可能暂时无法交付。

准确说法是：**HTTP/2 消除了应用层必须等待前一个响应完成才能处理下一个响应的部分限制，但共享 TCP 连接仍有跨流的传输层队头阻塞。**

这与某条流的业务处理慢不同：如果 reader 已读到其他流的数据，其他流仍可独立处理；TCP 缺口则可能让 reader 暂时根本拿不到后续字节。

### 15.2 如何处理

| 手段 | 可以改善什么 | 代价或限制 |
| --- | --- | --- |
| 改善丢包、拥塞和网络路径 | 减少触发队头阻塞的机会 | 不能消除 TCP 有序交付规则 |
| 控制消息大小、合理分块、避免长时间占满连接 | 减少排队和带宽争用 | 不会从协议层根除跨流 TCP 阻塞 |
| 将大流量长流与敏感短调用隔离到不同实际连接 | 缩小同一 TCP 缺口的影响范围 | 增加连接、握手与资源成本，仍可能共享网络瓶颈 |
| 多后端与适当负载均衡 | 分散负载、降低单点压力 | 不会迁移正在使用的流 |
| 具备支持条件时使用基于 QUIC 的传输 | 避免不同 QUIC 流因共同 TCP 字节序列而互相等待 | 需要客户端、服务端与代理完整支持 |

**多建几个 Stub 不等于多建物理连接。** 如果仍共用同一 Channel / transport，就没有实现连接隔离；任何连接池方案都应确认实际连接行为，而不是只数对象。

### 15.3 HTTP/3 / QUIC 的边界

QUIC 在传输层提供独立流，同一流仍然要求有序交付；某条流丢失数据，不要求其他流等待同一个 TCP 字节缺口。但拥塞控制、连接级资源和带宽仍可能造成共同影响。

这解释了 QUIC 对队头阻塞的改善方向，不能据此认为当前这套 grpc-go HTTP/2 实现已自动变成 HTTP/3，或更换一个地址前缀就能切换。[HTTP/3 规范背景](https://www.rfc-editor.org/rfc/rfc9114.html#section-1)

<a id="questions"></a>

## 16. 讨论中的疑惑与准确结论

| 当时的问题或理解 | 梳理后的结论 |
| --- | --- |
| gRPC 就是 HTTP body + 路径路由吗？ | 方向成立，还包括接口生成、消息封装、调用状态、流式、取消、错误和连接复用 |
| Proto 既要定义消息又要定义服务吗？ | 一个接口需要相应消息与服务契约；可以拆文件，并非每个 Proto 都必须两者齐全 |
| Protobuf 的 `rpc` 和普通消息有什么不同？ | `message` 定义数据，`service / rpc` 定义调用接口；运行时传输由框架负责 |
| 组装请求后怎样发，B 的地址谁知道？ | Stub 发起调用，Channel 根据创建时提供的 target 和解析结果选择连接 |
| Channel 是不是一条固定长连接？ | Channel 是长期逻辑对象，物理连接按策略和状态变化，通常复用 |
| 一个 service 一个 Stub 吗？ | 通常一个生成客户端类型；实例数不固定，多个类型可共用 Channel |
| Stream 就是 TCP 字节流吗？ | HTTP/2 Stream 是复用连接中的逻辑流，TCP 是它下面的字节传输 |
| Unary 没有 Stream 吗？ | Unary 同样使用底层流，只是每个方向的业务消息数量受限制 |
| 双向流两个协程共用 Stream 是因为同一 Stub 吗？ | 因为显式共用同一次调用返回的对象；同一 Stub 的两次调用会产生不同流 |
| 拦截器类似 Gin 中间件吗？ | 是，适合公共前后处理；接口位置及流式生命周期有自己的约束 |
| 一个流前面丢包，只堵这个流吗？ | HTTP/2 over TCP 下，同连接其他流的后续字节也可能因 TCP 缺口被延迟 |
| reader 负责拼出完整消息并交给协程吗？ | reader 解析帧、分发字节；RecvMsg 路径组装消息、解压和解码 |
| 缓冲区属于读取协程吗？ | 它属于 Stream，协程只是消费者 |
| Send 返回就说明发到了吗？ | 只说明当前发送提交成功，不能证明对端收取或业务完成 |
| Recv 得到响应就说明 RPC 成功吗？ | Unary 还要确认消息数和最终状态；流式还要继续接收直到正常终止或错误 |
| context 取消会杀掉业务吗？ | 不会强杀任意协程，业务和依赖必须配合取消 |
| 超时能立即重试扣款吗？ | 结果可能未知，先依赖业务幂等与结果核对来保证重试安全 |
| 每 RPC 独立协程，所以 server 字段无需加锁？ | 注册的实现对象可能被并发调用，共享可变状态仍需同步 |
| Keepalive 正常说明服务健康？ | 只说明相应连接通信可用，业务可服务性需另行判断 |

可用于快速复述的主线：

> Proto 定义消息和服务接口，生成代码把强类型方法接到 gRPC。客户端 Stub 通过长期复用的 Channel 为调用选择连接，并在 HTTP/2 Stream 中发送消息。两端连接 reader 读帧、按流分发，writer 调度并写帧；调用处理协程负责消息编解码和业务执行。每个调用有独立状态与流缓冲，但共享连接及部分资源。收到响应后仍要看最终状态；超时、取消与断线不能直接证明业务没有提交。

<a id="progress"></a>

## 17. 学习进度与后续顺序

本次已经覆盖了从接口定义到框架收发实现的完整主线。以下区分“讨论过”与“做过验证”，便于后续继续。

| 层次 | 已整理内容 | 验证边界 |
| --- | --- | --- |
| 基础概念 | RPC、Protobuf、Stub、Channel、连接与 Stream | 概念讨论与官方资料核对 |
| 调用行为 | 四种 RPC、Metadata、拦截器、Deadline、状态与重试 | 概念讨论、文档与接口核对 |
| 连接与运行 | 发现、负载均衡、背压、健康、保活、停机 | 原理讨论，未实测部署配置 |
| 底层实现 | 两端读写、流缓冲、路由、解码、最终状态 | 固定版本静态源码核对 |
| 图形材料 | 对象、双端架构、完整时序 | 结构、来源、浏览器自动检查 |
| 工程运行 | 真实调用、取消故障、重试重复、吞吐延迟 | 本次未执行 |

后续可以沿以下顺序继续，每次只验证一个问题：

| 下一步 | 动作 | 可观察输出 | 完成标准 |
| --- | --- | --- | --- |
| 最小 Unary | 实现并启动一个客户端和服务端 | 正常响应、参数错误和不存在状态 | 能把实际代码对应到 Stub → Invoke → handler |
| 并发与复用 | 多个 goroutine 共用一个客户端 | 并发调用结果、连接观察 | 能分清 RPC 数、流数和实际连接数 |
| 双向流 | 一个发送循环、一个接收循环 | 多条消息、半关闭与最终结束 | 能解释两个方向的独立推进，退出无遗留等待 |
| 超时与幂等 | 模拟业务提交后响应延迟 | 客户端超时、服务端已提交、重试查到同一结果 | 不把通信失败误判为业务回滚 |
| 源码断点 | 沿固定版本调用链设置断点 | 入队、reader 投递、RecvMsg 解码、Trailers 完成 | 能指出每一步执行协程和状态归属 |

这张表是后续学习建议，不表示这些实验已经完成。

<a id="sources"></a>

## 18. 源码与资料索引

### 18.1 固定版本源码入口

所有下面的实现链接均指向官方仓库的固定提交，避免文档描述随主分支变化。

| 阅读主题 | 源码入口 |
| --- | --- |
| 客户端创建与连接对象 | [clientconn.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/clientconn.go) |
| Unary 调用主线 | [call.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/call.go) |
| 逻辑调用、attempt、SendMsg / RecvMsg | [stream.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/stream.go) |
| 客户端 HTTP/2 transport | [http2_client.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/internal/transport/http2_client.go) |
| 服务端 HTTP/2 transport | [http2_server.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/internal/transport/http2_server.go) |
| 接收缓冲与 transport 公共结构 | [transport.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/internal/transport/transport.go) |
| 连接发送队列与 loopyWriter | [controlbuf.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/internal/transport/controlbuf.go) |
| 本地额度与 HTTP/2 流控 | [flowcontrol.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/internal/transport/flowcontrol.go) |
| 消息长度解析与解码工具 | [rpc_util.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/rpc_util.go) |
| 服务注册、调度、路由、统一处理与停机 | [server.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/server.go) |
| 生成 Stub、服务接口和 handler | [helloworld_grpc.pb.go](https://github.com/grpc/grpc-go/blob/c9ab42cdb0a2b3e7b9d5510ebbc999638ee41eb7/examples/helloworld/helloworld/helloworld_grpc.pb.go) |

### 18.2 继续查阅的官方资料

- [gRPC 核心概念](https://grpc.io/docs/what-is-grpc/core-concepts/)
- [Go 基础教程](https://grpc.io/docs/languages/go/basics/)
- [gRPC over HTTP/2 协议约定](https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-HTTP2.md)
- [HTTP/2 规范 RFC 9113](https://www.rfc-editor.org/rfc/rfc9113.html)
- [HTTP/3 规范 RFC 9114](https://www.rfc-editor.org/rfc/rfc9114.html)

官网文档用于解释通用概念；与本次函数名、协程和缓冲结构相关的结论，以固定版本源码为准。
