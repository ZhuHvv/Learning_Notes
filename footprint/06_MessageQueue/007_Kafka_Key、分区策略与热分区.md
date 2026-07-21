# Kafka Key、分区策略与热分区

> 所属分类：Message Queue / Kafka / RabbitMQ  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件专门解释 Kafka key 如何影响 partition、顺序性、负载均衡和热分区问题。

## 1. 总体性概念

Kafka 的 key 决定消息更倾向落到哪个 partition。相同 key 通常会被分到同一个 partition，因此可以保证同一业务实体的事件顺序；但如果某些 key 流量特别大，就会让某个 partition 压力远高于其它 partition，形成热分区。

Key 是 Kafka 里连接“业务顺序性”和“系统负载均衡”的关键点。

## 2. 原理性解释

### 有 key 与无 key 的分区选择不同

常见分区策略可以简化理解为：

```python
if record.key is not None:
    partition = hash(record.key) % partition_count
else:
    partition = sticky_or_round_robin_partition()
```

有 key 时，相同 key 会稳定进入同一个 partition；无 key 时，producer 会更关注吞吐和均衡，可能使用 sticky partitioner 批量写入某个 partition 后再切换。

### 顺序性依赖 partition，而不是 topic

Kafka 只能保证同一个 partition 内的消息顺序。假设同一订单的三个事件：

```text
OrderCreated(order_id=1001)
OrderPaid(order_id=1001)
OrderShipped(order_id=1001)
```

如果都以 `order_id` 作为 key，它们会进入同一个 partition，consumer 就能按顺序看到；如果没有 key，它们可能分散到不同 partitions，消费顺序就无法保证。

### 热分区的本质

热分区通常不是 Kafka 坏了，而是 key 分布不均。例如一个超大直播间、一个热门商品、一个大客户账号占据了 70% 流量，而你又用 `room_id`、`product_id`、`tenant_id` 做 key，那么所有相关消息都会打到同一个 partition。

表现通常是：

- 某个 partition 的 log end offset 增长极快；
- consumer lag 集中在少数 partitions；
- broker 某块磁盘或某个线程压力异常；
- 增加 consumer 实例也没用，因为热 partition 同一时刻只能给一个 group 内 consumer 处理。

### key 设计的取舍

Key 设计没有万能答案：

- 用 `order_id`：保证订单内顺序，但大订单可能热点。
- 用 `user_id`：保证用户维度顺序，但大用户可能热点。
- 用随机 key：负载均衡好，但业务顺序性弱。
- 用复合 key 或加盐 key：缓解热点，但可能破坏严格顺序。

工程设计就是在“顺序性”和“均衡性”之间做取舍。

## 3. 机制流程

### 3.1 正常按 key 分区

```text
Producer 发送消息，携带 key=user_id
  ↓
partitioner 计算 hash(user_id) % partition_count
  ↓
消息写入对应 partition
  ↓
同一 user_id 的消息进入同一 partition
  ↓
consumer 在该 partition 内按 offset 顺序处理
```

### 3.2 热分区产生流程

```text
某个 key 的业务流量远大于其它 key
  ↓
hash 后长期落到同一个 partition
  ↓
该 partition 写入量和 lag 急剧增加
  ↓
同一 group 内只能一个 consumer 消费它
  ↓
扩容 consumer 无法线性解决
```

### 3.3 缓解思路

```text
确认是否必须严格按该 key 保序
  ↓
如果必须保序：优化单 partition 消费性能、拆业务、减少下游瓶颈
  ↓
如果不必须严格保序：使用复合 key、加盐、拆 topic 或重新设计事件粒度
  ↓
监控 partition-level lag 和 broker 资源
```

## 4. 类比理解

Partition 像多个收银台，key 像顾客被分配到哪个收银台的规则。如果所有 VIP 客户都被规定只能去 1 号收银台，那么 1 号台会排爆，其它台很空。增加更多收银员没用，因为规则仍然让 VIP 只排 1 号台。

## 5. 应用举例 / 代码或伪代码

### 5.1 订单事件保序

```python
def publish_order_event(order_id, event):
    producer.send(
        "order-events",
        key=str(order_id).encode(),
        value=json.dumps(event).encode()
    )
```

### 5.2 加盐缓解热点，但牺牲严格顺序

```python
def salted_key(user_id, shard_count=8):
    salt = random.randint(0, shard_count - 1)
    return f"{user_id}:{salt}"
```

这种方式会把同一 user_id 拆到多个 partitions，提高并行度，但同一 user_id 的全局顺序不再天然保证。只能用于不要求严格按用户顺序处理的场景，或者需要在下游重新聚合排序。

### 5.3 热分区排查命令思路

```bash
# 查看 consumer group 各 partition lag
kafka-consumer-groups --bootstrap-server localhost:9092 \
  --describe --group order-service
```

重点看 lag 是否集中在某几个 partitions，而不是平均分布。

## 6. 你在讨论中的理解推进

你在 Kafka 学习中逐步意识到：partition 不只是存储单位，也是并行度、顺序性和负载均衡的边界。今天补充 key 与热分区后，这条线更完整：key 决定消息落点，落点决定顺序和消费并行度，流量分布不均就会形成热分区。

## 7. 常见误区与排查思路

- **误区 1：partition 多就一定均衡。** 如果 key 极度倾斜，再多 partitions 也可能有热点。
- **误区 2：随机 key 最好。** 随机 key 均衡但破坏同一实体顺序。
- **误区 3：扩 consumer 就能解决所有 lag。** 热 partition 同一时刻仍只能由一个 consumer 处理。
- **误区 4：加盐没有代价。** 加盐会牺牲 key 维度严格顺序，需要业务接受。

## 8. 关联知识点

- `003_Kafka：KRaft、Broker、Topic、Partition、Replica.md`
- `004_Kafka_Consumer_Group_与_Offset.md`
- `008_Kafka_消息分发、多消费者语义与幂等处理.md`

## 9. 复习检查问题

- Kafka 为什么只能保证 partition 内有序？
- key 如何影响 partition 选择？
- 什么是热分区？它为什么不是简单增加 consumer 就能解决？
- 加盐 key 能解决什么，又会破坏什么？
- 订单事件、用户行为事件、日志事件分别适合怎样设计 key？
