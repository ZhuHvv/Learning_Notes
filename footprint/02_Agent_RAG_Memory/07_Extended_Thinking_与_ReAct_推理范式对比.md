# 02.07 Extended Thinking 与 ReAct 推理范式对比

## 1. 总体性概念

Extended Thinking 可以泛指模型在输出答案或调用工具前，使用更多内部计算完成分析、规划和校验。ReAct 则是一种 Agent 编排范式：系统反复执行“推理决策 → 调用外部动作 → 接收观察结果 → 再决策”。

两者位于不同层次：

```text
Extended Thinking：模型内部怎样进行更充分的推理
ReAct：应用系统怎样组织模型与外部环境的交互循环
```

因此，把 Extended Thinking 说成“将 ReAct 的思考完全内化”只说对了一部分。它可能把某些规划与分析放到模型内部，但 ReAct 中真正关键的 **Action 和 Observation** 仍属于外部工具交互，不能仅靠内部推理替代。

## 2. 原理性解释

### 2.1 ReAct 的核心是闭环，而不只是显示 Thought

ReAct 常被写成：

```text
Thought → Action → Observation → Thought → ... → Final
```

但它的本质是：模型的下一步决策会受到真实工具结果影响。

```python
state = {"question": question, "observations": []}
for step in range(MAX_STEPS):
    decision = agent_model(state)
    if decision.type == "tool":
        obs = run_tool(decision.tool, decision.args)
        state["observations"].append(obs)
    elif decision.type == "final":
        return decision.answer
```

即使系统不向用户展示原始 Thought，外部的 action/observation loop 仍然是 ReAct 式的。

### 2.2 Extended Thinking 主要增加单次模型调用内部的推理深度

概念上，一次调用可以表示为：

```text
输入问题 + 当前工具观察
        ↓
模型内部分析、候选方案比较、自检
        ↓
输出工具调用或最终答案
```

内部推理可以完成：

- 对问题做更细的分解；
- 比较多条候选路径；
- 检查前后矛盾；
- 形成工具参数；
- 判断证据是否足够。

这些工作与 ReAct 的 Thought 功能存在重叠，所以你会产生“它把 Thought 内化了”的直觉。但它仍然无法凭内部计算获得实时网页、数据库记录或代码执行结果。

### 2.3 两者可以组合

一个 Agent 每轮都可以使用具备 Extended Thinking 能力的模型：

```text
ReAct 外部循环
  Round 1：模型内部充分推理 → search action
  Observation：搜索结果
  Round 2：模型内部充分推理 → database action
  Observation：查询结果
  Round 3：模型内部充分推理 → final answer
```

这不是二选一，而是“更强的每轮决策器 + 外部闭环执行”。

### 2.4 控制权和状态位置不同

| 维度 | Extended Thinking | ReAct / Agent Loop |
|---|---|---|
| 推理位置 | 单次模型调用内部 | 应用编排层的多轮循环 |
| 外部状态 | 通常只看到输入和最终输出/工具请求 | 显式保存 action、observation、step、stop reason |
| 获取新信息 | 不能仅靠思考获得外部事实 | 通过工具调用获得真实观察 |
| 可控性 | 主要通过模型配置（如 adaptive thinking、effort 档位；旧版为 token 预算）与提示 | 可限制工具、步数、超时、重试、状态迁移 |
| 可观测性 | 不应依赖暴露原始私有推理 | 可记录工具轨迹和结构化决策 |
| 适用问题 | 复杂但可在已知输入内完成的分析 | 需要搜索、执行、数据库、文件等环境反馈的任务 |

### 2.5 不要把“是否展示 Thought”当作范式判断标准

早期演示会显式输出 Thought，但生产系统为了安全、简洁和稳定，通常只记录结构化决策，例如：

```json
{
  "action": "search",
  "arguments": {"query": "Kafka ISR election"},
  "reason_summary": "需要外部资料验证故障选举机制"
}
```

ReAct 并不要求向用户公开完整 chain-of-thought。判断它是否是 ReAct，应看系统是否存在基于 observation 的迭代行动闭环。

## 3. 机制流程

### 3.1 纯内部推理

