# 07.10 RPC 心跳、服务注册与可用性检测

## 1. 总体性概念

在 RPC 系统中，客户端代理知道要调用 `UserService.GetUser`，但它还需要知道：**UserService 当前部署在哪些机器上？哪些实例还活着？应该调用哪一个？**

这就引出了服务注册、服务发现和心跳机制。

```text
服务提供者启动
  ↓
向注册中心注册：服务名、地址、端口、元数据
  ↓
周期性发送心跳，证明自己仍然可用
  ↓
注册中心维护健康实例列表
  ↓
服务消费者查询或订阅实例列表
  ↓
客户端负载均衡后发起 RPC 调用
```

心跳的核心作用是：**让注册中心或对端知道某个服务实例是否还存活**。如果一段时间没有收到心跳，就认为该实例不健康，把它从可用列表中摘除或标记为不可用。

## 2. 原理性解释

### 2.1 为什么只注册一次不够

服务启动时注册一次，只能说明“它启动过”，不能说明“它现在还活着”。

真实环境中可能发生：

- 进程崩溃。
- 容器被 kill。
- 机器断网。
- 端口被防火墙阻断。
- 服务线程池耗尽，进程还在但无法处理请求。

如果注册中心仍把这些实例当作可用实例，客户端就会不断把请求打到坏节点上。因此服务注册必须配合心跳或健康检查。

### 2.2 注册中心维护的是“服务名到实例列表”的映射

注册中心可以理解为一个动态电话簿：

```text
UserService
  ├─ 10.0.0.1:9000, healthy, version=v1
  ├─ 10.0.0.2:9000, healthy, version=v1
  └─ 10.0.0.3:9000, unhealthy, version=v1

OrderService
  ├─ 10.0.1.1:9100, healthy
  └─ 10.0.1.2:9100, healthy
```

客户端调用 `UserService` 时，不需要写死 IP，而是从注册中心拿到健康实例列表，再由负载均衡策略选择一个实例。

### 2.3 心跳通常是租约续期

很多注册中心采用 lease/TTL 思想：

```text
服务实例注册时获得一个租约，租约有效期 30 秒。
实例每 10 秒发送一次心跳续期。
如果超过 30 秒没有续期，注册中心认为实例失效。
```

也就是说，心跳不是“业务请求”，而是“存活证明”。它维护的是控制面状态，不直接承载业务数据。

### 2.4 心跳与健康检查的区别

- 心跳：通常由服务实例主动告诉注册中心“我还活着”。
- 健康检查：注册中心或探针主动请求服务实例的 `/health` 或 RPC health 方法，判断它是否可用。

二者可以结合：服务主动续约，注册中心也可以主动探测。

### 2.5 心跳不等于绝对健康

能发心跳只能说明进程或连接还在，不一定说明业务完全正常。例如：

- 服务能回心跳，但数据库连接池已经耗尽。
- 服务能回 `/health`，但某个核心依赖超时。
- 网络分区导致注册中心误判。

所以成熟系统会区分：

```text
进程存活 liveness
服务就绪 readiness
依赖健康 dependency health
实例权重 weight
熔断状态 circuit breaker state
```

## 3. 机制流程

### 3.1 服务提供者启动注册

```text
读取配置：serviceName、ip、port、version、metadata
  ↓
启动 RPC Server，监听端口
  ↓
向注册中心发送 register 请求
  ↓
注册中心写入实例表，并设置 TTL
  ↓
服务提供者启动 heartbeat 定时任务
```

### 3.2 心跳续约流程

```text
每隔 heartbeatInterval 秒
  ↓
服务实例向注册中心发送 heartbeat(instanceId)
  ↓
注册中心更新 lastSeen / leaseExpireTime
  ↓
如果持续未收到心跳
  ↓
实例被标记为 unhealthy 或从可用列表移除
  ↓
消费者收到变更通知或下次拉取时不再使用该实例
```

### 3.3 服务消费者发现与调用

```text
客户端代理准备调用 UserService.GetUser
  ↓
从本地缓存获取 UserService 健康实例列表
  ↓
如果缓存为空或过期，访问注册中心拉取
  ↓
负载均衡选择一个实例
  ↓
发起 RPC 调用
  ↓
如果调用失败，根据错误类型决定重试、熔断或刷新实例列表
```

### 3.4 优雅下线流程

```text
服务收到 shutdown 信号
  ↓
先向注册中心 unregister 或标记 draining
  ↓
停止接收新请求
  ↓
等待正在处理的请求完成
  ↓
关闭连接池、释放资源
  ↓
进程退出
```

优雅下线可以避免“实例已经准备退出，但客户端还继续把新请求打过来”。

