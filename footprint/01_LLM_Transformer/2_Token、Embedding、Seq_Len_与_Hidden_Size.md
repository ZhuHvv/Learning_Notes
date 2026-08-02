# Token、Embedding、Seq Len 与 Hidden Size

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
  ↓ 注入位置信息
  ├─ 绝对位置向量：与 Token Embedding 相加
  └─ RoPE 等相对位置方法：通常在 Attention 内作用于 Q/K
  + 可选 Segment/Type Embedding
  ↓
Transformer Block 输入 X
```

无论采用哪种位置方案，主干 hidden state 的形状通常仍是 `[B, S, H]`。工程排查时要特别关注 `batch_size`、`seq_len`、`hidden_size`，还要区分 padding mask、causal mask 和 position id。很多初学 bug 不是算法错，而是把 `[B, S, H]` 错当成 `[S, H]`，或者在 padding 后没有正确设置 mask，导致模型把补齐位置也当成真实 token 处理。

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
