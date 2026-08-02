# dataclass、TypedDict 与 Pydantic

> 学习层级：基础到中级  
> 前置知识：[可变对象与复制语义](3_可变默认参数、容器修改与复制语义.md)  
> 后续阅读：[JSON、XML 与正则提取](5_JSON、XML_与正则提取.md)

## 1. 三者解决的问题不同

| 工具 | 主要作用 | 默认运行时校验 |
|---|---|---|
| `dataclass` | 减少数据类样板代码 | 否 |
| `TypedDict` | 描述 dict 的静态类型结构 | 否 |
| Pydantic | 在系统边界验证、转换和序列化数据 | 是 |

类型注解本身是元数据，不等于运行时校验。是否校验取决于解释这些注解的工具。

## 2. dataclass 与 `__post_init__`

dataclass 通常生成 `__init__`、`__repr__` 和 `__eq__` 等方法，但初始化主要是赋值，不会自动根据注解执行 `isinstance`：

```python
from dataclasses import dataclass

@dataclass
class ModelConfig:
    name: str
    temperature: float = 0.7

    def __post_init__(self):
        if not isinstance(self.temperature, (int, float)):
            raise TypeError("temperature 必须是数字")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature 超出范围")
```

派生字段、跨字段约束或轻量显式校验可以放在 `__post_init__`。可变字段的创建方式见上一篇的 `default_factory`。

## 3. `TypedDict` 主要服务静态检查

```python
from typing import TypedDict

class JobState(TypedDict):
    status: str
    results: list[str]
```

在运行时，`JobState` 的实例仍是普通 dict。Python 不会自动拒绝缺键、错误类型或额外键；mypy、pyright 等静态检查器才能根据声明发现部分问题。

## 4. Pydantic 建立运行时契约

Pydantic 根据注解构造验证和序列化规则：

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    modes: list[Literal["fast", "accurate"]] = Field(default_factory=list)
    timeout: float | None = None
```

需要注意：

- `Optional[T]` 或 `T | None` 只表示允许 `None`，字段能否省略仍取决于默认值；
- `list` 只约束容器类型，`list[Literal[...]]` 才继续约束元素；
- Pydantic 可能进行类型转换；需要拒绝隐式转换时应启用严格配置；
- `description`、`example` 等主要是 schema 文档元数据，不自动形成业务约束；
- 构造时校验不代表后续每次赋值或 list 原地修改都会重新校验；
- 若要拒绝额外字段或验证赋值，应明确配置 `extra`、严格模式和赋值验证；
- Pydantic v1/v2 配置语法不同，应以项目锁定版本为准。

Pydantic 会为一些不可哈希的可变默认值创建副本，但显式使用 `Field(default_factory=...)` 更清晰，也与 dataclass 的思维模型一致。

## 5. 如何选择

- 只需要轻量数据对象和自动生成方法：dataclass；
- 仍需保留 dict API，并希望获得静态检查：`TypedDict`；
- 请求、配置、模型输出等不可信边界需要运行时验证：Pydantic；
- 大型运行状态既包含可持久化数据又包含连接、Queue、Task 时，应继续阅读后面的[状态模型与持久化边界](14_状态模型、ORM、JSONB_与持久化边界.md)。

不要因为 Pydantic 功能更多就把所有内部对象都改成 Pydantic 模型。选择工具时应同时考虑现有访问方式、序列化需求、性能和迁移成本。

