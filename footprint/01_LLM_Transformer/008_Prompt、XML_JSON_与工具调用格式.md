# Prompt、XML JSON 与工具调用格式

> 所属分类：LLM / Transformer  
> 修订版本：v12 学习顺序审查版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。
> 学习路径：在理解 decoder-only 生成后，先学习如何约束模型输出并接入工具，再进入下一篇训练与对齐。

## 1. 总体性概念

Prompt 可以包含结构化协议；XML 常用于划分边界，JSON 常用于传递工具调用参数。


## 2. 原理性解释

- XML 标签可标记 `<tools>`、`<tool_call>` 等区域。
- JSON 表达函数名和参数。
- 系统提示词要定义何时调用工具、输出格式和工具结果处理。
- 生产中应优先用严格 parser 或原生 tool calling。

### Prompt 中混入 XML/JSON 的目的不是“使用 XML 技术栈”

你之前看到系统提示词里使用 `<tools>...</tools>`、`<tool_call>...</tool_call>`，核心目的是给 LLM 一个清晰的结构边界，让模型更容易区分“工具列表”“输出格式”“普通自然语言”。XML 标签在这里更多是一种 prompt 分隔符，而 JSON 则适合承载机器可解析的函数名和参数。

工具调用链路通常是：把函数描述转换成 schema → 放入 prompt 或 API tools 字段 → 模型输出工具名和参数 → 程序解析 → 执行工具 → 把 observation 继续喂给模型。

```python
match = re.search(r"<tool_call>(.*?)</tool_call>", content, re.DOTALL)
args = json.loads(match.group(1))
```

## 3. 机制流程

1. 提示词列工具 schema。
2. 模型输出结构化调用。
3. 程序解析 JSON。
4. 执行工具。
5. 把结果放回上下文生成最终回答。

### 工具调用的健壮流程

```text
定义函数签名和 docstring
  ↓
转换为工具 schema
  ↓
LLM 决定是否调用工具
  ↓
校验 JSON / 参数类型 / 必填字段
  ↓
执行真实函数
  ↓
把结果作为 Observation 返回给 LLM
  ↓
LLM 生成最终回答或继续调用工具
```

工程上必须加校验层：LLM 可能输出非法 JSON、漏字段、参数类型错误，甚至请求不存在的工具。不要直接 `eval` 模型输出，也不要绕过 schema 校验调用外部系统。

## 4. 类比理解

XML 像包装盒标签，JSON 像盒子里的表单。

## 5. 应用举例 / 代码或伪代码

```python
m = re.search(r"<tool_call>(.*?)</tool_call>", content, re.DOTALL)
payload = json.loads(m.group(1))
tool_name = payload["name"]
args = payload["arguments"]
```

## 6. 你在讨论中的理解推进

你从“为什么提示词混 XML”推进到：XML 用于边界，JSON 用于参数，正则/解析器负责取出内容。
