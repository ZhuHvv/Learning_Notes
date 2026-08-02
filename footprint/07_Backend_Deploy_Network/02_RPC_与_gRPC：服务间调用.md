# 07.02 RPC 与 gRPC：服务间调用

## 1. 总体性概念

RPC（Remote Procedure Call，远程过程调用）解决的问题是：**一个服务想调用另一个服务的能力，但不希望业务代码到处手写网络连接、序列化、路由、超时、重试和结果解析**。

所以 RPC 框架会把一次远程调用包装成“像本地方法调用一样”的形式。业务代码看到的是：

```go
user, err := userClient.GetUser(ctx, &GetUserRequest{Id: "1001"})
```

但框架内部实际做了：

```text
本地方法调用
  ↓
客户端代理收集 method + args
  ↓
编码 / 序列化 / 组包
  ↓
网络传输
  ↓
服务端代理解码 / 解包
  ↓
反射或分发表调用真正服务实现
  ↓
结果编码并原路返回
```

gRPC 是一种主流 RPC 实现：它通常使用 Protobuf 定义接口和消息结构，使用 HTTP/2 传输，提供强类型代码生成、流式调用、拦截器、deadline、metadata 等工程能力。

## 2. 原理性解释

RPC 的核心不是“协议名字”，而是 **调用抽象 + 编解码 + 传输 + 服务治理** 这几层组合。

### 2.1 调用抽象：把远程调用伪装成本地调用

在普通 HTTP 调用中，你经常会写：

```text
拼 URL → 设置 header → JSON 序列化 → 发 HTTP → 解析 JSON → 判断状态码
```

RPC 希望把这些样板代码隐藏起来。业务代码只依赖接口：

```java
UserService userService = RpcClient.create(UserService.class);
UserDTO user = userService.getUser("1001");
```

这里的 `userService` 不一定是真实业务对象，通常是一个 **客户端代理对象**。它拦截 `getUser("1001")` 这次方法调用，然后把它转换成一条网络请求。

### 2.2 编解码：把方法调用转换成网络可传输的数据

方法调用本身不能直接在网络上传输。RPC 需要把它变成请求包，例如：

```json
{
  "service": "UserService",
  "method": "GetUser",
  "requestId": "req-10001",
  "args": {"id": "1001"}
}
```

这个过程就是编码/序列化/组包。服务端收到后，再解码/反序列化/解包，找到目标服务和目标方法。

gRPC 中，这一步通常由 Protobuf 完成；Dubbo、Thrift、Hessian、JSON-RPC 等 RPC 框架也都有自己的协议与序列化方案。

### 2.3 服务端代理：把网络请求还原成真实方法调用

服务端不会把所有请求都写成一个巨大的 `if else`。它通常会维护一个服务方法映射表：

```text
"UserService.GetUser" → UserServiceImpl.GetUser
"OrderService.CreateOrder" → OrderServiceImpl.CreateOrder
```

服务端代理收到请求后：

1. 解析服务名和方法名。
2. 找到本地注册的实现对象。
3. 把参数反序列化成语言内对象。
4. 调用真实方法。
5. 把返回值或异常重新编码返回。

### 2.4 RPC 不只是调用，还包含服务治理

真实项目中的 RPC 还要解决：

- 服务注册与发现：服务实例在哪里？
- 负载均衡：多个实例选哪个？
- 心跳与健康检查：实例还活着吗？
- 超时与取消：调用不能无限等待。
- 重试与幂等：失败后能不能重试？
- 熔断与限流：下游异常时如何保护系统？
- 观测性：如何知道一次跨服务调用在哪里失败？

所以你可以把 RPC 理解成：

```text
RPC = 远程调用语法糖 + 编解码协议 + 网络传输 + 服务治理能力
```

## 3. 机制流程

### 3.1 一次 RPC 调用的完整链路

```text
业务代码调用 userClient.GetUser(ctx, req)
  ↓
客户端代理捕获接口名、方法名、参数、上下文
  ↓
生成 requestId，设置 deadline、metadata、traceId
  ↓
编码请求体：service/method/args
  ↓
从注册中心或连接池中选择服务实例
  ↓
通过 TCP / HTTP2 / 自定义协议发送请求
  ↓
服务端网络层接收字节流
  ↓
服务端代理解码出 service/method/args
  ↓
根据服务注册表找到 UserServiceImpl.GetUser
  ↓
执行真实业务逻辑，访问 DB/Redis/MQ 等依赖
  ↓
编码 response：requestId/status/result/error
  ↓
客户端收到响应，通过 requestId 匹配等待中的调用
  ↓
解码结果，返回给业务代码
```

### 3.2 与你今天总结的对应关系

你的总结可以进一步精炼为：

> 客户端把调用请求交给客户端代理，客户端代理把调用信息编码/组包后发送给服务端；服务端代理收到后解码/解包，再交给真实服务对象执行；执行结果再按反向流程编码、传输、解码，最终返回给客户端调用方。

这是非常准确的主线。后续学习 RPC 时，只要围绕这条主线继续补：**代理如何生成、包如何编码、服务如何发现、失败如何处理**，就能把大多数 RPC 框架串起来。

## 4. 类比理解

RPC 像你在公司里“拨内线找另一个部门办事”：

