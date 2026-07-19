# GoFrame g.Meta 与声明式路由绑定

> 所属分类：Go / Gin / Runtime  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

GoFrame g.Meta 用结构体 tag 声明路由、方法、标签等元信息，实现声明式接口绑定。


## 2. 原理性解释

- 请求结构体嵌入 g.Meta。
- 字段 tag 可表达参数和校验。
- 框架按约定注册路由。
- 适合接口较多、文档校验统一的项目。

### GoFrame 的 `g.Meta` 是把路由信息声明在结构体上

GoFrame 常通过请求结构体中的 `g.Meta` 描述 method、path、tags、summary 等信息，再由框架完成路由绑定和接口文档生成。这种方式把 API 元数据和请求参数结构放在一起，适合中大型项目统一管理接口定义。

```go
type UserGetReq struct {
    g.Meta `path:"/user/{id}" method:"get"`
    ID int `json:"id" v:"required"`
}
```

## 3. 机制流程

1. 定义 req/res。
2. 写 g.Meta。
3. 实现 controller。
4. 框架注册。

### 声明式路由流程

```text
定义 Req/Res 结构体
  ↓
g.Meta 声明 path/method
  ↓
Controller 方法绑定
  ↓
框架解析请求参数并校验
  ↓
生成 OpenAPI/Swagger 元信息
```

和 Gin 手写路由相比，GoFrame 更强调工程规范和自动化；Gin 更轻量、自由度更高。

## 4. 类比理解

Gin 像手动画路线，GoFrame 像填表生成路线。

## 5. 应用举例 / 代码或伪代码

```go
type GetReq struct {
    g.Meta `path:"/user/{id}" method:"get"`
    ID int `p:"id" v:"required"`
}
```

## 6. 你在讨论中的理解推进

你在 Go 项目中接触 GoFrame，这里保留其与 Gin 不同的声明式风格。

