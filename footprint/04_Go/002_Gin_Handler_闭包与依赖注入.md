# Gin Handler 闭包与依赖注入

> 所属分类：Go / Gin / Runtime  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Gin Handler 闭包注入是外层函数接收依赖并返回 gin.HandlerFunc，让 handler 捕获 db/service/logger。


## 2. 原理性解释

- 闭包可捕获外层变量。
- 路由注册时执行外层函数。
- 请求到来时执行返回的 handler。
- 比全局变量更利于测试和分层。

### Handler 闭包注入的本质是“在注册路由时绑定依赖”

你问“其他文件通过调用外部函数得到里面的闭包函数实现使用？”答案是对的。`PingHandler(db)` 返回一个 `gin.HandlerFunc`，这个返回的函数捕获了外部传入的 `db`，之后每次请求进来都能使用同一个数据库连接池。

```go
func PingHandler(db *sql.DB) gin.HandlerFunc {
    return func(c *gin.Context) {
        if err := db.PingContext(c.Request.Context()); err != nil { ... }
    }
}
```

## 3. 机制流程

1. 初始化 db。
2. 调用 GetUserHandler(db)。
3. 注册路由。
4. 请求时闭包使用 db。

### 依赖注入流程

```text
main 初始化 db/logger/config
  ↓
调用 HandlerFactory(db, logger)
  ↓
返回闭包 handler
  ↓
Gin 路由注册
  ↓
每次请求执行闭包，访问捕获的依赖
```

闭包方式适合中小项目；更大项目可以用 `App struct` 持有依赖，再把方法作为 handler。

## 4. 类比理解

把数据库连接装进工具包再交给路由函数。

## 5. 应用举例 / 代码或伪代码

```go
func GetUserHandler(db *sql.DB) gin.HandlerFunc {
    return func(c *gin.Context) {
        id := c.Param("id")
        row := db.QueryRowContext(c.Request.Context(), "select name from users where id=$1", id)
        var name string
        if err := row.Scan(&name); err != nil { c.JSON(404, gin.H{"error":"not found"}); return }
        c.JSON(200, gin.H{"name": name})
    }
}
```

## 6. 你在讨论中的理解推进

你问其他文件是否通过调用外部函数得到闭包 handler；答案正是依赖注入闭包模式。

