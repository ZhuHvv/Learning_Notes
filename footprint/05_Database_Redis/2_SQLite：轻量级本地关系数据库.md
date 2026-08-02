# SQLite：轻量级本地关系数据库

## 1. 总体性概念

SQLite 是嵌入式关系数据库，不需要独立服务，数据存在本地文件。


## 2. 原理性解释

- 支持 SQL、事务、索引。
- 部署简单，适合本地、小型、测试。
- 并发写能力有限。
- 不适合高并发核心生产服务。

### SQLite 是嵌入式关系数据库，不是服务端数据库

SQLite 把整个数据库存成一个本地文件，应用进程直接链接库读写，不需要独立数据库服务。它非常适合本地工具、桌面应用、测试环境、小型单机服务，但不适合高并发写入的中心化后端。

```python
conn = sqlite3.connect("app.db")
conn.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT)")
```

## 3. 机制流程

1. 打开 db 文件。
2. 建表。
3. 读写。
4. 提交事务。

### SQLite 使用流程

```text
打开本地 db 文件
  ↓
执行 SQL
  ↓
事务提交
  ↓
关闭连接
```

如果项目后续要迁移到 MySQL/PostgreSQL，SQL 写法和类型系统要提前注意差异，避免过度依赖 SQLite 特性。

## 4. 类比理解

像随身笔记本，不是多人档案室。

## 5. 应用举例 / 代码或伪代码

```python
conn = sqlite3.connect("app.db")
conn.execute("create table if not exists users(id integer, name text)")
conn.execute("insert into users values(1, 'Alice')")
conn.commit()
```

## 6. 你在讨论中的理解推进

你问 SQLite 是什么；关键是它仍是关系数据库，但嵌入在应用内。
