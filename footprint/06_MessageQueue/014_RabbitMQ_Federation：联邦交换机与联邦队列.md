# RabbitMQ Federation：联邦交换机与联邦队列

> 所属分类：Message Queue / RabbitMQ  
> 修订版本：v11  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

RabbitMQ Federation 用来解决跨 broker、跨机房、跨区域的消息转发问题。它允许一个 RabbitMQ 节点从另一个 RabbitMQ 节点拉取消息或订阅交换机，从而在不建立强一致集群的情况下实现跨地域消息流动。

联邦主要有两种形态：

- **Federation Exchange（联邦交换机）**：把上游 exchange 的消息转发到下游 exchange。
- **Federation Queue（联邦队列）**：下游 queue 从上游 queue 拉取消息，相当于跨 broker 的队列消费扩展。

## 2. 原理性解释

### 2.1 Federation 解决什么问题

RabbitMQ 集群更适合同一局域网内的多个节点协作，不适合高延迟、不稳定的跨地域网络。Federation 的定位是：

```text
不把两个机房强行组成一个紧耦合集群
而是让消息在两个 RabbitMQ broker 之间异步流动
```

它常用于：

- 多机房业务消息汇聚；
- 跨区域订单/日志同步；
- 边缘节点到中心节点的数据上报；
- 不同团队或系统之间的 RabbitMQ 桥接。

### 2.2 联邦交换机

联邦交换机关注的是“发布订阅关系”。下游 exchange 会从上游 exchange 接收匹配消息，再按本地 binding 规则路由到本地下游队列。

```text
上游 Producer → 上游 Exchange
                    ↓ Federation Link
下游 Exchange → 下游 Queue → 下游 Consumer
```

它适合“我希望某个区域发布的事件，也能在另一个区域被订阅”的场景。

### 2.3 联邦队列

联邦队列关注的是“队列消费”。下游 queue 可以从上游 queue 拉取消息，本质上像一个跨 broker 的消费者。

```text
上游 Queue ← 上游 Producer
    ↓ Federation Link
下游 Queue → 下游 Consumer
```

它适合“我希望本地消费者能消费远端队列中的任务”的场景。

### 2.4 Federation 与 Quorum Queue 的区别（classic 镜像队列已于 RabbitMQ 4.0 移除）

Federation 不是强一致复制，不是为了让多个节点共享同一份队列状态。它是异步转发机制。

| 机制 | 主要目标 | 典型场景 |
|---|---|---|
| RabbitMQ Cluster | 同一集群内管理和路由 | 同机房低延迟网络 |
| Quorum Queue | 队列高可用、一致复制 | 单集群内可靠队列 |
| Federation | 跨 broker 异步转发 | 跨机房、跨区域、系统桥接 |
| Shovel | 点对点搬运消息 | 明确源队列到目标队列搬运 |

## 3. 机制流程

### 3.1 联邦交换机流程

```text
配置 upstream URI
  ↓
定义 federation policy 作用于 exchange
  ↓
下游 exchange 建立到上游 exchange 的 federation link
  ↓
上游 exchange 收到消息
  ↓
匹配消息经 link 转发到下游 exchange
  ↓
下游按本地 binding 分发给 queue
```

### 3.2 联邦队列流程

```text
配置 upstream URI
  ↓
定义 federation policy 作用于 queue
  ↓
下游 queue 像消费者一样从上游 queue 拉取消息
  ↓
消息到达下游 queue
  ↓
本地 consumer 消费
```

## 4. 类比理解

联邦交换机像“跨城市广播转播站”：A 城市电台播出的节目，B 城市转播台接收后再按本地频道分发。联邦队列像“跨仓库调货”：B 仓库缺货时从 A 仓库拉货，再交给本地配送员。

## 5. 应用举例 / 代码或伪代码

### 5.1 联邦交换机场景：区域事件汇聚

```text
上海机房：order.events.ex
新加坡机房：order.events.ex

上海产生 order.created
  ↓ federation exchange
新加坡也能订阅 order.created 做统计或风控
```

配置思路伪代码：

```bash
rabbitmqctl set_parameter federation-upstream sh-upstream   '{"uri":"amqp://user:pass@shanghai-rabbit"}'

rabbitmqctl set_policy federate-order-events '^order\.events\.ex$'   '{"federation-upstream":"sh-upstream"}'   --apply-to exchanges
```

### 5.2 联邦队列场景：远端任务本地消费

```text
center.task.q  生产任务
  ↓ federation queue
edge.task.q    边缘节点本地消费
```

适合边缘节点断续在线、允许异步同步的场景。

### 5.3 消费者仍要幂等

跨 broker 异步链路可能受到网络断开、重连、重复投递影响，消费者仍要使用业务幂等键：

```python
def handle_event(event):
    if already_processed(event.id):
        return
    apply(event)
    mark_processed(event.id)
```

## 6. 你在讨论中的理解推进

- 起点：你问联邦交换机和联邦队列“针对的问题是什么”。
- 修正：它们不是普通 exchange/queue 的替代，而是跨 RabbitMQ broker 的异步转发机制。
- 深化：你可以把二者区分为“exchange 级事件转播”和“queue 级任务拉取”。

## 7. 常见误区与排查思路

- **误区 1：Federation 等于集群。** Federation 是跨 broker 异步转发，不是强一致集群。
- **误区 2：联邦交换机和联邦队列用途一样。** 前者转播事件，后者跨队列拉取任务。
- **误区 3：跨地域转发可以忽略重复消费。** 网络重试和链路恢复都可能带来重复，消费者要幂等。

排查时看：

```text
upstream URI 是否可达？
federation link 是否建立？
policy apply-to 是 exchanges 还是 queues？
下游 binding 是否正确？
消费者是否具备幂等处理？
```

## 8. 关联知识点

- `009_RabbitMQ：vhost、exchange、queue、binding.md`
- `010_Routing_Key_与_Binding_Key.md`
- `002_流量削峰、异步解耦与最终一致性.md`

## 9. 复习检查问题

- Federation 主要解决什么问题？
- 联邦交换机和联邦队列的区别是什么？
- Federation 为什么不等于 RabbitMQ 集群？
- 跨 broker 消息转发为什么仍然需要幂等？
