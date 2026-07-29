# RabbitMQ 可靠投递、消费确认与队列存储

> 所属分类：Message Queue / RabbitMQ
> 修订版本：v12
> 知识边界：本文承接 `009/010` 的路由拓扑，解释消息进入队列前后的确认、流控、持久化和队列类型；TTL/DLX 延时见 `012`。

## 1. 总体性概念

RabbitMQ 的“可靠投递”不是一个开关，而是两段相互独立的确认链路：

```text
Publisher
  ↓ Publisher Confirm
Exchange → Queue
  ↓ Consumer ACK/NACK
Consumer
```

- **Publisher Confirm**：告诉生产者 broker 是否接管了发布。
- **Consumer ACK**：告诉 broker 消费者是否完成了处理。

要让消息经 broker 重启后仍有机会保留，还要结合 durable exchange、durable queue、persistent message，以及合适的队列类型。任何单独一项都不能代表端到端绝对可靠。

## 2. Publisher Confirm 与不可路由消息

### 2.1 Publisher Confirm

Publisher 开启 confirm 模式后，broker 会对已接管的发布返回 ack，失败时返回 nack 或让客户端超时。

```text
Publisher 发送消息
  ↓
Broker 接收并按队列类型完成所需处理
  ↓
basic.ack / basic.nack
  ↓
Publisher 决定记录成功、重试或告警
```

Confirm 解决的是“消息是否被 broker 接管”，不是“消费者是否完成业务”。

### 2.2 Mandatory 与 Return

Exchange 存在并不代表消息一定能路由到 queue。如果发布时启用 `mandatory`，消息无法路由时 broker 会通过 `basic.return` 返回给生产者；否则不可路由消息可能被丢弃。

```text
Confirm ack：Broker 接管了发布
basic.return：消息没有匹配到目标 Queue
Consumer ack：业务处理完成
```

这三者不要混为一谈。

## 3. Durable、Persistent 与队列类型

### 3.1 定义持久化与消息持久化

- durable exchange：broker 重启后保留 exchange 定义；
- durable queue：broker 重启后保留 queue 定义；
- persistent message：声明消息需要持久存储；
- Publisher Confirm：生产者确认 broker 已按当前队列语义接管消息。

仅把 queue 声明为 durable，并不会自动让所有消息都成为 persistent。仅设置消息 persistent，如果目标 queue 本身不持久，也无法形成完整的重启恢复链。

### 3.2 Classic Queue

Classic Queue 是通用、非复制的队列类型，适合不要求队列副本高可用或可以由上游重建消息的场景。单个节点永久丢失时，非复制 classic queue 的数据无法依靠其它节点恢复。

### 3.3 Quorum Queue

Quorum Queue 使用 Raft 在多个 RabbitMQ 节点之间复制队列日志，面向需要数据安全和节点故障恢复的持久任务队列。它通过多数派确认写入，适合订单、支付等可靠性要求较高的场景。

Quorum Queue 不是“所有场景都替代 classic queue”：临时队列、高频创建删除、单节点本地队列等场景仍要根据生命周期和性能选择。

### 3.4 Streams

RabbitMQ Streams 更接近可追加、按保留策略管理、支持重读的日志模型。它与普通 queue 的“确认后完成并逐步清理”语义不同，适合大吞吐、回放和流式消费。学习普通业务队列时先掌握 classic/quorum，避免把 stream offset 与 queue delivery tag 混用。

## 4. Consumer ACK、NACK 与 Requeue

Broker 投递消息后，会为当前 channel 上的 delivery 分配 delivery tag。手动确认时：

- `basic.ack`：处理成功，可以确认；
- `basic.reject`：拒绝单条消息；
- `basic.nack`：可以拒绝一条或多条消息；
- `requeue=true`：重新放回队列；
- `requeue=false`：丢弃，或在配置 DLX 时进入死信流程。

```text
ready
  ↓ deliver
unacked
  ├─ ack → 完成并清理
  ├─ nack/reject + requeue → 再次 ready
  └─ nack/reject + no requeue → DLX 或丢弃
```

消费者连接或 channel 在未确认时关闭，相关 unacked 消息通常会重新入队，因此消费者仍然需要幂等。

永久错误不能无限 `requeue=true`，否则会形成快速重投循环。应限制次数、记录死亡原因，并转入 DLQ 或人工补偿。

## 5. Prefetch 与消费流控

Prefetch 限制 broker 在一个 consumer 上最多保留多少条未确认消息：

```text
prefetch 太小 → 单消费者吞吐可能不足
prefetch 太大 → unacked、内存占用和故障重投批量增大
```

选择时要结合单条处理耗时、消息大小、消费者并发和可接受的故障重投范围。Prefetch 不是业务线程数本身，但会限制送到消费者端的在途窗口。

## 6. 队列存储与历史 Lazy Queue

### 6.1 Lazy Queue 的版本边界

RabbitMQ 3.6–3.11 的 classic queue 可以显式配置 `x-queue-mode=lazy`，让消息主体尽量早地写入磁盘并减少内存驻留。

从 RabbitMQ 3.12 起：

- `x-queue-mode` 被忽略；
- classic queue 默认采用类似 lazy mode 的低内存工作集行为；
- 消息通常短暂缓冲后写盘，只在内存保留少量适合快速投递的工作集；
- 如果消息立即投递并在写盘前被确认，就没有必要再写入磁盘。

