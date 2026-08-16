# 01.03 Q、K、V 注意力机制

## 1. 核心结论

Q、K、V 是同一份输入表示经过三组不同参数投影得到的三种角色：

- Q（Query）：当前位置想从可见上下文中查找什么；
- K（Key）：一个位置可以通过什么特征被其他位置匹配；
- V（Value）：该位置被关注后实际贡献什么信息。

因此可以把一次注意力概括为：**Q 与 K 决定“看谁”，注意力权重对 V 加权决定“取什么”。**

## 2. 计算过程

对某一层输入矩阵 $X$：

$$
Q=XW_Q,\qquad K=XW_K,\qquad V=XW_V
$$

单头缩放点积注意力为：

$$
\operatorname{Attention}(Q,K,V)
=\operatorname{softmax}\left(\frac{QK^T}{\sqrt{d_k}}+M\right)V
$$

其中 $M$ 可以是 causal mask、padding mask 等。计算分为五步：

1. 用三组参数矩阵投影得到 Q、K、V；
2. 计算 $QK^T/\sqrt{d_k}$，得到位置之间的匹配分数；
3. 应用 mask，排除不允许关注的位置；
4. 对每个 query 的分数做 softmax，得到注意力权重；
5. 用权重对对应的 V 加权求和，形成该 query 位置的新表示。

```python
Q = X @ Wq
K = X @ Wk
V = X @ Wv

scores = Q @ K.transpose(-2, -1) / sqrt(d_k)
scores = scores + mask
weights = softmax(scores, dim=-1)
output = weights @ V
```

从输入矩阵开始，逐项算出 Encoder 的 $QK^T$、缩放、Softmax、$AV$，再对照 Decoder 加入 Causal Mask 后的完整数值演算，见 [01.06 第 3.1、4.4 节](./06_Encoder、Decoder、Decoder-only_与_Cross_Attention.md)。

## 3. Q、K、V 的角色差异

以 token“吃”为例：

```
Q吃：我现在需要从前文查找什么？
K吃：以后别的 token 可以通过什么特征匹配我？
V吃：以后别的 token 关注我时，我能提供什么信息？
```

当后续 token“苹果”到来时，执行的是：

```
Q苹果
  ↓ 与历史 Key 匹配
K我  K喜欢  K吃  K苹果
  ↓ 形成注意力权重
V我  V喜欢  V吃  V苹果
  ↓ 加权汇聚
“苹果”当前位置的新表示
```

这里使用了历史 token 的 K/V，但不会再次使用它们当时的 Q。历史 Q 已经完成了“为自身位置读取上下文”的任务。

可以用数据库类比：Q 是一次查询请求，K 是索引，V 是记录内容。查询执行完后，旧 Q 没有后续用途；K/V 仍要留给未来的新查询使用。这正是 KV Cache 缓存 K/V 而不缓存 Q 的角色原因，完整推理过程见 [01.07 Causal Mask、自回归生成与 KV Cache](./07_Causal_Mask%E3%80%81%E8%87%AA%E5%9B%9E%E5%BD%92%E7%94%9F%E6%88%90%E4%B8%8E_KV_Cache.md)。

## 4. Q、K、V 是否会变化

Q/K/V 不是 token 在词表中的固定属性，而是由**当前层的输入表示**投影得到的。对第 $l$ 层、位置 $i$：

$$
q_i^{(l)}=h_i^{(l-1)}W_Q^{(l)},\quad
k_i^{(l)}=h_i^{(l-1)}W_K^{(l)},\quad
v_i^{(l)}=h_i^{(l-1)}W_V^{(l)}
$$

所以需要区分两种情况：

- token 所处的左侧上下文不同，输入表示可能不同，Q/K/V 也可能不同；
- 在同一条 decoder-only 因果序列中，仅在右侧追加未来 token，历史位置看不到新增 token，其各层输入表示不变，因此历史 Q/K/V 都不变。

第二点是 KV Cache 能安全复用历史 K/V 的数学基础。不是只有 K/V 不变，历史 Q 也不变；区别只是历史 Q 后续不再使用。

## 5. 常见误区

### 误区一：Q/K 是注意力权重

Q/K 本身不是权重。它们先产生匹配分数，经过 mask 和 softmax 后才得到注意力权重。

### 误区二：V 是“token 的固定含义”

V 是某一层上下文表示的线性投影。同一个词在不同上下文、不同层和不同注意力头中，V 都可能不同。

### 误区三：注意力权重就是完整解释

某层某头的权重只能说明该 query 在该处如何分配读取比例。模型还有多头拼接、残差连接、归一化、FFN 和后续层，不能只凭一张 attention map 完整解释最终输出。

## 6. 本次讨论中的理解推进

1. 从“Q/K/V 分别是关注比重、提供信息比重和具体值”，修正为“Q/K 产生匹配分数，V 是被加权读取的内容”；
2. 进一步明确 Q 是当前位置的一次性查询，K/V 是可供当前及未来 query 使用的可检索信息；
3. 明确历史 Q 并非因为未来 token 到来而变化，而是由于后续不再参与计算，所以不进入缓存；
4. 最终把 Q/K/V 的角色与 Causal Mask、KV Cache、Prefill/Decode 两阶段连成同一条推理链路。

## 7. 参考资料

- [Attention Is All You Need](https://arxiv.org/abs/1706.03762)
- [Hugging Face Transformers：How caching works](https://huggingface.co/docs/transformers/main/cache_explanation)
