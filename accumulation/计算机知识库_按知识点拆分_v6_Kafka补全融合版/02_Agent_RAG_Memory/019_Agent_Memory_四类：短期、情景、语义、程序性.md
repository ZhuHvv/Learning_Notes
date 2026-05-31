# Agent Memory 四类：短期、情景、语义、程序性

> 所属分类：Agent / RAG / Memory  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Agent Memory 可分短期、情景、语义、程序性：短期是当前上下文，情景记录经历，语义保存事实，程序性保存做事方法。


## 2. 原理性解释

- 短期记忆容量有限但可直接被模型看到。
- 情景记忆记录具体事件。
- 语义记忆记录抽象事实。
- 程序性记忆记录 SOP、规则、工具使用策略。
- 长期记忆要有写入、检索、更新、遗忘机制。

### 四类记忆解决的不是同一类问题

短期记忆通常是当前上下文窗口里的消息和中间状态；情景记忆记录发生过的具体事件；语义记忆保存稳定事实、概念和用户偏好；程序性记忆保存“如何做事”的流程或技能。Agent 记忆设计如果不区分这些类型，就会把聊天记录、知识库、工具使用经验混在一起，检索时噪声很大。

例如“用户喜欢 C++”偏语义记忆；“上次调 Kafka 时把 localhost 拼成 locolhost”偏情景记忆；“排查 Docker volume 要先看挂载路径是否绝对路径”偏程序性记忆。

## 3. 机制流程

1. 判断是否值得记忆。
2. 分类存储。
3. 生成 embedding 和 metadata。
4. 任务时检索相关记忆。
5. 注入上下文或状态。

### 记忆写入与检索流程

```python
def classify_memory(event):
    if event.is_current_task_state:
        return "short_term"
    if event.is_specific_episode:
        return "episodic"
    if event.is_stable_fact:
        return "semantic"
    if event.is_how_to:
        return "procedural"
```

检索时也应按用途选择：回答用户偏好优先语义记忆；复盘问题优先情景记忆；执行任务优先程序性记忆；当前多轮对话则依赖短期状态。

## 4. 类比理解

短期像桌面纸，情景像日记，语义像百科卡，程序性像操作手册。

## 5. 应用举例 / 代码或伪代码

```python
memory = {
  "short": messages[-12:],
  "episodic": event_logs,
  "semantic": facts,
  "procedural": rules,
}
```

## 6. 你在讨论中的理解推进

你问短期记忆是否等同 context window；工程上可近似如此，但长期记忆需要外部系统。

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

把 **Agent Memory 四类：短期、情景、语义、程序性** 放进 Agent 系统时，核心不是“让 LLM 多想几句”，而是要设计可追踪的状态机：

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

## 11. 针对 `Agent Memory 四类：短期、情景、语义、程序性` 的专项排查

在 Agent 工程里，判断 **Agent Memory 四类：短期、情景、语义、程序性** 是否设计正确，可以看四个问题：

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
    # 练习：给 Agent Memory 四类：短期、情景、语义、程序性 增加一个专门的 stop_reason 或 trace 字段
```

### 面试表达模板

讲 `Agent Memory 四类：短期、情景、语义、程序性` 时，不要只说“让 LLM 自动完成任务”，而要说清：它如何选择动作、如何保存中间状态、如何判断信息充分、如何防止循环。
