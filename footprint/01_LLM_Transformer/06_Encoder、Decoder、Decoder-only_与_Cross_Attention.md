# 01.06 Encoder、Decoder、Decoder-only 与 Cross Attention

## 1. 核心结论

Encoder、Decoder 的根本差异不是“一个输出矩阵、一个输出向量”，而是**注意力可见性、训练目标和使用方式**不同：

- Encoder 的 self-attention 通常是双向的，每个位置可以读取完整输入，适合构造上下文化表示；
- Decoder 的 self-attention 使用 causal mask，每个位置只能读取自己及左侧前缀，适合 next-token prediction；
- Decoder-only 把提示词和已生成内容统一视为一个因果序列，持续预测下一个 token；
- Encoder-Decoder 架构中，Decoder 除了 masked self-attention，还通过 Cross Attention 读取 Encoder 输出；
- Decoder 在训练或 Prefill 阶段同样输出 $[n,d]$ 矩阵；只有启用 KV Cache 的增量 Decode 阶段，才通常只继续计算新位置的 $[1,d]$ 表示。

典型用途不是硬性边界：decoder-only 模型也可以改造成 Embedding 模型，具体表示方式见 [01.11 稠密向量、稀疏向量与多向量表示及检索](./11_稠密向量、稀疏向量与多向量表示及检索.md)。

## 2. 三类架构的数据流

```
Encoder-only
文本 → 双向 Self-Attention → 上下文化表示 → 分类 / 匹配 / Embedding

Decoder-only
Prompt → Causal Self-Attention → 最后位置 hidden state
       → LM Head → next-token logits → 采样 → 追加 token

Encoder-Decoder
源序列 → Encoder → Encoder Memory ─────────────┐
                                               ↓ K/V
目标前缀 → Decoder Masked Self-Attention → Cross Attention → 生成目标 token
                                               ↑ Q
```

## 3. Encoder：双向理解与矩阵输出

假设输入有 3 个 token，Encoder self-attention 的可见性为：

```
           K1   K2   K3
Q1         ✓    ✓    ✓
Q2         ✓    ✓    ✓
Q3         ✓    ✓    ✓
```

因此每个位置的 hidden state 都可能依赖完整输入：

$$
h_i^{(l)}=f_l(x_1,x_2,x_3),\qquad i\in\{1,2,3\}
$$

若序列长度为 $n$、hidden size 为 $d$，Encoder 输出通常为：

$$
H_E\in\mathbb{R}^{n\times d}
$$

后续任务可以：

- 取 `[CLS]` 或池化结果做分类；
- 对 token 表示做序列标注；
- 对全序列做 pooling 得到文本向量；
- 把整个 $H\_E$ 作为 Encoder-Decoder 中供 Decoder 查询的 memory。

### 3.1 Encoder Self-Attention：完整数值手算

下面保留讨论中的极小 Transformer 演算。设：

```
d_model = 2
num_heads = 1
Encoder layers = 1
```

为了把矩阵流动看清楚，令三组投影参数都是单位矩阵：

$$
W_Q=W_K=W_V=
\begin{bmatrix}
1&0\\
0&1
\end{bmatrix}
=I
$$

真实模型中的参数由训练得到，并不会都是单位矩阵。这里如此设定只为便于手算。

假设“我、喜欢、苹果”经过 Embedding 与位置编码后分别为：

$$
x_1=[1,0],\qquad x_2=[0,1],\qquad x_3=[1,1]
$$

因此 Encoder 输入为：

$$
X=
\begin{bmatrix}
1&0\\
0&1\\
1&1
\end{bmatrix}
\in\mathbb{R}^{3\times2}
$$

#### 第一步：计算 Q、K、V

$$
Q=XW_Q,\qquad K=XW_K,\qquad V=XW_V
$$

因为 $W\_Q=W\_K=W\_V=I$，所以：

$$
Q=K=V=X=
\begin{bmatrix}
1&0\\
0&1\\
1&1
\end{bmatrix}
$$

#### 第二步：计算所有 token 两两之间的点积分数

$$
K^T=
\begin{bmatrix}
1&0&1\\
0&1&1
\end{bmatrix}
$$

