# 状态模型、ORM、JSONB 与持久化边界

> 学习层级：综合进阶  
> 前置知识：[Pydantic 数据模型](4_dataclass、TypedDict_与_Pydantic.md)、[后台任务边界](13_FastAPI_BackgroundTasks_与可靠任务边界.md)  
> 后续阅读：结合 Agent、数据库和消息队列专题继续学习

## 1. BusinessState 与 RuntimeContext 分层

大型工作流状态经常同时包含两类对象：

- **BusinessState**：状态、结果、计数、业务 ID 等可验证、可序列化数据；
- **RuntimeContext**：Queue、Task、锁、数据库 Session、HTTP client 和连接等进程内资源。

运行时资源不应为了“方便 checkpoint”而被 `str()`、深拷贝或直接写入 JSONB。持久化层保存重建资源所需的标识和配置，恢复时重新创建连接与任务。

## 2. 整体模型化的迁移成本

把大型 state 从 dict 改成 Pydantic 或 dataclass，会影响现有代码中的：

- `state["x"]`；
- `state.get()`；
- `items()`；
- 浅拷贝、深拷贝；
- JSON/JSONB 序列化；
- 动态添加运行时字段。

因此，“全部一次性模型化”与“保留外层 dict、只验证写入 Patch”是两种不同方案。选择时要评估调用面和迁移成本，而不是只比较类型声明是否漂亮。

## 3. 使用 Patch 明确合并语义

渐进方案可以保留业务 state，只允许组件产生经过验证的 Patch：

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

字段名可以直接表达合并方式：

- `*_add`：追加；
- `*_replace`：替换；
- 计数、集合和图结构：使用专用 reducer。

这样可以分别测试“组件产生什么 Patch”和“Patch 如何合并”。同时仍需定义：

- Patch 校验失败如何处理；
- 并发 Patch 如何排序或解决冲突；
- 是否允许绕过 Patch 直接修改 state；
- checkpoint 与业务事务如何保持一致。

## 4. ORM 列、关系与数据库级联

SQLAlchemy 中：

- `Column` / mapped column：描述数据库列；
- `relationship()`：描述 Python 对象之间的导航与加载关系。

ORM `cascade` 与数据库外键 `ON DELETE CASCADE` 属于不同层：

- ORM cascade 影响 Session 如何传播保存、删除等对象操作；
- 数据库级联由数据库约束执行；
- 二者可以配合，但不会自动等价。

设计删除行为时必须明确真正执行删除的是 ORM 还是数据库，以及并发、批量 SQL 和脱离 ORM 的操作会发生什么。

## 5. JSONB 保存 JSON 值，不验证业务模型

JSONB 应接收由 dict、list、字符串、数字、布尔值和 null 组成的 JSON-compatible 对象：

```python
record.payload = {"status": "done", "results": ["a", "b"]}
```

如果先对 dict 执行 `json.dumps()` 再作为对象写入：

```python
record.payload = json.dumps({"status": "done"})
```

数据库保存的会是一个 JSON 字符串值，而不是可直接按字段查询的 JSON object。JSONB 也不会自动验证业务必填字段、枚举和跨字段约束；这些仍需应用模型或数据库约束负责。

## 6. 默认工厂、UUID 与哈希

需要在每次插入时生成 UUID 时，应传入 callable：

```python
default=uuid.uuid4
```

而不是在模块导入时立即求值：

```python
default=uuid.uuid4()  # 多个记录可能复用同一个已生成值
```

哈希是摘要，不是可逆加密。MD5 只适合非安全缓存键、弱指纹或兼容场景，不能用于密码存储、签名或抗碰撞安全边界。

## 7. 持久化检查清单

1. 该字段是业务数据还是运行时资源？
2. 序列化后能否无歧义恢复？
3. Pydantic、JSON Schema、ORM 和数据库分别验证哪一层？
4. Patch 是追加、替换还是专用合并？
5. 并发更新和重试是否幂等？
6. 删除由 ORM 还是数据库级联？
7. UUID 默认值是在每次写入时生成，还是导入时就已求值？

