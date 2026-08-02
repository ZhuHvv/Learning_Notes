# Kafka Producer、Key、分区策略与热分区

## 1. 总体性概念

Producer 不只是“把消息发到 topic”。发送前，它还要完成序列化、选择 partition、批处理并找到该 partition 的 leader broker。

Key 是连接业务顺序性与系统负载均衡的关键：

- 相同 key 通常稳定进入同一个 partition，因此可以保证同一业务实体的事件顺序；
- 没有 key 时，Producer 更倾向于通过 sticky 等策略提高批处理效率和负载均衡；
- 少数 key 流量过大时，会形成热分区。

## 2. Producer 写入路径

一条消息的简化写入路径如下：

```text
业务事件
  ↓
序列化 key 和 value
  ↓
显式 partition / key hash / 无 key 分区策略
  ↓
按 partition 进入 Producer batch
  ↓
查询 metadata，找到 partition leader
  ↓
发送 ProduceRequest
  ↓
等待 005 所述的 acks 与副本确认
```

分区选择可以简化为：

```python
if record.partition is not None:
    partition = record.partition
elif record.key is not None:
    partition = hash(record.key) % partition_count
else:
    partition = sticky_partition_for_batching()
```

真实客户端还会处理可用分区、自适应分区、批次、压缩和 metadata 刷新，因此这段代码只用于理解决策顺序。

## 3. Key、顺序性与分区数

### 3.1 顺序性属于 partition，不属于整个 topic

Kafka 只保证同一个 partition 内的记录按 offset 有序。假设同一订单产生：

```text
OrderCreated(order_id=1001)
OrderPaid(order_id=1001)
OrderShipped(order_id=1001)
```

如果三条记录都使用 `order_id` 作为 key，它们通常会进入同一 partition，消费者便能按顺序读取。没有 key 时，它们可能进入不同 partitions，Kafka 不保证跨 partition 的全局顺序。

还要注意：增加 topic 的 partition 数后，`hash(key) % partition_count` 的结果可能改变。扩分区不会改写历史消息，但同一个 key 的新消息可能不再和旧消息处于同一 partition。对强顺序业务，扩分区前必须评估迁移边界。

### 3.2 Key 的设计取舍

- `order_id`：保证订单内顺序，但超大订单可能形成热点。
- `user_id`：保证用户维度顺序，但大用户可能形成热点。
- 随机 key 或无 key：分布更均衡，但失去实体维度顺序。
- 复合 key 或加盐 key：提高并行度，但会拆散原 key 的严格顺序。

Key 不是越细或越随机越好，设计时要先回答“业务究竟在哪个维度要求顺序”。

## 4. 热分区

热分区的本质是流量分布不均。比如一个热门商品、直播间或大租户占据大部分流量，同时又使用 `product_id`、`room_id` 或 `tenant_id` 作为 key，那么相关记录会集中写入一个 partition。

常见表现：

- 某个 partition 的 log end offset 增长明显更快；
- consumer lag 集中在少数 partitions；
- 某个 broker 的磁盘、网络或请求线程压力突出；
- 增加 consumer 实例后吞吐没有线性增长，因为同一 group 内一个 partition 同一时刻仍只交给一个 consumer。

## 5. 机制流程

### 5.1 正常按 key 分区

```text
Producer 携带 key=user_id
  ↓
partitioner 计算稳定映射
  ↓
同一 user_id 进入同一 partition
  ↓
consumer 按 partition offset 顺序处理
```

### 5.2 热分区产生与处理

```text
少数 key 占据绝大多数流量
  ↓
写入和 lag 集中到少数 partitions
  ↓
先确认是否必须严格按该 key 保序
  ├─ 必须：优化单 partition 消费、拆业务、减少下游瓶颈
  └─ 不必须：复合 key、加盐、拆 topic 或调整事件粒度
```

## 6. 应用举例

### 6.1 订单事件保序

```python
def publish_order_event(order_id, event):
    producer.send(
        "order-events",
        key=str(order_id).encode(),
        value=json.dumps(event).encode(),
    )
```

### 6.2 加盐缓解热点

```python
def salted_key(user_id, shard_count=8):
    salt = random.randint(0, shard_count - 1)
    return f"{user_id}:{salt}"
```

加盐会让同一 `user_id` 进入多个 partitions，因此只能用于不要求严格用户级顺序的场景，或由下游根据业务版本重新聚合排序。

### 6.3 排查热分区

```bash
kafka-consumer-groups --bootstrap-server localhost:9092 \
  --describe --group order-service
```

重点比较各 partition 的 current offset、log end offset 和 lag，而不是只看 group 总 lag。

## 7. 常见误区与排查思路

- **误区 1：partition 多就一定均衡。** Key 严重倾斜时，增加 partition 也不一定消除热点。
- **误区 2：随机 key 总是最好。** 它改善均衡，却会破坏实体级顺序。
- **误区 3：增加 consumer 就能解决所有 lag。** 单个热 partition 的并行消费上限仍然是一个 consumer。
- **误区 4：扩 partition 不影响 key 路由。** 分区总数变化可能改变 key 到 partition 的映射。

## 8. 关联知识点

- `003_Kafka：KRaft、Broker、Topic、Partition、Replica.md`
- `005_Kafka_Leader_Follower、ISR、acks_与故障选举.md`
- `006_Kafka_Consumer_Group、Offset_与_Rebalance.md`

## 9. 复习检查问题

- Producer 发送消息前如何选择 partition？
- Kafka 为什么只能保证 partition 内有序？
- Key 与 partition 数共同决定了什么？
- 热分区为什么不能总靠增加 consumer 解决？
- 加盐 key 改善了什么，又牺牲了什么？