- 你不需要知道对方办公室的物理位置，只要知道“找用户部门查用户”。
- 前台/总机相当于服务发现和路由。
- 电话线路相当于网络传输。
- 你说的话需要变成对方能理解的格式，相当于序列化协议。
- 对方办完后把结果告诉你，相当于响应返回。

动态代理则像“你的秘书”：你只说“帮我查用户”，秘书会自动帮你拨号、传话、记录结果。

## 5. 应用举例 / 代码或伪代码

### 5.1 Protobuf 定义 gRPC 服务

```proto
syntax = "proto3";

service UserService {
  rpc GetUser(GetUserRequest) returns (GetUserReply);
}

message GetUserRequest {
  string id = 1;
}

message GetUserReply {
  string id = 1;
  string name = 2;
}
```

生成代码后，客户端通常只需要调用 stub：

```go
// grpc-go 1.63+ 推荐 NewClient；grpc.Dial 与 grpc.WithInsecure() 均已弃用
conn, err := grpc.NewClient("user-service:9000",
    grpc.WithTransportCredentials(insecure.NewCredentials()))
if err != nil {
    log.Fatal(err)
}
client := pb.NewUserServiceClient(conn)

ctx, cancel := context.WithTimeout(context.Background(), time.Second)
defer cancel()

resp, err := client.GetUser(ctx, &pb.GetUserRequest{Id: "1001"})
```

### 5.2 简化版 RPC 请求包

```go
type RpcRequest struct {
    RequestID string        `json:"request_id"`
    Service   string        `json:"service"`
    Method    string        `json:"method"`
    Args      []interface{} `json:"args"`
}

type RpcResponse struct {
    RequestID string      `json:"request_id"`
    Error     string      `json:"error"`
    Result    interface{} `json:"result"`
}
```

### 5.3 服务端代理分发伪代码

```go
func handleRpcRequest(req RpcRequest) RpcResponse {
    key := req.Service + "." + req.Method
    handler := serviceRegistry[key]
    if handler == nil {
        return RpcResponse{RequestID: req.RequestID, Error: "method not found"}
    }

    result, err := handler.Call(req.Args)
    if err != nil {
        return RpcResponse{RequestID: req.RequestID, Error: err.Error()}
    }
    return RpcResponse{RequestID: req.RequestID, Result: result}
}
```

## 6. 你在讨论中的理解推进

- 起点：你先把 RPC 理解为“客户端调用请求经过代理编码后发给服务端，服务端解码后调用真实服务，再反向返回”。
- 修正与补充：这里的“客户代理/服务器代理”不是额外业务模块，而是 RPC 框架用来屏蔽网络细节的关键抽象。
- 今日新增：动态代理/字节码生成解释了“客户端代理从哪里来”；心跳与服务注册解释了“代理如何知道服务端在哪里、服务是否还可用”。
- 更完整的表达：RPC 的主线是调用链，服务治理是支撑调用链稳定运行的外围系统。


### gRPC 与 Go Protobuf 生成代码的衔接

gRPC 中的“客户端代理”并不一定依赖运行时动态代理，而是通过代码生成提前把代理类写出来：`protoc-gen-go` 生成消息结构体（xxx.pb.go），`protoc-gen-go-grpc` 生成 client stub 与 server interface（xxx_grpc.pb.go），`option go_package` 决定生成代码的 Go import path。Go 侧工具链细节（go_package、生成路径、proto 组织与常见报错）见 `017_Protobuf_go_package、生成路径与_proto_文件组织.md`。

## 7. 常见误区与排查思路

- **误区 1：RPC 等于 HTTP。** RPC 可以跑在 HTTP/2、TCP、自定义协议等之上；HTTP 只是传输选择之一。
- **误区 2：像本地调用就可以按本地调用思考。** 远程调用一定有网络失败、超时、重复请求、部分成功等问题。
- **误区 3：重试一定安全。** 查询通常容易重试，扣款、下单、发奖等写操作必须考虑幂等。
- **误区 4：只看客户端错误。** RPC 失败可能来自注册中心、负载均衡、连接池、超时配置、服务端异常、序列化不兼容、网络抖动。

排查 RPC 问题时可以按这条链路定位：

```text
接口定义是否一致 → 服务是否注册 → 实例是否健康 → 连接是否建立 → 请求是否编码成功 → 服务端是否找到方法 → 业务是否执行成功 → 响应是否解码成功
```

## 8. 关联知识点

- `009_RPC_动态代理与字节码生成.md`：解释客户端代理如何自动生成。
- `010_RPC_心跳、服务注册与可用性检测.md`：解释服务实例如何注册、续约和摘除。
- `005_Kubernetes、服务发现与弹性部署.md`：解释容器环境中的服务发现与弹性部署。
- `006_Prometheus、Grafana、OpenTelemetry_与日志.md`：解释跨服务调用的观测与排障。
- `007_HTTP_Streaming、SSE、WebSocket_与_gRPC_Streaming.md`：解释 RPC/gRPC 和流式协议的关系。

## 9. 复习检查问题

- RPC 为什么能让远程调用看起来像本地方法调用？
- 客户端代理和服务端代理分别做了哪些事情？
- 编码/解码和序列化/反序列化在 RPC 中解决什么问题？
- 服务注册、心跳、负载均衡和超时分别属于 RPC 调用链的哪一层？
- 为什么 RPC 调用必须考虑幂等、重试和 trace？
