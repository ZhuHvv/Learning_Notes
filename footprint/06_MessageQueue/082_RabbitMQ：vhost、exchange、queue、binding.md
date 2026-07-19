# RabbitMQ：vhost、exchange、queue、binding

> 所属分类：Message Queue / RabbitMQ  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

RabbitMQ 的核心链路是：Producer 把消息发给 Exchange，Exchange 根据 Binding 规则把消息路由到 Queue，Consumer 从 Queue 中消费消息。vhost 则提供逻辑隔离，让不同项目、环境或团队拥有相互独立的 exchange、queue、binding 和权限空间。

```text
Producer → Exchange → Binding → Queue → Consumer
```

## 2. 原理性解释

### 2.1 Producer 不直接面向 Queue

RabbitMQ 的一个关键设计是：生产者通常不直接关心具体队列，而是把消息交给 exchange。这样消费者侧可以通过新增队列和 binding 来订阅消息，而不需要生产者修改代码。

这和 Kafka 里 producer 直接写 topic/partition 不同。RabbitMQ 更强调“业务路由拓扑”，Kafka 更强调“可持久化事件日志”。

### 2.2 Exchange 只负责路由，Queue 才保存消息

Exchange 本身通常不保存消息。它像路由器，只根据 exchange 类型、routing key、binding key 判断消息应该去哪些队列。

Queue 才是消息等待消费者处理的地方。消息能不能被可靠消费，取决于 queue 是否 durable、message 是否 persistent、consumer 是否 ack，以及失败时是否配置死信策略。

### 2.3 Binding 是 exchange 和 queue 之间的订阅规则

Binding 把 queue 连接到 exchange。不同 exchange 类型下，binding 的含义不同：

- `direct`：routing key 与 binding key 精确匹配；
- `topic`：binding key 支持 `*` 和 `#`；
- `fanout`：忽略 routing key，广播到所有绑定队列；
- `headers`：按消息 header 匹配。

### 2.4 vhost 是逻辑隔离空间

vhost 可以理解为 RabbitMQ 内部的“租户空间”。不同 vhost 下可以有同名 exchange 和 queue，但互不影响。它常用于：

```text
/dev       开发环境
/test      测试环境
/prod      生产环境
/order     订单系统
/payment   支付系统
```

权限也通常绑定到 vhost 维度，这样某个应用只能访问自己的消息拓扑。

## 3. 机制流程

```text
创建 vhost
  ↓
为应用分配该 vhost 下的权限
  ↓
声明 exchange
  ↓
声明 queue
  ↓
queue 通过 binding key 绑定 exchange
  ↓
producer 携带 routing key 发布消息
  ↓
exchange 匹配 binding
  ↓
匹配队列收到消息
  ↓
consumer 消费并 ack
```

一条消息是否会被多个消费者处理，要分情况：

- 一个 queue 多个 consumer：通常是竞争消费，一条消息只给其中一个 consumer。
- 一个 exchange 绑定多个 queue：一条消息可能复制到多个 queue，每个 queue 的消费者都会处理一份。

## 4. 类比理解

vhost 像不同园区；exchange 像园区分拣中心；binding 像分拣规则；queue 像具体货架；consumer 像从货架取货处理的员工。

## 5. 应用举例 / 代码或伪代码

### 5.1 direct exchange：订单创建事件

```python
channel.exchange_declare("order.ex", exchange_type="direct", durable=True)
channel.queue_declare("order.created.q", durable=True)
channel.queue_bind("order.created.q", "order.ex", routing_key="order.created")

channel.basic_publish(
    exchange="order.ex",
    routing_key="order.created",
    body=json.dumps({"order_id": 1001}),
)
```

### 5.2 fanout exchange：广播通知

```python
channel.exchange_declare("notice.ex", exchange_type="fanout")
channel.queue_bind("email.notice.q", "notice.ex")
channel.queue_bind("sms.notice.q", "notice.ex")
```

一条 notice 消息会被复制到邮件队列和短信队列。

### 5.3 topic exchange：按业务维度订阅

```python
channel.exchange_declare("event.ex", exchange_type="topic")
channel.queue_bind("audit.q", "event.ex", routing_key="order.#")
channel.queue_bind("us.q", "event.ex", routing_key="*.created.us")
```

## 6. 你在讨论中的理解推进

- 你先从 exchange、binding、routing key 的关系入手，确认 RabbitMQ 不是 producer 直接写 queue。
- 随后你把 vhost 理解为项目隔离空间，这个理解基本正确，但要记住隔离的是拓扑、权限和命名空间。
- 之后你继续追问延时队列、惰性队列、联邦队列，说明你已经从“普通路由”推进到“可靠性、容量、跨 broker 和定时语义”。

## 7. 常见误区与排查思路

- **误区 1：exchange 保存消息。** 普通 exchange 只路由，queue 才保存。
- **误区 2：一个消息被多个 consumer 处理一定是异常。** 如果路由到多个 queue，这是设计结果。
- **误区 3：vhost 等于 exchange。** vhost 是隔离空间，exchange 是空间里的路由器。

排查消息丢失或没路由到队列时，看：

```text
vhost 是否正确？
exchange 是否存在？
exchange 类型是否正确？
routing key 与 binding key 是否匹配？
queue 是否绑定到了目标 exchange？
```

## 8. 关联知识点

- `083_Routing_Key_与_Binding_Key.md`
- `085_RabbitMQ_延时队列：TTL、死信交换机与延时插件.md`
- `087_RabbitMQ_Federation：联邦交换机与联邦队列.md`

## 9. 复习检查问题

- RabbitMQ 为什么要让 producer 面向 exchange 而不是直接面向 queue？
- exchange、queue、binding 各自保存或表达什么？
- 一条消息什么时候会被多个消费者处理？
- vhost 适合解决什么隔离问题？
