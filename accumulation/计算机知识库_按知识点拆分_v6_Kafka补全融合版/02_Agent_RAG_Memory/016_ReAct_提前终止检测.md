# ReAct 提前终止检测

> 所属分类：Agent / RAG / Memory  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

ReAct 提前终止检测判断已有信息是否足够回答，或是否已经陷入重复、低收益、工具失败循环。


## 2. 原理性解释

- 终止条件包括信息覆盖度、一致性、重复行动、预算上限。
- 信息充分性适合确切问答。
- 重复检测适合防循环。
- 冲突证据未解决时不应过早结束。

### 提前终止检测要同时看“充分性”和“循环性”

你之前总结得很准确：提前终止主要有两个方向：一是当前信息是否足够回答用户问题，二是最近若干轮行动是否重复或没有增益。ReAct 如果只靠模型自己说“我完成了”，容易过早结束；如果完全不终止，又会无限查找。

充分性检测可以看：用户问题中的槽位是否都被填充、关键结论是否有证据、不同证据是否一致、是否存在未解决约束。循环性检测可以看：工具名重复、query 高相似、observation 无新信息、状态摘要变化很小。

## 3. 机制流程

1. 每轮 ReAct 后抽取 evidence。
2. 评估 query 所需槽位覆盖。
3. 检测最近 action/observation 相似度。
4. 满足条件则合成答案。

### 提前终止伪代码

```python
def should_stop(state):
    if has_final_answer(state) and evidence_covers_question(state):
        return True, "answer_sufficient"
    if contradiction_unresolved(state):
        return False, "need_disambiguation_or_more_evidence"
    if repeated_actions(state.trace[-3:]) and no_new_evidence(state):
        return True, "loop_detected"
    if state.steps >= MAX_STEPS:
        return True, "max_steps"
    return False, "continue"
```

最终回答中可以根据停止原因调整语气：充分停止就直接回答；循环停止要说明“已查到的信息有限”；最大步数停止要给出阶段性结论和不确定点。

## 4. 类比理解

查资料时资料够了就下笔；连续翻到同一页就该停止。

## 5. 应用举例 / 代码或伪代码

```python
def should_stop(state):
    if coverage(state.question, state.evidence) > 0.85 and not conflict(state.evidence):
        return True, "evidence enough"
    if repeated(state.steps[-3:]):
        return True, "loop detected"
    return len(state.steps) >= 8, "budget"
```

## 6. 你在讨论中的理解推进

你已经总结出两个角度：信息是否足够、最近若干轮是否重复；这里将其工程化。

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

把 **ReAct 提前终止检测** 放进 Agent 系统时，核心不是“让 LLM 多想几句”，而是要设计可追踪的状态机：

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

## 11. 针对 `ReAct 提前终止检测` 的专项排查

在 Agent 工程里，判断 **ReAct 提前终止检测** 是否设计正确，可以看四个问题：

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
    # 练习：给 ReAct 提前终止检测 增加一个专门的 stop_reason 或 trace 字段
```

### 面试表达模板

讲 `ReAct 提前终止检测` 时，不要只说“让 LLM 自动完成任务”，而要说清：它如何选择动作、如何保存中间状态、如何判断信息充分、如何防止循环。
