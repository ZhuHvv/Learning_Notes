# Redis 基本数据类型与时间存储

## 1. 总体性概念

Redis 基本类型包括 String、Hash、List、Set、ZSet；时间通常用时间戳、TTL 或 ZSet score 表达，不是独立基本类型。


## 2. 原理性解释

- String 可做计数器和时间戳。
- Hash 适合对象字段。
- List 适合队列。
- Set 适合去重。
- ZSet 适合按分数排序。
- TTL 表达临时有效期。

### Redis 基本类型是围绕高频内存访问设计的

String 可做缓存、计数器、token；Hash 适合对象字段；List 适合队列；Set 适合去重集合；ZSet 适合排行榜和延迟队列。你问时间存储是不是基本类型：Redis 没有专门的时间类型，通常用 String/Hash 存时间戳，或用 TTL 表达过期时间。

```bash
SET session:123 userA EX 3600
HSET user:1 name Tom last_login 1710000000
```

## 3. 机制流程

1. 选择数据结构。
2. 设计 key。
3. 写入并设置 TTL。
4. 读取时处理过期。

### Redis 读写流程

```text
客户端命令
  ↓
事件循环读取请求
  ↓
执行内存数据结构操作
  ↓
可选 AOF/RDB 持久化
  ↓
返回响应
```

Redis 快不代表可以无限存。要关注 key 数量、value 大小、过期策略、内存淘汰策略和热 key。

## 4. 类比理解

Redis 像高速便签板，TTL 像便签自动过期时间。

## 5. 应用举例 / 代码或伪代码

```bash
SET token:abc user1 EX 3600
HSET user:1 name Alice lastSeen 1710000000
ZADD delay_jobs 1710003600 job42
```

## 6. 你在讨论中的理解推进

你问 Redis 时间是不是基本类型；结论是用 timestamp/TTL/ZSet score 表达时间语义。
