# 02.06 MRKL、ReAct、ToT 与 Plan-and-Execute

## 1. 总体性概念

MRKL、ReAct、ToT、Plan-and-Execute 都是在回答同一个核心问题：**Agent 面对一个任务时，应该如何决定“下一步做什么”**。

它们的区别不在于“是否使用 LLM”，而在于 **决策结构** 不同：

| 范式 | 核心动作 | 适合任务 | 关键风险 |
|---|---|---|---|
| MRKL | 路由到专家模块 | 问题类型明确、工具边界清楚 | 路由错了会整条链路错 |
| ReAct | Thought → Action → Observation 循环 | 需要边查边推理的任务 | 容易循环、上下文膨胀 |
| ToT | 生成多条思路并搜索/评估 | 推理路径不唯一的问题 | 成本高、评估器设计难 |
| Plan-and-Execute | 先计划，再逐步执行 | 长任务、多步骤任务 | 计划过时、不随反馈调整 |


## 2. 原理性解释

### 2.1 MRKL：路由型 Agent

MRKL 可以理解为 “LLM + 多个专家模块”。LLM 不一定亲自完成所有事，而是判断问题应该交给谁：

- 数学题 → calculator
- 实时信息 → search
- 数据查询 → SQL / vector DB
- 文件问题 → document retriever

关键点是 **router**：

```python
def mrkl_router(query):
    route = llm_classify(query, choices=["search", "calculator", "sql", "rag", "chat"])
    return route
```

MRKL 的优势是结构清楚、可控性强；缺点是路由错误会导致后续工具完全不匹配。

### 2.2 ReAct：边推理边行动

ReAct 的核心不是 “Thought” 本身，而是 **推理与外部观察交替更新状态**：

```text
Thought: 我需要查 A 信息
Action: search("A")
Observation: 搜索结果
Thought: 结果不足，还需要 B
Action: search("B")
Observation: ...
Final: 基于证据回答
```

它适合用户的问题一开始信息不足，需要通过工具逐步补齐。

### 2.3 ToT：多路径搜索

Tree of Thoughts 不只生成一个下一步，而是生成多个候选路径，然后评估、扩展、剪枝：

```python
frontier = [initial_state]
for depth in range(max_depth):
    candidates = []
    for state in frontier:
        thoughts = llm_generate_thoughts(state, n=3)
        candidates.extend(expand(state, thoughts))
    frontier = select_top_k(candidates, evaluator, k=5)
return best(frontier)
```

它更接近搜索算法，适合数学推理、规划、谜题、多方案设计，但成本明显高于普通 ReAct。

### 2.4 Plan-and-Execute：计划与执行分离

Plan-and-Execute 先把目标拆成步骤，再逐步执行：

```python
plan = [
    "收集需求",
    "检索相关资料",
    "生成初稿",
    "检查一致性",
    "输出最终结果",
]
```

工程上常见做法是：**Planner 生成计划，Executor 对每个子任务使用 ReAct 执行**。

### 四种行动范式的本质差异

MRKL、ReAct、ToT、Plan-and-Execute 的差异可以用“动作选择粒度”理解：MRKL 是先选模块；ReAct 是每一轮根据观察选下一步；ToT 是同时展开多条候选推理路径；Plan-and-Execute 是先生成任务列表，再逐项执行。

这四者可以组合，而不是互斥。例如一个长任务可以先 Plan-and-Execute 拆成 5 个子任务；每个子任务内部用 ReAct 调工具；遇到复杂规划点时用 ToT 评估多个方案；工具选择阶段再用 MRKL 路由到搜索、数据库、计算器或 RAG。

```python
if long_task:
    plan = make_plan(goal)
    for step in plan:
        result = react_execute(step)
elif needs_tool_route:
    tool = mrkl_route(query)
elif needs_search_tree:
    answer = tree_of_thoughts(query)
```

## 3. 机制流程

```text
用户目标
  ↓
判断任务复杂度
  ├─ 简单问答：直接回答
  ├─ 类型明确：MRKL 路由工具
  ├─ 信息不足：ReAct 循环补证据
  ├─ 多方案推理：ToT 搜索候选路径
  └─ 长任务：Plan-and-Execute 先拆解再执行
```

