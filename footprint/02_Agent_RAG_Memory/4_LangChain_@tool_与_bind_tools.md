# LangChain @tool 与 bind tools

## 1. 总体性概念

@tool 把普通函数声明为工具；函数签名和 docstring 会变成 schema；bind_tools 把 schema 发给模型，让模型能选择工具并生成参数。

本文件只说明 LangChain 的具体封装；通用 Function Calling 闭环以及它与 MCP 的层级关系见 `003_Function_Calling_与_MCP_工具接入.md`。


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
    # 安全提示：不要用内置 eval 执行模型生成的表达式，应使用受限的 safe_eval
    return safe_eval(expression)

calculate.__doc__  # 可被 bind_tools 转为 description
```

版本说明：@tool 与 bind_tools 在 LangChain 1.x（2025-10 发布）中仍是现行用法；但 1.x 推荐的高层入口是 `create_agent`，它内部管理工具绑定，不接受预先 `bind_tools` 过的模型。

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
