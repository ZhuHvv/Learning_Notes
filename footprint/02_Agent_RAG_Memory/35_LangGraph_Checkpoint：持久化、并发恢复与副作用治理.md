# 02.35 LangGraph Checkpoint：持久化、并发恢复与副作用治理

## 1. 总体性概念

LangGraph 的 Checkpoint（检查点）是某个 `thread_id` 对应图执行历史中的**可恢复状态快照**。它不是只保存一个 `State` 字典，而是保存：

- Graph 当前的数据状态；
- 已执行到的位置和下一批要执行的节点；
- 任务、版本和步骤等调度元数据；
- 与上一个快照的历史关系。

Checkpointer（检查点保存器）负责把这些快照存储和读取。它是持久化、断点恢复、Human-in-the-loop（人在回路）、故障恢复以及历史回放（time travel）的基础。

最准确的区分是：

```text
State
  = 现在有什么业务数据

Checkpoint
  = 某一时刻的 State + 控制流 + 调度元数据快照

Checkpointer
  = 负责保存和读取 Checkpoint 的组件
```

## 2. 最小使用方式

在编译图时提供 Checkpointer；每次调用提供稳定的 `thread_id`。同一个 `thread_id` 能让后续调用定位并恢复同一条图执行历史。

```python
from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    query: str
    plan: str
    result: str


def planner(state: State):
    return {"plan": f"plan for {state['query']}"}


def executor(state: State):
    return {"result": f"execute {state['plan']}"}


builder = StateGraph(State)
builder.add_node("planner", planner)
builder.add_node("executor", executor)
builder.add_edge(START, "planner")
builder.add_edge("planner", "executor")
builder.add_edge("executor", END)

graph = builder.compile(checkpointer=InMemorySaver())

config = {
    "configurable": {
        "thread_id": "user-001",
    }
}

result = graph.invoke({"query": "Explain checkpoints"}, config)
```

`thread_id` 不是 Python、Java 或操作系统线程 ID；它更接近 `conversation_id`、`workflow_instance_id` 或一次可持久化工作流实例的 ID。

## 3. Checkpoint 的保存时机：super-step 边界

不要把保存时机简单记成“每个节点执行完就保存一次”。LangGraph 按 super-step（超级步）组织图执行：一批当前可并发执行的节点读同一版本状态，产出写入，在屏障处统一合并，再进入下一批节点。

对于串行图：

```text
START → planner → executor → END
```

可近似理解为：

```text
Checkpoint 0：图初始化
        ↓
Checkpoint 1：写入输入；next = planner
        ↓
planner 执行
        ↓
Checkpoint 2：写入 plan；next = executor
        ↓
executor 执行
        ↓
Checkpoint 3：写入 result；next = END
```

因此，Checkpoint 同时回答两个问题：

1. 现在的数据是什么？
2. 图已经执行到哪里，下一步应该运行什么？

这也是恢复时可以从确定位置继续、而不是从 `START` 重跑的原因。

### 3.1 串行与并行的 super-step

串行节点通常位于不同 super-step：

```text
Super-step 1：A
Super-step 2：B
Super-step 3：C
```

可并行节点属于同一个 super-step：

```text
             ┌── A ──┐
START ───────┤       ├── C
             └── B ──┘
```

其概念执行过程是：

```text
State V1
  ├── A(State V1) → write A
  └── B(State V1) → write B
              ↓
           屏障
              ↓
       合并写入并运行 reducer
              ↓
           State V2
              ↓
        C(State V2)
```

A 和 B 都读取 super-step 开始时的 `State V1`，而不会看到对方“执行到一半”的更新。这是 Pregel / Bulk Synchronous Parallel（BSP，批同步并行）风格的计算模型。

## 4. 一个状态快照包含什么

`graph.get_state(config)` 返回的 `StateSnapshot` 可概念化为：

