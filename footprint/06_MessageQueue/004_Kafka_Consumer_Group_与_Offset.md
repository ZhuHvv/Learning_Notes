# Kafka Consumer Group 与 Offset

> 所属分类：Message Queue / Kafka / RabbitMQ  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件聚焦 Kafka 消费模型，覆盖 consumer group、partition 分配、offset、重复消费、崩溃恢复、手动提交和多消费者语义。

## 1. 总体性概念

Kafka Consumer Group 是同一类消费服务的多个实例集合。Kafka 会把 topic 的 partitions 分配给 group 内的消费者，使它们分摊处理压力；同一个 consumer group 内，同一个 partition 在同一时刻通常只会分配给一个 consumer。Offset 是某个 consumer group 在某个 partition 上的消费进度。

最重要的结论是：

- **同一 consumer group 内**：同一 partition 的消息正常情况下只由一个 consumer 处理。
- **不同 consumer group 之间**：可以各自完整消费同一 topic 的消息。
- **offset 是按 group + topic + partition 维度保存的**，不是全局唯一进度。
- **消费者失败后是否重复处理，取决于业务处理和 offset commit 的先后关系。**

## 2. 原理性解释

### Consumer Group 解决的是“同一消费逻辑如何水平扩展”

假设 `order-events` 有 6 个 partitions，`order-service` 有 3 个 consumer 实例，那么 Kafka 可能给每个实例分配 2 个 partitions。这样每个实例处理不同 partition 的消息，整体吞吐提升。

```text
order-events
  p0 ─┐
  p1 ─┤ consumer-1
  p2 ─┐
  p3 ─┤ consumer-2
  p4 ─┐
  p5 ─┤ consumer-3
```

如果 consumer 实例数超过 partition 数，多出来的 consumer 会空闲，因为一个 partition 不能在同一 group 内同时被多个 consumer 并行消费。这个规则保证了 partition 内顺序处理。

### 一条消息会不会被多个 consumer 处理

要分情况：

1. **不同 consumer group：会。** 例如 `order-service`、`analytics-service`、`search-index-service` 都订阅 `order-events`，它们各有自己的 offset，所以都会看到同一条消息。
2. **同一 consumer group：正常情况下不会。** 同一 partition 只分配给一个 consumer。
3. **异常情况下可能重复。** 例如 consumer 处理成功但还没 commit offset 就崩溃，恢复后会从旧 offset 再读一次。

所以 Kafka 的典型语义是“至少一次处理”更常见。消费者必须设计幂等逻辑，不能假设业务代码永远只执行一次。

### Offset 存在哪里，代表什么

Kafka 会把 consumer group 的 offset 提交到内部 topic `__consumer_offsets` 中。一个 offset 记录大致可以理解为：

```text
(group_id, topic, partition) -> next_offset_to_read
```

注意：提交的 offset 通常表示**下一条将要读取的消息位置**，不是“当前正在处理的消息”。例如处理完 offset=100 的消息后，提交 offset=101。

### Auto Commit 与 Manual Commit

自动提交简单，但容易在处理未完成时提前提交：

```text
poll 到消息
  ↓
auto commit 定时提交 offset
  ↓
业务处理还没完成，进程崩溃
  ↓
恢复后从已提交 offset 之后读，可能丢处理
```

更稳妥的方式是业务成功后手动提交：

```python
while True:
    records = consumer.poll(timeout_ms=1000)
    for msg in records:
        try:
            handle(msg)
            consumer.commit({msg.topic_partition: msg.offset + 1})
        except Exception:
            # 不提交 offset；后续会重读，或者主动投递 retry topic
            log_error(msg)
            raise
```

这能减少“处理失败但 offset 已提交”的风险，但也意味着如果处理成功后 commit 之前崩溃，消息会被再次处理。因此幂等仍然必须做。

## 3. 机制流程

### 3.1 Consumer 加入 group 与分区分配

