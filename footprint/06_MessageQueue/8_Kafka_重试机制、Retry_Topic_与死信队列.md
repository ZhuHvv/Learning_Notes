# Kafka 重试机制、Retry Topic 与死信队列

## 1. 总体性概念

Kafka broker 不知道消费者的业务逻辑是否成功。Consumer 处理失败后，需要由应用决定：

- 不提交 offset，稍后重新读取；
- 在当前进程内进行少量短重试；
- 把消息可靠转发到 Retry Topic；
- 超过次数或确认不可恢复后进入 DLQ。

Retry Topic 是一种应用层模式，不是 Kafka 原生的“延时队列”。Topic 只负责保存记录；“什么时候允许再次处理”必须由消费者、框架或外部调度器实现。

## 2. 断连恢复与业务重试不是一回事

- **Consumer 断连或崩溃**：Group Coordinator 通过心跳超时和 rebalance 重新分配 partition，新 consumer 从已提交 offset 恢复。
- **业务处理失败**：Broker 不理解异常，需要消费代码判断错误是否可重试、何时重试以及何时进入 DLQ。

```text
断连恢复：group coordinator + rebalance + committed offset
业务失败：consumer policy + backoff + Retry Topic / DLQ
```

## 3. 三种重试方式

### 3.1 不提交 offset

失败后不提交，下一次仍从旧位置读取。

优点是简单，缺点是：

- 失败消息阻塞同一 partition 后面的记录；
- 永久错误会形成毒丸消息；
- 难以实现分级退避。

它只适合少量、短暂、很快能恢复的错误。

### 3.2 当前进程内短重试

```text
处理失败
  ↓
毫秒或秒级退避，重试少量次数
  ↓
成功：提交 offset
失败：转发 Retry Topic 或 DLQ
```

不要长时间 sleep。Consumer 长时间不 poll 可能超过 `max.poll.interval.ms` 并触发 rebalance。

### 3.3 Retry Topic

```text
order-events
  ↓ 失败
order-events-retry-1m
  ↓ 再失败
order-events-retry-5m
  ↓ 再失败
order-events-dlq
```

消息应携带：

```json
{
  "event_id": "evt-001",
  "original_topic": "order-events",
  "original_partition": 2,
  "original_offset": 981,
  "retry_count": 2,
  "next_retry_at": "2026-07-29T12:05:00+08:00",
  "error_type": "TimeoutError",
  "error_message": "payment service timeout",
  "payload": {"order_id": "A1001"}
}
```

## 4. Retry Topic 的延迟由谁实现

单纯把消息写入 `retry-1m` 并不会让 Kafka 等一分钟再交付。必须明确采用一种调度方式：

1. **框架管理的非阻塞重试**：由框架创建分级 topics，并管理暂停、恢复和重新投递。
2. **专用重试消费者**：读取 `next_retry_at`，未到期时对相关 partition 做受控 pause，定时 resume。要避免一个未到期消息长期阻塞同 partition 的其它重试消息。
3. **外部调度器**：把待重试任务存入支持按时间索引的数据存储，到期后重新发布到 Kafka。适合大量不同延迟和更严格的调度要求。

无论采用哪一种，都要处理实例重启、rebalance、重复调度和时钟偏差。Retry Topic 负责持久保存，调度层负责“何时重试”。

## 5. 转发与提交的可靠性

失败消息进入 Retry Topic 或 DLQ 后，才能推进原 topic 的 offset。顺序必须是：

```text
处理失败
  ↓
确认 retry/DLQ 消息写入成功
  ↓
再提交原 offset
```

如果先提交后转发，进程在中间崩溃会丢处理；如果转发成功但提交失败，原消息会再次读取，因此 `event_id` 幂等仍然必不可少。

当 Retry Topic、DLQ 和原 offset 都在同一个 Kafka 集群内时，可以使用 Kafka transaction，把“生产新消息”和 `sendOffsetsToTransaction` 放入同一事务。简单实现至少要同步等待发送确认后再提交。

## 6. DLQ 的作用

DLQ 是异常工单池，不是垃圾桶。常见进入条件：

- 超过最大重试次数；
- 反序列化或 Schema 不兼容；
- 必填字段缺失；
- 业务约束永久不满足；
- 依赖系统持续异常，超过业务恢复窗口。

DLQ 必须配套报警、查询、修复、重放和审计。否则只是把问题换了一个 topic 保存。

## 7. 应用举例

### 7.1 Consumer 主流程

```python
while True:
    msg = consumer.poll()
    event = decode(msg.value)

    try:
        handle(event)
        consumer.commit(msg.offset + 1)
    except RetryableError as exc:
        retry_msg = build_retry_message(msg, event, exc)
        retry_producer.send(
            choose_retry_topic(retry_msg["retry_count"]),
            retry_msg,
        ).get(timeout=10)
        consumer.commit(msg.offset + 1)
    except NonRetryableError as exc:
        dlq_msg = build_dlq_message(msg, event, exc)
        retry_producer.send("order-events-dlq", dlq_msg).get(timeout=10)
        consumer.commit(msg.offset + 1)
```

生产代码还要处理发送超时：发送未确认时不能提交原 offset，应让消息保留在原消费位置，或中止 Kafka transaction。

### 7.2 分级 Topic 选择

```python
def choose_retry_topic(retry_count):
    if retry_count == 0:
        return "order-events-retry-1m"
    if retry_count == 1:
        return "order-events-retry-5m"
    if retry_count == 2:
        return "order-events-retry-30m"
    return "order-events-dlq"
```

### 7.3 DLQ 字段

```json
{
  "event_id": "evt-001",
  "original_topic": "order-events",
  "original_partition": 0,
  "original_offset": 12001,
  "retry_count": 3,
  "failed_at": "2026-07-29T12:30:00+08:00",
  "error_type": "ValidationError",
  "error_message": "missing user_id",
  "payload": {}
}
```

## 8. 常见误区与排查思路

- **误区 1：Kafka broker 知道业务失败。** Broker 只知道协议请求、心跳和 offset。
- **误区 2：Retry Topic 天然带延迟。** 延迟必须由框架、消费者或外部调度器实现。
- **误区 3：写入 retry 后可以立即提交原 offset。** 必须先确认写入成功，或放在同一 Kafka transaction 中。
- **误区 4：DLQ 等于问题解决。** DLQ 后还需要告警、排查、补偿和重放。
- **误区 5：失败永远不提交最安全。** 毒丸消息会长期阻塞 partition。

## 9. 关联知识点

- `006_Kafka_Consumer_Group、Offset_与_Rebalance.md`
- `007_Kafka_投递语义、重复消费与幂等处理.md`
- `002_流量削峰、异步解耦与最终一致性.md`

## 10. 复习检查问题

- Consumer 断连与业务处理失败分别由谁处理？
- 不提交 offset 和 Retry Topic 各有什么代价？
- Retry Topic 为什么不会自动产生延迟？
- 写 retry/DLQ 与提交原 offset 的顺序是什么？
- Kafka transaction 能在哪个边界内改善原子性？
- DLQ 为什么必须配套补偿和重放流程？
