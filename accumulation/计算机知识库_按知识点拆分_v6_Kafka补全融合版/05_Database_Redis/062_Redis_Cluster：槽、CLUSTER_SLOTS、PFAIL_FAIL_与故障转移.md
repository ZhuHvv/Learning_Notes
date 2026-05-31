# Redis Cluster：槽、CLUSTER SLOTS、PFAIL FAIL 与故障转移

> 所属分类：Database / Redis / Vector DB  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Redis Cluster 通过 16384 个 slot 分片；CLUSTER SLOTS 告诉客户端 slot 到节点映射；PFAIL/FAIL 参与故障确认。


## 2. 原理性解释

- key 通过 CRC16 落到 slot。
- master 负责 slot，replica 复制 master。
- MOVED/ASK 处理重定向。
- PFAIL 是主观疑似，FAIL 是集群确认。

### Redis Cluster 用槽把 key 空间切分到多个主节点

Redis Cluster 将 key 映射到 16384 个 hash slot，每个主节点负责一部分槽。客户端访问 key 时，如果连错节点，会收到 MOVED/ASK 重定向。`CLUSTER SLOTS` 能告诉客户端槽到节点的映射。

故障检测中 PFAIL 是某节点主观认为另一个节点疑似失败；FAIL 是集群多数确认失败并触发故障转移。

## 3. 机制流程

1. 客户端获取 slots。
2. 计算 key slot。
3. 路由请求。
4. 故障时 replica 晋升。

### Cluster 请求流程

```text
客户端计算 key 的 slot
  ↓
根据本地 slot cache 访问节点
  ↓
节点正确：执行命令
  ↓
节点不正确：返回 MOVED，客户端刷新路由
```

多 key 命令要求 key 在同一 slot，可以用 hash tag：`user:{42}:profile` 与 `user:{42}:orders` 会落到同一槽。

## 4. 类比理解

像城市片区划分，每个节点负责一些片区。

## 5. 应用举例 / 代码或伪代码

```bash
redis-cli -c CLUSTER SLOTS
SET order:{1001}:info x
SET order:{1001}:items y  # hash tag 保证同 slot
```

## 6. 你在讨论中的理解推进

你接触槽、CLUSTER_SLOTS、PFAIL/FAIL；重点是分片 + 复制 + 故障转移。

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

**Redis Cluster：槽、CLUSTER SLOTS、PFAIL FAIL 与故障转移** 要放到“数据读写路径”里理解：数据结构选择会直接影响查询复杂度、一致性和排障方式。

1. **数据模型**：先确定是关系型表、文档、KV、集合、流，还是向量。
2. **访问模式**：是按主键读、范围查、全文/向量检索、计数统计，还是临时状态更新。
3. **一致性要求**：是强一致事务，还是可接受最终一致、缓存延迟或近似统计。
4. **过期与回收**：缓存、会话、限流 key、临时映射都要设计 TTL 或清理机制。

### 最小数据访问伪代码

```python
def get_or_load(cache, db, key):
    value = cache.get(key)
    if value is not None:
        return value
    value = db.query_by_key(key)
    cache.set(key, value, ttl=300)     # 缓存必须带过期时间
    return value
```

### 工程落地要点

- 关系型数据库适合事务和复杂查询；Redis 适合高频状态、缓存、限流和临时映射。
- 索引不是越多越好，写入成本、锁竞争、内存占用都要一起考虑。
- 分布式场景下要明确：失败重试是否幂等，缓存失效是否会击穿，主从复制是否存在延迟。

## 11. 针对 `Redis Cluster：槽、CLUSTER SLOTS、PFAIL FAIL 与故障转移` 的专项排查

数据库与 Redis 的问题要从“访问模式”倒推设计。检查 **Redis Cluster：槽、CLUSTER SLOTS、PFAIL FAIL 与故障转移** 时：

- **读写比例**：高频读适合缓存，强事务写更适合关系型数据库。
- **Key / Index 设计**：是否能按最常用查询条件命中；是否存在大 key、热 key、无效索引。
- **一致性边界**：缓存与数据库是否可能不一致；MQ 重试是否可能重复写。
- **容量与过期**：临时状态是否有 TTL；统计结构是否能控制内存。

### 小型练习

```python
def cache_key(prefix, *parts):
    return prefix + ":" + ":".join(map(str, parts))

# 练习：为 Redis Cluster：槽、CLUSTER SLOTS、PFAIL FAIL 与故障转移 设计 key/index，并写出它支持的查询方式与不支持的查询方式。
```

### 面试表达模板

回答 `Redis Cluster：槽、CLUSTER SLOTS、PFAIL FAIL 与故障转移` 时，按“数据模型 → 访问路径 → 复杂度/一致性 → 故障场景”组织，会比单纯背命令更像工程回答。