```python
StateSnapshot(
    values=...,        # 当前 Graph State
    next=...,          # 下一批要执行的节点
    config=...,        # thread_id、checkpoint_id、namespace 等
    metadata=...,      # step、写入来源等
    created_at=...,    # 创建时间
    parent_config=..., # 父 checkpoint
    tasks=...,         # task、错误或 interrupt 信息
)
```

例如：

```python
snapshot = graph.get_state(config)

print(snapshot.values)
print(snapshot.next)
print(snapshot.config)
```

可能表达为：

```text
values = {"query": "...", "plan": "..."}
next = ("executor",)
config = {
  "configurable": {
    "thread_id": "user-001",
    "checkpoint_ns": "",
    "checkpoint_id": "..."
  }
}
```

它意味着：`planner` 已完成，`executor` 尚未运行；当前快照属于 `user-001` 的某段执行历史。

### 4.1 `thread_id`、`checkpoint_id` 与 `checkpoint_ns`

三者的职责不同：

| 字段 | 表示什么 | 类比 |
| --- | --- | --- |
| `thread_id` | 哪一条完整、持久化的执行历史 | 会话或工作流实例 ID |
| `checkpoint_id` | 这条历史中的某一个快照 | 历史版本 ID |
| `checkpoint_ns` | 同一历史中哪个图或嵌套子图 | 图的命名空间 |

```text
thread_id = research-session-123
  ├── checkpoint A
  ├── checkpoint B
  ├── checkpoint C
  └── checkpoint D
```

只传 `thread_id` 时，保存器通常读取该历史的最新 checkpoint；同时传 `checkpoint_id` 时，读取指定历史版本。

```python
# 读取 thread 123 的最新状态
{"configurable": {"thread_id": "123"}}

# 读取 thread 123 在 cp002 时的状态
{
    "configurable": {
        "thread_id": "123",
        "checkpoint_id": "cp002",
    }
}
```

若节点内部启动 `threading.Thread` 或 `asyncio.gather()`，那是 Python 或操作系统的并发，不会自动派生新的 LangGraph `thread_id`。

若是 Subgraph（子图），父图的 Checkpointer 默认会传播给子图，并用命名空间区分层级：

```text
thread_id = 123
  ├── checkpoint_ns = ""                   # Parent Graph
  ├── checkpoint_ns = "research:abc"       # Research Subgraph
  └── checkpoint_ns = "research:abc|search:def"  # Nested Subgraph
```

只有在显式调用另一张图并传入不同的 `thread_id` 时，才会创建另一条 LangGraph 执行历史。

## 5. 完整 checkpoint 与 task-level writes

`checkpoint_writes`（或称 task-level writes / pending writes）和完整 checkpoint 粒度不同：

| 对象 | 粒度 | 内容 | 常见保存时机 | 主要作用 |
| --- | --- | --- | --- | --- |
| checkpoint | 一个 super-step | 完整 Graph 状态、版本、调度信息 | super-step 成功收敛后 | 恢复、历史、回放 |
| checkpoint writes | 一个 Node / Task | 该任务写入了哪些 State channel | 任务完成时 | 避免失败后重跑已成功任务 |

设 A 与 B 并行：

```text
       A
      / \
START    C
      \ /
       B
```

super-step 开始前：

```python
state = {"query": "小米 CEO 是谁？"}
```

A 返回：

```python
{"web_result": "..."}
```

B 返回：

```python
{"db_result": "..."}
```

在完整 checkpoint 提交前，可以分别保存：

```text
task = A, channel = web_result, value = "..."
task = B, channel = db_result,  value = "..."
```

所有任务成功后，写入经过 reducer 合并成完整状态，再成为新的 checkpoint：

```python
{
    "query": "小米 CEO 是谁？",
    "web_result": "...",
    "db_result": "...",
}
```

底层保存器接口通常围绕以下能力：