```text
Consumer 启动，携带 group.id 连接 Kafka
  ↓
找到 Group Coordinator
  ↓
加入 group，触发 rebalance
  ↓
Coordinator 按策略分配 partitions
  ↓
Consumer 从分配到的 partitions 拉取消息
```

常见分配策略包括 range、round-robin、sticky 等。Rebalance 发生在 consumer 加入、退出、超时、topic partition 变化时。

### 3.2 正常消费与提交流程

```text
poll 拉取 records
  ↓
逐条或批量处理业务逻辑
  ↓
处理成功
  ↓
commit offset 到 __consumer_offsets
  ↓
下一轮从新 offset 继续 poll
```

### 3.3 Consumer 崩溃恢复流程

```text
consumer-A 处理 partition-0 的 offset=100
  ↓
业务处理过程中崩溃
  ↓
Group Coordinator 发现心跳超时
  ↓
触发 rebalance，把 partition-0 分配给 consumer-B
  ↓
consumer-B 从该 group 已提交 offset 开始读
  ↓
如果 offset=100 未提交，则消息会再次被处理
```

这就是为什么你理解的“offset 属于 partition，不同 consumer group 对应不同 offset”是正确的，但还要补充：offset 的提交时机决定了崩溃后是重复处理还是可能丢处理。

## 4. 类比理解

Consumer Group 像一个读账本的小组。一本账本有多本分册 partition，小组内每个人负责几本分册；另一个小组可以为了别的目的再完整读一遍同样的账本。Offset 就像每个小组在每本分册上的书签。

如果某个人读到第 100 行，已经完成业务但还没移动书签就离开，接手的人会从旧书签再读一次，这就是重复消费。

## 5. 应用举例 / 代码或伪代码

### 5.1 两个 group 各自完整消费同一 topic

```bash
kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic order-events --group order-service

kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic order-events --group analytics-service
```

这两个命令会形成两个不同 consumer group，因此都能消费 `order-events` 的消息。

### 5.2 幂等消费伪代码

```python
def handle_order_event(event):
    # event_id 是业务幂等键，不是 Kafka offset
    if db.exists("processed_events", event.event_id):
        return

    with db.transaction():
        apply_business_change(event)
        db.insert("processed_events", event.event_id)
```

### 5.3 手动提交 offset 的安全顺序

```text
poll → handle business → write idempotent result → commit offset
```

不要把 commit 放在业务处理之前，否则失败恢复时 Kafka 会认为这条消息已经处理完。

## 6. 你在讨论中的理解推进

你已经把几个关键点串起来了：offset 属于 partition；不同 consumer group 有不同 offset；同一 group 内一条消息通常只由一个 consumer 处理。现在进一步补充：Kafka 只能记录“读到哪里”，并不知道你的业务是否真的成功；业务失败、进程崩溃、rebalance 都会让同一条消息可能再次被处理，因此消费者端要主动做幂等和失败路由。

## 7. 常见误区与排查思路

- **误区 1：同一个 topic 只能被一个系统消费。** 不同 consumer group 可以各自消费完整消息流。
- **误区 2：commit offset 等于业务一定成功。** Kafka 只知道 offset 被提交，不知道数据库是否写成功。
- **误区 3：partition 数越多，consumer 越多就一定越快。** 并行度上限是 partition 数，下游数据库和外部接口也可能成为瓶颈。
- **误区 4：重复消费是 Kafka bug。** 至少一次语义下重复消费是正常工程边界。

## 8. 关联知识点

- `003_Kafka：KRaft、Broker、Topic、Partition、Replica.md`
- `006_Kafka_重试机制、Retry_Topic_与死信队列.md`
- `008_Kafka_消息分发、多消费者语义与幂等处理.md`
- `002_流量削峰、异步解耦与最终一致性.md`

## 9. 复习检查问题

- 为什么同一 group 内一个 partition 不能同时给多个 consumer 消费？
- 什么时候一条消息会被多个 consumer 处理？
- offset commit 过早和过晚分别有什么风险？
- consumer 处理消息中途崩溃后，恢复时如何决定从哪继续？
- 为什么 Kafka 消费者通常必须做幂等？
