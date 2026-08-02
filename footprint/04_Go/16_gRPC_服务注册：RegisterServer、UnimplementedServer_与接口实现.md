# 04.16 gRPC 服务注册：RegisterServer、UnimplementedServer 与接口实现

> 所属主线：Go RPC 与代码生成  
> 难度：深入  
> 前置知识：Go 接口与方法集、Protobuf 生成代码  
> 后续知识：gRPC 拦截器、流式 RPC 与可观测性

## 1. 总体性概念

gRPC 的 Go 代码生成后，通常会得到三类关键内容：

1. 服务接口，例如 `TradeServer`；
2. 注册函数，例如 `RegisterTradeServer(s grpc.ServiceRegistrar, srv TradeServer)`；
3. 默认未实现结构体，例如 `UnimplementedTradeServer`。

考虑下面的例子：

```go
type Trade struct {
    msg.UnimplementedTradeServer
}

func (this Trade) Buy(ctx context.Context, req *msg.TradeReq) (*msg.TradeRes, error) {
    return &msg.TradeRes{Status: 200, Msg: "ok"}, nil
}

msg.RegisterTradeServer(goodsServer, new(Trade))
```

为什么能通过？核心原因是：`RegisterTradeServer` 的第二个参数要求实现 `TradeServer` 接口，而 `new(Trade)` 的类型是 `*Trade`。由于 `Buy` 是值接收器方法，`Trade` 和 `*Trade` 都拥有这个方法，所以 `*Trade` 满足 `TradeServer`。

## 2. 原理性解释

### 2.1 生成的 TradeServer 接口是什么

根据 `.proto` 中的：

```proto
service Trade {
  rpc Buy(TradeReq) returns (TradeRes);
}
```

`protoc-gen-go-grpc` 会生成类似代码：

```go
type TradeServer interface {
    Buy(context.Context, *TradeReq) (*TradeRes, error)
    mustEmbedUnimplementedTradeServer()
}
```

具体生成细节会随插件版本和生成选项变化，但本质上它要求服务端类型提供 `Buy` 方法。默认配置下，为了向前兼容，服务实现应嵌入 `UnimplementedTradeServer`；若显式关闭 `require_unimplemented_servers`，生成接口可能没有强制嵌入方法，但通常不建议放弃该兼容机制。

### 2.2 UnimplementedTradeServer 的作用

`UnimplementedTradeServer` 不是业务逻辑，而是默认实现。它的意义主要有两个：

- **向前兼容**：以后 proto 新增 RPC 方法时，旧服务端即使没实现新方法，也能通过嵌入默认实现保持编译兼容。
- **明确未实现行为**：未实现的方法被调用时返回类似 `Unimplemented` 的错误，而不是静默失败。

可以理解为：你自己的 `Trade` 结构体只实现真正关心的业务方法，其余未实现方法由嵌入结构体兜底。

应按值嵌入：

```go
type Trade struct {
    msg.UnimplementedTradeServer
}
```

不要嵌入 `*msg.UnimplementedTradeServer`。指针字段若保持 nil，调用提升的方法可能触发 nil 指针问题；生成代码也通常会在注册时检查这种不安全用法。

### 2.3 为什么 `new(Trade)` 可以传给 RegisterTradeServer

`new(Trade)` 等价于：

```go
&Trade{}
```

它返回 `*Trade`。你的 `Buy` 方法是：

```go
func (this Trade) Buy(...)
```

这是值接收器，所以 `Trade` 和 `*Trade` 都拥有 `Buy` 方法。再加上 `Trade` 嵌入了 `UnimplementedTradeServer`，于是 `*Trade` 满足 `TradeServer` 接口。

如果你把方法改成指针接收器：

```go
func (this *Trade) Buy(...)
```

那么 `*Trade` 仍然满足接口，`Trade` 值本身通常不满足接口。gRPC 服务注册实践中一般传指针对象，因为服务实现往往需要持有数据库连接、配置、缓存或内部状态。

## 3. 机制流程

