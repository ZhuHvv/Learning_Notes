# Kafka vs RabbitMQ：事件流、业务路由与选型

## 1. 总体性概念

Kafka 偏向可保留、可回放的分布式事件日志；RabbitMQ 偏向灵活路由、任务分发和逐条投递控制。二者都能异步解耦，但核心抽象和运维重点不同。

不要只问“谁更快”，而要问：

- 消息是长期事件事实，还是等待完成的业务任务？
- 是否需要历史回放和多个独立订阅进度？
- 是否需要复杂 routing key / binding 路由？
- 失败后希望按 offset 重读，还是 ACK/NACK、requeue、DLX？
- 顺序、吞吐、延迟、积压和跨地域分别有什么要求？

## 2. 核心模型对比

| 维度 | Kafka | RabbitMQ |
|---|---|---|
| 核心抽象 | topic-partition-log-offset | exchange-binding-queue-delivery |
| 消费方式 | Consumer 主动 poll | Broker 投递或客户端拉取 |
| 消费进度 | Group 按 partition 保存 offset | Queue 保存 ready/unacked 状态 |
| 消息读取后 | 在保留策略内继续存在 | ACK 后逐步完成和清理 |
| 多订阅者 | 多个 consumer groups | 多个 queues 绑定同一 exchange |
| 顺序边界 | Partition 内顺序 | Queue 投递顺序受并发、重投等影响 |
| 失败处理 | 不提交、Retry Topic、DLQ | ACK/NACK、requeue、DLX、TTL |
| 典型高可用 | Partition replicas + ISR | Quorum Queue |
| 跨地域 | MirrorMaker 等流复制方案 | Federation / Shovel |

这些是模型倾向，不是绝对能力边界。两者都能覆盖一部分对方场景，但实现复杂度和可观测性可能不同。

## 3. Kafka 为什么更像事件日志

消息写入 partition 后不会因为某个 consumer 读取就立即删除，而是在保留时间、保留大小或压缩策略内继续存在。不同 consumer groups 各自维护 offsets，因此订单服务、统计服务和搜索索引服务可以独立读取同一事件流。

Kafka 的优势通常来自：

- 高吞吐追加写；
- Partition 并行；
- 事件保留与回放；
- 多 group 独立进度；
- 流处理、日志采集、CDC 等生态。

业务失败通常由消费者通过“不提交 offset、写 Retry Topic、写 DLQ”等方式处理。Broker 不理解数据库写入是否成功。

## 4. RabbitMQ 为什么更像业务路由器

Producer 面向 exchange 发布，exchange 根据 routing key 和 bindings 把消息复制或路由到目标 queues。每个 queue 独立管理 ready、unacked、ACK/NACK 和死信过程。

RabbitMQ 的优势通常来自：

- Direct、topic、fanout、headers 等灵活路由；
- 工作队列与竞争消费；
- Publisher Confirm、Consumer ACK/NACK；
- Prefetch、TTL、DLX 等细粒度投递控制；
- Federation、Shovel 等 broker 间消息桥接。

消费者 ACK 后，普通 queue 中的消息通常进入完成和清理路径，因此它不像 Kafka 那样天然以长期回放日志为中心。

## 5. 选型流程

```text
消息是否需要长期保留、回放或被多个系统按各自进度读取？
  ├─ 是 → 优先评估 Kafka
  └─ 否
       ↓
是否需要复杂路由、任务队列、逐条 ACK/NACK、TTL/DLX？
  ├─ 是 → 优先评估 RabbitMQ
  └─ 否
       ↓
结合现有基础设施、吞吐、延迟、运维能力和团队经验验证
```

进一步检查：

1. 顺序要求是实体级还是全局？
2. 峰值积压需要保存多久？
3. 消费失败会阻塞后续消息吗？
4. 是否需要重放修复历史数据？
5. 消息数量、大小和保留成本如何增长？
6. 跨地域是复制事件流，还是搬运任务？

## 6. 场景举例

更偏 Kafka：

```text
日志与埋点
CDC 数据变更流
订单状态事件流
用户行为流
需要多系统回放的领域事件
```

更偏 RabbitMQ：

```text
邮件、短信、文件处理任务
需要 direct/topic/fanout 的业务通知
需要逐条 ACK/NACK 的工作队列
TTL + DLX 延时任务
跨 RabbitMQ brokers 的 Federation 桥接
```

同一个系统也可以组合使用：Kafka 保存事实事件流，RabbitMQ 承担某些短生命周期、复杂路由的执行任务。但组合会增加运维和一致性边界，不能只为了“技术齐全”而同时引入。

## 7. 可靠性对比

Kafka 常见可靠性组合：

```text
replication factor
+ ISR
+ acks=all
+ min.insync.replicas
+ idempotent producer
+ consumer 幂等
```

RabbitMQ 常见可靠性组合：

```text
durable topology
+ persistent message
+ Publisher Confirm / mandatory return
+ Classic 或 Quorum Queue 选型
+ Consumer ACK/NACK
+ 幂等与 DLQ
```

两者都不能只依赖 broker 配置解决端到端业务恰好一次。数据库、外部接口和重试路径仍需要幂等或事务边界。

## 8. 常见误区

- **误区 1：Kafka 一定比 RabbitMQ 快，所以总应选 Kafka。** 模型适配比单一吞吐指标重要。
- **误区 2：RabbitMQ 不能广播。** 一个 exchange 可以路由到多个 queues。
- **误区 3：Kafka 的多个 consumer 等于 RabbitMQ 一个 queue 的竞争消费。** 必须同时区分 group 和 partition。
- **误区 4：RabbitMQ ACK 或 Kafka offset 能证明业务一定成功。** 它们只表达消息系统中的确认或进度。
- **误区 5：两个中间件一起用一定更可靠。** 更多组件也会产生更多转发、监控和一致性边界。

## 9. 关联知识点

- `003_Kafka：KRaft、Broker、Topic、Partition、Replica.md`
- `006_Kafka_Consumer_Group、Offset_与_Rebalance.md`
- `009_RabbitMQ：vhost、exchange、queue、binding.md`
- `011_RabbitMQ_可靠投递、消费确认与队列存储.md`
- `013_RabbitMQ_Federation：联邦交换机与联邦队列.md`

## 10. 复习检查问题

- Kafka 与 RabbitMQ 的核心存储和消费抽象分别是什么？
- 多个 Kafka groups 与多个 RabbitMQ queues 如何实现多系统订阅？
- 哪些需求会让你优先选择 Kafka，哪些会让你优先选择 RabbitMQ？
- 两者的确认机制为什么都不等于业务端到端恰好一次？
- 同时使用 Kafka 和 RabbitMQ 会增加哪些边界？
