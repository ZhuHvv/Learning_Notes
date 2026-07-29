# Message Queue

本目录按“通用原理 → Kafka 单链路深入 → RabbitMQ 单链路深入 → 综合选型”组织。序号越大，内容从名词与使用价值逐步进入分区、副本、投递语义、可靠性、延时和跨地域等工程问题。

知识点文件数：14

## 第一阶段：消息队列通用基础

1. [消息队列的核心概念：生产者、队列、消费者、消息分发](001_消息队列的核心概念：生产者、队列、消费者、消息分发.md)
   建立 Producer、Broker、Queue/Topic、Consumer 和确认的最小消息生命周期。
2. [流量削峰、异步解耦与最终一致性](002_流量削峰、异步解耦与最终一致性.md)
   理解为什么使用 MQ，以及异步化带来的延迟、幂等、补偿和可观测性成本。

## 第二阶段：Kafka——从写入到失败恢复

3. [Kafka：KRaft、Broker、Topic、Partition、Replica](003_Kafka：KRaft、Broker、Topic、Partition、Replica.md)
   架构、日志、segment、offset 和 KRaft 元数据边界。
4. [Kafka Producer、Key、分区策略与热分区](004_Kafka_Producer、Key、分区策略与热分区.md)
   Producer 写入、分区选择、实体顺序和负载倾斜。
5. [Kafka Leader/Follower、ISR、acks 与故障选举](005_Kafka_Leader_Follower、ISR、acks_与故障选举.md)
   副本同步、写入确认、高水位和 leader 故障恢复。
6. [Kafka Consumer Group、Offset 与 Rebalance](006_Kafka_Consumer_Group、Offset_与_Rebalance.md)
   消费并行度、进度提交、分区接管和崩溃窗口。
7. [Kafka 投递语义、重复消费与幂等处理](007_Kafka_投递语义、重复消费与幂等处理.md)
   At-most-once、at-least-once、exactly-once 边界和业务幂等。
8. [Kafka 重试机制、Retry Topic 与死信队列](008_Kafka_重试机制、Retry_Topic_与死信队列.md)
   短重试、延迟调度、可靠转发、Kafka transaction 和 DLQ。

Kafka 的连续因果链是：

```text
消息落到哪个 partition
  ↓
副本何时确认写入
  ↓
Consumer 从哪里继续
  ↓
为什么可能重复
  ↓
失败后如何重试与补偿
```

## 第三阶段：RabbitMQ——从路由到跨地域

9. [RabbitMQ：vhost、exchange、queue、binding](009_RabbitMQ：vhost、exchange、queue、binding.md)
   RabbitMQ 拓扑对象与基本消息链路。
10. [Routing Key 与 Binding Key](010_Routing_Key_与_Binding_Key.md)
    Direct、topic、fanout 的路由匹配与多队列订阅。
11. [RabbitMQ 可靠投递、消费确认与队列存储](011_RabbitMQ_可靠投递、消费确认与队列存储.md)
    Publisher Confirm、ACK/NACK、Prefetch、Classic/Quorum/Stream，以及历史 Lazy Queue。
12. [RabbitMQ 延时队列：TTL、死信交换机与延时插件](012_RabbitMQ_延时队列：TTL、死信交换机与延时插件.md)
    TTL、DLX、队头阻塞、历史插件和外部调度。
13. [RabbitMQ Federation：联邦交换机与联邦队列](013_RabbitMQ_Federation：联邦交换机与联邦队列.md)
    跨 broker/机房异步转发，以及与 Cluster、Quorum Queue、Shovel 的区别。

RabbitMQ 的连续因果链是：

```text
消息如何进入 Queue
  ↓
路由到哪些 Queues
  ↓
生产与消费如何确认
  ↓
消息如何持久化、限流和失败转移
  ↓
如何延时或跨地域转发
```

## 第四阶段：综合选型

14. [Kafka vs RabbitMQ：事件流、业务路由与选型](014_Kafka_vs_RabbitMQ：事件流、业务路由与选型.md)
    从存储模型、消费进度、路由、可靠性、回放和跨地域需求进行综合选择。

## 内容去重原则

- 基础文件只保留后续理解所需的简要定义，并用链接指向详细机制。
- Kafka Consumer Group 的完整分配过程只在 `006` 展开；`007` 只保留理解重复消费所需的摘要。
- Kafka ISR、acks 和故障选举集中在 `005`；`003` 只说明架构边界。
- RabbitMQ Lazy Queue 的历史知识没有删除，已合并到 `011` 的队列存储章节，并明确 3.12 之后的版本边界。
- Kafka/RabbitMQ 对比放在最后作为综合，不在中途打断单一技术栈的学习链。

另有：[附：通用学习与排查模板](附_通用学习与排查模板.md)。它只提供复习和排查框架，不替代上述知识正文。
