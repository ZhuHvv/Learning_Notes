# Routing Key 与 Binding Key

> 所属分类：Message Queue / Kafka / RabbitMQ  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Routing key 是消息携带的路由标签，binding key 是队列绑定 exchange 时声明的匹配规则。


## 2. 原理性解释

- direct 要求精确匹配。
- topic 中 `*` 匹配一个单词，`#` 匹配零个或多个单词。
- fanout 忽略 routing key。
- 一条消息可匹配多个 binding 进入多个队列。

### Routing Key 是消息携带的路由标签，Binding Key 是队列声明的匹配规则

在 direct exchange 中，routing key 必须和 binding key 精确匹配；在 topic exchange 中，binding key 可以使用 `*` 和 `#` 通配符。`*` 匹配一个单词，`#` 匹配零个或多个单词。

```text
routing key: order.created.us
binding key: order.*.us     → 匹配
binding key: order.#        → 匹配
binding key: payment.#      → 不匹配
```

## 3. 机制流程

1. queue 用 binding key 绑定。
2. producer publish 带 routing key。
3. exchange 执行匹配。
4. 匹配队列收到消息。

### 路由设计流程

```text
先定义业务事件命名规范
  ↓
选择 exchange 类型
  ↓
为不同消费者创建队列
  ↓
用 binding key 表达订阅规则
  ↓
producer 发布 routing key
```

不要把 routing key 设计得过于随意，否则后续新增消费者时会很难订阅精确事件。

## 4. 类比理解

routing key 是包裹地址，binding key 是分拣篮规则。

## 5. 应用举例 / 代码或伪代码

```text
direct: routing_key=order.created matches binding_key=order.created
topic:  order.* matches order.created
topic:  order.# matches order.created.high
```

## 6. 你在讨论中的理解推进

你要求详细区分 routing key 和 binding key；一个来自消息，一个来自绑定规则。

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

**Routing Key 与 Binding Key** 要从“消息生命周期”看，而不是只记 Producer/Consumer 名词：

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

## 11. 针对 `Routing Key 与 Binding Key` 的专项排查

消息队列的质量取决于端到端语义。检查 **Routing Key 与 Binding Key** 时：

- **投递语义**：最多一次、至少一次、近似恰好一次分别意味着什么。
- **确认机制**：什么时候 ack/commit，失败后是否会重复消费。
- **顺序性**：业务是否要求同一实体的事件按顺序处理；Kafka 通常依赖 partition key。
- **积压处理**：消费者挂了、下游慢了、消息暴涨时，系统如何削峰与恢复。

### 小型练习

```python
def handle_order_event(event):
    # 练习：为 Routing Key 与 Binding Key 设计幂等键，防止重复消费导致重复扣款/重复发货
    if processed(event.id):
        return
    apply_business_change(event)
    mark_processed(event.id)
```

### 面试表达模板

讲 `Routing Key 与 Binding Key` 时，要从生产、路由/存储、消费、确认、失败处理五段说明，而不是只说“异步解耦”。
