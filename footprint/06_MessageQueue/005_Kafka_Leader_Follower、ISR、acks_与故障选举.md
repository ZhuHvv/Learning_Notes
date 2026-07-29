# Kafka Leader/Follower、ISR、acks 与故障选举

> 所属分类：Message Queue / Kafka
> 修订版本：v12
> 知识边界：本文解释 partition 副本如何复制、Producer 何时收到确认，以及 leader 故障后如何恢复。

## 1. 总体性概念

每个 partition 可以有多个 replicas，其中一个 leader 处理该 partition 的客户端读写，其余 followers 主动从 leader 拉取日志。ISR（in-sync replicas）是当前同步状态满足要求的副本集合。

Kafka 的可靠写入由多个条件共同决定：

- replication factor 决定副本总数；
- ISR 表示当前同步副本；
- `acks` 决定 Producer 等待到什么程度；
- `min.insync.replicas` 决定 `acks=all` 时至少需要多少 ISR 才允许写入；
- leader 故障时优先从 ISR 中选新 leader。

## 2. Leader/Follower 与 ISR

### 2.1 角色属于 partition replica

一个 broker 可以是某些 partitions 的 leader，同时是另一些 partitions 的 follower：

```text
Broker-1: topicA-p0 leader,   topicA-p1 follower
Broker-2: topicA-p0 follower, topicA-p1 leader
Broker-3: topicA-p0 follower, topicA-p1 follower
```

不能说“Broker-1 是整个 Kafka 集群的 leader”。

### 2.2 Follower 主动 Fetch

```text
Follower 记录本地 log end offset
  ↓
向 leader 发 FetchRequest
  ↓
Leader 返回后续日志批次
  ↓
Follower 追加到本地日志
  ↓
下一次 fetch 继续暴露复制进度
```

Follower 不向 Producer 直接发送业务 ack。Leader 通过 replica fetch 的时间与追赶状态判断 follower 是否仍同步。

### 2.3 现代 Kafka 的 ISR 判断

现代 Kafka 不再使用固定的“落后多少条消息”阈值判断 ISR。核心配置是 `replica.lag.time.max.ms`：

- follower 长时间没有发送 fetch；
- 或 follower 在该时间窗口内始终没有追到过 leader 当时的日志末端；

满足这些落后条件时，leader 会把 follower 移出 ISR。Follower 重新追上后可以再次加入。

```python
def should_remain_in_isr(replica, now, replica_lag_time_max_ms):
    fetch_is_fresh = now - replica.last_fetch_time <= replica_lag_time_max_ms
    caught_up_recently = (
        now - replica.last_caught_up_time <= replica_lag_time_max_ms
    )
    return fetch_is_fresh and caught_up_recently
```

这段伪代码表达的是时间窗口，不是 Kafka 内部实现的逐行复制。

## 3. KRaft、ISR 与高水位

Leader broker 直接观察 follower fetch 进度并发起 ISR 变化；KRaft controller quorum 持久化和传播 partition leader、ISR 等元数据。

```text
leader 观察复制进度
  ↓
判断 ISR 是否变化
  ↓
提交 ISR 元数据变更
  ↓
KRaft controller quorum 持久化并传播
```

Kafka 还通过 high watermark 限制普通消费者可读取的范围。可以简化理解为：只有已经复制到足够同步副本、被视为已提交的日志范围才会推进高水位，消费者不会读取 leader 上尚未达到可见条件的尾部数据。

## 4. Producer 的 acks

- `acks=0`：不等待 broker 确认，吞吐高但可能在客户端不知情时丢失。
- `acks=1`：leader 本地追加成功就确认；leader 宕机且 follower 尚未复制时可能丢失已确认记录。
- `acks=all` 或 `acks=-1`：等待当前 ISR 中的副本确认。配合 `min.insync.replicas`，可以在同步副本不足时拒绝写入，避免以过低冗余继续接收可靠写请求。

典型可靠性组合：

