# RESTful API、持久化服务与微服务

> 所属分类：Backend / Deploy / Network  
> 修订版本：v11  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

RESTful API 用 HTTP 方法和资源路径表达操作；持久化服务保存业务状态；微服务是按边界独立部署的服务集合。


## 2. 原理性解释

- GET/POST/PUT/PATCH/DELETE 有语义区别。PUT 与 PATCH 都是"更新"但语义不同：PUT 是全量替换资源且幂等（重复执行结果一致），PATCH 是部分更新且不保证幂等。
- Handler 不应堆业务逻辑。
- Service 编排业务。
- Repository 访问存储。
- 微服务不是越拆越好。

### RESTful API 是围绕资源建模 HTTP 接口

REST 强调用 URI 表示资源，用 HTTP Method 表示动作：GET 查询、POST 创建、PUT/PATCH 更新（PUT 全量替换整个资源、幂等；PATCH 只修改部分字段、不保证幂等）、DELETE 删除。持久化服务则把业务状态落到数据库中，保证服务重启后数据不丢。微服务是在组织和部署层面拆分服务边界，不等于接口都写成 HTTP 就是微服务。

```text
GET /users/42
POST /orders
PATCH /orders/100/status
```

## 3. 机制流程

1. 请求到 API。
2. 中间件认证。
3. Handler 校验。
4. Service 调 DB/Redis/MQ。
5. 返回 JSON。

### 一次 API 请求流程

```text
Client → Gateway/Nginx → Service Router → Middleware → Handler
  ↓
参数校验 → 业务逻辑 → DB/Redis/MQ
  ↓
返回 JSON + 状态码
```

设计 API 时要统一错误码、幂等策略、分页、鉴权和 trace id，否则后期联调成本会很高。

## 4. 类比理解

API 是窗口，持久化层是档案室，微服务是不同科室。

## 5. 应用举例 / 代码或伪代码

```go
router.POST("/users", func(c *gin.Context) {
    var req CreateUserReq
    if err := c.ShouldBindJSON(&req); err != nil { c.JSON(400, gin.H{"error": err.Error()}); return }
    c.JSON(201, service.Create(c.Request.Context(), req))
})
```

## 6. 你在讨论中的理解推进

你在 Gin 学习中逐步接触路由、handler、DB 注入，这里上升到后端分层。

