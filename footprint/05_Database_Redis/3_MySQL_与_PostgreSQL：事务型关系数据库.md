# MySQL 与 PostgreSQL：事务型关系数据库

## 1. 总体性概念

MySQL/PostgreSQL 是事务型关系数据库，适合结构化核心数据、约束、事务和复杂查询。


## 2. 原理性解释

- schema 约束数据结构。
- ACID 事务保证一致性。
- 索引提升读但增加写成本。
- 参数化 SQL 防注入。
- 连接池影响并发能力。

### MySQL/PostgreSQL 的核心价值是事务和可靠持久化

关系型数据库通过表结构、约束、索引和事务保证数据一致性。MySQL/InnoDB 常用于互联网业务；PostgreSQL 在复杂 SQL、扩展能力、JSON/地理信息等方面强。二者都不是简单“存表格”，而是承担业务事实的权威存储。

ACID 中最容易被忽视的是隔离性：并发事务如果隔离级别不合适，会出现脏读、不可重复读、幻读等问题。

## 3. 机制流程

1. handler 接收请求。
2. service 开事务。
3. repo 执行 SQL。
4. 提交/回滚。

### 一次事务流程

```sql
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;
```

应用层要处理事务失败、死锁重试、连接池超时和慢查询；不要把长时间外部 RPC 放在数据库事务里，否则会拖长锁持有时间。

## 4. 类比理解

像严格表格和审批流程的档案系统。

## 5. 应用举例 / 代码或伪代码

```go
tx, err := db.BeginTx(ctx, nil)
if err != nil {
    return err
}
if _, err := tx.ExecContext(ctx, "update accounts set balance=balance-? where id=?", amount, from); err != nil {
    tx.Rollback()
    return err
}
if _, err := tx.ExecContext(ctx, "update accounts set balance=balance+? where id=?", amount, to); err != nil {
    tx.Rollback()
    return err
}
return tx.Commit() // Commit 的错误同样必须检查，不能忽略
```

## 6. 你在讨论中的理解推进

你在 Gin 示例里用 QueryRowContext；应始终结合 context 和参数化查询。
