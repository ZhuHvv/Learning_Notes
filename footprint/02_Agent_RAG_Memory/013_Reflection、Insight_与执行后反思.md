# Reflection、Insight 与执行后反思

> 所属分类：Agent / RAG / Memory  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释“执行后复盘与经验沉淀”，不复用 ReAct/Plan/IterResearch 的原理段。

## 1. 总体性概念

Reflection 是 Agent 在一次执行失败或完成后，对 **目标、行动轨迹、工具结果、错误、最终输出** 进行复盘；Insight 是从一次或多次 Reflection 中提炼出的 **可复用经验**。

简化理解：

- **ReAct**：我现在下一步做什么？
- **Reflection**：刚才为什么成功/失败？
- **Insight**：以后遇到类似问题应记住什么？


## 2. 原理性解释

Reflection 的本质是 **把一次运行过程转化为可分析的数据结构**。如果只让 LLM “反思一下”，结果往往空泛；工程上更常见的是让它输出结构化字段：

```json
{
  "success": false,
  "failure_reason": "检索结果不足，缺少来源时间",
  "bad_actions": ["只搜索了一个关键词"],
  "better_strategy": "先拆实体，再分别检索权威来源",
  "memory_to_save": "回答最新事实类问题时，需要优先确认日期和来源"
}
```

Insight 则是对 `memory_to_save` 的进一步过滤：

- 是否具有长期复用价值？
- 是否不是一次偶然错误？
- 是否会污染未来回答？
- 是否应该存入用户记忆、任务记忆，还是项目经验库？

### Reflection 与 Insight 的核心是“把执行轨迹变成可复用经验”

Reflection 不是让模型再想一遍，也不是普通摘要。它要回答的是：这次执行为什么成功/失败？哪些工具调用有效？哪些假设被证伪？未来遇到类似任务应该如何调整？Insight 则是从反思中沉淀出来的较高层经验，可以写入记忆系统或规则库。

例如 ReAct 查资料失败后，普通摘要可能写“搜索了 A、B 没找到”；有效 Reflection 应该写“原 query 过宽，应该先抽取实体名和时间范围再检索”。这类 insight 才能指导下一次行动。

```python
reflection_prompt = build_prompt(trace, final_result, errors)
insights = llm(reflection_prompt)
memory.write(type="insight", content=insights, tags=["search_strategy"])
```

## 3. 机制流程

```text
执行完成/失败
  ↓
收集 trajectory
  ↓
结构化反思：成功点、失败点、原因、改进策略
  ↓
判断是否需要重试
  ├─ 是：把反思结果作为下一轮约束
  └─ 否：输出最终结果
  ↓
筛选可复用 Insight
  ↓
写入长期记忆或经验库
```

### 执行后反思流程

```text
任务目标 + 执行轨迹 + 工具结果 + 最终输出
  ↓
判断结果质量：是否完成、是否有证据、是否出错
  ↓
提取失败点或成功策略
  ↓
形成 insight：可复用、可检索、可执行
  ↓
写入 memory / checklist / prompt policy
  ↓
下次任务触发时检索并应用
```

在工程中要避免“反思污染”：不要把未验证的猜测直接写成事实。可以把 insight 分成 `verified`、`heuristic`、`warning` 三类，并记录来源任务和时间。

## 4. 类比理解

Reflection 像“错题分析”：不只是知道错了，而是要知道错在审题、公式、计算还是时间管理。Insight 像“错题本里总结出的通用规则”：以后遇到同类题时提前避免。

## 5. 应用举例 / 代码或伪代码

```python
def reflect(goal, trajectory, final_output, user_feedback=None):
    prompt = {
        "goal": goal,
        "trajectory": trajectory,
        "final_output": final_output,
        "user_feedback": user_feedback,
        "required_json_schema": {
            "success": "bool",
            "failure_reason": "str",
            "evidence_gap": "list[str]",
            "bad_actions": "list[str]",
            "better_strategy": "str",
            "memory_to_save": "str | null",
        }
    }
    return llm_json(prompt)

def should_save_insight(reflection):
    if not reflection["memory_to_save"]:
        return False
    if reflection["success"] and not reflection["better_strategy"]:
        return False
    if "一次性" in reflection["memory_to_save"]:
        return False
    return True

reflection = reflect(goal, trajectory, answer)
if should_save_insight(reflection):
    memory_store.add(
        text=reflection["memory_to_save"],
        tags=["agent_insight", "execution_feedback"]
    )
```

## 6. 你在讨论中的理解推进

你曾经问过：**Reflection 是否只在失败时触发？**

更准确的结论是：

1. 失败后最需要 Reflection，因为它能找出下一轮如何改。
2. 成功后也可以 Reflection，因为它能总结可复用经验。
3. 但 Reflection 不能无脑写入长期记忆，否则会造成记忆污染。
4. Insight 不是原始日志，而是经过提炼和筛选的经验。

## 7. 常见误区与排查思路

- **误区 1：Reflection 就是让 LLM 再回答一次。**  
  正确做法是输入完整 trajectory，让模型解释执行过程，而不是重做问题。

- **误区 2：所有反思都保存。**  
  低质量经验会污染长期记忆，使未来 Agent 更容易走偏。

- **误区 3：只在最终失败时反思。**  
  长任务可以阶段性反思，比如每 5 步检查一次是否偏离目标。

## 8. 关联知识点

- `006 MRKL、ReAct、ToT 与 Plan-and-Execute`：Reflection 使用它们产生的执行轨迹。
- `012 Agent Memory 四类`：Insight 可能进入长期语义/程序性记忆。
- `014 Generative Agents`：反思机制可从多条 memory stream 中提炼高层 insight。
- `017 Mem0 与 A-Mem`：生产系统中如何管理长期记忆写入。

## 9. 复习检查问题

1. Reflection 的输入为什么必须包含 trajectory？
2. Insight 和普通日志有什么区别？
3. 为什么不能把所有 reflection 都写入长期记忆？
4. 完成后反思和失败后反思分别有什么价值？

