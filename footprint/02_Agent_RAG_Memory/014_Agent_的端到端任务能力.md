# Agent 的端到端任务能力

> 所属分类：Agent / RAG / Memory  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Agent 的端到端任务能力是把 LLM 从文本回答扩展为目标理解、状态维护、工具调用、观察反馈和最终交付的闭环。


## 2. 原理性解释

- Agent 需要显式 state，不只是多轮聊天。
- 工具调用结果要写回 observation。
- planner/executor/evaluator/memory 是常见组件。
- 必须设计权限、日志、停止条件和失败恢复。

### 端到端不是“一步到位”，而是把目标闭环交给系统管理

Agent 的端到端任务能力指：用户只描述目标，系统负责拆解、调用工具、处理结果、修正错误并产出最终结果。这里的“端到端”不是说中间没有模块，而是说用户不需要手动串联每个模块。

一个最小 Agent 闭环必须包含：目标理解、状态表示、动作选择、工具执行、观察结果、停止判断。缺少状态，系统无法知道做到哪一步；缺少停止判断，容易无限循环；缺少工具约束，容易执行危险或无效操作。

## 3. 机制流程

1. 接收目标。
2. 规划或选择工具。
3. 执行并获得 observation。
4. 更新 state。
5. 判断继续或结束。

### Agent 闭环流程

```python
state = {"goal": user_goal, "trace": [], "done": False}
while not state["done"]:
    action = planner_or_llm(state)
    if action.type == "tool":
        obs = tools[action.name](**action.args)
        state["trace"].append((action, obs))
    elif action.type == "final":
        state["done"] = True
        answer = action.content
```

真实工程会在循环外再加：最大步数、超时、权限校验、参数 schema、错误重试、审计日志、可观测性指标。

## 4. 类比理解

普通 LLM 像顾问，Agent 像能查系统、填表、执行任务的助理。

## 5. 应用举例 / 代码或伪代码

```python
state = {"goal": goal, "steps": [], "evidence": []}
while not done(state):
    action = plan_next(state)
    obs = run_tool(action)
    state["steps"].append((action, obs))
return synthesize(state)
```

## 6. 你在讨论中的理解推进

你从“LLM 文本输入输出”推进到“端到端完成任务”的工程闭环。