$$
QK^T=
\begin{bmatrix}
1&0&1\\
0&1&1\\
1&1&2
\end{bmatrix}
$$

例如：

$$
Q_{\text{苹果}}\cdot K_{\text{苹果}}
=[1,1]\cdot[1,1]
=1\times1+1\times1=2
$$

而：

$$
Q_{\text{我}}\cdot K_{\text{喜欢}}
=[1,0]\cdot[0,1]=0
$$

这个 $3\\times3$ 矩阵的行对应 Query 位置，列对应 Key 位置：

```
             K我   K喜欢   K苹果
Q我           1      0       1
Q喜欢         0      1       1
Q苹果         1      1       2
```

#### 第三步：按 $\\sqrt{d\_k}$ 缩放

这里 $d\_k=2$，所以：

$$
\sqrt{d_k}=\sqrt2\approx1.414
$$

$$
S=\frac{QK^T}{\sqrt2}
\approx
\begin{bmatrix}
0.707&0&0.707\\
0&0.707&0.707\\
0.707&0.707&1.414
\end{bmatrix}
$$

#### 第四步：逐行 Softmax

第一行：

$$
\operatorname{softmax}([0.707,0,0.707])
\approx[0.401,0.198,0.401]
$$

第二行：

$$
\operatorname{softmax}([0,0.707,0.707])
\approx[0.198,0.401,0.401]
$$

第三行：

$$
\operatorname{softmax}([0.707,0.707,1.414])
\approx[0.248,0.248,0.503]
$$

于是注意力权重矩阵为：

$$
A_E\approx
\begin{bmatrix}
0.401&0.198&0.401\\
0.198&0.401&0.401\\
0.248&0.248&0.503
\end{bmatrix}
$$

每行分别描述一个 Query 如何在三个 Value 位置之间分配读取权重；每行之和约为 1，显示出的微小误差来自小数截断。

#### 第五步：用权重对 V 加权求和

$$
O_E=A_EV
$$

第一行：

$$
0.401[1,0]+0.198[0,1]+0.401[1,1]
=[0.802,0.599]
$$

第二行：

$$
0.198[1,0]+0.401[0,1]+0.401[1,1]
=[0.599,0.802]
$$

第三行：

$$
0.248[1,0]+0.248[0,1]+0.503[1,1]
\approx[0.752,0.752]
$$

所以 Encoder Self-Attention 输出约为：

$$
O_E\approx
\begin{bmatrix}
0.802&0.599\\
0.599&0.802\\
0.752&0.752
\end{bmatrix}
\in\mathbb{R}^{3\times2}
$$

```
我      → [0.802, 0.599]
喜欢    → [0.599, 0.802]
苹果    → [0.752, 0.752]
```

Encoder 没有把三个 token 压成一个向量；每个 token 仍对应一行，但每一行现在都吸收了其他位置的信息。

需要严格区分：这里手算到的是 **Self-Attention 子层的输出**。真实 Encoder Block 后面还有输出投影、残差连接、LayerNorm 和逐位置 FFN，例如：

$$
\operatorname{FFN}(x)=W_2\sigma(W_1x+b_1)+b_2
$$

这些结构不会改变“序列长度为 3，因此仍有 3 行 hidden state”的结论，但会改变每行的具体数值。

## 4. Decoder：因果可见性与自回归生成

Decoder causal self-attention 的可见性为：

```
           K1   K2   K3
Q1         ✓    ×    ×
Q2         ✓    ✓    ×
Q3         ✓    ✓    ✓
```

因此：

$$
h_1=f(x_1)
$$

$$
h_2=f(x_1,x_2)
$$

$$
h_3=f(x_1,x_2,x_3)
$$

过去位置不依赖未来位置，但未来位置会依赖过去位置。于是右侧新增 token 不会改变旧位置已经得到的 hidden state，这也是 KV Cache 可复用的基础。

### 4.1 训练阶段

训练时目标序列已经完整存在，可以把右移后的目标前缀一次输入模型，并对所有位置并行计算 loss。Causal mask 保证每个位置不能利用未来答案：

