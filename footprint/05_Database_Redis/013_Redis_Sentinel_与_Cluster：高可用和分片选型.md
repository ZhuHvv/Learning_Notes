# Redis Sentinel 与 Cluster：高可用和分片选型

> 学习定位：Redis 部署架构选型；建议先理解主从复制，再进入 Cluster 的槽与路由细节。
> 所属分类：Database / Redis / Vector DB  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Sentinel 负责监控和主从故障转移；Cluster 负责分片扩展和高可用。Sentinel 不分片，Cluster 分片。


## 2. 原理性解释

- Sentinel 适合单主多从自动切换。
- Cluster 将数据分到多个 master。
- Sentinel 客户端发现当前 master。
- Cluster 客户端处理 slot 路由。

### Sentinel 管高可用，Cluster 管分片扩展

Sentinel 监控一主多从，主节点故障后选举新主，适合单分片高可用。Cluster 不仅能故障转移，还能把数据按 slot 分散到多个主节点，实现横向扩展。二者关注点不同，不应混为一谈。

```text
Sentinel: 1 个主分片 + 自动故障转移
Cluster: 多个主分片 + slot 路由 + 故障转移
```

## 3. 机制流程

1. Sentinel 监控 master。
2. 确认客观下线。
3. 选举并提升 replica。
4. 通知客户端。

### 选择流程

```text
数据量和吞吐单机可承受，只需要故障转移 → Sentinel
需要横向扩展容量/吞吐 → Cluster
只是本地缓存或开发环境 → 单机 Redis
```

Sentinel 模式下客户端要能感知主节点切换；Cluster 模式下客户端要支持 slot 路由和重定向。

## 4. 类比理解

Sentinel 是值班监控员，Cluster 是多分店体系。

## 5. 应用举例 / 代码或伪代码

```text
Sentinel: HA only, no sharding
Cluster: sharding + HA, 16384 slots
```

## 6. 你在讨论中的理解推进

复制、Sentinel、Cluster 要拆开理解：副本、自动切换、分片扩展。
