# Gin Middleware：BasicAuth、Session 与 Cookie

> 所属主线：Go Web 工程  
> 难度：基础  
> 前置知识：Gin Handler 与请求处理链  
> 后续知识：Context、SSE 与统一错误处理

## 1. 总体性概念

Gin middleware 是请求处理链；BasicAuth 校验 Authorization；Session/Cookie 在无状态 HTTP 上维护登录状态。


## 2. 原理性解释

- BasicAuth 不匹配会直接返回 401。
- Cookie 存在客户端。
- Session 通常用 cookie 存 id，服务端/Redis 存状态。
- HTTP 长连接不是 session。

### BasicAuth、Middleware、Session/Cookie 分别解决不同层次的问题

BasicAuth 是一种简单认证方式，浏览器把 username/password 编码进 Authorization header；Gin 的 BasicAuth 中间件会在请求进入 handler 前校验。Session/Cookie 则用于“登录后记住状态”：Cookie 存在客户端，Session 数据可以存在服务端或签名 cookie 中。

BasicAuth 的凭据只是 Base64 编码，并未加密，因此必须配合 HTTPS/TLS。`gin.Accounts` 适合教程、小型内部工具或受控环境，不应替代生产系统中的密码哈希、密钥管理、限速和审计机制。

`gin.Accounts` 本质上是用户名到密码的 map，可理解为一张合法账号表；请求不匹配时，中间件直接返回 401，handler 不会继续执行。

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

生产环境中的 Session Cookie 通常还应设置：

- `HttpOnly`：阻止前端脚本直接读取；
- `Secure`：仅通过 HTTPS 发送；
- `SameSite`：降低跨站请求伪造风险；
- 合理的有效期、登录后 session id 轮换和服务端失效机制。

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

## 6. 边界判断

- BasicAuth 解决“每次请求如何携带简单凭据”；
- Cookie 解决“客户端如何随请求携带状态标识”；
- Session 解决“服务端如何根据标识恢复登录状态”；
- HTTP keep-alive 只解决连接复用，不代表用户会话。
