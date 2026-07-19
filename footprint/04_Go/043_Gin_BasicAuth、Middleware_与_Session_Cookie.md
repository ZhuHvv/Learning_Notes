# Gin BasicAuth、Middleware 与 Session Cookie

> 所属分类：Go / Gin / Runtime  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Gin middleware 是请求处理链；BasicAuth 校验 Authorization；Session/Cookie 在无状态 HTTP 上维护登录状态。


## 2. 原理性解释

- BasicAuth 不匹配会直接返回 401。
- Cookie 存在客户端。
- Session 通常用 cookie 存 id，服务端/Redis 存状态。
- HTTP 长连接不是 session。

### BasicAuth、Middleware、Session/Cookie 分别解决不同层次的问题

BasicAuth 是一种简单认证方式，浏览器把 username/password 编码进 Authorization header；Gin 的 BasicAuth 中间件会在请求进入 handler 前校验。Session/Cookie 则用于“登录后记住状态”：Cookie 存在客户端，Session 数据可以存在服务端或签名 cookie 中。

你问 `gin.Accounts` 是否以 map 存储用户名密码，可以理解为它提供了一张合法账号表；请求不匹配时，中间件直接返回 401，handler 不会继续执行。

## 3. 机制流程

1. 请求进入中间件。
2. 认证/解析 session。
3. 通过则调用 handler。
4. 响应可 Set-Cookie。

### 请求穿过中间件流程

```text
Request
  ↓
Logger / Recovery
  ↓
BasicAuth 校验
  ├─ 失败：401 Unauthorized
  └─ 成功：写入 gin.AuthUserKey
  ↓
Session middleware 读取/写入 Cookie
  ↓
业务 Handler
```

Session 不等于 HTTP 长连接。HTTP 请求可以是短连接，但靠 Cookie 携带 session id，服务端就能识别“这是同一个用户”。

## 4. 类比理解

中间件像安检，session 像访客证。

## 5. 应用举例 / 代码或伪代码

```go
authorized := r.Group("/admin", gin.BasicAuth(gin.Accounts{"foo":"bar"}))
authorized.GET("/secrets", func(c *gin.Context) {
    user := c.MustGet(gin.AuthUserKey).(string)
    c.JSON(200, gin.H{"user": user})
})
```

## 6. 你在讨论中的理解推进

你问 gin.Accounts 和 Auth 不匹配，也澄清 session 不是 HTTP 长连接。

