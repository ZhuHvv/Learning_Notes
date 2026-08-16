# 01.04 Multi-Head Attention 与表达能力

## 1. 核心结论

Multi-Head Attention（MHA）的目标不是把模型宽度扩大 `num_heads` 倍，而是在**总表示宽度基本不变**的前提下，让多组独立的 Q/K/V 投影在不同子空间中并行学习不同的注意力模式。

对第 $i$ 个 head：

$$
head_i=operatorname{Attention}(XW_i^Q,;XW_i^K,;XW_i^V)
$$

所有 head 的输出拼接后，再通过输出投影混合：

$$
\operatorname{MultiHead}(X)
=\operatorname{Concat}(head_1,\ldots,head_h)W^O
$$

需要特别避免一种过度解释：可以把不同 head 类比为关注语法、指代、位置或远距离依赖，但模型没有人工规定“Head 1 负责语法、Head 2 负责情感”。准确说法是：**不同 head 使用不同参数投影，因而有能力学习不同的 token 关系；每个 head 最终学到什么由训练决定。**

## 2. 为什么需要多个 Head

单个 attention head 只有一套 Q/K/V 投影，所有关系都要在同一个匹配空间中表达。模型处理一句话时，可能同时需要表示主体、指代、属性、因果和远距离依赖等关系。例如：

```text
“苹果很好吃，因为它很甜。”

很好吃 → 苹果：主体/属性关系
它 → 苹果：指代关系
甜 → 好吃：属性或因果关系
```

MHA 让同一个 hidden state 经过多组不同投影，在多个子空间中独立计算 attention，再把结果融合。因此“表达能力增强”具体指：模型能够并行表示和组合更多不同类型的关系，而不是让每个 head 重复执行完全相同的工作。

## 3. 两头注意力的投影演算

讨论中使用了一个便于手算的例子：

```text
hidden_size = 4
num_heads   = 2
head_dim    = hidden_size / num_heads = 2

token：我 喜欢 苹果
```

假设上一层输出为：

$$
H=
\begin{bmatrix}
1&0&1&0\\
0&1&0&1\\
1&1&0&0
\end{bmatrix}
\in\mathbb{R}^{3\times4}
$$

### 3.1 不是机械切片

可以用“把 4 维拆成两个 2 维 head”帮助理解 shape，但真实 MHA 的关键不是直接把：

```text
[1, 0, 1, 0]
```

机械切成两个片段，而是每个 head 都有自己学习得到的投影矩阵。

### 3.2 Head 1 的 Q 投影

令：

$$
W_Q^{(1)}=
\begin{bmatrix}
1&0\\
0&1\\
0&0\\
0&0
\end{bmatrix}
\in\mathbb{R}^{4\times2}
$$

则：

$$
Q^{(1)}=HW_Q^{(1)}
=
\begin{bmatrix}
1&0\\
0&1\\
1&1
\end{bmatrix}
\in\mathbb{R}^{3\times2}
$$

### 3.3 Head 2 的 Q 投影

令：

$$
W_Q^{(2)}=
\begin{bmatrix}
0&0\\
0&0\\
1&0\\
0&1
\end{bmatrix}
\in\mathbb{R}^{4\times2}
$$

则：

$$
Q^{(2)}=HW_Q^{(2)}
=
\begin{bmatrix}
1&0\\
0&1\\
0&0
\end{bmatrix}
\in\mathbb{R}^{3\times2}
$$

同一个 $H$ 被不同矩阵投影后，各 token 在两个 head 中得到不同表示。真实模型中的 $W_Q^{(i)}$、$W_K^{(i)}$、$W_V^{(i)}$ 都由训练学习；K、V 的投影过程与 Q 相同。

## 4. 每个 Head 独立计算 Attention

两个 head 分别拥有：

$$
Q^{(1)},K^{(1)},V^{(1)}
$$

和：

$$
Q^{(2)},K^{(2)},V^{(2)}
$$

Head 1：

$$
O_1=operatorname{softmax}
\left(
\frac{Q^{(1)}(K^{(1)})^T}{\sqrt{2}}
\right)V^{(1)}
\in\mathbb{R}^{3\times2}
$$

