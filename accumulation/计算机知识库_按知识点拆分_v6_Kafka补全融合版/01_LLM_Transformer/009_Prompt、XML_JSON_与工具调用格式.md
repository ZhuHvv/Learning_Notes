# Prompt、XML JSON 与工具调用格式

> 所属分类：LLM / Transformer  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

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

理解 **Prompt、XML JSON 与工具调用格式** 时，不要只停留在“名词解释”，而要追踪张量和信息流：

1. **输入形态**：一段文本先变成 token id，再查 embedding table 得到向量。
2. **中间变换**：Transformer 层反复做注意力聚合、残差连接、归一化和 FFN 非线性变换。
3. **输出用途**：生成模型会把最后一层 hidden state 投影到词表 logits；Embedding/RAG 模型则会把向量用于相似度检索。
4. **调试方式**：看 shape 是否一致、mask 是否正确、logits 是否异常、相似度分布是否过于集中。

### 最小验证实验

```python
# 伪代码：用 shape 跟踪 Prompt、XML JSON 与工具调用格式 是否真的理解到位
tokens = tokenizer("hello agent")
x = embedding(tokens)                 # [seq_len, hidden_size]
for layer in transformer_layers:
    x = layer.self_attention(x)        # token 之间交换上下文信息
    x = layer.ffn(x)                   # 每个 token 内部做非线性特征变换
logits = lm_head(x[-1])                # 只用最后一个位置预测下一个 token
next_token = argmax(logits)
```

### 常见落地场景

- 做 RAG 时，Encoder-only 或 Embedding 模型用于“把问题和文档变成可比较向量”。
- 做工具调用时，Decoder-only 模型根据 prompt 中的 schema 预测结构化 JSON/XML。
- 做性能优化时，KV Cache、batching、量化、LoRA 会影响推理成本和部署策略。

## 11. 针对 `Prompt、XML JSON 与工具调用格式` 的专项排查

学习或实现 **Prompt、XML JSON 与工具调用格式** 时，可以用下面的方式检查自己是否真正掌握：

- **形状检查**：是否能说清输入和输出的 shape，例如 `[batch, seq_len, hidden_size]`、`[seq_len, vocab_size]`。
- **信息流检查**：是否能说明一个 token 的信息如何影响另一个 token，哪些位置因为 mask 看不到未来。
- **训练/推理差异检查**：训练时通常并行计算整段序列，推理时则逐 token 生成，并通过 KV Cache 复用历史键值。
- **和 RAG 的连接**：如果本主题产出的是 embedding，要关注相似度；如果产出的是 logits，要关注下一个 token 概率。

### 小型练习

```python
# 练习：给一个 Transformer 相关概念写 shape 注释
batch = 2
seq_len = 5
hidden = 768

x = Tensor(shape=[batch, seq_len, hidden])
# 问题：经过 self-attention 后 shape 是否改变？
# 答案：通常仍是 [batch, seq_len, hidden]，但每个位置的向量已经融合了上下文。
```

### 面试表达模板

当被问到 `Prompt、XML JSON 与工具调用格式` 时，可以按“定义 → 数据流 → 为什么需要 → 工程影响”回答，避免只背名词。