```text
问题 + 已知材料
  ↓ 模型内部延长分析
答案
```

适合：数学推导、给定代码分析、已有文档归纳等不需要新外部信息的任务。

### 3.2 ReAct 外部循环

```text
问题
  ↓ 模型决定下一动作
工具调用
  ↓
真实 Observation
  ↓ 模型根据新证据继续决策
...直到满足停止条件
```

### 3.3 组合架构

```python
def react_with_deep_reasoning(question):
    state = AgentState(question=question)
    for _ in range(8):
        # 每轮决策内部可使用更充足的推理预算
        decision = reasoning_model.decide(state)

        if decision.kind == "tool":
            result = tools[decision.name](**decision.arguments)
            state.add_observation(decision, result)
        elif decision.kind == "final" and evidence_is_sufficient(state):
            return decision.answer

    return fallback_answer(state)
```

外层保证可控执行，内层提高决策质量。

## 4. 类比理解

Extended Thinking 像一个人在采取行动前，在脑中多推演几步；ReAct 像这个人实际走到现场、查看仪表、询问他人，再根据新情况继续调整。脑内推演再充分，也不能替代现场观察；现场闭环中的每一步又可以先认真思考。

## 5. 应用举例 / 代码或伪代码

### 5.1 只需要内部推理的任务

```text
给定一段 Go channel 代码，判断为什么会 deadlock。
```

代码已经完整提供，模型可以在一次调用中分析 channel 容量、阻塞点和关闭语义，不一定需要工具循环。

### 5.2 必须依赖外部 Observation 的任务

```text
查找当前线上服务的最近 10 分钟错误率，并判断是否需要回滚。
```

模型必须调用监控系统：

```text
Action: query_prometheus(...)
Observation: error_rate = 12.4%
Action: query_deployment_history(...)
Observation: new version deployed 8 minutes ago
Final: 建议回滚，并说明证据
```

无论内部推理多强，都不能凭空知道线上指标。

### 5.3 状态记录应保存什么

```python
trace.append({
    "step": step,
    "action": decision.name,
    "arguments": redact_sensitive(decision.arguments),
    "observation_summary": summarize(result),
    "source_ids": result.source_ids,
    "stop_reason": None,
})
```

应记录结构化行动轨迹和证据，而不是依赖保存或展示模型的完整私有思考。

## 6. 你在讨论中的理解推进

- 起点：你提出“相比 ReAct，Claude 的做法是不是把思考工作内化，而不是显式放在工作循环中”。
- 肯定部分：模型内延长推理确实把一部分任务分解、方案比较和自检放进了单次模型调用内部。
- 关键修正：ReAct 不只有 Thought，还包含 Action 和真实 Observation。外部环境交互、状态持久化和停止控制仍需要 Agent loop。
- 最终理解：Extended Thinking 与 ReAct 是不同层级、可以叠加的能力；前者增强每一轮“怎么想”，后者规定多轮“怎么做、怎么观察、怎么继续”。

## 7. 常见误区与排查思路

- **误区：模型想得更久就不需要工具。** 外部事实必须通过工具获得。
- **误区：没有展示 Thought 就不是 ReAct。** 结构化 action/observation 闭环仍可属于 ReAct。
- **误区：把完整私有推理日志作为可观测性。** 工程应记录决策摘要、工具参数、观察结果和证据来源。
- **排查：** 区分错误来自单轮决策质量、工具结果质量、状态更新错误还是停止条件错误。

## 8. 关联知识点

- `06_MRKL、ReAct、ToT_与_Plan-and-Execute.md`
- `13_Reflection、Insight_与执行后反思.md`
- `08_ReAct_提前终止检测.md`
- `11_LangGraph_状态更新、invoke_与_stream.md`
- `02_Agent_的端到端任务能力.md`

## 9. 复习检查问题

1. Extended Thinking 与 ReAct 分别位于哪一层？
2. 为什么 ReAct 的关键不只是 Thought？
3. 隐藏 Thought 后，系统还能否采用 ReAct？
4. 什么任务只需要内部推理，什么任务必须依赖工具观察？
5. 如何组合“更强单轮推理”和“可控外部 Agent 循环”？