```text
.proto 定义 service Trade
  ↓
protoc-gen-go-grpc 生成 TradeServer 接口和 RegisterTradeServer 函数
  ↓
开发者定义 Trade struct
  ↓
嵌入 UnimplementedTradeServer 获得默认未实现方法
  ↓
实现 Buy 等业务方法
  ↓
调用 RegisterTradeServer(grpcServer, &Trade{})
  ↓
gRPC Server 将方法名映射到具体 handler
  ↓
请求到达时反序列化参数并调用 Trade.Buy
```

## 4. 类比理解

`.proto service` 像接口合同；`TradeServer` 是 Go 版合同；`Trade` 是你写的承包商；`UnimplementedTradeServer` 像合同里“默认不承接的条款兜底”；`RegisterTradeServer` 则是把承包商登记到服务大厅，让外部请求能找到它。

## 5. 应用举例 / 代码或伪代码

### 5.1 推荐写法：指针接收器 + 构造函数

```go
type Trade struct {
    msg.UnimplementedTradeServer
    repo *TradeRepository
}

func NewTrade(repo *TradeRepository) *Trade {
    return &Trade{repo: repo}
}

func (t *Trade) Buy(ctx context.Context, req *msg.TradeReq) (*msg.TradeRes, error) {
    // 1. 校验参数
    if req.GoodsId == 0 {
        return nil, status.Error(codes.InvalidArgument, "goods_id required")
    }

    // 2. 调用业务层或仓储层
    if err := t.repo.CreateOrder(ctx, req.UserId, req.GoodsId); err != nil {
        slog.Error("create order failed", "err", err)
        return nil, status.Error(codes.Internal, "create order failed")
    }

    // 3. 返回响应
    return &msg.TradeRes{Status: 200, Msg: "ok"}, nil
}

func main() {
    grpcServer := grpc.NewServer()
    msg.RegisterTradeServer(grpcServer, NewTrade(repo))
}
```

### 5.2 编译期检查

```go
var _ msg.TradeServer = (*Trade)(nil)
```

这样如果 `Trade` 少实现了某个方法，或者方法签名不一致，编译期就能发现。

### 5.3 gRPC 注册函数的伪代码

生成代码里的注册过程可以抽象为：

```go
func RegisterTradeServer(s grpc.ServiceRegistrar, srv TradeServer) {
    s.RegisterService(&grpc.ServiceDesc{
        ServiceName: "msg.Trade",
        Methods: []grpc.MethodDesc{
            {MethodName: "Buy", Handler: buyHandler},
        },
    }, srv)
}
```

RPC 到来时，gRPC 框架根据服务名和方法名找到 handler，再回调你的 `srv.Buy(ctx, req)`。

## 6. 常见误区与排查思路

- **误区 1：`UnimplementedTradeServer` 就是业务实现。** 它只是默认未实现兜底。
- **误区 2：Register 函数会自动帮你实现接口。** 不会，接口匹配仍由 Go 编译器完成。
- **误区 3：值接收器和指针接收器随便写。** 服务端通常建议用指针接收器，方便共享依赖和避免拷贝。
- **误区 4：直接把内部错误文本返回客户端。** 这可能泄露数据库、路径或下游信息；应在服务端记录详细错误，对外返回稳定的 gRPC 状态码和安全消息。

排查时优先确认三件事：

```text
1. 生成的接口方法签名是什么？
2. 我的 struct 是否实现完全一致的方法？
3. 我传给 Register 的是值还是指针？
```

## 7. 关联知识点

- Go 接口实现、方法集与指针接收器
- Protobuf `go_package`、生成路径与 proto 文件组织
- Context：取消、超时与值传递
- gRPC unary、server-streaming、client-streaming 与双向流

## 8. 复习检查问题

- `new(Trade)` 的类型是什么？
- 为什么值接收器方法能让 `*Trade` 也实现接口？
- `UnimplementedTradeServer` 解决的是什么兼容性问题？
- gRPC 注册函数本质上把什么东西登记到了服务端？
