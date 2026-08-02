# 05.12 Redis 复制：PSYNC、FULLRESYNC、RDB 与 backlog

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
