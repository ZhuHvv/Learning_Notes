# Gin Handler：闭包与依赖注入

> 所属主线：Go Web 工程  
> 难度：基础  
> 前置知识：函数、闭包、结构体方法与 `net/http` 请求模型  
> 后续知识：Gin Middleware、认证与 Session

## 1. 总体性概念

Gin Handler 闭包注入是外层函数接收依赖并返回 gin.HandlerFunc，让 handler 捕获 db/service/logger。


## 2. 原理性解释

- 闭包可捕获外层变量。
- 路由注册时执行外层函数。
- 请求到来时执行返回的 handler。
- 比全局变量更利于测试和分层。

### Handler 闭包注入的本质是“在注册路由时绑定依赖”

`PingHandler(db)` 返回一个 `gin.HandlerFunc`。返回的函数捕获了外部传入的 `db`，之后每次请求进来都能使用同一个数据库连接池；外部文件只需调用工厂函数并注册返回的 Handler。

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

### Handler 在完整请求链路中的位置

```text
HTTP/RPC 请求
  → Router / Middleware
  → Handler：解析输入、调用 Service、转换响应
  → Service：编排业务
  → Repository：访问 DB / Redis / MQ
  → 日志、指标与链路追踪
```

不要把复杂业务、SQL 和外部调用全部堆进 Handler。Handler 应尽量只负责协议层工作，把业务规则交给 Service，把存储细节交给 Repository。

服务部署后通常运行在 Docker 容器或 Kubernetes 等环境中；日志、指标和 trace 用于把入口、业务、存储、异步任务与部署状态串成排查闭环。SQL/Redis 主要承担数据访问与缓存，MQ 承担跨进程异步和削峰，不能用进程内 goroutine 替代需要持久化的任务。

一种常见的结构体注入方式：

```go
type App struct {
    DB     *sql.DB
    Logger *zap.Logger
}

func (a *App) Register(r *gin.Engine) {
    r.GET("/users/:id", a.GetUser)
}
```

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

## 6. 工程边界

闭包工厂和 `App struct` 都是在显式绑定依赖；前者更轻量，后者在依赖较多时更容易统一管理。完整的目录划分和 import 方向统一放在 [Go Module、包与导入路径](001_Go_Module、包与导入路径.md) 中维护。