Head 2：

$$
O_2=operatorname{softmax}
\left(
\frac{Q^{(2)}(K^{(2)})^T}{\sqrt{2}}
\right)V^{(2)}
\in\mathbb{R}^{3\times2}
$$

然后：

$$
O_{concat}=\operatorname{Concat}(O_1,O_2)
\in\mathbb{R}^{3\times4}
$$

再乘 $W_O$，得到整个 MHA 的输出。数据流为：

```text
原 hidden state [3,4]
        │
        ├── Head 1：Q1/K1/V1 → Attention → [3,2]
        │
        └── Head 2：Q2/K2/V2 → Attention → [3,2]
                              │
                         Concatenate
                              ↓
                            [3,4]
                              ↓
                             W_O
                              ↓
                            [3,4]
```

$W_O$ 不只是恢复 shape，还会重新混合各 head 提取的信息。

## 5. 为什么每个 Head 通常只使用 `hidden_size / num_heads` 维

讨论中的实际维度为：

$$
d_{model}=4096,qquad h=32,qquad
d_{head}=\frac{4096}{32}=128
$$

因此每个 head 的 Q/K/V 都是 128 维，32 个 head 拼接后仍为：

$$
32\times128=4096
$$

### 5.1 参数量演算

单个 head 的 Q 投影：

$$
W_Q^{(i)}\in\mathbb{R}^{4096\times128}
$$

32 个 head 合计：

$$
32\times4096\times128
=4096\times4096
=16{,}777{,}216
$$

工程实现通常把这些分块合成一个：

$$
W_Q\in\mathbb{R}^{4096\times4096}
$$

K、V 同理。

如果错误地让每个 head 都输出完整的 4096 维，则仅 Q 的输出总宽度就变成：

$$
32\times4096=131072
$$

Q 投影参数量变成：

$$
32\times4096\times4096
=536{,}870{,}912
$$

约为标准设计的 32 倍；K、V 同样膨胀。拼接后 $W_O$ 还要执行：

$$
131072\rightarrow4096
$$

其参数和计算成本也约膨胀 32 倍。

### 5.2 Attention 计算量演算

标准设计中，单个 head 的 $QK^T$：

$$
[n,128]\times[128,n]
$$

复杂度约为：

$$
O(n^2\times128)
$$

32 个 head 合计：

$$
O(32\times n^2\times128)
=O(n^2\times4096)
$$

若每个 head 都是 4096 维，则变成：

$$
O(32\times n^2\times4096)
$$

同样约为标准设计的 32 倍。

所以 MHA 的设计重点是：**在总宽度和总体计算量可控的条件下，用多个低维子空间换取多种注意力模式，而不是简单把模型宽度扩大 h 倍。**

## 6. MHA、GQA、MQA 与共享 K/V

### 6.1 标准 MHA

标准 MHA 中，每个 query head 都有自己的 K/V head：

```text
Q1 → K1/V1
Q2 → K2/V2
...
Q32 → K32/V32
```

不同 head 的 K/V 通常不同，因为它们使用不同的 $W_K^{(i)}$、$W_V^{(i)}$。

### 6.2 GQA

Grouped-Query Attention（GQA）保留较多 query heads，但从结构上只设置较少的 KV heads。例如：

```text
32 Q heads
 8 KV heads

Q1~Q4   → KV1
Q5~Q8   → KV2
...
Q29~Q32 → KV8
```

可以从参数共享角度理解为：同组 Q heads 各有独立的 $W_Q$，但共同使用一套 $W_K/W_V$。实现时不是先生成 4 份相同 K/V 再保存，而是只计算并缓存 1 份独立 KV head；Attention 计算时通过分组或广播让多组 Q 读取它。

### 6.3 MQA

Multi-Query Attention（MQA）更极端：

```text
32 Q heads
 1 K head
 1 V head
```

所有 query heads 共享同一组 K/V。

### 6.4 相同 K/V 为什么仍能产生不同输出：完整演算

假设两个 query heads 共用：

$$
K=
\begin{bmatrix}
1&0\\
0&1
\end{bmatrix},qquad
V=
\begin{bmatrix}
10&0\\
0&20
\end{bmatrix}
$$

