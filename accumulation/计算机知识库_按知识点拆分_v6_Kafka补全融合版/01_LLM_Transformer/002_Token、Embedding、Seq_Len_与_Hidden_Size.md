# Token、Embedding、Seq Len 与 Hidden Size

> 所属分类：LLM / Transformer  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Token 是离散文本单位，embedding 是 token 的连续向量，seq_len 是 token 数量，hidden_size 是每个 token 的向量维度。


## 2. 原理性解释

- 矩阵 X 常见形状是 `[seq_len, hidden_size]` 或 `[batch, seq_len, hidden_size]`。
- 每一行对应一个 token 的向量。
- hidden_size 不是人工可读属性，而是模型训练出的隐空间维度。
- 上下文窗口主要限制 seq_len。

### `[seq_len, hidden_size]` 的真实含义

`seq_len` 表示这次输入中有多少个 token；`hidden_size` 表示每个 token 被表示成多少维向量。你之前疑惑“每个 token 都变成长度为 hidden size 的向量，为什么 X 是 `[seq_len, hidden_size]`”，本质原因是：模型一次处理的是一串 token，所以把每个 token 的向量按行堆起来，就形成了一个矩阵。

例如句子被切成 5 个 token，每个 token 的向量长度是 768，那么输入矩阵就是 `[5, 768]`。第 3 行不是“第三个特征”，而是“第三个 token 的 768 维表示”。Transformer 层不会把这个矩阵当二维图片处理，而是沿 token 维度做 attention，沿 hidden 维度做向量投影。

```python
# batch_size=2, seq_len=5, hidden_size=768
x.shape == (2, 5, 768)
# x[0, 3, :] 表示第 1 个样本第 4 个 token 的完整向量
```

## 3. 机制流程

1. tokenizer 切分文本。
2. token id 查 embedding 表。
3. 形成 X 矩阵。
4. 输入 Transformer block。

### Embedding 的数据流

从文本到模型输入通常经历：

```text
原始文本
  ↓ tokenizer
input_ids: [101, 2769, 4263, 102]
  ↓ embedding lookup
Token Embedding: [seq_len, hidden_size]
  + Position Embedding
  + 可选 Segment/Type Embedding
  ↓
Transformer Block 输入 X
```

工程排查时要特别关注三个维度：`batch_size`、`seq_len`、`hidden_size`。很多初学 bug 不是算法错，而是把 `[B, S, H]` 错当成 `[S, H]`，或者在 padding 后没有正确设置 attention mask，导致模型把补齐位置也当成真实 token 处理。

## 4. 类比理解

token 像卡片，embedding 是卡片背后的属性表，seq_len 是卡片数量，hidden_size 是属性栏数量。

## 5. 应用举例 / 代码或伪代码

```python
seq_len = 5
hidden_size = 768
X = [[0.0] * hidden_size for _ in range(seq_len)]
print(len(X), len(X[0]))  # 5 768
```

## 6. 你在讨论中的理解推进

你问过为什么每个 token 是 hidden size 向量却说 X 是 `[seq_len, hidden_size]`；关键是“一行一个 token”。

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

理解 **Token、Embedding、Seq Len 与 Hidden Size** 时，不要只停留在“名词解释”，而要追踪张量和信息流：

1. **输入形态**：一段文本先变成 token id，再查 embedding table 得到向量。
2. **中间变换**：Transformer 层反复做注意力聚合、残差连接、归一化和 FFN 非线性变换。
3. **输出用途**：生成模型会把最后一层 hidden state 投影到词表 logits；Embedding/RAG 模型则会把向量用于相似度检索。
4. **调试方式**：看 shape 是否一致、mask 是否正确、logits 是否异常、相似度分布是否过于集中。

### 最小验证实验

```python
# 伪代码：用 shape 跟踪 Token、Embedding、Seq Len 与 Hidden Size 是否真的理解到位
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

## 11. 针对 `Token、Embedding、Seq Len 与 Hidden Size` 的专项排查

学习或实现 **Token、Embedding、Seq Len 与 Hidden Size** 时，可以用下面的方式检查自己是否真正掌握：

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

当被问到 `Token、Embedding、Seq Len 与 Hidden Size` 时，可以按“定义 → 数据流 → 为什么需要 → 工程影响”回答，避免只背名词。
