# Multi-Head Attention 与表达能力

> 所属分类：LLM / Transformer  
> 修订版本：v9 昨日今日增量版  
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

