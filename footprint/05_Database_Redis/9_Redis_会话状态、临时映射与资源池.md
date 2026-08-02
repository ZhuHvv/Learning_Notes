# Redis 会话状态、临时映射与资源池

## 1. 总体性概念

Redis 可用于会话状态、临时映射和资源池；这类数据高频变化，必须考虑 TTL、原子迁移和异常清理。


## 2. 原理性解释

- Hash 可保存 session 字段。
- 临时映射可保存 task->worker。
- Set/List 可管理资源池。
- 在线状态要靠心跳和过期。
- 多命令迁移要 Lua 或事务。

### Redis 存会话和临时映射的优势是快与自动过期

会话状态、房间号到端口映射、在线状态、短期令牌，都具有访问频繁、生命周期短、可重建或可过期的特点。Redis 的 TTL、Hash、Set、List 很适合这类状态。

```bash
HSET user:42 isOnline true curLevelName level_1
EXPIRE user:42 86400
SADD used_ports 11001
LPUSH freePorts 11002
```

## 3. 机制流程

1. 创建会话/任务。
2. 写入映射并设置 TTL。
3. 分配资源。
4. 完成后释放。
5. 清理过期残留。

### 会话状态流程

```text
用户登录
  ↓
写入 session/user hash
  ↓
请求携带 session id
  ↓
服务端查 Redis 获取状态
  ↓
断线/退出时更新状态或设置 TTL
```

注意：Redis 中的状态如果是业务强一致事实，应考虑落库或补偿；如果只是临时运行态，可以接受过期和重建。

## 4. 类比理解

像调度台白板：谁占用什么资源、哪些空闲都写在白板上。

## 5. 应用举例 / 代码或伪代码

```bash
HSET session:s1 user_id u1 role admin
EXPIRE session:s1 3600
SPOP free_workers
SADD used_workers worker3
```

## 6. 你在讨论中的理解推进

本版已去除专项场景，只保留 Redis 临时状态管理的通用后端模式。
