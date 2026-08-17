# 05.17 UNIQUE、UPSERT 与数据库写入幂等

## 1. 总体性概念

`UNIQUE + UPSERT` 是让数据库在并发条件下可靠处理“同一业务对象重复写入”的组合：

- `UNIQUE` 定义什么是同一条业务数据；
- `UPSERT` 定义发生冲突时如何插入或更新；
- 两者共同避免应用层“先查再写”产生的竞态，并可支撑数据库写入幂等。

## 2. UNIQUE：定义业务唯一性

```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    name VARCHAR(100)
);
```

这里 `email` 不可重复。唯一性也可由多个字段组成：

```sql
CREATE TABLE orders (
    user_id BIGINT,
    product_id BIGINT,
    status VARCHAR(20),
    UNIQUE (user_id, product_id)
);
```

业务键应表达真正的“同一对象”定义，例如文章的规范化 URL、外部事件 ID，或经过规范化的内容哈希。不要把随机主键误当成幂等键。

## 3. UPSERT：将冲突处理交给数据库

PostgreSQL 的常见写法：

```sql
INSERT INTO users (email, name)
VALUES ('aaa@test.com', '张三')
ON CONFLICT (email)
DO UPDATE SET name = EXCLUDED.name;
```

第一次执行时插入；同一 `email` 再写入时触发唯一约束冲突，转而更新已有记录。`EXCLUDED.name` 指本次原本准备插入但被冲突排除的那行值。

```text
UNIQUE：什么算重复？
          ↓
UPSERT：重复后新增、更新还是忽略？
```

例如知识库抓取可用规范 URL 做唯一键：

```sql
INSERT INTO articles (url, title, content)
VALUES (:url, :title, :content)
ON CONFLICT (url)
DO UPDATE SET
    title = EXCLUDED.title,
    content = EXCLUDED.content;
```

## 4. 为什么不能先 SELECT 再 INSERT/UPDATE

应用层分支在并发下会发生 TOCTOU（检查与使用之间的竞争）：

```text
线程 A：SELECT 不存在 ─┐
                         ├─ 两者都尝试 INSERT
线程 B：SELECT 不存在 ─┘
```

没有唯一约束会写出重复数据；即使有唯一约束，后到者也只会收到错误。`INSERT ... ON CONFLICT ...` 让数据库在约束与事务机制内完成判断和处理，从而使同一业务键最终只落到一条记录。

## 5. 幂等边界

```sql
CREATE TABLE documents (
    id BIGSERIAL PRIMARY KEY,
    content_hash VARCHAR(64) UNIQUE,
    content TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

```sql
INSERT INTO documents (content_hash, content, updated_at)
VALUES (:hash, :content, NOW())
ON CONFLICT (content_hash)
DO UPDATE SET
    content = EXCLUDED.content,
    updated_at = NOW();
```

这使数据库中的该次写入接近幂等：多个 Agent 同时保存相同内容不会形成多条记录。但它不使整个业务流程天然幂等。例如“创建云资源后写数据库”包含外部副作用，仍需幂等请求键、outbox、补偿或对账来处理半完成状态。

## 6. 设计检查清单

- 选择稳定、可规范化的业务唯一键；
- 明确冲突时是 `DO NOTHING` 还是更新哪些字段；
- 不要无条件覆盖需要审计、人工修改或更高版本数据的字段；
- 对内容哈希先统一编码、空白、大小写和规范化策略；
- 将 UPSERT 错误、死锁和事务失败纳入重试与观测；
- 跨数据库方言时核对语义：MySQL 的 `ON DUPLICATE KEY UPDATE` 与 PostgreSQL 的 `ON CONFLICT` 写法不同。

## 7. 关联知识点

- [MySQL 与 PostgreSQL：事务型关系数据库](03_MySQL_%E4%B8%8E_PostgreSQL%EF%BC%9A%E4%BA%8B%E5%8A%A1%E5%9E%8B%E5%85%B3%E7%B3%BB%E6%95%B0%E6%8D%AE%E5%BA%93.md)
- [内容 Hash：MD5、SHA-256 与稳定内容指纹](../03_Python/15_%E5%86%85%E5%AE%B9_Hash%EF%BC%9AMD5%E3%80%81SHA-256_%E4%B8%8E%E7%A8%B3%E5%AE%9A%E5%86%85%E5%AE%B9%E6%8C%87%E7%BA%B9.md)
