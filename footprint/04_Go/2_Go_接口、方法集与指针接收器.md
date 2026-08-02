# Go 接口、方法集与指针接收器

> 所属主线：Go 类型系统  
> 难度：入门  
> 前置知识：结构体、函数与指针  
> 后续知识：依赖注入、error 接口、gRPC 服务实现

## 1. 总体性概念

Go 中一个类型是否实现接口，不需要显式写 `implements`。只要它的方法集包含接口要求的全部方法，就自动实现接口。

关键点在于：**值类型 `T` 和指针类型 `*T` 的方法集不完全一样**。讨论“某个结构体是否实现接口”时，必须明确判断的是 `T` 还是 `*T`。

结论可以先记住：

- 如果方法接收器是值接收器 `func (t T) M()`：`T` 和 `*T` 都实现接口。
- 如果方法接收器是指针接收器 `func (t *T) M()`：通常只有 `*T` 实现接口，`T` 不实现。

## 2. 原理性解释

### 2.1 接口看的是“方法集”，不是结构体字段

接口本质上是一组方法签名：

```go
type Buyer interface {
    Buy(ctx context.Context, req *TradeReq) (*TradeRes, error)
}
```

Go 编译器判断某个类型是否满足接口时，只检查这个类型的方法集中有没有 `Buy` 方法，且参数、返回值完全一致。结构体里有没有字段、有没有嵌入其他类型，不是接口匹配的直接依据。

### 2.2 值类型和指针类型的方法集不同

假设有：

```go
type Trade struct{}

func (t Trade) Buy(ctx context.Context, req *TradeReq) (*TradeRes, error) {
    return &TradeRes{Status: 200, Msg: "ok"}, nil
}
```

这里 `Buy` 是值接收器方法。Go 允许 `Trade` 值调用，也允许 `*Trade` 指针调用，因为指针可以自动解引用调用值方法。所以：

```text
Trade  的方法集包含 Buy
*Trade 的方法集也包含 Buy
```

因此下面两种都可以作为接口值：

```go
var a Buyer = Trade{}
var b Buyer = &Trade{}
```

再看指针接收器：

```go
func (t *Trade) Buy(ctx context.Context, req *TradeReq) (*TradeRes, error) {
    t.counter++
    return &TradeRes{Status: 200}, nil
}
```

这时方法属于 `*Trade` 的方法集。虽然一个可寻址的 `Trade` 变量在普通调用中可由编译器自动取地址来调用指针接收器方法，但接口赋值检查的是类型的方法集，不会执行这种调用语法转换。因此只有：

```go
var b Buyer = &Trade{} // 可以
var a Buyer = Trade{}  // 不可以
```

### 2.3 为什么 Go 这样设计

指针接收器通常表示方法可能修改对象内部状态，或者为了避免大对象拷贝。如果让值类型也自动实现接口，接口内部可能持有一个拷贝，修改行为就会变得不清晰。

所以 Go 的规则本质是在保证：**接口调用时，方法的接收对象语义是明确的。**

## 3. 机制流程

```text
定义接口
  ↓
编译器读取接口方法签名
  ↓
检查具体类型 T 的方法集
  ├─ 值接收器方法：属于 T，也属于 *T
  └─ 指针接收器方法：属于 *T，不一定属于 T
  ↓
若方法签名全部匹配，则该类型实现接口
  ↓
接口变量可保存该具体值或指针
```

可以用下面的表记忆：

| 方法定义 | `T` 是否实现接口 | `*T` 是否实现接口 |
|---|---:|---:|
| `func (t T) M()` | 是 | 是 |
| `func (t *T) M()` | 否 | 是 |

## 4. 类比理解

接口像“岗位要求”：会 `Buy` 方法就能当 `TradeServer`。值接收器像“本人和本人名片都能完成工作”；指针接收器像“必须拿到本人本体才能修改状态”，只有指针对象才满足岗位要求。

## 5. 应用举例 / 代码或伪代码

### 5.1 值接收器：值和指针都实现接口

```go
package main

import "fmt"

type Service interface {
    Run()
}

type Worker struct {
    Name string
}

func (w Worker) Run() {
    fmt.Println("run", w.Name)
}

func main() {
    var s1 Service = Worker{Name: "value"}
    var s2 Service = &Worker{Name: "pointer"}
    s1.Run()
    s2.Run()
}
```

### 5.2 指针接收器：只有指针实现接口

```go
type CounterService interface {
    Inc()
}

type Counter struct {
    N int
}

func (c *Counter) Inc() {
    c.N++
}

func main() {
    // var s CounterService = Counter{}  // 编译失败：Counter 没有实现 Inc
    var s CounterService = &Counter{}    // 正确
    s.Inc()
}
```

### 5.3 编译期检查写法

工程中常用下面的写法提前让编译器帮你检查：

```go
var _ CounterService = (*Counter)(nil)
```

它的含义是：我期望 `*Counter` 实现 `CounterService`，如果没有实现，编译期直接报错。

## 6. 常见误区与排查思路

- **误区 1：结构体有这个方法名就一定实现接口。** 要看方法签名和接收器属于谁。
- **误区 2：`T` 能调用指针方法，就代表 `T` 实现接口。** 普通变量可取地址调用，不等于接口赋值时方法集匹配。
- **误区 3：嵌入字段等于接口实现。** 嵌入只会提升方法，最终仍然看方法集。

排查时直接写：

```go
var _ SomeInterface = (*MyType)(nil)
```

让编译器给出最准确答案。

## 7. 关联知识点

- Go error、panic 与 recover
- Gin Handler 闭包与依赖注入
- Protobuf `go_package`、生成路径与 proto 文件组织
- gRPC `RegisterServer`、`UnimplementedServer` 与接口实现

## 8. 复习检查问题

- 值接收器和指针接收器的方法集有什么区别？
- 为什么 `*T` 可以调用值接收器方法？
- 为什么 `T` 不一定实现只包含指针接收器方法的接口？
- `var _ Interface = (*Type)(nil)` 的作用是什么？
