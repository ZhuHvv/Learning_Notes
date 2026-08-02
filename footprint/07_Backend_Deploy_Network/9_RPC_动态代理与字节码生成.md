# 07.09 RPC 动态代理与字节码生成

## 1. 总体性概念

动态代理和字节码生成解决的是 RPC 中的一个关键问题：**业务代码调用的是接口方法，但真正执行的不是本地实现，而是一段自动生成的“网络调用逻辑”**。

例如业务代码写：

```java
UserService userService = RpcClient.getProxy(UserService.class);
UserDTO user = userService.getUser("1001");
```

看起来像调用本地对象，实际上 `userService` 是一个代理对象。代理对象接管 `getUser` 方法调用，把它转换成 RPC 请求：

```text
getUser("1001")
  ↓
代理拦截 method + args
  ↓
构造 RpcRequest
  ↓
序列化并发送给远程服务
  ↓
收到响应后反序列化
  ↓
返回 UserDTO
```

动态代理强调“运行时生成代理对象”；字节码生成强调“直接生成 JVM 能执行的 class 字节码”。二者经常一起出现。需要注意：JDK 动态代理本身也是在运行时生成 `$Proxy` 字节码类，只是所有方法体统一转发到 `InvocationHandler`（内部经反射 `Method` 调用）；真正的对立不是“反射 vs 字节码”，而是“统一转发+反射调用”vs“为每个方法生成直连调用的字节码”。

## 2. 原理性解释

### 2.1 为什么 RPC 需要代理

如果没有代理，业务代码需要这样写：

```java
RpcRequest req = new RpcRequest();
req.setService("UserService");
req.setMethod("getUser");
req.setArgs(new Object[]{"1001"});
byte[] body = codec.encode(req);
byte[] respBytes = transport.send("10.0.0.8:9000", body);
RpcResponse resp = codec.decode(respBytes);
UserDTO user = (UserDTO) resp.getResult();
```

这会让每个远程方法调用都充满重复样板代码。动态代理把这些样板代码集中到框架里，让业务层只关心接口调用。

### 2.2 静态代理、动态代理与字节码生成的区别

```text
静态代理：提前手写 UserServiceProxy 类
动态代理：运行时根据 UserService 接口生成代理对象
字节码生成：直接生成 .class 字节码，让代理方法变成真实 JVM 方法
```

#### 静态代理

```java
class UserServiceProxy implements UserService {
    public UserDTO getUser(String id) {
        return rpcClient.invoke("UserService", "getUser", new Object[]{id});
    }
}
```

优点是直观，缺点是接口多时要写大量重复代理类。

#### 动态代理

动态代理让框架在运行时根据接口生成代理对象。业务方只传入 `UserService.class`，框架自动返回一个实现了该接口的对象。

JDK 动态代理的核心是 `InvocationHandler`：所有接口方法调用都会进入 `invoke`。

#### 字节码生成

字节码生成可以使用 ASM、Javassist、ByteBuddy、CGLIB 等工具（注：CGLIB 原项目已停止维护，Java 17+ 的兼容依赖各框架内嵌的 fork，如 Spring 的重打包版；新项目建议选择 ByteBuddy/ASM），直接生成类似下面的代理类：

```java
public class UserService$Proxy implements UserService {
    private RpcClient client;

    public UserDTO getUser(String id) {
        return (UserDTO) client.invoke("UserService", "getUser", new Object[]{id});
    }
}
```

它的好处是减少反射开销，也可以做更细的优化；缺点是实现复杂、调试难度更高。

### 2.3 RPC 框架中代理对象的本质

代理对象不是业务对象，它更像一个“本地壳子”。这个壳子负责：

1. 记录当前调用的是哪个接口。
2. 记录当前调用的是哪个方法。
3. 收集方法参数。
4. 读取上下文信息，例如 traceId、deadline、鉴权 token。
5. 构造 RPC 请求包。
6. 调用底层 transport 发送。
7. 把响应转换成方法返回值。

因此你可以把“客户端代理”理解为 RPC 的入口适配层：它把语言层面的函数调用适配为网络层面的消息传输。

## 3. 机制流程

### 3.1 动态代理生成流程

```text
业务传入接口 UserService.class
  ↓
RPC 框架读取接口方法列表
  ↓
生成代理对象 proxy
  ↓
业务调用 proxy.getUser("1001")
  ↓
调用被 InvocationHandler / 拦截器捕获
  ↓
构造 Invocation：接口名、方法名、参数、返回类型
  ↓
交给 RpcClient 进行编码、路由、发送、解码
```

### 3.2 字节码生成流程

```text
读取接口元数据
  ↓
拼装代理类结构：类名、字段、构造函数、方法
  ↓
为每个接口方法生成方法体
  ↓
方法体中写入 rpcClient.invoke(...) 调用逻辑
  ↓
把字节码加载进 JVM
  ↓
实例化代理对象并返回给业务代码
```

### 3.3 与 RPC 调用链的关系

