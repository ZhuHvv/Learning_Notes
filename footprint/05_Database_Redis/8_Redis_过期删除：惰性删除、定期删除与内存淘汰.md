# 05.08 Redis 过期删除：惰性删除、定期删除与内存淘汰

## 1. 总体性概念

Redis 中带 TTL 的 key 并不是到期瞬间一定被删除。Redis 通常结合三类机制处理过期数据：

1. **惰性删除**：访问 key 时发现过期，现场删除并返回不存在。
2. **定期删除**：后台周期性抽样检查一批带过期时间的 key，删除已过期的部分。
3. **内存淘汰**：内存达到上限时，根据淘汰策略移除部分 key。

你把它类比到 RabbitMQ 延时消息时提出的理解是对的：有些系统并不会为每个对象都创建独立计时器，而是在“访问、扫描、调度点”上判断是否已经到期。

## 2. 原理性解释

### 2.1 为什么不为每个 key 创建一个计时器

如果 Redis 中有几百万个带 TTL 的 key，为每个 key 创建一个系统级计时器会带来巨大开销：

- 计时器对象本身占内存；
- 定时器堆或时间轮维护需要 CPU；
- 同一时间大量 key 过期会造成抖动；
- 删除操作本身也可能阻塞主线程。

所以 Redis 采用折中策略：**不追求毫秒级绝对准时删除，而追求整体吞吐、内存可控和延迟稳定。**

### 2.2 惰性删除

惰性删除发生在读写 key 时。Redis 会先检查该 key 是否设置了过期时间，以及当前时间是否超过过期时间：

```text
GET user:1
  ↓
检查 expire 字典
  ↓
如果 now > expireAt：删除 key，返回 nil
  ↓
否则返回 value
```

优点是简单、精准，只处理真正被访问的 key。缺点是如果大量过期 key 永远没人访问，它们会暂时留在内存里。

### 2.3 定期删除

为了避免过期 key 长期占用内存，Redis 会周期性抽样检查过期字典。它不是每轮扫描全部 key，而是在时间预算内抽样删除。

抽象伪代码：

```python
def active_expire_cycle():
    for db in redis_databases:
        keys = random_sample(db.expire_dict, limit=20)
        expired = 0
        for key in keys:
            if now() > db.expire_dict[key]:
                delete(key)
                expired += 1
        if expired / len(keys) < threshold:
            break
```

这体现了 Redis 的工程取舍：用抽样和时间上限避免删除任务影响正常请求。

### 2.4 内存淘汰与过期删除不同

过期删除是 key 已经超过 TTL；内存淘汰是 Redis 内存达到 `maxmemory` 后，不管 key 是否过期，都可能根据策略淘汰。例如：

- `volatile-lru`：只在设置过期时间的 key 中按 LRU 淘汰；
- `allkeys-lru`：所有 key 都可按 LRU 淘汰；
- `noeviction`：不淘汰，写入直接报错。

所以 TTL 不是内存安全的唯一保障。高并发缓存系统还要结合内存上限和淘汰策略。

## 3. 机制流程

```text
SET key value EX 60
  ↓
数据写入主字典，过期时间写入 expire 字典
  ↓
访问 key 时触发惰性检查
  ├─ 未过期：返回 value
  └─ 已过期：删除并返回 nil
  ↓
后台定期抽样扫描 expire 字典
  ↓
内存不足时触发 maxmemory 淘汰策略
```

过期时间一般不直接存在 value 里，而是由 Redis 维护额外的过期字典。这样普通 key 查询和 TTL 管理可以分开处理。

## 4. 类比理解

惰性删除像图书馆借书证过期检查：不是每天主动检查所有读者，而是在读者来借书时检查证件是否过期；定期删除像管理员每天抽查一批过期证件；内存淘汰像书架满了以后按规则下架旧书。

## 5. 应用举例 / 代码或伪代码

### 5.1 登录验证码 TTL

```go
func SaveCode(ctx context.Context, rdb *redis.Client, phone, code string) error {
    key := "sms:code:" + phone
    return rdb.Set(ctx, key, code, 5*time.Minute).Err()
}

func VerifyCode(ctx context.Context, rdb *redis.Client, phone, input string) bool {
    key := "sms:code:" + phone
    val, err := rdb.Get(ctx, key).Result()
    if err == redis.Nil {
        return false // 可能是不存在，也可能是访问时发现过期并删除
    }
    if err != nil {
        return false // 网络、超时等错误不能当作校验成功
    }
    return val == input
}
```

### 5.2 缓存穿透保护

```go
func CacheUser(ctx context.Context, id string) (*User, error) {
    key := "user:" + id
    if data := redisGet(key); data != nil {
        return decodeUser(data), nil
    }

    user := dbFindUser(id)
    if user == nil {
        redisSet(key, "NULL", 30*time.Second) // 空值短 TTL
        return nil, nil
    }

    redisSet(key, encode(user), 10*time.Minute)
    return user, nil
}
```

这里的短 TTL 并不保证 30 秒整点清除，而是保证过期后访问不会再返回旧值。

## 6. 你在讨论中的理解推进

- 起点：你联想到 Redis 惰性删除：查询时判断数据是否过期，不过期返回，过期则删除。
- 修正：这个理解是对的，但 Redis 不是只有惰性删除，还有定期抽样删除和内存淘汰。
- 深化：你把它和 RabbitMQ 延时消息对比，理解了“过期检测不一定等于每个对象一个独立计时器”。

## 7. 常见误区与排查思路

- **误区 1：TTL 到期就立即删除。** Redis 通常不保证立即物理删除。
- **误区 2：设置 TTL 就不会占内存。** 过期但未删除的 key 可能短暂占用内存。
- **误区 3：过期删除和内存淘汰是一回事。** 一个基于时间，一个基于内存压力。

排查内存问题时关注：

```text
used_memory / maxmemory
expired_keys
evicted_keys
keyspace_hits / keyspace_misses
```

## 8. 关联知识点

- [Redis 基本数据类型与时间存储](6_Redis_基本数据类型与时间存储.md)
- [Redis 会话状态、临时映射与资源池](9_Redis_会话状态、临时映射与资源池.md)
- [Redis 限流与 Lua 原子操作](10_Redis_限流与_Lua_原子操作.md)
- [RabbitMQ 延时队列：TTL、死信交换机与延时插件](../06_MessageQueue/12_RabbitMQ_延时队列：TTL、死信交换机与延时插件.md)

## 9. 复习检查问题

- 为什么 Redis 不给每个 TTL key 创建独立计时器？
- 惰性删除和定期删除分别解决什么问题？
- TTL 过期和 maxmemory 淘汰有什么区别？
- Redis 的过期检测和 RabbitMQ 延时消息检测有哪些相似点和差异？