```
输入：<BOS> 我 喜欢 苹果
目标： 我   喜欢 苹果 <EOS>

位置 1 根据 <BOS> 预测“我”
位置 2 根据 <BOS>、我 预测“喜欢”
位置 3 根据 <BOS>、我、喜欢 预测“苹果”
```

此时 Decoder 仍输出：

$$
H_D\in\mathbb{R}^{n\times d}
$$

“因果依赖”由注意力矩阵中的 mask 表达，不等于程序必须用 for-loop 串行计算已知的训练序列。

### 4.2 Prefill 阶段

推理开始时，完整 prompt 已知，因此同样可以并行处理所有 prompt token：

```
[n, hidden_size]
      ↓
全部 Decoder Layers
      ↓
[n, hidden_size]
      ↓
建立各层 KV Cache
      ↓
取最后位置预测第一个输出 token
```

### 4.3 增量 Decode 阶段

输出 token 尚未出现，只能先采样当前 token，再把它作为下一步输入。启用 KV Cache 后，历史位置不再重复计算，每层通常只继续计算新位置：

$$
[1,d]
$$

这才是“Decoder 从矩阵变成一个向量”这一感觉的来源。准确对比为：

| 场景 | 典型计算 shape |
| --- | --- |
| Encoder 全序列 | $[n,d]$ |
| Decoder 训练 | $[n,d]$ |
| Decoder Prefill | $[n,d]$ |
| Decoder 增量 Decode + KV Cache | 当前新位置为 $[1,d]$ |

### 4.4 Decoder Masked Self-Attention：完整数值手算

继续使用 Encoder 演算中的同一组输入和单位投影矩阵：

$$
Q=K=V=X=
\begin{bmatrix}
1&0\\
0&1\\
1&1
\end{bmatrix}
$$

在应用 mask 以前，缩放分数与 Encoder 完全相同：

$$
S=\frac{QK^T}{\sqrt2}
\approx
\begin{bmatrix}
0.707&0&0.707\\
0&0.707&0.707\\
0.707&0.707&1.414
\end{bmatrix}
$$

#### 第一步：加入 Causal Mask

$$
M=
\begin{bmatrix}
0&-\infty&-\infty\\
0&0&-\infty\\
0&0&0
\end{bmatrix}
$$

$$
S+M=
\begin{bmatrix}
0.707&-\infty&-\infty\\
0&0.707&-\infty\\
0.707&0.707&1.414
\end{bmatrix}
$$

使用 $-\\infty$ 是因为 $e^{-\\infty}=0$，所以被遮蔽位置经过 Softmax 后权重为 0。

#### 第二步：逐行 Softmax

第一行：

$$
\operatorname{softmax}([0.707,-\infty,-\infty])=[1,0,0]
$$

第二行：

$$
\operatorname{softmax}([0,0.707,-\infty])
\approx[0.330,0.670,0]
$$

第三行：

$$
\operatorname{softmax}([0.707,0.707,1.414])
\approx[0.248,0.248,0.503]
$$

因此：

$$
A_D\approx
\begin{bmatrix}
1&0&0\\
0.330&0.670&0\\
0.248&0.248&0.503
\end{bmatrix}
$$

这三行分别表示：

```
“我”   只能看“我”
“喜欢” 33.0% 看“我”，67.0% 看“喜欢”，不能看“苹果”
“苹果” 可以看“我、喜欢、苹果”
```

#### 第三步：用权重对 V 加权求和

$$
O_D=A_DV
$$

逐行计算：

$$
o_{\text{我}}=1[1,0]+0[0,1]+0[1,1]=[1,0]
$$

$$
o_{\text{喜欢}}
=0.330[1,0]+0.670[0,1]+0[1,1]
=[0.330,0.670]
$$

$$
o_{\text{苹果}}
=0.248[1,0]+0.248[0,1]+0.503[1,1]
\approx[0.752,0.752]
$$

所以 Decoder Masked Self-Attention 输出约为：

$$
O_D\approx
\begin{bmatrix}
1&0\\
0.330&0.670\\
0.752&0.752
\end{bmatrix}
$$