```python
get_tuple()   # 读取 checkpoint 及其相关信息
put()         # 写完整 checkpoint
put_writes()  # 写某个 task 的中间写入
list()        # 查询 checkpoint 历史
```

### 5.1 Pending writes 如何支持失败恢复

假设一个并行 super-step 中：

```text
search_web  ✅
search_db   ✅
search_api  ❌
```

若只在整个 super-step 成功后保存，恢复时三个任务都可能重跑。保存成功任务的 pending writes 后，恢复时可以复用 `search_web` 与 `search_db` 的结果，只处理失败任务。

这只覆盖“任务成功执行并且结果已被 LangGraph 持久化”的情况；外部副作用成功但持久化前崩溃，仍是业务层必须处理的故障窗口，详见第 9 节。

## 6. Channel 与 Reducer：为什么 State 不直接原地修改

表面上，State 是普通字段：

```python
class ResearchState(TypedDict):
    query: str
    search_results: list[str]
    final_answer: str
```

编译后可以近似理解为一组有更新规则的 channel（状态通道）：

```text
ResearchState
  ├── query
  ├── search_results
  └── final_answer

        编译后近似为

channels
  ├── query          → LastValue(str)
  ├── search_results → 某种聚合 Channel
  └── final_answer   → LastValue(str)
```

所以 Node 的：

```python
return {"search_results": ["A"]}
```

更接近于“向 `search_results` channel 投递一次 update”，而非原地执行：

```python
state["search_results"] = ["A"]
```

### 6.1 默认覆盖与显式 reducer

普通字段默认可近似看作 `LastValue`：新值替换旧值。

```python
class State(TypedDict):
    query: str
```

```text
旧值：query = "old"
写入：query = "new"
结果：query = "new"
```

并行场景下，集合类字段通常应显式指定 reducer：

```python
import operator
from typing import Annotated
from typing_extensions import TypedDict


class State(TypedDict):
    results: Annotated[list[str], operator.add]
```

若两个并行节点分别返回：

```python
# Node A
{"results": ["A"]}

# Node B
{"results": ["B"]}
```

`results` channel 会使用 reducer 合并：

```text
[] + ["A"] + ["B"] → ["A", "B"]
```

这种聚合语义可近似理解为 `BinaryOperatorAggregate`。如果两个并行节点同时覆盖没有 reducer 的同一字段，LangGraph 应报 `InvalidUpdateError`，而不应偷偷采用“最后写入者胜出”。

### 6.2 Channel、super-step 与 checkpoint 的关系

```text
Super-step N
  ├── Node A → write results = ["A"]
  └── Node B → write results = ["B"]
                    ↓
                 reducer
                    ↓
            results = ["A", "B"]
                    ↓
          新 checkpoint（完整状态）
```

因此 checkpoint 通常还需要记录 `channel_values`、`channel_versions` 和 `versions_seen`：

- `channel_values`：每个 channel 当前的值；
- `channel_versions`：哪些 channel 已更新及其版本；
- `versions_seen`：任务已消费到哪些 channel 版本。

它们让 Checkpoint 不只是业务数据备份，也保存了部分图调度状态。这也是自己执行 `json.dump(state)` 不能替代 LangGraph Checkpointer 的原因。

## 7. 恢复、Human-in-the-loop 与历史回放

### 7.1 故障恢复

假设运行到 `writer` 失败：

```text
START → planner ✅ → searcher ✅ → analyzer ✅ → writer ❌ → reviewer
```

最近的成功 checkpoint 可以表达为：

```text
analyzer 已完成
next = writer
```

恢复时加载这个 checkpoint，恢复 State、`next` 和任务信息，从 `writer` 重试，而不是从 `planner`、`searcher`、`analyzer` 全部重跑。

### 7.2 Human-in-the-loop

节点调用 `interrupt()` 时，图可以暂停；Checkpointer 将当时的 State、下一步任务和 interrupt 信息持久化。之后用户批准或补充信息，再携带相同 `thread_id` 恢复。

