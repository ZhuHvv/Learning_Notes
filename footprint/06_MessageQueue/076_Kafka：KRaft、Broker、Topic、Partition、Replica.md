# Kafka：KRaft、Broker、Topic、Partition、Replica

> 所属分类：Message Queue / Kafka / RabbitMQ  
> 修订版本：v11  
> 质量要求：本文件聚焦 Kafka 的存储与副本模型，覆盖 KRaft、broker、topic、partition、replica、leader/follower、ISR、offset 定位与写入复制流程。

## 1. 总体性概念

Kafka 不是传统意义上“消息从队列中取走就消失”的队列，而是一个**分布式追加日志系统**。Producer 把事件写入 topic，topic 被拆成多个 partition；每个 partition 内部是有序日志，日志有副本 replica，其中一个副本是 leader，其它是 follower。Broker 是承载 partition 日志和处理网络请求的服务器节点，KRaft 是 Kafka 负责元数据管理和 controller 选举的内部共识机制，自 Kafka 3.3 起生产可用；Kafka 4.0（2025-03）起 ZooKeeper 已被彻底移除，KRaft 是唯一的元数据机制。

可以把 Kafka 理解成：

- **Topic**：业务事件分类，例如 `order-created`。
- **Partition**：同一 topic 的分册，每个分册内部严格有序。
- **Offset**：partition 内每条消息的递增序号。
- **Broker**：存放这些分册的机器。
- **Replica**：同一本分册的多个副本。
- **Leader replica**：负责读写请求的主副本。
- **Follower replica**：从 leader 拉取数据、保持同步的备份。
- **KRaft controller quorum**：维护集群元数据；Kafka 3.3 起生产可用，4.0 起彻底取代 ZooKeeper 成为唯一元数据机制。

## 2. 原理性解释

### Kafka 的核心不是“把消息发给消费者”，而是“把事件稳定写进可回放日志”

Producer 写入 Kafka 时，消息不会直接推给某个 consumer，而是先被追加到某个 partition 的日志文件中。Consumer 只是根据自己的 offset 去拉取日志。正因为消息先落到日志中，Kafka 才能支持：

- 多个 consumer group 各自消费同一批消息；
- consumer 挂掉后从上次 offset 继续读；
- 历史消息在保留期内被重新回放；
- 通过 partition 并行提高吞吐量。

### Partition 是 Kafka 的顺序、并行和容错单位

同一个 partition 内消息按 offset 递增，因此**分区内有序**；但多个 partition 之间没有全局顺序。Kafka 的并行度主要来自 partition：一个 topic 有多少 partition，同一 consumer group 最多就有多少个消费者实例能真正并行消费它。

如果业务要求同一个订单、同一个用户、同一场比赛的事件顺序处理，就应该让这些事件使用相同 key，使它们落到同一个 partition。

### Offset 不是磁盘字节位置，而是 partition 内的逻辑序号

你之前问过“partition 是文件，broker 如何根据 offset 找到消息”。更准确地说，Kafka 的 partition 日志在磁盘上会被切成多个 segment，每个 segment 通常包含：

```text
00000000000000000000.log      # 真实消息数据
00000000000000000000.index    # offset -> 物理位置的稀疏索引
00000000000000000000.timeindex# timestamp -> offset 的索引
```

查找某个 offset 时，大致流程是：

```text
目标 offset
  ↓
根据 segment base offset 找到目标 segment
  ↓
查 .index 稀疏索引，定位到接近位置
  ↓
顺序扫描 .log，找到准确消息
```

所以 offset 更像“账本内的行号”，而不是“文件中的绝对字节地址”。Kafka 依靠 segment + 稀疏索引避免从头扫描整个 partition。

### Leader/Follower 与 ISR

每个 partition 的多个 replica 中，只有 leader 对外处理读写；followers 会不断向 leader 拉取日志，追赶 leader 的最新进度。Kafka 用 ISR（in-sync replicas）表示“当前与 leader 保持同步的一组副本”。

需要注意一个细节：**KRaft 管理集群元数据和 controller 选举，但 follower 是否还在 ISR 中，主要由 partition leader 根据 follower 的 fetch 进度和滞后时间判断，再把 ISR 变化写入/传播到集群元数据中。** 因此不能简单说“ISR 完全由 KRaft 主动维护”，更准确的说法是：leader broker 观察复制进度并触发 ISR 变更，KRaft controller 负责保存和广播这类元数据变更。

### Producer 的 acks 与数据可靠性

Producer 写入时可以配置 `acks`：

- `acks=0`：不等 broker 确认，吞吐高但容易丢。
- `acks=1`：leader 写入成功就返回，leader 宕机且 follower 未复制时可能丢。
- `acks=all` 或 `acks=-1`：等待 ISR 中足够副本确认，更可靠，通常配合 `min.insync.replicas` 使用。

典型生产环境为了可靠性，常使用：

```properties
acks=all
enable.idempotence=true
min.insync.replicas=2
replication.factor=3
```