对照 Encoder 的 $O\_E$ 可以看到，shape 同为 $[3,2]$；差异来自 Decoder 对未来位置施加了 mask。

如果当前真实前缀只有“我、喜欢”，则只取前两行：

$$
H=
\begin{bmatrix}
1&0\\
0.330&0.670
\end{bmatrix}
$$

其中：

$$
h_{\text{喜欢}}=[0.330,0.670]
$$

代表基于完整前缀“我、喜欢”的当前位置表示，因此用它预测下一个 token。下一节的 LM Head 演算正是从这个数值继续。

同样要注意：这里为了保持原讨论可手算，省略了输出投影、残差、LayerNorm 和 FFN，并把该 Attention 输出直接当作送入 LM Head 的最终 hidden state。真实模型会经过完整 Block 和后续层后，才把最后一层 hidden state 送入 LM Head。

## 5. Q、Attention 输出、Hidden State 与 Token 的区别

讨论中最关键的误区是把“最后一个 token 的 Q”当成“用于预测下一个 token 的最终向量”。二者不是一回事。

Q 只是某一层 Attention 内部的临时查询变量。第 $l$ 层、当前位置 $t$：

$$
q_t^{(l)}=h_t^{(l-1)}W_Q^{(l)},\quad
k_t^{(l)}=h_t^{(l-1)}W_K^{(l)},\quad
v_t^{(l)}=h_t^{(l-1)}W_V^{(l)}
$$

然后：

$$
a_t^{(l)}=\operatorname{Attention}
\left(q_t^{(l)},K^{(l)},V^{(l)}\right)
$$

经过输出投影、残差、归一化和 FFN 后得到新的：

$$
h_t^{(l)}
$$

它再进入下一层，并重新产生该层自己的 Q/K/V：

```
Layer 1：h⁰ → Q¹/K¹/V¹ → Attention → FFN → h¹
Layer 2：h¹ → Q²/K²/V² → Attention → FFN → h²
...
Layer L：hᴸ⁻¹ → Qᴸ/Kᴸ/Vᴸ → Attention → FFN → hᴸ
                                                    ↓
                                                  LM Head
                                                    ↓
                                               Vocabulary logits
```

因此：

> Q 负责在某一层中查询 K、聚合 V；最后一层 hidden state 才通过 LM Head 映射到词表。

## 6. 从最终 Hidden State 到 Token：完整演算

用一个最小词表演示 Decoder 最后一步。沿用第 4.4 节手算得到的最后位置表示，并在这个极小模型中把它直接作为最终 hidden state：

$$
h=[0.330,\;0.670]
$$

词表为：

```
0 → 我
1 → 喜欢
2 → 苹果
3 → 。
```

LM Head 权重为：

$$
W_{LM}=
\begin{bmatrix}
1&0&0&-1\\
0&1&2&0
\end{bmatrix}
\in\mathbb{R}^{2\times4}
$$

计算：

$$
logits=hW_{LM}
$$

逐列展开：

token“我”：

$$
0.330\times1+0.670\times0=0.330
$$

token“喜欢”：

$$
0.330\times0+0.670\times1=0.670
$$

token“苹果”：

$$
0.330\times0+0.670\times2=1.340
$$

token“。”：

$$
0.330\times(-1)+0.670\times0=-0.330
$$

所以：

$$
logits=[0.330,\;0.670,\;1.340,\;-0.330]
$$

Softmax 概率约为：

```
我       17.7%
喜欢     24.8%
苹果     48.4%  ← 最大
。        9.1%
```

若采用 greedy decoding：

$$
token\_id=\arg\max(logits)=2
$$

Tokenizer 再把 `2` 解码为“苹果”。完整链路是：

```
最终 hidden state
      ↓ LM Head
Vocabulary logits
      ↓ Softmax / sampling / argmax
token_id
      ↓ Tokenizer decode
文本 token
```

## 7. 新 Token 必须经过全部 Decoder Layers

有 32 层 Decoder 时，新 token 不能只在第 32 层计算。它必须从 embedding 开始依次经过全部 32 层：

