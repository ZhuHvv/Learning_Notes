# Redis 限流与 Lua 原子操作

> 所属分类：Database / Redis / Vector DB  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Redis 限流常用计数器/ZSet/令牌桶；Lua 可把多命令组合为原子操作，避免并发竞态。


## 2. 原理性解释

- 固定窗口用 INCR + EXPIRE。
- 滑动窗口可用 ZSet。
- Lua 在 Redis 中原子执行。
- 脚本应短小避免阻塞。

### Lua 脚本让多条 Redis 命令具备原子性

限流常需要“读计数 → 判断 → 写计数/过期”多个步骤。如果客户端分多条命令执行，中间可能被其它请求插入，造成并发错误。Redis 执行 Lua 脚本时是原子的，脚本期间不会穿插其它命令，因此适合计数限流、库存扣减等小型原子逻辑。

```lua
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return current
```

## 3. 机制流程

1. 请求到达。
2. 计算 key。
3. Lua 增加计数并设置过期。
4. 判断是否允许。

### 固定窗口限流流程

```text
请求到达
  ↓
以用户ID+时间窗口构造 key
  ↓
Lua: INCR key，并在首次创建时 EXPIRE
  ↓
如果计数超过阈值 → 拒绝
否则 → 放行
```

Lua 不适合写复杂长耗时逻辑，因为 Redis 单线程执行命令，脚本过长会阻塞其它请求。

## 4. 类比理解

像闸机一次完成查人数、放人、更新时间。

## 5. 应用举例 / 代码或伪代码

```lua
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
if n > tonumber(ARGV[2]) then return 0 else return 1 end
```

## 6. 你在讨论中的理解推进

分布式限流不能只会 INCR，还要保证 INCR 和 EXPIRE 的原子性。

