# LangGraph 状态更新、invoke 与 stream

## 1. 总体性概念

LangGraph 类框架把 Agent 表示为状态图：节点读取 state 并返回增量更新，reducer 负责合并；`invoke` 通常返回最终状态，`stream` 暴露中间事件、消息或状态变化；checkpoint 则保存可恢复的业务状态和执行位置。

## 2. 原理性解释

- Tool、Agent node、workflow 分别承担窄能力、局部决策和全局编排；
- 带审核、重试或回退循环的工作流不是严格 DAG，而是一般状态图；
- 节点内 LLM 可以流式吐 token，但正式 state 通常在节点返回 update 后合并；
- UI 事件、token/message、tool observation、state update 要区分；
- checkpoint 不只是序列化 dict，还要定义快照边界、恢复位置、版本迁移和副作用语义；
- 可持久化 BusinessState 必须与 Queue、Task、Session、client 等 RuntimeContext 分层。

### LangGraph 的状态更新与流式输出要分开理解

节点返回增量比任意原地修改共享 dict 更容易审计、重放和并发合并。复杂字段应明确是追加、替换、计数还是专用图合并，不能全部使用普通 `dict.update()`。

`invoke()` 更像运行到终点并返回最终 state；`stream()` 可以暴露：

- `values`：每步后的完整状态；
- `updates`：每步的状态增量；
- `messages`：节点内模型消息/token；
- `custom`：节点主动发送的事件。

节点内 token 已经流出，不代表节点 state 已提交。前端实时性还取决于服务端是否把对应事件继续转成 SSE/WebSocket。

### Tool、Agent Node、Workflow 与 DAG

Tool 接收参数并返回 observation；Agent node 结合模型、Prompt 和上下文完成一段更新；workflow 管理顺序、分支、循环、取消、checkpoint 和终止。若审核后返回修改、失败后重试，就存在回边，不应称为 DAG。

### `yield` 与 checkpoint 顺序

异步生成器执行 `yield event` 时，事件已交给上层，`yield` 后的保存代码尚未执行。若协议要求“checkpoint_saved”，必须先成功保存再发送该事件；否则应准确命名为 `stage_output_ready`。

### Checkpoint 的恢复语义

一个可用 checkpoint 至少回答：

1. 保存哪些业务状态、阶段和外部副作用进度；
2. 在节点、阶段还是时间间隔边界保存；
3. 保存时是否仍有并发 Task 修改 state；
4. 恢复后从哪个节点继续，哪些资源重建；
5. 代码升级后旧快照怎样迁移；
6. 是否可能重复请求、写库、发消息或扣费。

适合持久化的是字符串、数字、枚举、列表、字典和按协议编码的 datetime/UUID。不应直接持久化 Queue、Task、Future、文件/socket、Session、锁和进程绑定 client。

### 序列化、快照一致性与幂等

```text
领域状态
  → 只选允许持久化字段
  → 编码 datetime / UUID / Enum
  → schema_version 校验
  → JSON-compatible object
  → 数据库驱动
```

`json.dumps(value, default=str)` 只让本次调用临时字符串化未知对象，不会修改原对象，也不保证可逆。JSONB 应接收 dict/list/标量，而不是先 dumps 后得到的整个 JSON 字符串。

并发 Task 仍修改嵌套 state 时，`dict(state)` 浅拷贝也不是一致快照。常用策略是在节点/阶段收敛后保存、不可变更新、加锁复制、单一 reducer 或事件日志。

恢复可能重复外部副作用，应使用幂等键、步骤状态、结果缓存、outbox、去重表或补偿操作，并明确至少一次/至多一次语义。Checkpoint 不能自动回滚已发生的外部动作。

给同步保存函数套 `async def` 并直接调用，数据库 I/O 仍会阻塞事件循环；应使用异步驱动/Session，或在确认线程安全后把完整同步事务隔离到线程池。

## 3. 机制流程

1. 初始输入写入 state；
2. 节点读取 state，发出可选的 token/custom 事件；
3. 节点返回增量，reducer 合并；
4. 路由选择下一节点或循环；
5. 在一致边界构造业务快照并保存；
6. 恢复时迁移、验证快照，重建 RuntimeContext；
7. 根据步骤记录和幂等策略继续执行。

### invoke、stream 与 checkpoint 抽象流程

```text
invoke：初始 state → 节点/路由循环 → 最终 state

stream：节点执行 → token/custom/update 事件 → 调用方

checkpoint：阶段收敛 → 业务快照 → 版本化持久化
resume：加载 → 迁移/验证 → 重建 Queue/client/Session → 下一节点
```

## 4. 类比理解

`invoke` 像等会议结束后拿纪要，`stream` 像实时旁听，state update 像正式记入会议记录，checkpoint 像在确认议程节点完成后保存可恢复档案。

## 5. 应用举例 / 代码或伪代码

```python
from langgraph.config import get_stream_writer

def write_node(state):
    writer = get_stream_writer()
    chunks = []
    for chunk in llm.stream(state["prompt"]):
        chunks.append(chunk.content)
        writer({"type": "token", "data": chunk.content})
    return {"answer": "".join(chunks)}

for mode, event in graph.stream(
    inputs,
    stream_mode=["messages", "updates", "custom"],
):
    handle(mode, event)
```

通用 checkpoint 快照：

```python
def checkpoint_snapshot(state):
    return {
        "schema_version": 1,
        "job_id": state["job_id"],
        "stage": state["stage"],
        "completed_items": list(state["completed_items"]),
    }

async def resume(checkpoint_id, repository):
    raw = await repository.load(checkpoint_id)
    state = migrate_and_validate(raw)
    runtime = rebuild_runtime_context()
    return state, runtime
```

## 6. 你在讨论中的理解推进

你从“节点什么时候更新 state、stream 能看到什么”推进到完整状态工作流：过程事件与正式提交分层，带回路流程不是 DAG，checkpoint 还必须处理序列化、快照一致性、运行时资源重建和副作用幂等。