```
新 token embedding
      ↓
Layer 1：当前 Q¹ 查询 Layer 1 历史 KV Cache
      ↓ h¹
Layer 2：当前 Q² 查询 Layer 2 历史 KV Cache
      ↓ h²
...
      ↓
Layer 32：当前 Q³² 查询 Layer 32 历史 KV Cache
      ↓ h³²
LM Head → logits → next token
```

KV Cache 省掉的是**历史 token 在各层的重复计算**，不是省掉新 token 必须经过的层。每层的 K/V 由该层输入产生，所以每层都有独立缓存。详见 [01.07 Causal Mask、自回归生成与 KV Cache](./07_Causal_Mask、自回归生成与_KV_Cache.md)。

## 8. Encoder-Decoder 与 Cross Attention

原始 Transformer 是 Encoder-Decoder 架构：

```
源序列
  ↓
Encoder
  ↓
H_E（源序列 memory）
  │
  └──────────── K/V ───────────┐
                               ↓
目标前缀 → Decoder masked self-attention
                               ↓ Q
                         Cross Attention
                               ↓
                            目标输出
```

设 Encoder 输出为：

$$
H_E\in\mathbb{R}^{n_s\times d}
$$

Decoder 当前表示为：

$$
H_D\in\mathbb{R}^{n_t\times d}
$$

Cross Attention 中：

$$
Q=H_DW_Q
$$

$$
K=H_EW_K,\qquad V=H_EW_V
$$

来源不同是关键：

```
Q：Decoder 当前生成状态
K/V：Encoder 对源序列的上下文化表示
```

于是每个 Decoder 位置可以询问：“为了生成当前 token，源序列的哪些位置最有用？”

原始 Transformer Decoder 的典型子层包括：

1. Masked Self-Attention；
2. Encoder-Decoder Cross Attention；
3. FFN。

GPT 类 decoder-only LLM 没有单独 Encoder，也没有这层 Encoder-Decoder Cross Attention，主要堆叠 causal self-attention 与 FFN。某些多模态或检索增强架构仍可能引入 cross-attention，不能把“decoder-only 永远没有任何外部注意力”当作普遍定律。

## 9. 常见误区

### 误区一：Encoder 输出矩阵，Decoder 输出向量

Decoder 在训练和 Prefill 中同样输出序列矩阵。只有增量 Decode 时通常只继续计算新位置。

### 误区二：最后一个 Q 直接预测 token

Q 只在某层 Attention 内部使用；最终 token 来自最后一层 hidden state 经 LM Head 得到的词表 logits。

### 误区三：一个 Q 会贯穿全部 Decoder 层

每层都根据新的层输入重新投影本层 Q/K/V。

### 误区四：有 KV Cache 后，新 token 可以跳过前面层

新 token 仍必须经过全部层；缓存只复用历史位置的 K/V。

### 误区五：Causal Mask 使整个 Decoder 只能串行计算

已知的训练序列或 prompt 可以用一个大矩阵并行计算；真正串行的是尚未出现的自回归输出 token。

## 10. 本次讨论中的理解推进

1. 从“Encoder 输出矩阵、Decoder 输出向量”，修正为按训练、Prefill、增量 Decode 区分 shape；
2. 从“最后一个 token 的 Q 用来预测 token”，修正为“Q 是层内变量，最终 hidden state 经 LM Head 预测 token”；
3. 通过最小词表和 $W\_{LM}$ 的逐列乘法，补全 hidden state → logits → 概率 → token\_id → 文本的演算链；
4. 明确新 token 必须经过全部 Decoder 层，并在每层生成新的 Q/K/V、查询该层缓存；
5. 最终区分 Encoder 双向 Self-Attention、Decoder Causal Self-Attention，以及 Q 来自 Decoder、K/V 来自 Encoder 的 Cross Attention。

## 11. 参考资料

- [Attention Is All You Need](https://arxiv.org/abs/1706.03762)
- [Hugging Face Transformers：Causal language modeling](https://huggingface.co/docs/transformers/tasks/language_modeling)
- [Hugging Face Transformers：Cache strategies](https://huggingface.co/docs/transformers/kv_cache)
