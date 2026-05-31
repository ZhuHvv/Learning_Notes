# Kafka vs RabbitMQ：事件流与业务路由

> 所属分类：Message Queue / Kafka / RabbitMQ  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Kafka 偏事件流和日志保留，RabbitMQ 偏业务路由和任务分发。


## 2. 原理性解释

- Kafka 以 topic-partition-log 和 offset 为核心。
- RabbitMQ 以 exchange-queue-binding 为核心。
- Kafka 适合高吞吐事件流和回放。
- RabbitMQ 适合复杂路由和任务队列。

### Kafka 偏日志流，RabbitMQ 偏业务投递路由

Kafka 更像可持久保存、可回放的分布式事件日志，消费者通过 offset 管理进度；RabbitMQ 更像灵活的消息路由器，强调 exchange、binding、ack、死信等投递语义。二者都能做异步解耦，但核心抽象不同。

选择时不要只问“谁更快”，要问：是否需要回放历史？是否需要复杂路由？是否需要严格业务 ack？是否有流处理需求？

## 3. 机制流程

1. 判断是否需要回放。
2. 判断是否需要复杂路由。
3. 判断吞吐和顺序要求。
4. 选择中间件。

### 选型流程

```text
需要事件流、日志保留、回放、多 consumer group → Kafka
需要复杂路由、任务队列、灵活 ack/死信 → RabbitMQ
简单异步任务且已用 Redis → 可考虑 Redis Stream / List
```

Kafka 适合订单事件流、日志采集、用户行为流；RabbitMQ 适合邮件任务、业务通知、工作队列、复杂订阅规则。

## 4. 类比理解

Kafka 像可翻阅流水账，RabbitMQ 像分拣后取走的快递篮。

## 5. 应用举例 / 代码或伪代码

```text
日志/埋点/CDC -> Kafka
订单事件分发/任务队列/复杂路由 -> RabbitMQ
```

## 6. 你在讨论中的理解推进

你分别学习两者后，应按消息模型而非名字选择。

## 7. 常见误区与排查思路

- 只背名词，不知道它在完整链路中的输入、输出和失败模式。
- 只看正常路径，忽略异常、超时、权限、重复和可观测性。
- 把相邻概念混用，导致设计或排查时定位错误。

## 8. 关联知识点

- 回到 00_总体索引.md 查看上下游知识点。
- 结合 00_总体知识网络图.md 理解跨模块关系。

## 9. 复习检查问题

- 它解决的核心问题是什么？
- 它的输入、输出和中间状态分别是什么？
- 它在真实项目中最容易出错的边界条件是什么？
- 它和上游、下游知识点如何连接？

## 10. 更细的工程拆解

**Kafka vs RabbitMQ：事件流与业务路由** 要从“消息生命周期”看，而不是只记 Producer/Consumer 名词：

1. **生产**：业务代码把一次状态变化包装成事件或任务消息。
2. **路由/存储**：Kafka 通过 topic/partition 保序与持久化；RabbitMQ 通过 exchange/binding 做灵活路由。
3. **消费**：消费者拉取或接收消息，处理成功后确认；失败时重试、进入死信或等待人工介入。
4. **观测**：关注堆积量、消费延迟、失败率、重复消费和顺序性。

### 最小消费伪代码

```python
while True:
    msg = consumer.poll()
    try:
        handle(msg)
        consumer.ack(msg)              # 成功后确认
    except RetryableError:
        consumer.retry(msg)
    except Exception:
        consumer.send_to_dlq(msg)       # 不可恢复错误进入死信队列
```

### 工程落地要点

- MQ 不是“远程函数调用”，调用方通常不能假设对方立刻完成。
- 至少一次投递很常见，所以消费者必须尽量幂等。
- Kafka 更像事件日志，RabbitMQ 更像业务消息路由器；二者不是简单替代关系。

## 11. 针对 `Kafka vs RabbitMQ：事件流与业务路由` 的专项排查

消息队列的质量取决于端到端语义。检查 **Kafka vs RabbitMQ：事件流与业务路由** 时：

- **投递语义**：最多一次、至少一次、近似恰好一次分别意味着什么。
- **确认机制**：什么时候 ack/commit，失败后是否会重复消费。
- **顺序性**：业务是否要求同一实体的事件按顺序处理；Kafka 通常依赖 partition key。
- **积压处理**：消费者挂了、下游慢了、消息暴涨时，系统如何削峰与恢复。

### 小型练习

```python
def handle_order_event(event):
    # 练习：为 Kafka vs RabbitMQ：事件流与业务路由 设计幂等键，防止重复消费导致重复扣款/重复发货
    if processed(event.id):
        return
    apply_business_change(event)
    mark_processed(event.id)
```

### 面试表达模板

讲 `Kafka vs RabbitMQ：事件流与业务路由` 时，要从生产、路由/存储、消费、确认、失败处理五段说明，而不是只说“异步解耦”。

## 12. 本知识点的边界与复习建议

**Kafka vs RabbitMQ：事件流与业务路由** 的学习边界可以这样把握：先能用自己的话解释它解决的问题，再能画出输入、处理、输出三段流程，最后能写出一个最小代码或命令例子。复习时不要把它和相邻知识点混在一起：相邻知识点通常负责上游准备、下游消费或异常处理，而本文件只保留与 **Kafka vs RabbitMQ：事件流与业务路由** 直接相关的机制。

建议你复习时做三件事：

1. **复述定义**：不用术语堆砌，说明它为什么出现。
2. **画流程图**：至少标出输入、核心机制、输出、失败点。
3. **写最小例子**：哪怕只是伪代码，也要体现真实项目中会怎样使用。

如果之后继续扩展本知识库，可以在本文件下追加“项目踩坑记录”和“面试问答”，但不要把无关项目经历混入 **Kafka vs RabbitMQ：事件流与业务路由** 的原理解释中。


## Kafka 侧补充：为什么它更像事件日志

Kafka 的核心优势来自 partition 日志、consumer group offset 和可回放能力。消息写入 partition 后不会因为某个 consumer 读取就立刻删除，而是在保留时间或保留大小范围内继续存在。不同 consumer group 可以各自维护 offset，因此订单服务、统计服务、搜索索引服务可以同时订阅同一条事件流。

Kafka 的失败处理也更偏应用层：consumer 业务失败后通常通过“不提交 offset”“写入 retry topic”“写入 DLQ”等方式处理，而不是依赖 broker 理解业务异常。它适合高吞吐、可回放、事件驱动、日志型数据流。