两个 Query 分别为：

$$
q_1=[1,0],qquad q_2=[0,1]
$$

Head 1：

$$
q_1K^T=[1,0]
$$

缩放后：

$$
\frac{q_1K^T}{\sqrt2}=[0.707,0]
$$

Softmax 近似：

$$
\alpha_1\approx[0.67,0.33]
$$

输出：

$$
o_1=0.67[10,0]+0.33[0,20]
=[6.7,6.6]
$$

Head 2：

$$
q_2K^T=[0,1]
$$

Softmax 后近似：

$$
\alpha_2\approx[0.33,0.67]
$$

输出：

$$
o_2=0.33[10,0]+0.67[0,20]
=[3.3,13.4]
$$

因此：

```text
相同 K、相同 V
q1 → [6.7,  6.6]
q2 → [3.3, 13.4]
```

共享 K/V 不等于输出相同；只要 Q 不同，$QK^T$、注意力权重和最终输出仍会不同。

### 6.5 表达能力与效率权衡

```text
MHA：Q=32，KV=32 → K/V 自由度最高，KV Cache 最大
GQA：Q=32，KV=8  → 质量与效率折中
MQA：Q=32，KV=1  → KV Cache 最小，K/V 自由度最低
```

GQA/MQA 对 KV Cache 的影响和显存演算见 [01.07 Causal Mask、自回归生成与 KV Cache](./07_Causal_Mask、自回归生成与_KV_Cache.md)。

## 7. 典型张量形状与实现

若：

```text
X: [B, S, H]
num_heads = N
head_dim  = D = H / N
```

标准 MHA 的实现可写成：

```python
q = linear_q(X).view(B, S, N, D).transpose(1, 2)  # [B, N, S, D]
k = linear_k(X).view(B, S, N, D).transpose(1, 2)
v = linear_v(X).view(B, S, N, D).transpose(1, 2)

scores = q @ k.transpose(-1, -2) / sqrt(D)         # [B, N, S, S]
weights = softmax(scores + mask, dim=-1)
head_out = weights @ v                              # [B, N, S, D]

out = head_out.transpose(1, 2).reshape(B, S, H)     # [B, S, H]
out = out_proj(out)
```

真实实现通常用一次大矩阵投影再 reshape，而不是用 Python 循环逐头执行；数学上仍可把大矩阵视为各 head 投影矩阵的拼接。

## 8. 常见误区

### 误区一：每个 Head 的语义职责是人工固定的

不同 head 能学习不同关系，但不能把“某 head 永远负责语法/情感”当作结构定义。

### 误区二：多头就是把原向量机械切片

shape 上可以理解为拆分，机制核心是各 head 的独立可学习投影。

### 误区三：32 个 Head 会把最终 hidden size 变成 `32 × 4096`

标准设计令 $d_{head}=d_{model}/h$，所以 concat 后仍为 $d_{model}$。

### 误区四：GQA 先生成 32 份 K/V，再把相同结果合并

GQA 的参数结构本来就只有较少 KV heads；缓存也只保存这些独立 K/V。

## 9. 本次讨论中的理解推进

1. 从“不同 head 分别负责语法、情感”等直觉，修正为“不同参数投影允许学习不同关系，但职责不是人工预设”；
2. 从“把 hidden vector 一刀切开”，推进到“每个 head 通过独立的 $W_Q/W_K/W_V$ 投影到低维子空间”；
3. 通过 $d_{model}=4096,h=32,d_{head}=128$ 的参数量和计算量演算，明确低维 head 是为了在总宽度可控时获得多种注意力模式；
4. 从“不同 head 的 K/V 应该不同”，区分标准 MHA 与 GQA/MQA：后两者直接减少独立 KV heads；
5. 通过共享 K/V、不同 Q 的数值演算，确认共享 K/V 仍能产生不同注意力权重和输出。

## 10. 参考资料

- [Attention Is All You Need](https://arxiv.org/abs/1706.03762)
- [GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints](https://arxiv.org/abs/2305.13245)
- [Fast Transformer Decoding: One Write-Head is All You Need](https://arxiv.org/abs/1911.02150)
