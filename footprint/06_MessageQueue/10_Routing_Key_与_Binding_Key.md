# Routing Key 与 Binding Key

## 1. 总体性概念

Routing key 是生产者发布消息时携带的路由标签；binding key 是队列绑定 exchange 时声明的匹配规则。Exchange 会把 routing key 和 binding key 进行匹配，决定消息进入哪些队列。

一句话区分：

```text
routing key：消息说“我是谁 / 我属于哪类事件”
binding key：队列说“我想订阅哪类事件”
```

## 2. 原理性解释

### 2.1 direct exchange：精确匹配

在 direct exchange 中，routing key 必须和 binding key 完全一致：

```text
routing_key = order.created
binding_key = order.created   ✅ 匹配
binding_key = order.paid      ❌ 不匹配
```

它适合明确业务事件，例如订单创建、订单支付、库存扣减。

### 2.2 topic exchange：模式匹配

Topic exchange 用 `.` 分隔单词，并支持两个通配符：

- `*`：匹配一个单词；
- `#`：匹配零个或多个单词。

```text
routing key: order.created.us
binding key: order.*.us   ✅ 匹配
binding key: order.#      ✅ 匹配
binding key: *.paid.#     ❌ 不匹配
```

Topic 模式适合事件维度较多的场景，比如：

```text
业务.动作.地区
order.created.us
order.paid.cn
payment.failed.sg
```

### 2.3 fanout exchange：忽略 routing key

Fanout exchange 不看 routing key，而是把消息发送给所有绑定队列。它适合广播通知，例如配置变更、缓存刷新、系统公告。

### 2.4 一条消息进入多个队列不是重复消费错误

如果一个 routing key 同时匹配多个 binding，RabbitMQ 会把消息复制到多个队列。每个队列各自保存一份消息，各自被消费者消费。

```text
routing_key = order.created.us
  ↓
匹配 audit.q: order.#
匹配 us_stat.q: *.created.us
  ↓
两个队列各收到一份消息
```

这和“一个队列多个 consumer 竞争消费”不同。

## 3. 机制流程

```text
定义事件命名规范
  ↓
选择 exchange 类型
  ├─ direct：精确业务事件
  ├─ topic：多维事件订阅
  └─ fanout：广播
  ↓
为每类消费者创建独立 queue
  ↓
queue 通过 binding key 订阅事件
  ↓
producer 发布 routing key
  ↓
exchange 执行匹配并路由
```

设计 routing key 时要稳定、可扩展，不要把随机参数放进 routing key。订单 ID、用户 ID 这类高基数字段通常不适合作为 RabbitMQ topic routing key 的层级。

## 4. 类比理解

Routing key 像包裹上的地址标签；binding key 像分拣篮上的收件规则。Direct 是完整地址匹配，topic 是按省市区模式匹配，fanout 是所有篮子都放一份。

## 5. 应用举例 / 代码或伪代码

### 5.1 事件命名规范

```text
order.created.cn
order.paid.cn
order.cancelled.us
payment.failed.sg
```

### 5.2 topic 订阅

```python
channel.exchange_declare("biz.event.ex", exchange_type="topic", durable=True)

# 审计系统订阅所有订单事件
channel.queue_bind("audit.order.q", "biz.event.ex", routing_key="order.#")

# 新加坡统计系统订阅所有新加坡创建事件
channel.queue_bind("sg.created.q", "biz.event.ex", routing_key="*.created.sg")

# 支付系统只订阅支付失败
channel.queue_bind("payment.failed.q", "biz.event.ex", routing_key="payment.failed.*")
```

### 5.3 发布消息

```python
channel.basic_publish(
    exchange="biz.event.ex",
    routing_key="order.created.sg",
    body=json.dumps({"order_id": 1001}),
)
```

这条消息会进入：

```text
audit.order.q    因为匹配 order.#
sg.created.q     因为匹配 *.created.sg
```

## 6. 你在讨论中的理解推进

- 你先区分 routing key 和 binding key：一个来自消息，一个来自队列绑定规则。
- 你继续学习 direct/topic/fanout 后，理解了不同 exchange 类型下匹配规则不同。
- 你对“一条消息是否会被多个消费者处理”的疑问，也可以通过“多个队列各得一份 vs 一个队列竞争消费”来解释。

## 7. 常见误区与排查思路

- **误区 1：routing key 和 binding key 是同一个东西。** 一个是消息属性，一个是订阅规则。
- **误区 2：topic 的 `*` 可以匹配多个单词。** `*` 只匹配一个单词，`#` 才匹配零个或多个。
- **误区 3：消息进入多个队列就是异常重复。** 多队列匹配是发布订阅模型的正常结果。

排查路由问题时写出三元组：

```text
exchange type = ?
routing key   = ?
binding key   = ?
```

然后按 exchange 类型手动判断是否匹配。

## 8. 关联知识点

- `009_RabbitMQ：vhost、exchange、queue、binding.md`
- `011_RabbitMQ_可靠投递、消费确认与队列存储.md`
- `012_RabbitMQ_延时队列：TTL、死信交换机与延时插件.md`
- `013_RabbitMQ_Federation：联邦交换机与联邦队列.md`

## 9. 复习检查问题

- routing key 和 binding key 分别由谁提供？
- direct、topic、fanout 的匹配规则有什么区别？
- `*` 和 `#` 的区别是什么？
- 一条消息进入多个队列和一个队列多个消费者有什么区别？
