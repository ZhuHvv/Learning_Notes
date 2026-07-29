# Kafka Consumer Group、Offset 与 Rebalance

> 所属分类：Message Queue / Kafka
> 修订版本：v12
> 知识边界：本文聚焦消费任务如何分配、进度如何保存以及故障后如何接管；重复处理的业务防护见 `007`，失败重试见 `008`。

## 1. 总体性概念

Consumer Group 是执行同一类消费逻辑的多个消费者实例集合。Kafka 把 topic 的 partitions 分配给 group 内的消费者，使它们分摊处理压力。

核心结论：

- 同一 group 内，一个 partition 在同一时刻通常只分配给一个 consumer；
- consumer 数量超过 partition 数时，多出的 consumer 会空闲；
- 不同 group 各自维护进度，可以完整读取同一个 topic；
- offset 按 `group + topic + partition` 保存，通常表示下一条要读取的位置。

## 2. Consumer Group 如何扩展消费

假设 `order-events` 有 6 个 partitions，group 中有 3 个 consumer：

```text
p0、p1 → consumer-1
p2、p3 → consumer-2
p4、p5 → consumer-3
```

同一 partition 不会在稳定状态下同时交给组内多个 consumer，这既限定了并行度，也维护了 partition 内的读取顺序。

不同 group 则互不影响：

```text
order-service group      → 独立 offset
analytics-service group  → 独立 offset
search-service group     → 独立 offset
```

因此同一条业务事件可以被多个系统分别处理，这属于正常发布订阅语义，不是重复消费错误。

## 3. Offset 的含义与存储

Consumer Group 的 offset 提交到 Kafka 内部 topic `__consumer_offsets`。记录可以抽象为：

```text
(group_id, topic, partition) -> next_offset_to_read
```

处理完 offset `100` 后，通常提交 `101`。Offset 只表示 Kafka 消费进度，不表示数据库写入、外部接口调用等业务动作一定成功。

## 4. Auto Commit 与 Manual Commit

### 4.1 自动提交的风险

```text
poll 到消息
  ↓
自动提交定时器推进 offset
  ↓
业务尚未完成，进程崩溃
  ↓
恢复后从新 offset 继续，业务处理可能被跳过
```

### 4.2 成功后手动提交

```python
while True:
    records = consumer.poll(timeout_ms=1000)
    for msg in records:
        handle(msg)
        consumer.commit({msg.topic_partition: msg.offset + 1})
```

推荐顺序是：

```text
poll → 完成业务事务 → commit 下一 offset
```

如果业务成功但 commit 前崩溃，消息会再次读取。这是常见的至少一次处理边界，`007` 会继续解释幂等。

批量 poll 时还要按 partition 维护连续成功位置。不能在同一 partition 的较早消息失败后，直接提交较晚消息的 offset，否则会跳过失败消息。

## 5. Rebalance

### 5.1 加入与分配

```text
Consumer 携带 group.id 启动
  ↓
找到 Group Coordinator
  ↓
加入 group
  ↓
Coordinator 执行 partition assignment
  ↓
Consumer 从已分配 partition 拉取消息
```

常见分配策略包括 range、round-robin、sticky/cooperative-sticky。Consumer 加入、退出、心跳超时或 topic partition 数变化都可能触发 rebalance。

### 5.2 Consumer 崩溃后的接管

```text
consumer-A 处理 partition-0
  ↓
进程崩溃或心跳超时
  ↓
Coordinator 触发 rebalance
  ↓
partition-0 分配给 consumer-B
  ↓
consumer-B 从该 group 已提交 offset 继续
```

如果 A 完成业务但没提交 offset，B 会再次处理该消息；如果 A 先提交后完成业务，业务可能被跳过。

### 5.3 长时间处理与 poll

Consumer 如果长时间不 poll，可能超过 `max.poll.interval.ms` 并被认为无法正常处理，继而触发 rebalance。耗时任务应考虑：

- 缩小单次 poll 数量；
- 将耗时工作移交给受控工作线程，同时正确管理 pause/resume 和 offset；
- 调整 `max.poll.interval.ms`，但不能用无限增大配置掩盖处理能力不足。

## 6. 应用举例

### 6.1 两个 group 各自消费完整事件流

```bash
kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic order-events --group order-service

kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic order-events --group analytics-service
```

### 6.2 崩溃恢复的判断

```text
先处理、后提交 → 可能重复，但不轻易跳过处理
先提交、后处理 → 可能跳过业务处理
```

Kafka 只负责保存 offset，无法替应用决定数据库事务与 offset 之间的原子边界。

## 7. 常见误区与排查思路

- **误区 1：同一个 topic 只能被一个系统消费。** 不同 group 可以各自完整消费。
- **误区 2：commit offset 等于业务成功。** Kafka 不知道业务事务是否完成。
- **误区 3：consumer 越多一定越快。** 同一 group 的有效并行度受 partition 数约束。
- **误区 4：重复读取一定是 Kafka 分发错误。** 先检查崩溃、rebalance、提交时机和处理超时。

## 8. 关联知识点

- `004_Kafka_Producer、Key、分区策略与热分区.md`
- `007_Kafka_投递语义、重复消费与幂等处理.md`
- `008_Kafka_重试机制、Retry_Topic_与死信队列.md`

## 9. 复习检查问题

- 同一 group 的消费并行度为什么受 partition 数限制？
- Offset 为什么按 group、topic、partition 保存？
- 先处理后提交与先提交后处理分别有什么风险？
- Rebalance 后新的 consumer 从哪里继续？
- 批量处理时为什么不能越过失败消息提交更大的 offset？
