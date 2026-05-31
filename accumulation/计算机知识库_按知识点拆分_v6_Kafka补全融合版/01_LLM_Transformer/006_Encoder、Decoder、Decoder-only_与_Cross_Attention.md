# Encoder、Decoder、Decoder-only 与 Cross Attention

> 所属分类：LLM / Transformer  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Encoder 适合双向理解，Decoder 适合自回归生成，Decoder-only 是主流生成式大模型架构；Cross Attention 是 decoder 查询 encoder 输出的机制。


## 2. 原理性解释

- Encoder self-attention 通常能看全文。
- Decoder masked self-attention 只能看过去。
- Decoder-only 把 prompt 当上文持续预测后续 token。
- Cross Attention 中 Q 来自 decoder，K/V 来自 encoder。

### Encoder、Decoder 的差异来自“能看见什么”和“要生成什么”

Encoder 的 self-attention 通常可以看见完整输入，因此适合理解任务，例如分类、匹配、embedding。Decoder 的 masked self-attention 只能看见当前位置之前的 token，因此适合自回归生成。Encoder-Decoder 架构还会在 Decoder 中加入 Cross Attention：Decoder 用自己的 Q 去查询 Encoder 输出的 K/V，从源序列中拿信息。

你之前问“decoder 在训练和使用时是否有区分”。训练时通常把完整目标序列右移后并行输入，通过 causal mask 保证每个位置只能预测下一个 token；推理时则一步步生成，每次把已生成 token 作为上下文。

```text
训练：一次输入答案前缀，mask 保证不能偷看未来
推理：每次生成一个 token，再追加回上下文
```

## 3. 机制流程

1. encoder-only：全文理解。
2. decoder-only：预测下一个 token。
3. encoder-decoder：encoder 编码源文本，decoder 逐步生成目标文本。
4. cross-attention 读取源文本语义。

### 三类架构的典型数据流

```text
Encoder-only:
文本 → 双向 self-attention → pooled/CLS/embedding → 分类或检索

Decoder-only:
prompt → causal self-attention → next-token logits → 采样 → 追加 token

Encoder-Decoder:
源文本 → Encoder 输出 memory
目标前缀 → Decoder masked self-attention
Decoder Q + Encoder K/V → Cross Attention → 生成目标 token
```

Cross Attention 的关键是 Query 来自 Decoder 当前生成状态，Key/Value 来自 Encoder 对源输入的理解。这使翻译、摘要等任务可以一边生成，一边对齐源文本信息。

## 4. 类比理解

Encoder 像阅读理解老师；Decoder 像写作者；Cross Attention 像写作者翻阅原文资料。

## 5. 应用举例 / 代码或伪代码

```python
Q = decoder_hidden @ Wq
K = encoder_outputs @ Wk
V = encoder_outputs @ Wv
context = attention(Q, K, V)
```

## 6. 你在讨论中的理解推进

你困惑 decoder 训练和使用是否区分、如何预测下一个 token；答案是训练学 next-token，推理自回归展开。

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

理解 **Encoder、Decoder、Decoder-only 与 Cross Attention** 时，不要只停留在“名词解释”，而要追踪张量和信息流：

1. **输入形态**：一段文本先变成 token id，再查 embedding table 得到向量。
2. **中间变换**：Transformer 层反复做注意力聚合、残差连接、归一化和 FFN 非线性变换。
3. **输出用途**：生成模型会把最后一层 hidden state 投影到词表 logits；Embedding/RAG 模型则会把向量用于相似度检索。
4. **调试方式**：看 shape 是否一致、mask 是否正确、logits 是否异常、相似度分布是否过于集中。

### 最小验证实验

```python
# 伪代码：用 shape 跟踪 Encoder、Decoder、Decoder-only 与 Cross Attention 是否真的理解到位
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

## 11. 针对 `Encoder、Decoder、Decoder-only 与 Cross Attention` 的专项排查

学习或实现 **Encoder、Decoder、Decoder-only 与 Cross Attention** 时，可以用下面的方式检查自己是否真正掌握：

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

当被问到 `Encoder、Decoder、Decoder-only 与 Cross Attention` 时，可以按“定义 → 数据流 → 为什么需要 → 工程影响”回答，避免只背名词。
