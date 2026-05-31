# 预训练、SFT、RLHF 与 LoRA

> 所属分类：LLM / Transformer  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

预训练学习语言分布，SFT 学会指令跟随，RLHF/DPO 对齐人类偏好，LoRA 用低秩增量做参数高效微调。


## 2. 原理性解释

- 预训练常用 next-token prediction。
- SFT 使用指令-回答样本。
- RLHF/DPO 优化偏好而非补实时知识。
- LoRA 冻结主权重，只训练低秩矩阵。

### 预训练、SFT、RLHF、LoRA 分别改变模型的哪一部分能力

预训练让模型学语言统计规律和世界知识；SFT 让模型学会按指令格式回答；RLHF/DPO 等偏好优化让模型更符合人类偏好；LoRA 则是一种低成本微调方式，通过给部分线性层增加低秩增量矩阵，让模型在少量参数上适配新任务。

可以把基础模型看成“读了大量书但不一定听话的人”，SFT 是“教它按问答格式办事”，RLHF 是“告诉它哪些回答更好”，LoRA 是“不给整个人重训，只给关键神经通路加小插件”。

```python
# LoRA 思想：原权重 W 冻结，只训练 A/B
W_eff = W + B @ A * scale
output = x @ W_eff
```

## 3. 机制流程

1. 预训练。
2. SFT。
3. 偏好对齐。
4. 部署时结合 prompt/RAG/tool。
5. 必要时 LoRA 微调。

### 模型训练/适配的流程选择

```text
大规模无监督语料 → 预训练 base model
  ↓
人工指令数据 → SFT instruct model
  ↓
偏好数据 / reward model / DPO → 对齐模型
  ↓
领域数据 + LoRA/QLoRA → 垂直任务适配
```

工程上不要把所有问题都归结为“微调”。如果知识频繁变化，优先 RAG；如果输出格式不稳定，优先 prompt/schema/SFT；如果领域风格和任务策略长期稳定，才考虑 LoRA 或全参微调。

## 4. 类比理解

预训练像读书，SFT 像学答题格式，RLHF 像老师按偏好打分，LoRA 像加一个小适配器。

## 5. 应用举例 / 代码或伪代码

```python
# y = x @ (W + A @ B)
W.requires_grad_(False)
A = Parameter(randn(in_dim, r))
B = Parameter(randn(r, out_dim))
y = x @ W + alpha * (x @ A @ B)
```

## 6. 你在讨论中的理解推进

对 AI 应用开发而言，优先判断问题该用 prompt、RAG、工具还是微调解决。

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

理解 **预训练、SFT、RLHF 与 LoRA** 时，不要只停留在“名词解释”，而要追踪张量和信息流：

1. **输入形态**：一段文本先变成 token id，再查 embedding table 得到向量。
2. **中间变换**：Transformer 层反复做注意力聚合、残差连接、归一化和 FFN 非线性变换。
3. **输出用途**：生成模型会把最后一层 hidden state 投影到词表 logits；Embedding/RAG 模型则会把向量用于相似度检索。
4. **调试方式**：看 shape 是否一致、mask 是否正确、logits 是否异常、相似度分布是否过于集中。

### 最小验证实验

```python
# 伪代码：用 shape 跟踪 预训练、SFT、RLHF 与 LoRA 是否真的理解到位
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

## 11. 针对 `预训练、SFT、RLHF 与 LoRA` 的专项排查

学习或实现 **预训练、SFT、RLHF 与 LoRA** 时，可以用下面的方式检查自己是否真正掌握：

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

当被问到 `预训练、SFT、RLHF 与 LoRA` 时，可以按“定义 → 数据流 → 为什么需要 → 工程影响”回答，避免只背名词。