因此 Lazy Queue 现在是理解历史演进的概念，不应再作为新项目需要显式开启的队列模式。

### 6.2 不是“完全不用内存”

即使消息主体主要在磁盘，broker 仍需在内存维护：

- 队列头尾、索引或定位信息；
- ready、delivered、acked 等投递状态；
- delivery tag 与 unacked 集合；
- 当前消费者需要的工作集。

消费者不会自己读取磁盘文件。Broker 根据队列状态定位下一条 ready 消息，必要时把消息主体读入内存后投递。

### 6.3 磁盘优先的代价

磁盘优先行为降低大积压时的内存压力，但磁盘吞吐和延迟会变得重要。

| 场景 | 关注点 |
|---|---|
| 大量积压、削峰填谷 | 磁盘容量、IO、恢复时间 |
| 消费者短时离线 | messages_ready 增长速度 |
| 极低延迟热路径 | 工作集命中、磁盘写入和 confirm 延迟 |
| 高可靠持久任务 | Quorum Queue 多数派复制成本 |

## 7. 完整机制流程

```text
Publisher 发布 persistent message
  ↓
Durable Exchange 根据 binding 路由
  ↓
Durable Classic / Quorum Queue 接管消息
  ↓
Publisher 收到 confirm
  ↓
Broker 按 prefetch 投递，消息进入 unacked
  ↓
Consumer 执行业务
  ├─ 成功：ack
  ├─ 短暂失败：受控 requeue / retry
  └─ 永久失败：nack no-requeue → DLX
```

Publisher Confirm 和 Consumer ACK 分属链路两端，不能相互替代。

## 8. 应用举例

### 8.1 声明持久队列并发布持久消息

```python
channel.exchange_declare(
    exchange="order.ex",
    exchange_type="direct",
    durable=True,
)
channel.queue_declare(
    queue="order.created.q",
    durable=True,
)
channel.queue_bind(
    queue="order.created.q",
    exchange="order.ex",
    routing_key="order.created",
)

channel.confirm_delivery()
channel.basic_publish(
    exchange="order.ex",
    routing_key="order.created",
    body=json.dumps({"event_id": "evt-001", "order_id": 1001}),
    properties=pika.BasicProperties(delivery_mode=2),
    mandatory=True,
)
```

具体客户端对 confirm 失败和 `basic.return` 的 API 表达不同，生产代码必须显式处理。

### 8.2 手动 ACK 与有限失败路由

```python
def on_message(ch, method, properties, body):
    try:
        process_order(body)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except RetryableError:
        ch.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=True,
        )
    except NonRetryableError:
        ch.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=False,
        )
```

真实系统还要限制重投次数，避免 `RetryableError` 永久存在时无限循环。

### 8.3 Prefetch

```python
channel.basic_qos(prefetch_count=20)
```

### 8.4 历史 Lazy Queue 声明

```python
# 仅用于理解 RabbitMQ 3.11 及更早版本。
# 3.12 起 x-queue-mode 被忽略。
channel.queue_declare(
    queue="order.backlog.q",
    durable=True,
    arguments={"x-queue-mode": "lazy"},
)
```

## 9. 监控与排查

```text
messages_ready              等待投递
messages_unacknowledged     已投递未确认
publisher confirm latency   发布确认延迟
consumer utilisation        消费者利用率
redelivered / delivery count 重投情况
disk_free / io_read / io_write
```

排查顺序：

1. Producer 是否收到 confirm 或 return？
2. Exchange、routing key、binding 是否正确？
3. Queue 是否存在并具备预期 durable/queue type？
4. 消息是 ready、unacked 还是已进入 DLX？
5. Prefetch、消费者处理速度和磁盘 IO 是否成为瓶颈？

## 10. 常见误区

- **误区 1：durable queue 等于消息绝不丢。** 还要考虑消息持久化、confirm、队列类型和故障范围。
- **误区 2：Publisher Confirm 等于业务成功。** 它只确认 broker 接管发布。
- **误区 3：Consumer ACK 等于 Producer 已可靠发送。** 两段确认彼此独立。
- **误区 4：失败永远 requeue 最安全。** 永久错误会形成重投循环。
- **误区 5：Lazy Queue 仍需在新版本显式开启。** 3.12 起该参数已被忽略。
- **误区 6：消费者要自己定位磁盘消息。** 存储定位由 broker 完成。

## 11. 关联知识点

- `009_RabbitMQ：vhost、exchange、queue、binding.md`
- `010_Routing_Key_与_Binding_Key.md`
- `012_RabbitMQ_延时队列：TTL、死信交换机与延时插件.md`
- `013_RabbitMQ_Federation：联邦交换机与联邦队列.md`

## 12. 复习检查问题

- Publisher Confirm 与 Consumer ACK 分别确认什么？
- Durable queue 和 persistent message 为什么需要配合？
- ACK、NACK、reject、requeue 的边界是什么？
- Prefetch 太大或太小分别有什么风险？
- Classic Queue、Quorum Queue 和 Stream 的目标有何不同？
- 为什么 Lazy Queue 在 RabbitMQ 3.12 后主要是历史概念？
- Broker 如何知道下一条要投递的消息，而消费者为什么不需要关心磁盘位置？
