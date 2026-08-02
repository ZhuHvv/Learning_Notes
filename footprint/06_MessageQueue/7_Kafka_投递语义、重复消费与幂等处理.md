# Kafka 投递语义、重复消费与幂等处理

## 1. 总体性概念

Kafka 能记录 consumer group 读到了哪里，却不知道数据库写入、扣款或外部接口是否成功。端到端是否重复或遗漏，取决于业务处理与 offset commit 的先后关系。

常见语义：

- **At-most-once（最多一次）**：可能丢处理，但通常不重复；典型做法是先提交再处理。
- **At-least-once（至少一次）**：尽量不丢处理，但可能重复；典型做法是处理成功后提交。
- **Exactly-once（恰好一次）**：需要限定系统边界。Kafka 事务可以原子处理 Kafka 内的“消费—生产—提交 offset”，但涉及普通数据库、支付接口等外部系统时，仍需要幂等、事务消息或 Outbox 等设计。

多数业务消费者采用“至少一次 + 幂等处理”。

## 2. 一条消息什么时候会被多次处理

需要区分三种情况：

1. **不同 consumer group**：每个 group 各处理一次，是多系统订阅事件流的正常行为。
2. **同一 group 的稳定状态**：同一 partition 同一时刻通常只交给一个 consumer，不会正常并发处理同一 offset。
3. **同一 group 的异常恢复**：业务完成但 offset 未提交，崩溃或 rebalance 后会从旧 offset 重读。

详细的 group 分配与 rebalance 过程见 `006_Kafka_Consumer_Group、Offset_与_Rebalance.md`，本文只保留理解幂等所需的边界。

## 3. 处理与提交之间的失败窗口

### 3.1 先提交、后处理

```text
commit offset
  ↓
处理业务
  ↓
处理中崩溃
  ↓
Kafka 认为消息已消费，业务可能永远没完成
```

这是最多一次倾向。

### 3.2 先处理、后提交

```text
处理业务成功
  ↓
commit 前崩溃
  ↓
恢复后从旧 offset 重读
  ↓
同一业务事件再次执行
```

这是至少一次倾向，也是消费者必须幂等的主要原因。

## 4. 幂等处理方法

幂等意味着同一业务事件执行多次，最终结果与执行一次一致。常见手段：

- 用业务 `event_id` 建去重表；
- 用数据库唯一索引阻止重复插入；
- 用状态机限制合法状态迁移；
- 用业务版本号或乐观锁拒绝旧事件；
- 调用外部系统时传递稳定的幂等请求号；
- 将业务更新与“已处理事件”记录放入同一个数据库事务。

不要只用 Kafka offset 作为业务幂等键。Offset 只在 `topic + partition` 内唯一，消息进入 retry topic、跨 topic 转发或业务重放后，offset 都可能改变。更稳定的做法是从事件产生时就携带全局业务 `event_id`。

## 5. 机制流程

```text
poll 消息
  ↓
读取 event_id
  ↓
开启数据库事务
  ↓
写入幂等记录（唯一键）
  ├─ 已存在：说明处理过，跳过业务变更
  └─ 不存在：执行业务变更
  ↓
提交数据库事务
  ↓
commit Kafka offset
```

数据库事务成功而 offset commit 失败时，消息会重读，但唯一键会阻止业务重复生效。

## 6. 应用举例

### 6.1 幂等表

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

### 6.2 幂等消费

```python
def consume(msg):
    event = json.loads(msg.value)
    event_id = event["event_id"]

    try:
        with db.transaction():
            db.execute(
                "INSERT INTO processed_event(event_id, processed_at) VALUES (?, now())",
                event_id,
            )
            apply_business_change(event)
        consumer.commit(msg.offset + 1)
    except UniqueKeyConflict:
        # 数据库确认该事件已经生效，可以安全推进消费进度
        consumer.commit(msg.offset + 1)
```

### 6.3 状态机防重复

```python
def pay_order(order_id, event_id):
    order = db.get_order(order_id)
    if order.status == "PAID":
        return
    if order.status != "CREATED":
        raise InvalidState(order.status)
    db.update_order_status(order_id, "PAID")
```

### 6.4 外部接口的幂等键

```python
payment_client.capture(
    payment_id=payment_id,
    idempotency_key=event["event_id"],
)
```

如果外部系统不支持幂等键，单靠 Kafka 事务无法保证该外部副作用恰好一次。

## 7. 常见误区与排查思路

- **误区 1：Kafka 保证业务 exactly-once。** Kafka 的事务保证有明确边界，不能自动覆盖任意数据库和外部接口。
- **误区 2：看到重复日志就是 broker 分发错了。** 应先检查 commit、rebalance、超时、进程重启和 retry 路径。
- **误区 3：offset 可以直接当全局事件 ID。** 它只在某个 topic-partition 内有意义。
- **误区 4：状态已经是目标值就一定安全。** 扣款、发券等非简单状态覆盖操作还需要独立幂等流水。

## 8. 关联知识点

- `006_Kafka_Consumer_Group、Offset_与_Rebalance.md`
- `008_Kafka_重试机制、Retry_Topic_与死信队列.md`
- `002_流量削峰、异步解耦与最终一致性.md`

## 9. 复习检查问题

- At-most-once 和 at-least-once 的提交顺序分别是什么？
- 为什么同一 group 在稳定状态下不重复，异常恢复后仍可能重复？
- Offset 与业务 event_id 有什么区别？
- Kafka 事务为什么不能自动保证外部支付接口恰好一次？
- 去重表为什么要与业务变更处于同一数据库事务？
