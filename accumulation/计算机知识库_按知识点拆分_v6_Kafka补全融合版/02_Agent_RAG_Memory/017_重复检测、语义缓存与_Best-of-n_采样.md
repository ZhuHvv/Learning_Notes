# 重复检测、语义缓存与 Best-of-n 采样

> 所属分类：Agent / RAG / Memory  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

重复检测发现相似 query/action，语义缓存复用相似问题结果，Best-of-n 生成多个候选并用 verifier 选择最优。


## 2. 原理性解释

- 字符串缓存只能命中完全相同表达。
- 语义缓存用 embedding 判断相似，但要有阈值和过期。
- Best-of-n 成本约为 n 倍，需要评估器。
- 重复检测还应看工具参数和 observation。

### 重复检测要从“字符串相等”升级到“语义等价”

你指出过一个关键问题：如果只用历史 query 的字符串完全匹配，用户换一种问法就会失效。工程上通常要结合标准化、embedding 相似度、意图分类和参数抽取。比如“介绍 Best-of-n 采样”和“什么是 best of n sampling”本质相近，应该能命中语义缓存。

Best-of-n 则是另一类优化：不是缓存已有结果，而是一次生成多个候选答案/行动路径，再用评分器选择更优结果。它提升质量，但会增加成本。

## 3. 机制流程

1. 计算 query embedding。
2. 查相似历史。
3. 命中则复用或改写。
4. 复杂任务并行生成候选。
5. 用 verifier 选最优。

### 语义缓存与 Best-of-n 流程

```python
def semantic_cache_lookup(query):
    q = normalize(query)
    qv = embed(q)
    hit = cache.search(qv, top_k=1)
    if hit and cosine(qv, hit.vector) > 0.88 and same_intent(query, hit.query):
        return hit.answer
    return None

def best_of_n(prompt, n=5):
    candidates = [llm(prompt, temperature=0.7) for _ in range(n)]
    scored = [(judge(prompt, c), c) for c in candidates]
    return max(scored)[1]
```

语义缓存适合稳定问答；Best-of-n 适合开放生成、推理或方案设计。二者可以组合：先查缓存，未命中再采样多个候选。

## 4. 类比理解

语义缓存像记得问过类似问题；Best-of-n 像多个人做题后选最优答案。

## 5. 应用举例 / 代码或伪代码

```python
hit = cache.search(embed(query), threshold=0.92)
if hit and not hit.expired:
    return adapt(hit.answer, query)

answers = [llm(question, temperature=0.7) for _ in range(n)]
return max(answers, key=lambda a: verifier(question, a))
```

## 6. 你在讨论中的理解推进

你指出同一问题不同表达会让简单缓存失效；因此需要语义相似度而非纯字符串匹配。

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

把 **重复检测、语义缓存与 Best-of-n 采样** 放进 Agent 系统时，核心不是“让 LLM 多想几句”，而是要设计可追踪的状态机：

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

## 11. 针对 `重复检测、语义缓存与 Best-of-n 采样` 的专项排查

在 Agent 工程里，判断 **重复检测、语义缓存与 Best-of-n 采样** 是否设计正确，可以看四个问题：

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
    # 练习：给 重复检测、语义缓存与 Best-of-n 采样 增加一个专门的 stop_reason 或 trace 字段
```

### 面试表达模板

讲 `重复检测、语义缓存与 Best-of-n 采样` 时，不要只说“让 LLM 自动完成任务”，而要说清：它如何选择动作、如何保存中间状态、如何判断信息充分、如何防止循环。
