# Redis Cluster：槽、CLUSTER SLOTS、PFAIL FAIL 与故障转移

> 所属分类：Database / Redis / Vector DB  
> 修订版本：v11  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Redis Cluster 通过 16384 个 slot 分片；CLUSTER SLOTS 告诉客户端 slot 到节点映射；PFAIL/FAIL 参与故障确认。


## 2. 原理性解释

- key 通过 CRC16 落到 slot。
- master 负责 slot，replica 复制 master。
- MOVED/ASK 处理重定向。
- PFAIL 是主观疑似，FAIL 是集群确认。

### Redis Cluster 用槽把 key 空间切分到多个主节点

Redis Cluster 将 key 映射到 16384 个 hash slot，每个主节点负责一部分槽。客户端访问 key 时，如果连错节点，会收到 MOVED/ASK 重定向。`CLUSTER SLOTS` 能告诉客户端槽到节点的映射。注意：`CLUSTER SLOTS` 自 Redis 7.0 起被标注为 deprecated，官方推荐使用 `CLUSTER SHARDS`（旧命令仍可用，仅不再推荐）。

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

## 12. 本知识点的边界与复习建议

面试表达 Redis Cluster 时抓住三条主线即可：一是分片——key 经 CRC16 映射到 16384 个 slot，多 key 命令需用 hash tag 保证同槽；二是路由——客户端缓存 slot 映射，靠 MOVED/ASK 纠正后刷新；三是高可用——PFAIL 经多数节点确认升级为 FAIL 后触发 replica 晋升。能按“分片 → 路由 → 故障转移”讲清整条链路，就覆盖了本知识点的核心。

