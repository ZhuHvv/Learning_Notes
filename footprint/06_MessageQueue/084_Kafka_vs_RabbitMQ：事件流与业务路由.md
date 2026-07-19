# Kafka vs RabbitMQ：事件流与业务路由

> 所属分类：Message Queue / Kafka / RabbitMQ  
> 修订版本：v9 昨日今日增量版  
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

## Kafka 侧补充：为什么它更像事件日志

Kafka 的核心优势来自 partition 日志、consumer group offset 和可回放能力。消息写入 partition 后不会因为某个 consumer 读取就立刻删除，而是在保留时间或保留大小范围内继续存在。不同 consumer group 可以各自维护 offset，因此订单服务、统计服务、搜索索引服务可以同时订阅同一条事件流。

Kafka 的失败处理也更偏应用层：consumer 业务失败后通常通过“不提交 offset”“写入 retry topic”“写入 DLQ”等方式处理，而不是依赖 broker 理解业务异常。它适合高吞吐、可回放、事件驱动、日志型数据流。
