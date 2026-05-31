# Multi-Head Attention 与表达能力

> 所属分类：LLM / Transformer  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Multi-Head Attention 让多个注意力头在不同子空间并行观察同一段上下文，从而捕获多种关系。


## 2. 原理性解释

- 每个 head 有独立的 Q/K/V 投影。
- 不同 head 可学习不同关注模式。
- 多个 head 输出拼接后再投影回 hidden_size。
- 表达能力来自多视角特征组合，而不是单个 head 的人工规则。

### 多头不是“重复算很多遍”，而是并行学习不同关系子空间

单个 attention head 只有一套 Q/K/V 投影，容易把所有关系压在同一个相似度空间里。Multi-Head Attention 则把 hidden 向量切分或投影到多个子空间，每个 head 可以学不同类型的依赖：有的关注主谓关系，有的关注实体指代，有的关注局部搭配，有的关注远距离依赖。

这就是你追问“表达能力”时的核心：表达能力不是神秘概念，而是模型能表示的函数/关系复杂度。多头结构增加了并行关系建模能力，让同一 token 可以同时从多个角度收集上下文信息。

```python
heads = []
for h in range(num_heads):
    heads.append(attention(X @ Wq[h], X @ Wk[h], X @ Wv[h]))
out = concat(heads) @ Wo
```

## 3. 机制流程

1. 拆分 head。
2. 每个 head 独立 attention。
3. 拼接所有 head。
4. 输出投影融合。

### Multi-Head 的工程流程

实际实现中通常不会真的写 Python for 循环逐头计算，而是把维度 reshape：

```python
# X: [B, S, H], heads=n, head_dim=H//n
q = linear_q(X).view(B, S, n, head_dim).transpose(1, 2)  # [B, n, S, D]
k = linear_k(X).view(B, S, n, head_dim).transpose(1, 2)
v = linear_v(X).view(B, S, n, head_dim).transpose(1, 2)
attn = softmax(q @ k.transpose(-1, -2) / sqrt(head_dim))
out = (attn @ v).transpose(1, 2).reshape(B, S, H)
out = out_proj(out)
```

机制上是“拆成多头 → 各自 attention → 拼接 → 输出投影”。输出投影 `Wo` 的作用是把多个 head 的结果重新混合，而不是简单拼起来就结束。

## 4. 类比理解

单头像一个专家，多头像多个专家分别看语法、实体、位置和任务线索。

## 5. 应用举例 / 代码或伪代码

```python
outs = []
for head in heads:
    outs.append(attention(X @ head.Wq, X @ head.Wk, X @ head.Wv))
Y = concat(outs) @ Wo
```

## 6. 你在讨论中的理解推进

你追问“表达能力是什么”，这里可落到多头提供更丰富、可组合的特征空间。

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

理解 **Multi-Head Attention 与表达能力** 时，不要只停留在“名词解释”，而要追踪张量和信息流：

1. **输入形态**：一段文本先变成 token id，再查 embedding table 得到向量。
2. **中间变换**：Transformer 层反复做注意力聚合、残差连接、归一化和 FFN 非线性变换。
3. **输出用途**：生成模型会把最后一层 hidden state 投影到词表 logits；Embedding/RAG 模型则会把向量用于相似度检索。
4. **调试方式**：看 shape 是否一致、mask 是否正确、logits 是否异常、相似度分布是否过于集中。

### 最小验证实验

```python
# 伪代码：用 shape 跟踪 Multi-Head Attention 与表达能力 是否真的理解到位
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

## 11. 针对 `Multi-Head Attention 与表达能力` 的专项排查

学习或实现 **Multi-Head Attention 与表达能力** 时，可以用下面的方式检查自己是否真正掌握：

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

当被问到 `Multi-Head Attention 与表达能力` 时，可以按“定义 → 数据流 → 为什么需要 → 工程影响”回答，避免只背名词。