这样不是绝对“不会出问题”，但能显著降低 leader 宕机导致已确认消息丢失的风险。

## 3. 机制流程

### 3.1 Producer 写入流程

```text
Producer 生成消息
  ↓
根据 key 或分区器选择 topic 的某个 partition
  ↓
向该 partition 的 leader broker 发送 ProduceRequest
  ↓
leader 把消息追加到本地 log segment
  ↓
follower 通过 FetchRequest 从 leader 拉取新日志
  ↓
leader 根据 acks/min.insync.replicas 判断是否返回成功
  ↓
消息对 consumer 可见，consumer 后续按 offset 拉取
```

### 3.2 Follower 同步流程

Follower 不是 leader 主动“推送”给它，而是不断向 leader 发起 fetch 请求：

```text
Follower 记录自己已复制到的 offset
  ↓
向 leader 请求从该 offset 之后的数据
  ↓
leader 返回日志记录
  ↓
follower 追加到本地日志
  ↓
follower 下一次 fetch 继续上报自己的进度
```

leader 正是通过这些 fetch 请求和进度来判断 follower 是否落后太多。如果 follower 长时间不 fetch 或落后超过阈值，就可能被移出 ISR。

### 3.3 Leader Broker 挂掉后的切换流程

```text
某个 broker 宕机或心跳超时
  ↓
KRaft controller 发现 broker 不可用
  ↓
对该 broker 上担任 leader 的 partitions 重新选 leader
  ↓
优先从 ISR 中选择新的 leader
  ↓
更新元数据并通知其它 broker
  ↓
producer/consumer 收到 NotLeaderOrFollower 等错误后刷新 metadata
  ↓
客户端改向新 leader 读写
```

如果 ISR 中没有可用副本，Kafka 可能选择等待副本恢复；如果开启 `unclean.leader.election.enable=true`，也可能从非 ISR 副本中选 leader，但这会牺牲一致性，可能丢失已确认或接近确认的数据。多数核心业务不建议开启 unclean leader election。

## 4. 类比理解

Kafka 像一个“分布式账本系统”：

- Topic 是账本类型，比如订单账本、支付账本。
- Partition 是账本分册。
- Offset 是分册里的行号。
- Broker 是存放账本的柜子。
- Leader 是当前可写的主账本。
- Follower 是复印件管理员，持续从主账本同步。
- ISR 是“复印质量合格、随时可以接任”的副本集合。
- KRaft controller 像档案室管理员，记录每本账本在哪个柜子、哪个副本是主本。

## 5. 应用举例 / 代码或伪代码

### 5.1 Docker Compose 中 KRaft 单节点核心配置

```yaml
services:
  kafka:
    image: confluentinc/cp-kafka:7.8.3
    ports:
      - "9092:9092"
      - "9093:9093"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_LOG_DIRS: /var/lib/kafka/data
```

### 5.2 生产消息时使用 key 保证同一实体顺序

```python
producer.send(
    topic="order-events",
    key=order_id.encode(),          # 相同 order_id 会稳定落到同一 partition
    value=json.dumps(event).encode()
)
```

### 5.3 高可靠 topic 创建示例

```bash
kafka-topics --bootstrap-server localhost:9092 \
  --create --topic order-events \
  --partitions 6 \
  --replication-factor 3 \
  --config min.insync.replicas=2
```

## 6. 你在讨论中的理解推进

你最初把 KRaft 理解为“管理若干 broker”，这是正确方向；现在需要进一步细化为：KRaft 管的是 Kafka 集群元数据和 controller 共识，而每个 partition 的复制进度主要由 leader broker 通过 follower fetch 进度感知。你也已经明确：partition 是存储与顺序单位，offset 是 partition 内消息进度，不同 consumer group 会有独立 offset。

## 7. 常见误区与排查思路

- **误区 1：Kafka 是普通队列。** Kafka 更像可回放日志，消息不会因为一个 consumer 读过就立刻消失。
- **误区 2：offset 是全局消息 ID。** offset 只在某个 partition 内有意义。
- **误区 3：KRaft 直接负责复制数据。** KRaft 管元数据；数据复制是 leader/follower replica 之间完成的。
- **误区 4：分区越多越好。** 分区过多会增加文件句柄、controller 元数据、rebalance 和恢复成本。

## 8. 关联知识点

- `077_Kafka_Consumer_Group_与_Offset.md`
- `078_Kafka_Leader_Follower_ISR_与故障选举.md`
- `080_Kafka_Key、分区策略与热分区.md`
- `084_Kafka_vs_RabbitMQ：事件流与业务路由.md`

## 9. 复习检查问题

- Kafka 的 topic、partition、replica、broker 分别对应什么职责？
- offset 为什么只能在 partition 内解释？
- follower 的同步进度是如何被 leader 感知的？
- KRaft 管理元数据，与 leader/follower 数据复制是什么关系？
- leader broker 挂掉后，新 leader 为什么通常要从 ISR 中选？
