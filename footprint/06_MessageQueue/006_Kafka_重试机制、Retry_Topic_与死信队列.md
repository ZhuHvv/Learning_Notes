# Kafka 重试机制、Retry Topic 与死信队列

> 所属分类：Message Queue / Kafka / RabbitMQ  
> 修订版本：v11  
> 质量要求：本文件专门解释 Kafka 消费失败后的重试设计、retry topic、延迟重试、DLQ 以及与 consumer 断连的区别。

## 1. 总体性概念

Kafka 的 broker 并不知道你的业务处理是否成功。Consumer poll 到消息后，业务代码如果处理失败，需要由 consumer 端决定：不提交 offset 等待再次消费、立即本地重试、投递到 retry topic 延迟重试，或者超过次数后进入 DLQ（dead letter queue，死信队列）。

因此 Kafka 的重试机制更偏“应用层设计模式”，不像 RabbitMQ 那样有更直接的 nack/requeue/dead-letter-exchange 语义。

## 2. 原理性解释

### Consumer 处理失败与 consumer 断连是两类问题

你之前区分得很准确：

- **Consumer 断连/崩溃**：Kafka 通过心跳超时和 rebalance 把 partition 分配给其它 consumer；新 consumer 从已提交 offset 继续读。
- **Consumer 业务处理失败**：Kafka broker 默认不知道失败原因；是否重试、怎么重试，需要 consumer 代码主动处理。

```text
断连问题：由 group coordinator + offset 恢复处理
业务失败：由 consumer 逻辑 + retry topic / DLQ 处理
```

### 不提交 offset 的简单重试

最朴素的方式是处理失败就不提交 offset，等待下次再读同一条消息。这种方式简单，但有明显问题：

- 失败消息会阻塞同一 partition 后面的消息；
- 如果错误是永久性的，会形成“毒丸消息”反复失败；
- 难以做分级延迟重试。

### Retry Topic 模式

更常见的工程方案是把失败消息重新投递到 retry topic：

```text
order-events
  ↓ consumer 处理失败
order-events-retry-1m
  ↓ 1 分钟后重试失败
order-events-retry-5m
  ↓ 5 分钟后仍失败
order-events-dlq
```

Retry topic 中的消息通常会附带元数据：

```json
{
  "original_topic": "order-events",
  "original_partition": 2,
  "original_offset": 981,
  "retry_count": 2,
  "error": "payment service timeout",
  "payload": {"order_id": "A1001"}
}
```

### DLQ 的作用

DLQ 不是“垃圾桶”，而是人工排查和补偿入口。进入 DLQ 的消息通常满足：

- 超过最大重试次数；
- 反序列化失败；
- 数据字段缺失；
- 业务约束永久不满足；
- 依赖系统持续异常。

DLQ 要配合报警、可视化、人工修复和补偿脚本，否则只是把问题换了个 topic 存着。

## 3. 机制流程

### 3.1 同步本地重试

```text
poll 消息
  ↓
业务处理失败
  ↓
在当前 consumer 内 sleep/backoff 重试几次
  ↓
成功：commit offset
失败：投递 retry topic 或 DLQ
```

适合非常短暂的偶发错误，但不适合长时间 sleep，因为 consumer 长时间不 poll 可能触发 rebalance。

### 3.2 Retry Topic 分级重试流程

```text
主 topic: order-events
  ↓
consumer 处理失败
  ↓
生产一条消息到 order-events-retry-1m，并增加 retry_count
  ↓
提交主 topic offset，避免卡住原 partition
  ↓
retry consumer 到时间后重新投递回主 topic 或直接执行处理
  ↓
多次失败后投递 order-events-dlq
```

### 3.3 为什么通常要提交原消息 offset

一旦失败消息被安全写入 retry topic，原 topic 的 offset 通常可以提交。否则同一条消息会同时留在原 topic 待重读，又进入 retry topic，导致重复路径更复杂。

关键是顺序：

```text
处理失败
  ↓
先确保 retry 消息写入成功
  ↓
再 commit 原 topic offset
```

如果先 commit 再写 retry topic，进程在中间崩溃会导致消息丢处理。

## 4. 类比理解

主 topic 像正常办理窗口，retry topic 像“稍后再办”的等待区，DLQ 像异常工单池。窗口工作人员处理不了某个单子，不应该永远卡在窗口前面，而是把它转到等待区或异常工单池，并留下失败原因和原始编号。

## 5. 应用举例 / 代码或伪代码

### 5.1 Consumer 主流程伪代码

```python
MAX_RETRY = 3

while True:
    msg = consumer.poll()
    event = decode(msg.value)

    try:
        handle(event)
        consumer.commit(msg.offset + 1)
    except RetryableError as e:
        retry_msg = build_retry_message(msg, event, e)
        # send 是异步的，必须 .get() 同步等待（或 flush）确认 retry 消息真正写入成功，
        # 才能 commit 原 offset；否则进程崩溃时消息可能既没进 retry topic 又被跳过
        retry_producer.send("order-events-retry-1m", retry_msg).get(timeout=10)
        consumer.commit(msg.offset + 1)  # retry 消息确认写入成功后再提交原 offset
    except NonRetryableError as e:
        dlq_msg = build_dlq_message(msg, event, e)
        producer.send("order-events-dlq", dlq_msg)
        consumer.commit(msg.offset + 1)
```

### 5.2 分级 retry topic 选择

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

### 5.3 DLQ 消息结构建议

```json
{
  "event_id": "evt-001",
  "original_topic": "order-events",
  "original_partition": 0,
  "original_offset": 12001,
  "retry_count": 3,
  "failed_at": "2026-05-31T21:30:00+08:00",
  "error_type": "ValidationError",
  "error_message": "missing user_id",
  "payload": {}
}
```

## 6. 你在讨论中的理解推进

你已经抓住了 Kafka 重试的核心：retry topic 并不是 broker 自动帮你完成的魔法，而是 consumer 处理失败后主动把消息转发到另一个 topic；订阅 retry topic 的 consumer 可以是同一服务的另一个实例，也可以是专门的重试服务。这个理解非常接近真实项目中的设计方式。

## 7. 常见误区与排查思路

- **误区 1：Kafka broker 知道业务失败。** Broker 只知道 offset、心跳和请求结果，不知道你的数据库写入是否成功。
- **误区 2：失败就不 commit。** 不 commit 会重读，但可能阻塞 partition，适合少量临时失败，不适合复杂业务重试。
- **误区 3：DLQ 等于问题解决。** DLQ 只是隔离异常，后续仍需要报警、排查和补偿。
- **误区 4：retry consumer 一定要独立服务。** 可以独立，也可以和主 consumer 同一套代码不同订阅，取决于复杂度和隔离需求。

## 8. 关联知识点

- `004_Kafka_Consumer_Group_与_Offset.md`
- `008_Kafka_消息分发、多消费者语义与幂等处理.md`
- `002_流量削峰、异步解耦与最终一致性.md`

## 9. 复习检查问题

- Kafka 中业务失败为什么通常需要 consumer 主动处理？
- retry topic 和“不提交 offset 等待重读”有什么区别？
- 写 retry topic 与 commit 原 offset 的顺序为什么重要？
- DLQ 应该保存哪些排查字段？
- retry consumer 是否必须是专门服务？
