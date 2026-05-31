# LangChain @tool 与 bind tools

> 所属分类：Agent / RAG / Memory  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

@tool 把普通函数声明为工具；函数签名和 docstring 会变成 schema；bind_tools 把 schema 发给模型，让模型能选择工具并生成参数。


## 2. 原理性解释

- 函数体开头三引号字符串是 docstring，保存在 `__doc__`。
- @tool 读取名称、参数类型和 docstring。
- bind_tools 不执行工具，只告诉模型有哪些工具。
- 模型返回 tool_call 后程序再执行。

### `@tool` 的关键价值是把普通函数变成模型可理解的工具描述

`@tool` 不只是给函数贴标签，它通常会读取函数名、类型注解、docstring，把它转换成 LLM 可见的 schema。你问到为什么函数体开头可以直接写字符串：那是 Python 的 docstring，保存在函数的 `__doc__` 属性里，工具绑定时可以读取它作为工具说明。

```python
def calculate(expression: str) -> str:
    """计算数学表达式，如 '2 + 3 * 4'。"""
    return str(eval(expression))

calculate.__doc__  # 可被 bind_tools 转为 description
```

## 3. 机制流程

1. 写函数和 docstring。
2. @tool 包装。
3. bind_tools 绑定到模型。
4. 模型输出 tool_call。
5. 执行工具并返回 observation。

### bind_tools 的机制流程

```text
Python 函数
  ↓ 读取 name / annotations / docstring
工具 schema
  ↓ 发送给 LLM
模型输出 tool_call(name,args)
  ↓ 参数校验
真实函数执行
  ↓ observation
模型继续推理或最终回答
```

工具描述要写清楚参数含义和使用场景，否则模型可能在不该调用时调用，或者传错参数。对于危险工具，还要在执行前做人为权限校验。

## 4. 类比理解

schema 像工具说明书；bind_tools 是把说明书递给模型。

## 5. 应用举例 / 代码或伪代码

```python
@tool
def calculate(expression: str) -> str:
    """计算数学表达式，如 2 + 3 * 4。"""
    return safe_eval(expression)

llm_with_tools = llm.bind_tools([calculate])
```

## 6. 你在讨论中的理解推进

你已理解 @tool 声明工具、bind_tools 转 schema；追问 docstring 后理解框架读取 `__doc__`。

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

把 **LangChain @tool 与 bind tools** 放进 Agent 系统时，核心不是“让 LLM 多想几句”，而是要设计可追踪的状态机：

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

## 11. 针对 `LangChain @tool 与 bind tools` 的专项排查

在 Agent 工程里，判断 **LangChain @tool 与 bind tools** 是否设计正确，可以看四个问题：

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
    # 练习：给 LangChain @tool 与 bind tools 增加一个专门的 stop_reason 或 trace 字段
```

### 面试表达模板

讲 `LangChain @tool 与 bind tools` 时，不要只说“让 LLM 自动完成任务”，而要说清：它如何选择动作、如何保存中间状态、如何判断信息充分、如何防止循环。