```text
planner → 生成计划 → interrupt() → 等待用户 → executor
```

`interrupt()` 负责暂停；能跨分钟、跨小时乃至服务重启继续，依赖的是 Checkpoint 的持久化。

### 7.3 历史、Replay 与 Fork

可用：

```python
history = list(graph.get_state_history(config))
```

查看历史 `StateSnapshot`。选择过去的某一个 checkpoint 后：

```python
graph.invoke(None, history_checkpoint.config)
```

会从该 checkpoint 之后重新执行；它之前的节点不再重跑。需要注意：这可能重新调用 LLM、API 或其他外部系统。

也可修改历史状态：

```python
new_config = graph.update_state(
    old_checkpoint.config,
    {"plan": "新的计划"},
)
```

这不是修改旧历史，而是在旧 checkpoint 处分叉出一条新执行路径：

```text
CP1 → CP2 → CP3
       ├── 原执行路径
       └── 修改状态 → 新执行路径
```

## 8. 保存器与存储模型

Checkpoint 是抽象机制；Checkpointer 决定数据保存位置。

```text
BaseCheckpointSaver
  ├── InMemorySaver  → Python 进程内存
  ├── SqliteSaver    → SQLite
  └── PostgresSaver  → PostgreSQL
```

| 实现 | 适用场景 | 进程重启后 |
| --- | --- | --- |
| `InMemorySaver` | 实验、单元测试、本地调试 | 历史丢失 |
| `SqliteSaver` | 单机开发、Demo | 可保留 |
| `PostgresSaver` / `AsyncPostgresSaver` | 多实例或生产部署 | 可保留 |

概念上，数据库至少需要区分：

```text
checkpoints
  ├── thread_id
  ├── checkpoint_id
  ├── parent_checkpoint_id
  ├── checkpoint_state
  └── metadata

checkpoint_writes
  ├── thread_id
  ├── checkpoint_id
  ├── task_id
  ├── channel
  └── value
```

完整 checkpoint 倾向保存 channel 值、版本和调度信息；writes 表保存单个任务的写入记录。

## 9. 幂等、副作用与孤儿资源

Checkpoint 提供的是**可恢复执行**，不是把外部系统和 Checkpointer 自动组成 Exactly-Once（恰好一次）分布式事务。

关键语义是：已经成功并持久化的工作尽量不重复；已开始但结果尚未成功持久化的任务，恢复时可能再次执行。因此，产生外部副作用的节点必须由业务层实现幂等。

### 9.1 最危险的故障窗口

```python
def create_server(state):
    server = cloud.create_server()
    return {"server_id": server.id}
```

可能发生：

```text
cloud.create_server() 创建 server-001  ✅
进程在返回值写入 checkpoint 前崩溃       ❌
恢复后 create_server() 再次执行
创建 server-002
```

此时 `server-001` 是孤儿资源。LangGraph 无法单独消除该窗口：外部云 API 创建资源与 Checkpointer 写数据库是两个独立事务。

同理，扣款、发邮件、创建订单、发布消息、写文件都可能出现“外部动作成功，但图状态尚未记录”的不一致。

### 9.2 稳定 operation_id：先持久化，再执行副作用

不要在可能重跑的副作用节点中临时生成 UUID：

```python
def bad_create_server(state):
    operation_id = str(uuid.uuid4())
    return cloud.create_server(idempotency_key=operation_id)
```

节点重跑会产生不同 key，不能幂等。应先生成并保存稳定的 `operation_id`，让它先进入一个 checkpoint：

```python
import uuid
from typing_extensions import TypedDict


class State(TypedDict):
    operation_id: str
    server_id: str | None


def prepare(state: State):
    return {"operation_id": str(uuid.uuid4())}


def create_server(state: State):
    server = cloud.create_server(
        idempotency_key=state["operation_id"],
    )
    return {"server_id": server.id}
```

执行顺序：