```text
动态代理/字节码生成
  ↓ 负责制造“客户端代理”
客户端代理
  ↓ 负责把方法调用转成 RpcRequest
编解码器
  ↓ 负责把 RpcRequest 转成字节
网络层
  ↓ 负责传输
服务端代理
  ↓ 负责把字节转回方法调用
真实业务服务
```

动态代理解决的是“调用入口如何自动化”；编解码解决的是“调用信息如何传输”；服务注册和心跳解决的是“该发给哪台机器”。

## 4. 类比理解

动态代理像一个“自动秘书”：你对秘书说“帮我查用户 1001”，秘书知道要怎么写请求、发给哪个部门、等待结果并转述给你。

字节码生成像“为每个部门定制一位专职秘书”：秘书不是临时查规则，而是已经被训练成固定动作，执行更直接，但培养和维护成本更高。

## 5. 应用举例 / 代码或伪代码

### 5.1 JDK 动态代理示例

```java
public interface UserService {
    UserDTO getUser(String id);
}

public class RpcProxyFactory {
    @SuppressWarnings("unchecked")
    public static <T> T create(Class<T> interfaceClass, RpcClient client) {
        return (T) Proxy.newProxyInstance(
            interfaceClass.getClassLoader(),
            new Class[]{interfaceClass},
            (Object proxy, Method method, Object[] args) -> {
                RpcRequest req = new RpcRequest();
                req.setService(interfaceClass.getName());
                req.setMethod(method.getName());
                req.setParamTypes(method.getParameterTypes());
                req.setArgs(args);
                req.setRequestId(UUID.randomUUID().toString());

                RpcResponse resp = client.invoke(req);
                if (resp.getError() != null) {
                    throw new RuntimeException(resp.getError());
                }
                return resp.getResult();
            }
        );
    }
}
```

业务侧：

```java
UserService userService = RpcProxyFactory.create(UserService.class, rpcClient);
UserDTO user = userService.getUser("1001");
```

### 5.2 代理方法的伪字节码逻辑

真实字节码不适合直接背，但可以理解为自动生成了这样的代码：

```java
public UserDTO getUser(String id) {
    RpcRequest req = new RpcRequest(
        "com.demo.UserService",
        "getUser",
        new Object[]{id}
    );
    return (UserDTO) rpcClient.invoke(req).getResult();
}
```

### 5.3 Go 里的类比实现

Go 没有 Java 那样通用的运行时动态代理机制，工程里通常通过代码生成或显式 client struct 实现类似能力：

```go
type UserServiceClient struct {
    rpc *Client
}

func (c *UserServiceClient) GetUser(ctx context.Context, id string) (*UserDTO, error) {
    req := RpcRequest{
        Service: "UserService",
        Method:  "GetUser",
        Args:    []any{id},
    }
    var resp UserDTO
    err := c.rpc.Invoke(ctx, req, &resp)
    return &resp, err
}
```

gRPC 生成的 Go client stub，本质上就是这种“代码生成版代理”。

## 6. 你在讨论中的理解推进

- 起点：你问“RPC 中动态代理和字节码生成是什么”。
- 推进：你已经能把 RPC 主流程描述为客户端代理组包、服务端代理解包并调用真实服务。
- 关键补充：动态代理/字节码生成解释的是“客户端代理这个对象从哪里来、为什么业务代码可以像本地调用一样写”。
- 更精确表达：动态代理是运行时生成代理对象的技术；字节码生成是生成代理对象的一种更底层、更高性能的实现方式。

## 7. 常见误区与排查思路

- **误区 1：动态代理就是 RPC。** 动态代理只是 RPC 客户端调用入口的实现方式之一。
- **误区 2：字节码生成一定比反射好。** 它可能更快，但增加了复杂度；很多场景瓶颈在网络和序列化，不在代理调用本身。
- **误区 3：代理对象里有真实业务逻辑。** 客户端代理通常不执行业务，只负责把调用转成请求。
- **误区 4：忽略接口版本。** 代理根据接口生成，如果客户端和服务端接口不一致，会出现序列化、参数、返回值不兼容。

排查时重点看：接口定义是否一致、代理是否生成成功、方法名/参数类型是否匹配、序列化协议是否兼容、调用是否进入服务端。

## 8. 关联知识点

- `002_RPC_与_gRPC：服务间调用.md`：RPC 总体调用链。
- `010_RPC_心跳、服务注册与可用性检测.md`：代理如何找到可用服务实例。
- `../01_LLM_Transformer/8_Prompt、XML_JSON_与工具调用格式.md`：结构化调用思想上类似“把意图转换成可执行请求”。
- [LangGraph 状态更新、invoke 与 stream](../02_Agent_RAG_Memory/11_LangGraph_状态更新、invoke_与_stream.md)：框架如何隐藏底层执行细节。

## 9. 复习检查问题

- 为什么 RPC 框架需要客户端代理？
- 静态代理、动态代理、字节码生成分别解决什么问题？
- JDK 动态代理的 `InvocationHandler` 在 RPC 中通常做什么？
- gRPC 生成的 client stub 和动态代理有什么共同点？
- 为什么说代理对象是“本地壳子”，而不是真实服务对象？
