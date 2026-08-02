# Q K V 注意力机制

## 1. 总体性概念

Q/K/V 是注意力机制中的三组投影表示：Q 表示当前 token 想找什么，K 表示每个 token 可被怎样匹配，V 表示真正被汇聚的信息内容。


## 2. 原理性解释

- Q/K/V 由输入 X 分别乘 Wq/Wk/Wv 得到。
- QK 点积得到匹配分数，softmax 后才是注意力权重。
- 权重加权求和 V 得到上下文表示。
- K 负责匹配，V 负责传递内容，二者不能混淆。

### Q、K、V 不是三份静态知识，而是三种投影视角

你之前的理解已经接近核心：Q 可以理解成“我想找什么信息”，K 可以理解成“我能被什么问题匹配上”，V 是“真正要贡献出去的内容”。更准确地说，Q/K/V 都是由当前 token 向量通过不同线性层投影得到的，它们不是预先手写的规则，而是在训练中学出来的表示空间。

计算时，一个 token 的 Q 会和所有 token 的 K 做点积，得到它对其它 token 的注意力分数；softmax 后再对所有 V 做加权求和。也就是说，QK 决定“看谁”，V 决定“拿什么”。

```python
Q = X @ Wq
K = X @ Wk
V = X @ Wv
scores = Q @ K.T / sqrt(d_k)
weights = softmax(scores, dim=-1)
out = weights @ V
```

这也解释了为什么 Q/K/V 不能简单理解成“本 token 的固定属性表”：同一个 token 在不同上下文中，输入 X 变了，投影后的 Q/K/V 也会变。

## 3. 机制流程

1. 计算 Q、K、V。
2. 计算 `QK^T / sqrt(d)`。
3. 应用 mask。
4. softmax 得到权重。
5. 权重乘 V 得到输出。

### 注意力的逐步流程

一个单头 self-attention 的机制流程：

1. 输入矩阵 X 中每行代表一个 token。
2. 通过三组参数矩阵生成 Q、K、V。
3. 对每个 query token，计算它和所有 key token 的相似度。
4. 对相似度做缩放和 softmax，得到注意力权重。
5. 用权重对所有 value 向量加权求和。
6. 输出的新向量替换/补充原 token 的表示。

调试时可打印 `attention_weights[i]`：它能告诉你第 i 个 token 在这一层这一头里主要关注了哪些位置，但它不是完整解释模型行为的全部证据。

## 4. 类比理解

像图书馆检索：Q 是问题，K 是索引标签，V 是书的正文。

## 5. 应用举例 / 代码或伪代码

```python
scores = Q @ K.T / sqrt(d_k)
scores = apply_mask(scores)
weights = softmax(scores)
output = weights @ V
```

## 6. 你在讨论中的理解推进

你最初把 Q/K/V 理解为关注比重、提供信息比重、具体值；后来修正为 Q/K 产生匹配分数，V 是被读取内容。