```text
prepare → checkpoint(operation_id = abc123) → create_server
```

若 `create_server` 成功后崩溃，恢复仍使用 `abc123`。外部服务支持幂等键时，应返回已有的 `server-001`，而不是再创建 `server-002`。

### 9.3 数据库幂等：唯一约束与 Upsert

数据库写入通常以 `operation_id` 建唯一约束：

```sql
INSERT INTO jobs(operation_id, status)
VALUES (:operation_id, 'running')
ON CONFLICT(operation_id) DO NOTHING;
```

重跑时唯一键命中，因此不会重复创建。常用方案包括：

- 外部 API 的 idempotency key；
- 数据库唯一约束与 upsert；
- 写前按 `operation_id` 查询已有结果；
- outbox / 去重表；
- 可重试的纯读、检索、计算节点。

### 9.4 `@task` 缩小重跑范围，但不取代幂等

一个大节点内若顺序调用 A、B、C：

```python
def research_node(state):
    a = call_api_a()
    b = call_api_b()
    c = call_api_c()
    return {"result": combine(a, b, c)}
```

若 A、B 成功、C 失败，整个节点没有成功返回，恢复可能从节点开头重跑。可把可独立持久化的工作拆成 Task：

```python
from langgraph.func import task


@task
def call_a():
    return call_api_a()


@task
def call_b():
    return call_api_b()


@task
def call_c():
    return call_api_c()


def research_node(state):
    a = call_a().result()
    b = call_b().result()
    c = call_c().result()
    return {"result": combine(a, b, c)}
```

Task 结果可被 checkpoint 复用，A/B 已成功时可减少重复调用。但 Task 的外部副作用成功而其结果尚未持久化时，同一个故障窗口仍然存在，所以 Task 本身也必须幂等。

### 9.5 Super-step 的“事务性”边界

同一 super-step 的 LangGraph State 更新在收敛时统一提交；一个分支失败时，这一批 State 更新不会成为新的完整 checkpoint。

这不等于外部副作用会回滚：

```text
Node B：payment_api.charge(100)  # 已扣款
Node C：抛出异常
        ↓
LangGraph State：该 super-step 不提交
外部世界：扣款已发生
```

“事务性”只描述 LangGraph 状态边界，不是对数据库、云 API、支付系统或文件系统的 ACID 保证。

## 10. 并发控制分两层

### 10.1 单个 Run 内的节点并发

并行节点通过“读取旧状态 → 返回 update → Channel / Reducer 合并”避免共享可变对象竞争。不要在节点中并发原地修改嵌套 `dict` 或 `list`；把更新作为返回值交给 reducer。

可通过配置限制同时运行的任务数：

```python
graph.invoke(
    inputs,
    {"configurable": {"max_concurrency": 10}},
)
```

这主要保护 API 限流、数据库连接池和 CPU / I/O 资源；它不保证副作用幂等。

### 10.2 同一个 `thread_id` 的 Run 级并发

这与同一图中的 Node 并行不同：

```text
thread_id = 123
  ├── Run A
  └── Run B
```

两个 Run 同时修改同一条执行历史可能发生竞态。使用 LangGraph Agent Server / LangSmith Deployment 时，可使用 `multitask_strategy` 管理同一线程的并发请求：

| 策略 | 语义 |
| --- | --- |
| `enqueue` | 后来的 Run 排队，等待当前 Run 完成 |
| `reject` | 当前 Run 运行时拒绝新 Run |
| `interrupt` | 用新 Run 中断当前 Run |
| `rollback` | 按服务端策略处理先前执行结果 |

自行通过 `graph.ainvoke()` 暴露 HTTP 服务时，应在应用层按 `thread_id` 设计串行队列、锁或乐观并发控制；不要把节点并行机制误当成 Run 级并发控制。

## 11. 生产级副作用工作流

对重要的外部资源，推荐采用 Prepare → Execute → Finalize / Reconcile（准备 → 执行 → 收尾 / 对账）模式：

