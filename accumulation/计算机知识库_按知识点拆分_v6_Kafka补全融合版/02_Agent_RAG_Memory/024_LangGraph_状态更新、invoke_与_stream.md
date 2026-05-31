# LangGraph 状态更新、invoke 与 stream

> 所属分类：Agent / RAG / Memory  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

LangGraph 类框架把 Agent 表示为状态图；invoke 通常最终返回完整结果，stream 则逐步输出节点事件、状态增量或 token。


## 2. 原理性解释

- 节点读取 state，结束时返回 state update。
- 节点内部 LLM 可以流式吐 token，但图状态通常在节点返回后合并。
- 工具调用结果应结构化写回 state。
- 要区分 UI 流、LLM token 流、图状态更新。

### LangGraph 的状态更新与流式输出要分开理解

图式 Agent 的节点通常以 state 为输入，返回对 state 的增量更新。即使节点内部调用 LLM 可以 token-level stream，图状态也往往要等节点函数返回后才能提交。这就是你追问“节点内部多轮执行是否会整个节点结束后才更新状态”的关键。

`invoke()` 更像一次性运行直到终点并返回最终 state；`stream()` 则把节点执行过程中的事件、状态增量或消息分块暴露给调用方。但 stream 能看到什么，取决于框架是否在节点内部主动 yield 事件，而不是只看 LLM 是否支持流式。

## 3. 机制流程

1. 输入初始 state。
2. 执行节点。
3. 节点内部可 emit token。
4. 节点结束返回 update。
5. stream 产出事件给前端。

### invoke 与 stream 抽象流程

```python
# invoke
state = initial
while node := next_node(state):
    delta = node(state)
    state.update(delta)
return state

# stream
for event in graph.stream(initial):
    yield event  # 可能是节点开始、token、工具结果、state delta
```

工程上如果想让用户提前看到 LLM 输出，需要在节点内部把 token 事件转发到 SSE/WebSocket；如果只在节点结束后返回 state，前端仍然会感觉“卡住”。

## 4. 类比理解

invoke 像等会议纪要，stream 像实时听会议。

## 5. 应用举例 / 代码或伪代码

```python
async def node(state, emit):
    text = ""
    async for token in llm.astream(state["prompt"]):
        text += token
        await emit({"type": "token", "data": token})
    return {"answer": text}
```

## 6. 你在讨论中的理解推进

你问节点内部多轮执行是否要等结束才更新状态；答案是流式输出可以提前，正式 state 合并取决于框架。

## 7. 常见误区与排查思路

- 只背名词，不知道它在完整链路中的输入、输出和失败模式。
- 只看正常路径，忽略异常、超时、权限、重复和可观测性。
- 把相邻概念混用，导致设计或排查时定位错误。

## 8. 关联知识点

- 回到 00_总体索引.md 查看上下游知识点。
- 结合 00_总体知识网络图.md 理解跨模块关系。

## 9. 复习检查问题

- 它解决的核心问题是什么？
- 它的输入、输出和中间状态分别是什么？
- 它在真实项目中最容易出错的边界条件是什么？
- 它和上游、下游知识点如何连接？

## 10. 更细的工程拆解

把 **LangGraph 状态更新、invoke 与 stream** 放进 Agent 系统时，核心不是“让 LLM 多想几句”，而是要设计可追踪的状态机：

1. **State**：保存用户目标、当前计划、工具结果、检索证据、失败原因、是否结束。
2. **Policy**：决定下一步是调用工具、检索、反思、重试，还是输出 final answer。
3. **Memory / Evidence**：区分临时上下文、可长期复用经验、外部文档证据，避免把噪声写入长期记忆。
4. **Stop Condition**：防止无限循环，通常结合充分性、一致性、重复行动次数和最大步数。

### 最小 Agent 状态伪代码

```python
state = {
    "goal": user_query,
    "plan": [],
    "evidence": [],
    "tool_trace": [],
    "memory_hits": [],
    "final_answer": None,
    "stop_reason": None,
}

while not state["final_answer"]:
    decision = policy_llm(state)       # 选择 search/tool/reflect/final
    if decision.type == "tool":
        obs = run_tool(decision.name, decision.args)
        state["tool_trace"].append((decision, obs))
    elif decision.type == "retrieve":
        state["evidence"] += retriever(decision.query)
    elif decision.type == "reflect":
        state["memory_hits"] += reflect_and_retrieve(state)
    elif decision.type == "final":
        state["final_answer"] = decision.answer
```

### 工程落地要点

- 任何 Agent 范式都要落成“可序列化状态”，否则无法调试、恢复、缓存或流式输出。
- 对工具结果要保留原始 observation，不要只保留模型改写后的摘要。
- 对反思和记忆写入要加过滤条件，避免长期记忆被一次错误执行污染。

## 11. 针对 `LangGraph 状态更新、invoke 与 stream` 的专项排查

在 Agent 工程里，判断 **LangGraph 状态更新、invoke 与 stream** 是否设计正确，可以看四个问题：

- **状态是否显式**：计划、证据、工具轨迹、记忆命中、停止原因是否能被打印和回放。
- **工具调用是否可控**：是否限制最大步数、参数 schema、错误重试和超时。
- **证据是否可追溯**：最终回答能不能回到具体 observation、文档片段或 memory item。
- **失败是否可恢复**：失败后是直接结束，还是进入反思、重试、改写 query 或降级回答。

### 小型练习

```python
def debug_agent_state(state):
    print("goal:", state.get("goal"))
    print("steps:", len(state.get("tool_trace", [])))
    print("evidence:", len(state.get("evidence", [])))
    print("stop_reason:", state.get("stop_reason"))
    # 练习：给 LangGraph 状态更新、invoke 与 stream 增加一个专门的 stop_reason 或 trace 字段
```

### 面试表达模板

讲 `LangGraph 状态更新、invoke 与 stream` 时，不要只说“让 LLM 自动完成任务”，而要说清：它如何选择动作、如何保存中间状态、如何判断信息充分、如何防止循环。
