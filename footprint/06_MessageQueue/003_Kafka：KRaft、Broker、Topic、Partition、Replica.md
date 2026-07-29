# Kafka：KRaft、Broker、Topic、Partition、Replica

> 所属分类：Message Queue / Kafka
> 修订版本：v12
> 知识边界：本文建立 Kafka 的架构与日志存储模型；Producer 分区见 `004`，副本确认和故障选举见 `005`，消费进度见 `006`。

## 1. 总体性概念

Kafka 不是“消费者取走后消息立即消失”的传统队列，而是一个分布式追加日志系统。Producer 把事件写入 topic；topic 被拆成多个 partitions；每个 partition 是一条有序日志，并可以保存多个 replicas。

核心对象：

- **Topic**：事件分类，例如 `order-events`。
- **Partition**：Topic 的分册，是顺序、并行和复制的基本单位。
- **Offset**：Partition 内记录的递增逻辑序号。
- **Broker**：保存 partition 日志并处理客户端请求的服务器节点。
- **Replica**：同一个 partition 的副本。
- **Leader replica**：负责该 partition 的对外读写。
- **Follower replica**：从 leader 拉取日志的备份副本。
- **KRaft controller quorum**：通过共识管理 broker、topic、partition、leader 等集群元数据。

Kafka 3.3 起 KRaft 可用于生产；Kafka 4.0 起 ZooKeeper 模式被移除，KRaft 成为唯一元数据机制。

## 2. Kafka 为什么更像事件日志

Producer 先把记录追加到 partition 日志，Consumer 再根据自己的 offset 拉取。消息不会因为某一个 consumer 读过就立刻从日志删除，而是由保留时间、保留大小或日志压缩策略管理。

这带来几项关键能力：

- 多个 consumer group 可以各自读取同一事件流；
- Consumer 挂掉后可以从已提交 offset 恢复；
- 在保留边界内可以重置 offset 并回放历史；
- 多个 partitions 可以并行读写；
- Replica 为 partition 提供故障恢复基础。

## 3. Partition 与 Offset

### 3.1 Partition 是顺序和并行单位

同一 partition 内，记录按 offset 排列；不同 partitions 之间没有全局顺序。同一 consumer group 的有效消费并行度通常不会超过订阅 topic 的 partition 数。

需要同一订单或用户的事件保持顺序时，应让相同业务 key 稳定进入同一 partition。Key 的具体选择、扩分区影响和热分区问题见 `004_Kafka_Producer、Key、分区策略与热分区.md`。

### 3.2 Offset 是逻辑序号

Offset 不是磁盘文件的绝对字节地址，只在某个 partition 内有意义。Partition 日志在磁盘上被切成多个 segments，每个 segment 通常包含：

```text
00000000000000000000.log       # 记录数据
00000000000000000000.index     # offset 到物理位置的稀疏索引
00000000000000000000.timeindex # timestamp 到 offset 的索引
```

定位记录的简化过程：

```text
目标 offset
  ↓
根据 segment base offset 选择 segment
  ↓
查询稀疏 .index，定位到接近的物理位置
  ↓
在 .log 中顺序扫描到准确记录
```

因此 offset 更像“分册中的行号”，segment 和稀疏索引负责把逻辑位置映射到磁盘数据。

## 4. KRaft 与数据复制的边界

KRaft 管理的是集群元数据和 controller 共识，不直接搬运业务消息。Partition 数据复制由 leader/follower replicas 完成。

```text
KRaft controller quorum
  ├─ broker 注册与存活元数据
  ├─ topic / partition 元数据
  ├─ partition leader 与 ISR 变更记录
  └─ controller 故障切换

Broker 上的 partition replicas
  ├─ 追加业务日志
  ├─ follower fetch
  └─ 维护复制进度
```

Leader broker 观察 follower 的复制状态并触发 ISR 变化，KRaft controller 负责持久化和传播相关元数据。更详细的 ISR、acks 和故障选举见 `005`。

## 5. 基础机制流程

### 5.1 创建 Topic

```text
客户端向集群提交创建 topic 请求
  ↓
Controller 生成 partition 与 replica 分配
  ↓
在不同 brokers 上创建 replica
  ↓
为每个 partition 指定 leader
  ↓
元数据传播到 brokers 和客户端
```

### 5.2 写入与读取的高层路径

```text
Producer
  ↓ 选择 partition
Partition Leader
  ↓ 追加日志并复制
Partition Log
  ↑ 按 offset 拉取
Consumer
```

Producer 如何选 partition 见 `004`；leader 等待哪些副本后确认见 `005`；Consumer 如何保存 offset 见 `006`。

## 6. 类比理解

Kafka 像分布式账本：

- Topic 是账本类型；
- Partition 是账本分册；
- Offset 是分册行号；
- Broker 是存放账本的柜子；
- Replica 是同一分册的副本；
- Leader 是当前对外提供读写的主本；
- KRaft controller quorum 是维护全局档案目录和主本归属的管理员集体。

## 7. 应用举例

### 7.1 KRaft 单节点学习环境

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

单节点只适合学习，不能演示真实副本容错。

### 7.2 查看 Topic 分区和副本

```bash
kafka-topics --bootstrap-server localhost:9092 \
  --describe --topic order-events
```

输出中的 `Leader`、`Replicas`、`Isr` 都是 partition 维度的信息，而不是给整个 broker 贴的固定角色标签。

## 8. 常见误区与排查思路

- **误区 1：Kafka 是读取后立即删除的普通队列。** 它首先是可保留、可回放的日志。
- **误区 2：offset 是全局消息 ID。** 它只在某个 partition 内有意义。
- **误区 3：KRaft 负责复制业务消息。** KRaft 管元数据，replicas 之间复制日志。
- **误区 4：broker 整体是 leader 或 follower。** 角色属于具体 partition replica。
- **误区 5：partition 越多越好。** 过多 partitions 会增加元数据、文件句柄、恢复和 rebalance 成本。

## 9. 关联知识点

- `004_Kafka_Producer、Key、分区策略与热分区.md`
- `005_Kafka_Leader_Follower、ISR、acks_与故障选举.md`
- `006_Kafka_Consumer_Group、Offset_与_Rebalance.md`
- `014_Kafka_vs_RabbitMQ：事件流、业务路由与选型.md`

## 10. 复习检查问题

- Topic、partition、offset、broker、replica 分别承担什么职责？
- Kafka 为什么能让多个 group 回放同一事件流？
- Offset 如何通过 segment 和稀疏索引定位磁盘记录？
- KRaft 元数据管理与 leader/follower 数据复制有什么区别？
- 为什么顺序、并行和复制都以 partition 为边界？