```text
1. Prepare
   生成并持久化 operation_id
   状态：PREPARED
        ↓ checkpoint

2. Execute
   调外部系统，携带 operation_id / idempotency key
        ↓
   返回 resource_id

3. Finalize
   持久化 resource_id
   状态：COMPLETE

4. Reconcile
   恢复或定期任务按 operation_id 查询外部系统
   已存在：接管并完成记录
   不存在：安全重试
```

若外部 API 不支持幂等键：

1. 在外部资源 metadata / tag 中写入 `workflow_id` 和 `operation_id`；
2. 失败后按这些标识做对账，决定接管、删除或重试；
3. 为临时资源配置 TTL（生存时间）或 Lease（租约）；
4. 为可补偿操作建立 Saga：后续失败时执行删除、取消或反向操作。

补偿不是数据库回滚。若“资源已创建，但 `resource_id` 尚未写回图状态且进程死亡”，补偿节点也不知道要删除什么；稳定 operation_id 和对账机制仍不可省略。

## 12. 机制全链路

一次调用可粗略理解为：

```text
graph.invoke(input, {thread_id})
        ↓
Checkpointer.get_tuple()
        ↓
查找该 thread 的最新 checkpoint
        ├── 不存在：创建初始 State
        └── 存在：恢复 State + next + task 信息
        ↓
执行当前 super-step
        ├── Node A → put_writes()
        └── Node B → put_writes()
        ↓
合并 Node 输出
        ↓
Channel / Reducer 更新 State
        ↓
Checkpointer.put() 保存完整 checkpoint
        ↓
按 next 进入下一 super-step 或结束
```

## 13. 常见误区与检查清单

### 常见误区

- 把 `thread_id` 当作系统线程 ID；它实际标识持久化工作流历史。
- 把“节点执行一次”与“一个 super-step”画等号；并行节点可属于同一 super-step。
- 把 checkpoint 视为 `json.dumps(state)`；它还含控制流、任务与 Channel 版本信息。
- 把 pending writes 当完整快照；前者是任务级写入，后者是收敛后的图状态。
- 认为 super-step 的事务边界能回滚外部 API；它只约束 LangGraph State。
- 依赖 checkpoint 自动避免扣款、发信、建资源重复；副作用必须业务幂等。
- 在副作用节点里新建 UUID；必须先把稳定 `operation_id` 持久化。
- 以为 `max_concurrency` 能处理同一 `thread_id` 的多个 Run；它主要限制单个 Run 的任务并发。

### 设计检查清单

1. 这个节点突然重跑一次，会造成什么后果？
2. 副作用是否携带已持久化的稳定 `operation_id`？
3. 外部系统是否支持幂等键、唯一约束、upsert 或查询复用？
4. 资源创建成功但图状态未保存时，能否通过 tag / 对账找到它？
5. 并行节点写同一 State key 时，是否定义了正确 reducer？
6. 同一个 `thread_id` 的并发 Run 是否有明确排队或冲突策略？
7. Replay 或 `update_state()` 后的下游节点重跑，是否仍然安全？

## 14. 关联知识点

- [LangGraph 状态更新、invoke 与 stream](11_LangGraph_%E7%8A%B6%E6%80%81%E6%9B%B4%E6%96%B0%E3%80%81invoke_%E4%B8%8E_stream.md)
- [UNIQUE、UPSERT 与数据库写入幂等](../05_Database_Redis/17_UNIQUE%E3%80%81UPSERT%20%E4%B8%8E%E6%95%B0%E6%8D%AE%E5%BA%93%E5%86%99%E5%85%A5%E5%B9%82%E7%AD%89.md)
- [async、await 与协程调度](../03_Python/07_async%E3%80%81await_%E4%B8%8E%E5%8D%8F%E7%A8%8B%E8%B0%83%E5%BA%A6.md)
