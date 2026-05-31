# Redis 复制：PSYNC、FULLRESYNC、RDB 与 backlog

> 所属分类：Database / Redis / Vector DB  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Redis 复制通过 PSYNC 尝试部分重同步，失败则 FULLRESYNC 全量同步；backlog 保存最近命令用于补齐。


## 2. 原理性解释

- 全量同步发送 RDB + 增量命令。
- 部分同步依赖 replication id、offset、backlog。
- backlog 覆盖不到缺口就全量。
- 复制异步，读从库可能滞后。

### Redis 复制要解决主从数据同步和断线续传

从节点初次连接主节点通常需要全量同步：主节点生成 RDB，把数据传给从节点，再发送期间新增的命令。断线时间较短时，可以通过 PSYNC 使用复制 backlog 做部分重同步；如果 backlog 不够，就退化为 FULLRESYNC。

```text
PSYNC replid offset
  ├─ backlog 覆盖 offset：部分重同步
  └─ 不覆盖：FULLRESYNC + RDB
```

## 3. 机制流程

1. replica 连接 master。
2. 发送 PSYNC。
3. master 判断 offset。
4. 部分同步或全量同步。

### 复制流程

```text
Replica 连接 Master
  ↓
发送 PSYNC
  ↓
Master 判断是否可部分同步
  ├─ 可以：发送缺失命令
  └─ 不可以：生成/发送 RDB，再持续命令流
```

复制是异步的，因此主从之间可能有延迟；读从库要接受短暂旧数据风险。

## 4. 类比理解

缺几页笔记就补几页，缺太多只能重新发整本。

## 5. 应用举例 / 代码或伪代码

```text
replica: PSYNC <replid> <offset>
master: CONTINUE + backlog
# or
master: FULLRESYNC <newid> <offset> + RDB
```

## 6. 你在讨论中的理解推进

抓住 PSYNC、FULLRESYNC、RDB、backlog 的关系即可理解复制。

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

**Redis 复制：PSYNC、FULLRESYNC、RDB 与 backlog** 要放到“数据读写路径”里理解：数据结构选择会直接影响查询复杂度、一致性和排障方式。

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

## 11. 针对 `Redis 复制：PSYNC、FULLRESYNC、RDB 与 backlog` 的专项排查

数据库与 Redis 的问题要从“访问模式”倒推设计。检查 **Redis 复制：PSYNC、FULLRESYNC、RDB 与 backlog** 时：

- **读写比例**：高频读适合缓存，强事务写更适合关系型数据库。
- **Key / Index 设计**：是否能按最常用查询条件命中；是否存在大 key、热 key、无效索引。
- **一致性边界**：缓存与数据库是否可能不一致；MQ 重试是否可能重复写。
- **容量与过期**：临时状态是否有 TTL；统计结构是否能控制内存。

### 小型练习

```python
def cache_key(prefix, *parts):
    return prefix + ":" + ":".join(map(str, parts))

# 练习：为 Redis 复制：PSYNC、FULLRESYNC、RDB 与 backlog 设计 key/index，并写出它支持的查询方式与不支持的查询方式。
```

### 面试表达模板

回答 `Redis 复制：PSYNC、FULLRESYNC、RDB 与 backlog` 时，按“数据模型 → 访问路径 → 复杂度/一致性 → 故障场景”组织，会比单纯背命令更像工程回答。

## 12. 本知识点的边界与复习建议

**Redis 复制：PSYNC、FULLRESYNC、RDB 与 backlog** 的学习边界可以这样把握：先能用自己的话解释它解决的问题，再能画出输入、处理、输出三段流程，最后能写出一个最小代码或命令例子。复习时不要把它和相邻知识点混在一起：相邻知识点通常负责上游准备、下游消费或异常处理，而本文件只保留与 **Redis 复制：PSYNC、FULLRESYNC、RDB 与 backlog** 直接相关的机制。

建议你复习时做三件事：

1. **复述定义**：不用术语堆砌，说明它为什么出现。
2. **画流程图**：至少标出输入、核心机制、输出、失败点。
3. **写最小例子**：哪怕只是伪代码，也要体现真实项目中会怎样使用。

如果之后继续扩展本知识库，可以在本文件下追加“项目踩坑记录”和“面试问答”，但不要把无关项目经历混入 **Redis 复制：PSYNC、FULLRESYNC、RDB 与 backlog** 的原理解释中。