## 4. 类比理解

注册中心像公司的“通讯录系统”：记录每个部门当前有哪些值班人员、电话号码是多少。

心跳像值班人员每隔一段时间打卡：

- 正常打卡：通讯录显示可联系。
- 长时间不打卡：系统认为这个人离岗，暂时不再把电话转给他。
- 优雅下线：值班人员主动告诉系统“我马上下班，别再派新任务给我”。

## 5. 应用举例 / 代码或伪代码

### 5.1 注册中心数据结构伪代码

```go
type Instance struct {
    ID        string
    Service   string
    Address   string
    Metadata  map[string]string
    LastSeen  time.Time
    TTL       time.Duration
    Healthy   bool
}

var registry = map[string]map[string]*Instance{}
```

### 5.2 服务注册与心跳

```go
func Register(inst *Instance) {
    if registry[inst.Service] == nil {
        registry[inst.Service] = map[string]*Instance{}
    }
    inst.LastSeen = time.Now()
    inst.Healthy = true
    registry[inst.Service][inst.ID] = inst
}

func Heartbeat(service, instanceID string) {
    inst := registry[service][instanceID]
    if inst == nil {
        return
    }
    inst.LastSeen = time.Now()
    inst.Healthy = true
}
```

### 5.3 TTL 过期检测

```go
func SweepExpiredInstances() {
    ticker := time.NewTicker(3 * time.Second)
    for range ticker.C {
        now := time.Now()
        for _, instances := range registry {
            for _, inst := range instances {
                if now.Sub(inst.LastSeen) > inst.TTL {
                    inst.Healthy = false
                }
            }
        }
    }
}
```

### 5.4 客户端服务发现与负载均衡

```go
func PickInstance(service string) (*Instance, error) {
    var healthy []*Instance
    for _, inst := range registry[service] {
        if inst.Healthy {
            healthy = append(healthy, inst)
        }
    }
    if len(healthy) == 0 {
        return nil, errors.New("no healthy instance")
    }

    // 简化：轮询、随机、权重都可以
    return healthy[rand.Intn(len(healthy))], nil
}
```

### 5.5 RPC 调用中使用服务发现

```go
func (c *RpcClient) Invoke(ctx context.Context, req RpcRequest, resp any) error {
    inst, err := c.discovery.Pick(req.Service)
    if err != nil {
        return err
    }

    conn := c.pool.Get(inst.Address)
    return conn.Send(ctx, req, resp)
}
```

## 6. 你在讨论中的理解推进

- 起点：你问“心跳是什么，以及 RPC 如何通过心跳注册服务”。
- 关键修正：服务注册不是只靠心跳完成，通常是“启动时注册 + 周期性心跳续约 + 过期摘除/健康标记”。
- 推进：心跳让注册中心知道实例是否仍然可用，客户端代理再通过服务发现拿到健康实例列表。
- 更完整表达：RPC 调用链解决“怎么调用”，注册中心和心跳解决“调用谁、谁还活着”。

## 7. 常见误区与排查思路

- **误区 1：注册成功就永远可用。** 实例可能随时崩溃，必须通过心跳或健康检查持续维护状态。
- **误区 2：心跳成功等于业务健康。** 心跳只能证明有限维度的可用性，核心依赖异常仍可能导致业务失败。
- **误区 3：心跳间隔越短越好。** 过短会增加注册中心压力；过长会导致故障摘除不及时。
- **误区 4：客户端每次调用都查注册中心。** 常见做法是本地缓存实例列表，并通过订阅/轮询更新。

排查服务发现问题时可以按这条链路：

```text
服务是否启动 → 是否注册成功 → 心跳是否续约 → 注册中心是否标记 healthy → 客户端是否拉到新列表 → 负载均衡是否选中坏实例 → 调用失败是否触发摘除/熔断
```

## 8. 关联知识点

- `002_RPC_与_gRPC：服务间调用.md`：RPC 完整调用链。
- `009_RPC_动态代理与字节码生成.md`：客户端代理如何生成并发起调用。
- `005_Kubernetes、服务发现与弹性部署.md`：K8s 中 Service、Endpoint、Pod 健康检查的类似机制。
- `006_Prometheus、Grafana、OpenTelemetry_与日志.md`：心跳、健康检查、调用失败率需要通过指标和 trace 观测。

## 9. 复习检查问题

- 服务注册、服务发现、心跳分别解决什么问题？
- 为什么注册一次不够，还需要周期性心跳？
- TTL/lease 模型如何判断实例过期？
- 心跳、liveness、readiness、dependency health 有什么区别？
- 客户端代理如何利用服务发现选择目标实例？
