# Kafka 消息分发、多消费者语义与幂等处理

> 所属分类：Message Queue / Kafka / RabbitMQ  
> 修订版本：v11  
> 质量要求：本文件专门回答“一条消息是否会被多个 consumer 处理”、consumer group 分发边界、重复消费和幂等处理。

## 1. 总体性概念

Kafka 的消息分发不是 broker 把消息“平均推送”给所有 consumer，而是 consumer group 按 partition 分配后主动拉取。是否会出现一条消息被多个 consumer 处理，取决于这些 consumer 是否属于同一个 group，以及 offset 是否已经正确提交。

核心结论：

```text
不同 group：同一条消息可以被多个 group 各处理一次。
同一 group：同一 partition 同一时刻只给一个 consumer，正常不会并发重复处理。
异常恢复：同一 group 内仍可能因为 offset 未提交、rebalance、超时而重复处理。
```

## 2. 原理性解释

### Kafka 的“分发”其实是 partition assignment + consumer pull

RabbitMQ 更像 broker 根据 exchange/queue/ack 主动管理投递；Kafka 更像把日志放在那里，由 consumer 根据分配到的 partition 和自己的 offset 拉取。

```text
Group Coordinator 负责分配 partition
Consumer 负责 poll
Offset 负责记录进度
业务代码负责处理成功与幂等
```

所以 Kafka broker 并不直接知道“这条消息的业务逻辑是否成功执行”。它只知道 consumer group 提交到了哪个 offset。

### 多个 consumer 处理同一条消息的三种情况（摘要）

- **不同 group**：各自维护 offset，同一条消息每个 group 各处理一次，这是事件流被多系统订阅的正常能力。
- **同一 group 正常情况**：一个 partition 同一时刻只分配给组内一个 consumer，不会并发重复处理。
- **同一 group 异常情况**：处理成功但未 commit offset 就崩溃，rebalance 后接管者从旧 offset 重读，产生“恢复后的再次处理”。

三种情况的详细展开见 `077_Kafka_Consumer_Group_与_Offset.md`，本文聚焦由此引出的幂等处理。

### 幂等处理是 Kafka 消费端基本功

幂等的含义是：同一条业务事件执行多次，最终结果和执行一次一致。常见做法：

- 用 `event_id` 建去重表；
- 数据库唯一索引防重复插入；
- 状态机只允许合法状态迁移；
- 使用业务版本号；
- 对外部调用保存请求流水号。

不要用 Kafka offset 直接做业务幂等键，因为 offset 只在 topic-partition 内唯一，业务重放、跨 topic 转发、retry topic 后可能不再适合作为业务唯一 ID。

## 3. 机制流程

### 3.1 多 group 订阅流程

```text
Producer 写入 order-events
  ↓
order-service group 按自己的 offset 消费
analytics-service group 按自己的 offset 消费
search-service group 按自己的 offset 消费
  ↓
每个 group 互不影响
```

### 3.2 同 group 分摊流程

```text
多个 consumer 使用同一个 group.id
  ↓
Group Coordinator 执行 rebalance
  ↓
每个 partition 分配给其中一个 consumer
  ↓
各 consumer 只 poll 自己负责的 partitions
```

### 3.3 重复消费防护流程

```text
poll 消息
  ↓
解析业务 event_id
  ↓
检查幂等表 / 唯一索引 / 状态机
  ↓
未处理：执行业务并记录 event_id
已处理：直接跳过
  ↓
commit offset
```

## 4. 类比理解

Kafka 像图书馆里的多本账本。不同部门可以各自借阅同一本账本复印件做自己的统计；同一部门内部会分工，每个人负责几本分册。某个人读完一页但没在部门书签上标记，换人后就可能再读一遍，所以部门内部必须能识别“这张单据是否已经处理过”。

## 5. 应用举例 / 代码或伪代码

### 5.1 幂等表设计

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

### 5.2 幂等消费代码

```python
def consume(msg):
    event = json.loads(msg.value)
    event_id = event["event_id"]

    try:
        with db.transaction():
            db.execute("INSERT INTO processed_event(event_id, processed_at) VALUES (?, now())", event_id)
            apply_business_change(event)
        consumer.commit(msg.offset + 1)
    except UniqueKeyConflict:
        # 说明处理过，直接提交 offset
        consumer.commit(msg.offset + 1)
```

### 5.3 状态机防重复

```python
def pay_order(order_id, event_id):
    order = db.get_order(order_id)
    if order.status == "PAID":
        return  # 重复支付事件，不再重复扣款
    if order.status != "CREATED":
        raise InvalidState(order.status)
    db.update_order_status(order_id, "PAID")
```

## 6. 你在讨论中的理解推进

你已经明确了一个关键判断：同一个 consumer group 中一条消息通常只由一个 consumer 处理；不同 consumer group 则会各自处理。同一 group 内真正需要警惕的是异常恢复带来的重复消费，而不是正常路径下的并发抢同一条消息。

## 7. 常见误区与排查思路

- **误区 1：Kafka 会保证业务 exactly-once。** Kafka 可以提供一些事务和幂等 producer 能力，但端到端业务 exactly-once 仍依赖你的数据库、外部接口和幂等设计。
- **误区 2：看到重复日志就是 Kafka 分发错了。** 先检查 offset 提交、rebalance、超时、consumer 重启和 retry 逻辑。
- **误区 3：offset 可以直接当业务唯一 ID。** 更建议使用业务 event_id。
- **误区 4：不同 group 重复消费是异常。** 这是 Kafka 支持多系统订阅事件流的正常能力。

## 8. 关联知识点

- `077_Kafka_Consumer_Group_与_Offset.md`
- `079_Kafka_重试机制、Retry_Topic_与死信队列.md`
- `080_Kafka_Key、分区策略与热分区.md`

## 9. 复习检查问题

- 哪些情况下同一条 Kafka 消息会被多个 consumer 处理？
- 为什么同一 group 内仍然需要幂等？
- offset 和业务 event_id 有什么区别？
- rebalance 为什么可能导致重复处理？
- 消费者处理失败时应该如何设计 retry 和 DLQ？