```properties
acks=all
enable.idempotence=true
```

Topic 侧：

```text
replication.factor=3
min.insync.replicas=2
```

`acks=all` 并不等于绝对不会丢数据。机房级灾难、错误配置、磁盘同时损坏、主动删除或允许不干净选举等因素仍会影响结果。

Producer 的幂等模式还能避免客户端重试造成同一 partition 内的重复写入，并约束安全的重试与 in-flight 请求配置。

## 5. 完整写入流程

```text
Producer 根据 key 或分区器选择 partition
  ↓
向该 partition leader 发送 ProduceRequest
  ↓
leader 追加本地日志
  ↓
followers 通过 FetchRequest 拉取新日志
  ↓
leader 根据 acks、ISR 和 min.insync.replicas 判断是否确认
  ↓
推进可见范围
  ↓
Consumer 后续按 offset 拉取
```

分区选择的详细过程见 `004_Kafka_Producer、Key、分区策略与热分区.md`。

## 6. Leader 故障选举

```text
Broker 心跳超时或网络断开
  ↓
KRaft controller 判断 broker 不可用
  ↓
找出该 broker 上担任 leader 的 partitions
  ↓
优先从各 partition 的 ISR 中选择新 leader
  ↓
更新 leader、leader epoch、ISR 等元数据
  ↓
其它 brokers 和客户端刷新 metadata
  ↓
Producer / Consumer 重试并连接新 leader
```

客户端在切换过程中可能收到连接失败、`NotLeaderOrFollower` 等错误。它们不会参与选举，而是刷新 metadata 后重试。

### 为什么优先从 ISR 选择

ISR 中的副本在规定时间窗口内保持同步，更有机会包含旧 leader 已确认的数据。如果允许从 ISR 外的落后副本接任，日志可能回退。

`unclean.leader.election.enable=true` 可以在没有可用 ISR 时允许非 ISR 副本接任，提高可用性但可能丢数据。订单、支付等核心业务通常不建议开启。

## 7. 应用举例

### 7.1 创建高可用 Topic

```bash
kafka-topics --bootstrap-server kafka1:9092 \
  --create --topic payment-events \
  --partitions 12 \
  --replication-factor 3 \
  --config min.insync.replicas=2
```

### 7.2 Producer 配置

```properties
acks=all
enable.idempotence=true
retries=2147483647
max.in.flight.requests.per.connection=5
```

具体默认值会随客户端版本变化，生产配置应以所用版本文档为准；这里表达的是“允许安全重试并启用幂等 Producer”的组合思路。

## 8. 常见误区与排查思路

- **误区 1：broker 是固定 leader 或 follower。** 角色属于 partition replica。
- **误区 2：ISR 按固定 offset 差值判断。** 现代 Kafka 使用未追上的时间窗口。
- **误区 3：follower 直接给 Producer ack。** Producer 只与 leader 交互。
- **误区 4：KRaft 线程负责复制数据。** KRaft 管元数据和选举，replica fetch 复制日志。
- **误区 5：unclean election 是免费高可用。** 它用数据一致性换取可用性。

排查可靠性问题时同时查看：

```text
replication factor
当前 ISR 大小
min.insync.replicas
Producer acks / idempotence
UnderReplicatedPartitions
OfflinePartitionsCount
```

## 9. 关联知识点

- `003_Kafka：KRaft、Broker、Topic、Partition、Replica.md`
- `004_Kafka_Producer、Key、分区策略与热分区.md`
- `006_Kafka_Consumer_Group、Offset_与_Rebalance.md`

## 10. 复习检查问题

- Leader 如何感知 follower 的复制进度？
- 现代 Kafka 为什么不再用固定消息差值判断 ISR？
- `acks=1` 与 `acks=all` 的故障窗口有什么区别？
- `min.insync.replicas` 在什么条件下生效？
- KRaft controller 在 leader 故障时做什么？
- Unclean leader election 为什么可能造成日志回退？
