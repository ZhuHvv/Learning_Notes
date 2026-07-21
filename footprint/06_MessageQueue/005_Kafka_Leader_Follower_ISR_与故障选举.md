# Kafka Leader/Follower、ISR 与故障选举

> 所属分类：Message Queue / Kafka / RabbitMQ  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件专门解释 Kafka partition leader 宕机后的副本同步、ISR 维护与新 leader 选择过程。

## 1. 总体性概念

Kafka 的高可用不是“每条消息随便存几份”这么简单，而是围绕每个 partition 建立一组 replica。每组 replica 中只有一个 leader 对外提供读写，其它 follower 从 leader 拉取日志。ISR（in-sync replicas）表示当前同步状态足够好的副本集合。Leader broker 挂掉后，Kafka 会优先从 ISR 中选择新的 leader，以尽量保证已确认消息不丢失。

## 2. 原理性解释

### Leader 和 follower 是 partition 维度的角色

一个 broker 可以同时是某些 partition 的 leader，也可以是另一些 partition 的 follower。也就是说，leader/follower 不是整个 broker 的固定身份，而是针对具体 partition 的角色。

```text
Broker-1: topicA-p0 leader, topicA-p1 follower
Broker-2: topicA-p0 follower, topicA-p1 leader
Broker-3: topicA-p0 follower, topicA-p1 follower
```

### ISR 是“有资格接任 leader 的同步副本集合”

Follower 会持续向 leader 发送 fetch 请求，同步 leader 上的新日志。Leader 根据 follower 的 fetch 进度和延迟判断它是否仍然“跟得上”。如果 follower 长时间没有 fetch，或落后超过阈值，就会被移出 ISR；追上后又可以重新加入。

这也回答了你之前的疑问：**follower 的同步进度不是靠业务 ack，而是 follower 复制日志时向 leader 发起 fetch，并在 fetch 过程中暴露自己的日志进度。** Leader 通过这些进度判断 follower 是否同步。

### KRaft 与 ISR 的关系

KRaft 是 Kafka 新版本中的元数据共识层，负责 controller quorum、broker/topic/partition/leader 等元数据管理。ISR 变化最终也会成为集群元数据的一部分，但“谁发现 follower 落后”主要发生在 partition leader 这一侧。

更准确的表达是：

```text
leader broker 观察 follower 复制进度
  ↓
判断 ISR 是否变化
  ↓
向 controller / 元数据层提交 ISR 变化
  ↓
KRaft controller quorum 持久化并广播元数据变化
```

因此，KRaft 不是数据复制线程本身；它更像元数据大脑。

### 为什么优先从 ISR 选 leader

因为 ISR 中的副本与旧 leader 足够同步。若从 ISR 外选 leader，那个副本可能缺少旧 leader 上已经写入、甚至已经对 producer 确认的消息，导致数据回退或丢失。

Kafka 有一个配置叫 `unclean.leader.election.enable`。如果开启，当 ISR 中没有副本可用时，Kafka 可能从非 ISR 副本中选 leader，提高可用性但牺牲一致性。对订单、支付等核心业务，通常不建议开启。

## 3. 机制流程

### 3.1 正常复制流程

```text
Producer 写入 partition leader
  ↓
leader 追加消息到本地日志
  ↓
follower 周期性向 leader fetch 新日志
  ↓
follower 追加到自己的本地日志
  ↓
leader 根据 follower 进度维护 ISR
```

### 3.2 Leader broker 挂掉后的选举流程

```text
Broker 心跳超时或网络断开
  ↓
KRaft controller 判断 broker 不可用
  ↓
找出该 broker 上担任 leader 的 partitions
  ↓
对每个 partition，从 ISR 中选择新的 leader
  ↓
更新 partition metadata：leader、leader epoch、ISR 等
  ↓
其它 broker 和客户端刷新 metadata
  ↓
producer/consumer 重试并连接新 leader
```

### 3.3 Producer 端看到的表现

Producer 不会直接参与选举。它通常会遇到类似“不是 leader”或连接失败的错误，然后刷新 metadata，再向新 leader 重试。

```python
def send_with_metadata_refresh(record):
    try:
        producer.send(record)
    except NotLeaderForPartition:
        producer.refresh_metadata()
        producer.send(record)
```

## 4. 类比理解

一个 partition 像一份重要账本。Leader 是当前唯一允许写入的主账本，follower 是实时复印本。ISR 是“复印进度合格，可以随时接替主账本”的复印本名单。KRaft controller 像档案管理员，负责在主账本柜子坏掉时宣布哪一本复印本升为新主账本。

## 5. 应用举例 / 代码或伪代码

### 5.1 高可用 topic 配置建议

```bash
kafka-topics --bootstrap-server kafka1:9092 \
  --create --topic payment-events \
  --partitions 12 \
  --replication-factor 3 \
  --config min.insync.replicas=2
```

Producer 配置：

```properties
acks=all
enable.idempotence=true
retries=2147483647
max.in.flight.requests.per.connection=5
```

含义：leader 必须等待 ISR 中足够副本同步，producer 也要支持安全重试。

### 5.2 简化版 ISR 判断伪代码

```python
def update_isr(partition, now):
    new_isr = []
    for replica in partition.replicas:
        lag_time = now - replica.last_fetch_time
        lag_offset = partition.leader_end_offset - replica.log_end_offset
        if lag_time <= REPLICA_LAG_TIME_MAX and lag_offset <= LAG_OFFSET_MAX:
            new_isr.append(replica)
    partition.isr = new_isr
```

真实 Kafka 的实现更复杂，但核心思想就是通过 follower 的复制进度判断其是否仍然同步。

## 6. 你在讨论中的理解推进

你先确认了 leader/follower 是 partition 的概念，又进一步追问“partition 只是存储单位，维护 ISR 的是不是 leader 所在 broker”。这个推进非常关键：partition 的 leader replica 在某个 broker 上，该 broker 对这个 partition 的复制状态有直接观察能力；KRaft controller 负责全局元数据和 leader 变更协调。

## 7. 常见误区与排查思路

- **误区 1：broker 是 leader 或 follower。** 实际上 broker 可以对不同 partitions 扮演不同角色。
- **误区 2：follower 会给 producer 发 ack。** Producer 只和 leader 交互；follower 复制进度通过 fetch 体现。
- **误区 3：ISR 越大越好。** ISR 代表同步副本集合，过小代表风险；但如果 follower 慢，强行等待会拖慢写入。
- **误区 4：unclean election 是免费高可用。** 它提高可用性，但可能丢数据。

## 8. 关联知识点

- `003_Kafka：KRaft、Broker、Topic、Partition、Replica.md`
- `004_Kafka_Consumer_Group_与_Offset.md`
- `007_Kafka_Key、分区策略与热分区.md`

## 9. 复习检查问题

- ISR 是谁根据什么信息维护的？
- KRaft controller 在 leader 故障时做什么？
- follower 同步进度如何体现？
- 为什么优先从 ISR 中选新 leader？
- unclean leader election 的代价是什么？
