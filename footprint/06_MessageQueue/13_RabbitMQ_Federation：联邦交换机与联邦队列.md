# 06.13 RabbitMQ Federation：联邦交换机与联邦队列

## 1. 总体性概念

RabbitMQ Federation 用于跨 broker、跨机房或跨区域传递消息。它允许下游 RabbitMQ 连接上游 RabbitMQ 并异步转发事件，不需要把高延迟网络两端强行组成一个紧耦合集群。

主要形态：

- **Federation Exchange（联邦交换机）**：把上游 exchange 的发布转播到下游 exchange。
- **Federation Queue（联邦队列）**：下游 queue 按消费者需求从上游 queue 拉取消息。

## 2. Federation 解决什么问题

RabbitMQ Cluster 更适合同机房、低延迟、稳定网络中的节点协作。跨地域链路的延迟、抖动和分区会放大集群协调成本。Federation 选择异步连接：

```text
不共享一套强耦合队列状态
  ↓
在两个独立 RabbitMQ brokers / clusters 之间建立 link
  ↓
按 policy 转发需要的消息
```

典型用途：

- 多机房事件汇聚；
- 区域业务向中心系统上报；
- 不同组织之间的 RabbitMQ 桥接；
- 远端消费者按需处理上游任务。

## 3. 联邦交换机

联邦交换机关注发布订阅。下游 exchange 建立到上游 exchange 的 federation link，上游中符合联邦订阅需求的消息被转发到下游，再按下游本地 bindings 路由。

```text
上游 Producer → 上游 Exchange
                    ↓ Federation Link
下游 Exchange → 下游 Queue → 下游 Consumer
```

它适合“某区域发布的事件，也应被另一地区的本地系统订阅”。

下游 queue 的 binding 很重要：Federation Exchange 会传播绑定需求，避免无条件复制所有上游发布。设计时仍应使用稳定的 routing key 和清晰的本地队列边界。

## 4. 联邦队列

联邦队列关注任务消费。下游 queue 的 federation link 像上游 queue 的消费者，在本地存在消费需求时从上游拉取消息。

```text
上游 Queue
  ↓ Federation Link
下游 Queue
  ↓
下游 Consumer
```

它适合让本地消费者处理远端积压任务，但消息被转移后并不是在两地各复制一份供双方都完整处理。若目标是事件广播和多地各自消费，应优先考虑联邦交换机及各地下游队列。

## 5. Federation、Cluster、Quorum Queue 与 Shovel

| 机制 | 主要目标 | 典型范围 |
|---|---|---|
| RabbitMQ Cluster | 共享集群元数据与路由 | 同机房低延迟网络 |
| Quorum Queue | 单集群内队列副本一致性 | 可靠持久任务队列 |
| Federation | Brokers/Clusters 间按策略异步转发 | 跨机房、跨区域 |
| Shovel | 明确源端到目标端的消息搬运 | 点对点桥接和迁移 |

Federation 不是 Quorum Queue 的替代品，也不是强一致跨区域复制。Classic mirrored queue 已在 RabbitMQ 4.0 移除；单集群内需要复制的持久队列应优先评估 Quorum Queue。

## 6. 机制流程

### 6.1 联邦交换机

```text
配置 upstream URI
  ↓
定义 policy，apply-to exchanges
  ↓
下游 exchange 建立 federation link
  ↓
上游 exchange 接收发布
  ↓
需要的消息经 link 转到下游 exchange
  ↓
下游按本地 binding 路由到 queues
```

### 6.2 联邦队列

```text
配置 upstream URI
  ↓
定义 policy，apply-to queues
  ↓
下游 queue 建立 federation link
  ↓
存在本地消费需求时从上游 queue 拉取
  ↓
下游 consumer 处理并确认
```

网络断开时 link 会重连。因为跨链路确认、重连和消费者故障都可能产生再次投递，业务仍需使用稳定的 `event_id` 做幂等。

## 7. 应用举例

### 7.1 区域事件汇聚

```text
上海：order.events.ex
  ↓ Federation Exchange
新加坡：order.events.ex
  ↓
本地统计 / 风控队列
```

配置思路：

```bash
rabbitmqctl set_parameter federation-upstream sh-upstream \
  '{"uri":"amqp://user:pass@shanghai-rabbit"}'

rabbitmqctl set_policy federate-order-events '^order\.events\.ex$' \
  '{"federation-upstream":"sh-upstream"}' \
  --apply-to exchanges
```

凭据不应直接硬编码在公开脚本中，生产环境应使用受控配置和最小权限账号。

### 7.2 远端任务本地消费

```text
center.task.q
  ↓ Federation Queue
edge.task.q
  ↓
边缘节点 Consumer
```

适合允许异步同步和断线重连的边缘处理，但需要评估网络恢复后的积压速度和重复投递。

### 7.3 消费者幂等

```python
def handle_event(event):
    if already_processed(event.id):
        return
    with db.transaction():
        apply(event)
        mark_processed(event.id)
```

## 8. 常见误区与排查思路

- **误区 1：Federation 等于 RabbitMQ Cluster。** 它是独立 brokers 之间的异步转发。
- **误区 2：Federation 等于 Quorum Queue 跨地域副本。** 它不共享一份强一致队列状态。
- **误区 3：联邦交换机与联邦队列用途相同。** 前者转播事件，后者按需拉取队列任务。
- **误区 4：跨地域链路不会重复。** 重连、确认窗口和消费者恢复都要求幂等。

排查顺序：

```text
upstream URI 与权限是否正确？
网络和 TLS 是否可达？
federation link 是否 running？
policy pattern 和 apply-to 是否匹配？
下游 exchange binding / queue consumer 是否存在？
是否出现积压、重连或重复处理？
```

## 9. 关联知识点

- `009_RabbitMQ：vhost、exchange、queue、binding.md`
- `010_Routing_Key_与_Binding_Key.md`
- `011_RabbitMQ_可靠投递、消费确认与队列存储.md`
- `014_Kafka_vs_RabbitMQ：事件流、业务路由与选型.md`

## 10. 复习检查问题

- Federation 为什么比跨地域 RabbitMQ Cluster 更适合异步桥接？
- 联邦交换机和联邦队列的消息语义有什么区别？
- Federation、Quorum Queue 和 Shovel 分别解决什么问题？
- 为什么 Federation 消费者仍然需要幂等？
- 排查 federation link 时应从哪些层次入手？
