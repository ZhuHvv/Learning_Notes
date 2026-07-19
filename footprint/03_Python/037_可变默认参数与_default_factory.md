# 可变默认参数与 default factory

> 所属分类：Python / Async / FastAPI  
> 修订版本：v11 审查修订版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

可变默认参数会被所有调用/实例共享；default_factory 每次创建实例时生成新对象。


## 2. 原理性解释

- 默认参数在定义时求值。
- list/dict/set 是可变对象。
- dataclass 字段应使用 field(default_factory=list)。
- 函数默认参数也有同样问题。

### 可变默认参数的问题来自“默认值只在定义时创建一次”

真正会“静默共享”的是**普通函数的默认参数**：默认值在函数定义时求值一次，之后所有调用共享同一个对象（见第 3 节示例）。三种场景要区分开：

- 普通函数参数：`def f(x, arr=[])` 静默共享，是真正的陷阱；
- dataclass：`embedding: List[float] = []` 不会静默共享——dataclass 在类定义时就会直接抛 `ValueError: mutable default ... use default_factory`，强制你改用 `field(default_factory=list)`（每次实例化调用工厂函数，生成独立列表）；
- Pydantic 模型：允许写可变默认值，但会对默认值做深拷贝，每个实例各自独立，是安全的。

```python
@dataclass
class Doc:
    embedding: list[float] = field(default_factory=list)
```

## 3. 机制流程

1. 定义默认列表。
2. 多个实例共享它。
3. 一个实例修改。
4. 其他实例受到影响。

### 错误与正确流程对比

```python
def bad_append(x, arr=[]):
    arr.append(x)
    return arr

bad_append(1)  # [1]
bad_append(2)  # [1, 2]，不是你期望的新列表

def good_append(x, arr=None):
    if arr is None:
        arr = []
    arr.append(x)
    return arr
```

规则：默认参数适合不可变值，如 `None`、数字、字符串；可变容器用 `None` 或 `default_factory`。

## 4. 类比理解

像所有人共用一个草稿本；default_factory 是每人一本新本子。

## 5. 应用举例 / 代码或伪代码

```python
@dataclass
class Chunk:
    text: str
    embedding: list[float] = field(default_factory=list)
```

## 6. 你在讨论中的理解推进

你看到 `embedding=[]` 与 `default_factory=list` 后理解了共享列表陷阱。