### 选择行动范式的决策流程

```text
任务是否可以直接回答？
 ├─ 是：直接生成
 └─ 否
    ↓
是否只是工具类型明确？
 ├─ 是：MRKL 路由
 └─ 否
    ↓
是否需要边查边补证据？
 ├─ 是：ReAct 循环
 └─ 否
    ↓
是否存在多条候选解法？
 ├─ 是：ToT 展开、评估、剪枝
 └─ 否
    ↓
是否是长任务？
 └─ 是：Plan-and-Execute + 必要时 Replan
```

工程实现时不要只保存自然语言 Thought，应把 `action_name`、`args`、`observation`、`evidence_ids`、`stop_reason` 都结构化保存，方便提前终止、回放和调试。

## 4. 类比理解

- **MRKL**：像医院分诊台，先判断你该去内科、外科还是影像科。
- **ReAct**：像侦探查案，一边假设一边找证据，证据会改变下一步行动。
- **ToT**：像下棋，不只想一步，而是展开多条路线并评估局面。
- **Plan-and-Execute**：像项目经理先排任务表，再让成员逐项完成。

## 5. 应用举例 / 代码或伪代码

```python
class AgentState(dict):
    pass

def choose_strategy(query: str) -> str:
    if is_simple(query):
        return "direct"
    if needs_fixed_tool(query):
        return "mrkl"
    if is_long_task(query):
        return "plan_execute"
    if has_many_reasoning_paths(query):
        return "tot"
    return "react"

def react_execute(task, tools, max_steps=8):
    state = AgentState(task=task, trace=[], evidence=[])
    for step_id in range(max_steps):
        decision = llm_decide_next_action(state)
        if decision["type"] == "final":
            return decision["answer"]
        obs = tools[decision["tool"]](**decision["args"])
        state["trace"].append({"decision": decision, "observation": obs})
    return summarize_with_warning(state)

def plan_and_execute(goal, tools):
    plan = llm_make_plan(goal)
    results = []
    for subtask in plan:
        results.append(react_execute(subtask, tools))
        if should_replan(goal, plan, results):
            plan = llm_replan(goal, finished=results)
    return synthesize(goal, results)
```

## 6. 你在讨论中的理解推进

你一开始把 Agent 范式理解成“LLM 调工具的方法”。后来你进一步追问：

1. **ReAct 和 Plan-and-Execute 是什么关系？**  
   修正后：Plan-and-Execute 是任务拆解框架，ReAct 可以作为每个子任务的执行器。

2. **Multi-Agent 和 Plan-and-Execute 是否一回事？**  
   修正后：不是。Multi-Agent 是角色/实体划分；Plan-and-Execute 是流程划分。两者可以组合。

3. **ReAct 是否就是把所有历史拼接进上下文？**  
   修正后：朴素 ReAct 会这么做，但工程上要通过摘要、状态结构化、提前终止、缓存来控制成本。

## 7. 常见误区与排查思路

- **误区 1：所有 Agent 都是 ReAct。**  
  实际上 ReAct 只是行动循环的一种；路由型、规划型、搜索型都可能不用典型 ReAct 格式。

- **误区 2：计划一旦生成就固定。**  
  真实环境中 Observation 可能推翻计划，因此需要 replan 条件。

- **误区 3：ToT 一定更强。**  
  ToT 成本高，只有在多路径推理收益明显时才值得使用。

## 8. 关联知识点

- `013 Reflection、Insight 与执行后反思`：执行后如何总结经验。
- `008 ReAct 提前终止检测`：ReAct 如何避免无限循环。
- `009 重复检测、语义缓存与 Best-of-n`：如何降低重复请求和多路径成本。
- `016 IterResearch`：长研究任务如何保持上下文规模稳定。

## 9. 复习检查问题

1. MRKL 和 ReAct 的核心区别是什么？
2. Plan-and-Execute 中 Executor 能不能使用 ReAct？
3. ToT 为什么成本更高？
4. 什么情况下应该触发 replan？
5. 为什么行动范式必须配合状态结构，而不是只靠 prompt？
