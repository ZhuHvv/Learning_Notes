# 可变默认参数与 default factory

> 所属分类：Python / Async / FastAPI  
> 修订版本：v11 审查修订版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

普通函数的可变默认参数在定义时只创建一次，会被多次调用共享；dataclass 使用 `field(default_factory=...)` 在每次实例化时创建新对象。类型注解本身是元数据，不等于运行时校验，`TypedDict`、dataclass 和 Pydantic 的保证也不同。

## 2. 原理性解释

- 普通函数的 list/dict/set 默认值会静默共享；
- 现代 dataclass 通常在类定义阶段拒绝常见可变默认值，要求 `default_factory`；
- dataclass 自动生成初始化、显示和比较方法，但默认不按注解校验类型；
- `TypedDict` 运行时仍是普通 dict；
- Pydantic 会运行时验证，并可能进行类型转换；
- `dict(state)` 只浅拷贝外层映射；
- 内部状态整体模型化与只校验状态 Patch 的迁移成本不同。

### 可变默认参数的问题来自“默认值只在定义时创建一次”

```python
def bad_append(item, values=[]):
    values.append(item)
    return values

bad_append(1)  # [1]
bad_append(2)  # [1, 2]
```

函数参数通常使用 `None`，dataclass 字段使用工厂：

```python
from dataclasses import dataclass, field

@dataclass
class Document:
    title: str
    tags: list[str] = field(default_factory=list)
```

嵌套对象也应通过 `default_factory=lambda: ...` 为每个实例重新构造。Pydantic 会复制不可哈希的可变默认值，但显式工厂仍更清楚。

### dataclass 与 `__post_init__`

dataclass 通常生成 `__init__`、`__repr__`、`__eq__` 等方法，初始化主要是赋值，并不会自动执行 `isinstance`。需要派生字段或显式校验时，可使用 `__post_init__`：

```python
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

### `TypedDict`、浅拷贝与运行时状态

`TypedDict` 主要告诉 mypy/pyright 一个 dict 预期有哪些键，运行时不会拒绝缺键、错类型或额外键。

```python
copied = dict(state)
copied["status"] = "done"       # 不改变原字典的外层字段
copied["results"].append("ok")  # 内部 list 仍与原字典共享
```

真正隔离嵌套状态要用不可变更新、按字段复制或谨慎深拷贝；Queue、连接、锁等运行时资源不适合深拷贝或持久化。

### Pydantic 的运行时契约

Pydantic 根据注解构造验证和序列化规则。`Optional[T]` / `T | None` 只表示允许 None；字段能否省略还取决于默认值。description/example 是 schema 元数据，不会自动限制值；`list` 只约束容器，`list[Literal[...]]` 才继续约束元素。

构造时验证也不表示以后每次赋值或 list 原地修改都会重验。需要拒绝隐式转换、额外字段或赋值错误时，应明确配置严格模式、`extra` 和赋值验证。Pydantic v1/v2 的配置语法不同，应以实际版本为准。

### 整体模型化与状态 Patch

把大型 state 从 dict 改为 Pydantic/dataclass，会影响 `state["x"]`、`state.get()`、`items()`、复制、JSONB 和动态运行时字段。Queue、Task、数据库 Session、client 应从可持久化 BusinessState 拆到 RuntimeContext。

渐进方案是保留外层 dict，只校验写入 Patch。字段名明确合并语义：`*_add` 追加，`*_replace` 替换，计数和图合并使用专用 reducer。这样可以分别测试“组件产生什么 Patch”和“Patch 怎样合并”，但仍要定义校验失败、并发冲突和绕过 Patch 的处理。

### 其他相关对象语义

- `@property` 只改变访问语法，不自动缓存；需在 getter 内保存结果才是手动懒加载；
- `append(x)` 把 x 作为一个元素加入，`extend(iterable)` 逐项加入；二者原地修改并返回 None；
- 单事件循环中一次不含 await 的 list 操作不会中途切换，但多步骤“检查后写入”不是事务或通用线程安全保证；
- `.format()` 模板中的字面 JSON 花括号要写 `{{` / `}}`；
- 数据库默认工厂应传 `default=uuid.uuid4`，而不是导入时求值的 `default=uuid.uuid4()`；
- 哈希是摘要，不是可逆加密；MD5 只适合非安全缓存键或弱指纹。

## 3. 机制流程

1. Python 在函数定义时计算默认参数；
2. 后续调用复用同一可变对象；
3. dataclass 在实例化时调用 `default_factory`；
4. 类型注解交给静态检查器或框架解释；
5. Pydantic 在边界构造时验证；
6. 共享状态通过明确 Patch / reducer 更新；
7. 可序列化业务状态与进程内运行时资源分层。

### 错误与正确流程对比

```python
def good_append(item, values=None):
    values = [] if values is None else values
    values.append(item)
    return values

@dataclass
class Chunk:
    text: str
    embedding: list[float] = field(default_factory=list)
```

## 4. 类比理解

可变默认值像所有人共用一本草稿本；`default_factory` 是每人领一本新本子。`TypedDict` 像填写说明，Pydantic 像入口检查员；状态 Patch 则像只允许提交格式明确的变更单。

## 5. 应用举例 / 代码或伪代码

```python
from typing import TypedDict
from pydantic import BaseModel, ConfigDict, Field

class JobState(TypedDict):
    status: str
    results: list[str]

class WorkerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results_add: list[str] = Field(default_factory=list)
    status_replace: str | None = None

def apply_patch(state: JobState, patch: WorkerPatch) -> None:
    state["results"].extend(patch.results_add)
    if patch.status_replace is not None:
        state["status"] = patch.status_replace
```

## 6. 你在讨论中的理解推进

你从共享列表陷阱推进到完整的数据模型边界：注解不等于校验，TypedDict、dataclass、Pydantic 各有职责；复杂工作流还要处理浅拷贝、Patch 合并以及 BusinessState / RuntimeContext 分层。
