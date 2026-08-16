# 01.07 Causal Mask、自回归生成与 KV Cache

## 1. 核心结论

Causal Mask、Autoregressive Generation 和 KV Cache 分别回答三个问题：

- Causal Mask：当前位置在计算时能看哪些 token；
- 自回归生成：模型如何基于已有序列逐个预测新 token；
- KV Cache：逐 token 推理时如何避免重复计算历史 token 的 K/V。

最关键的一句话是：

> 过去不会因为未来而改变；未来通过 Attention 读取过去，并把截至当前位置的信息继续向右传递。

## 2. Causal Mask 为什么使历史表示保持不变

假设序列先后为：

```text
第一轮：我 喜欢 吃
第二轮：我 喜欢 吃 苹果
```

第一轮的 causal mask 为：

$$
\begin{bmatrix}
1&0&0\\
1&1&0\\
1&1&1
\end{bmatrix}
$$

第二轮为：

$$
\begin{bmatrix}
1&0&0&0\\
1&1&0&0\\
1&1&1&0\\
1&1&1&1
\end{bmatrix}
$$

第二个矩阵左上角的 $3\times3$ 子矩阵与第一轮完全相同。因此即使把整个新序列重新计算一遍：

```text
“我”     仍只能看“我”
“喜欢”   仍只能看“我、喜欢”
“吃”     仍只能看“我、喜欢、吃”
“苹果”   可以看“我、喜欢、吃、苹果”
```

对任意历史位置 $i\leq3$，它每一层能读取的输入都没有变化，所以：

$$
h_i^{(l),\,new}=h_i^{(l),\,old}
$$

进而由该层输入投影出的 $Q_i^{(l)}$、$K_i^{(l)}$、$V_i^{(l)}$ 也都不变。这是历史 K/V 可以缓存复用的数学基础。

新 token 到来后，不是让“吃”回头看到“苹果”，而是让“苹果”向左读取“吃”。“吃苹果”这个关系会编码进“苹果”位置的 hidden state，而不是回头刷新“吃”的 hidden state：

```text
h1 ≈ 截至“我”的信息
h2 ≈ 截至“我喜欢”的信息
h3 ≈ 截至“我喜欢吃”的信息
h4 ≈ 截至“我喜欢吃苹果”的信息
```

## 3. Prefill 与 Decode 必须分开理解

“Decoder 自注意力只使用最后一个 token 的 Q”不是始终成立，只适用于**启用 KV Cache 的增量 Decode 阶段**。

| 阶段 | 输入 | 使用的 Q | K/V 处理 | 目的 |
| --- | --- | --- | --- | --- |
| Prefill | 整个 prompt | prompt 所有位置的 Q | 计算并建立每层缓存 | 得到首个 next-token logits |
| Decode | 通常一个新 token | 仅当前新位置的 Q | 复用历史缓存，追加当前 K/V | 计算下一个 token |

### 3.1 Prefill

首次输入 prompt“我 喜欢 吃 苹果”时，没有现成缓存。每层会并行计算：

```text
Q1 K1 V1 ← 我
Q2 K2 V2 ← 喜欢
Q3 K3 V3 ← 吃
Q4 K4 V4 ← 苹果
```

在 causal mask 下：

```text
Q1 查询 K1
Q2 查询 K1 K2
Q3 查询 K1 K2 K3
Q4 查询 K1 K2 K3 K4
```

所以 prompt 中所有 Q 都会参与本轮计算。同时，每一层的全部 K/V 被保存到该层自己的 KV Cache。最终通常取最后位置 $h_4^{(L)}$ 经 LM Head 预测第 5 个 token。

### 3.2 Decode

假设新生成 token 为 $x_t$。第 $l$ 层只需要处理当前位置的输入 $h_t^{(l-1)}$：

$$
q_t^{(l)}=h_t^{(l-1)}W_Q^{(l)},\quad
k_t^{(l)}=h_t^{(l-1)}W_K^{(l)},\quad
v_t^{(l)}=h_t^{(l-1)}W_V^{(l)}
$$

把当前 K/V 追加到该层缓存：

$$
K_{cache}^{(l)}\leftarrow[K_{past}^{(l)},k_t^{(l)}],\qquad
V_{cache}^{(l)}\leftarrow[V_{past}^{(l)},v_t^{(l)}]
$$

然后仅用当前 query 计算当前位置的输出：

$$
h_t^{(l)}=\operatorname{Attention}
\left(q_t^{(l)},K_{cache}^{(l)},V_{cache}^{(l)}\right)
$$

当前 token 逐层读取各层的历史缓存，直到得到 $h_t^{(L)}$，再通过 LM Head 预测 $x_{t+1}$。

## 4. 为什么缓存 K/V，不缓存 Q

历史 Q、K、V 都不会因右侧追加未来 token 而改变，但它们的后续用途不同：

```text
历史 Q：当时用于计算自身位置的输出，任务已经完成
历史 K：未来新 token 的 Q 仍需与它匹配
历史 V：未来新 token 仍需从中读取信息
```

因此“KV Cache”而不是“QKV Cache”的根本原因不是历史 Q 会变化，而是历史 Q 不会再被使用。

例如“苹果”到来时：

$$
Q_{苹果}\rightarrow[K_{我},K_{喜欢},K_{吃},K_{苹果}]
\rightarrow\text{attention weights}
\rightarrow[V_{我},V_{喜欢},V_{吃},V_{苹果}]
$$

这一计算完全不需要过去的 $Q_{我}$、$Q_{喜欢}$、$Q_{吃}$。

## 5. 每一层都有独立的 KV Cache

K/V 不是只在模型入口计算一次。第 $l$ 层的 K/V 来自第 $l-1$ 层输出，因此每层数值不同：

```text
Layer 1 cache: K1¹ K2¹ ... / V1¹ V2¹ ...
Layer 2 cache: K1² K2² ... / V1² V2² ...
...
Layer L cache: K1ᴸ K2ᴸ ... / V1ᴸ V2ᴸ ...
```

每生成一个新 token，都要在每一层产生该 token 的新 Q/K/V，使用本层历史 K/V 计算本层输出，再把本层的新 K/V 追加进本层缓存。

## 6. 最小伪代码

```python
# Prefill：并行处理整个 prompt，并为每层建立 KV Cache
logits, kv_cache = model(prompt_ids, use_cache=True)
next_token = sample(logits[:, -1])

# Decode：每次只提交尚未处理的新 token
for _ in range(max_new_tokens - 1):
    logits, kv_cache = model(
        next_token,
        past_key_values=kv_cache,
        use_cache=True,
    )
    next_token = sample(logits[:, -1])
```

单层内部逻辑可抽象为：

```python
q_t = h_t @ Wq
k_t = h_t @ Wk
v_t = h_t @ Wv

K, V = cache.update(k_t, v_t, layer_idx)
h_t = attention(q_t, K, V)
```

## 7. 性能收益与边界

- 不使用缓存：每一步都重新计算整个历史序列的投影和中间表示；
- 使用缓存：每一步只为新 token 计算新的 Q/K/V，但当前 Q 仍需读取可用缓存中的 K/V；
- KV Cache 主要用于推理，不应用于常规训练，因为训练需要保留完整计算图并并行处理训练序列；
- 缓存按层存储，典型张量包含 batch、head、sequence length、head dimension；
- 动态缓存的显存占用随 batch size、层数、KV head 数、上下文长度和 head dimension 增长；
- 滑动窗口、KV 量化、offloading 等策略可以降低显存压力，但可能引入上下文截断、精度或传输开销方面的权衡；
- KV Cache 是等价计算的复用优化；在相同模型、位置编码、mask 和数值精度条件下，不应改变生成语义。

## 8. KV Cache 显存公式与数值演算

KV Cache 缓存的是每一层、每个历史 token、每个独立 KV head 的 K 和 V。忽略对齐、元数据、分页碎片和框架额外开销时，单个 batch 的简化公式为：

$$
\operatorname{KVBytes}
=B_{batch}\times L\times T\times2\times H_{kv}\times D_{head}\times B_{elem}
$$

其中：

```text
B_batch = batch size / 并发序列数
L       = Transformer 层数
T       = 当前缓存的序列长度
2       = K + V
H_kv    = KV head 数
D_head  = 每个 head 的维度
B_elem  = 每个元素占用字节数
```

### 8.1 标准 MHA + FP32

讨论中的例子：

```text
batch_size  = 1
layers      = 32
tokens      = 8000
query_heads = 32
kv_heads    = 32
hidden_size = 4096
head_dim    = 4096 / 32 = 128
FP32        = 4 bytes
```

传统 MHA 中：

$$
H_{kv}\times D_{head}=32\times128=4096
$$

所以：

$$
\begin{aligned}
\operatorname{KVBytes}
&=1\times32\times8000\times2\times32\times128\times4\\
&=32\times8000\times2\times4096\times4\\
&=8{,}388{,}608{,}000\text{ bytes}
\end{aligned}
$$

即：

```text
约 8.39 GB（十进制）
约 7.81 GiB（二进制）
```

如果 8000 个 token 都已经完成当前层计算，缓存长度就是 8000；`7999` 只对应“正在计算第 8000 个 token、尚未把当前 K/V 追加进缓存”的瞬间。

### 8.2 FP16 / BF16

每元素由 4 bytes 降为 2 bytes，结果减半：

$$
32\times8000\times2\times4096\times2
=4{,}194{,}304{,}000\text{ bytes}
$$

即：

```text
约 4.19 GB
约 3.91 GiB
```

这仍只是一个序列的 KV Cache，不包括模型参数、临时激活、采样状态和运行时碎片。

### 8.3 GQA / MQA 为什么能直接缩小缓存

KV Cache 的大小取决于 $H_{kv}$，而不是 query head 数 $H_q$。

若保持：

```text
query_heads = 32
head_dim    = 128
```

但使用 GQA：

```text
kv_heads = 8
```

则理论缓存比例为：

$$
\frac{8}{32}=\frac14
$$

上述 FP32 例子变为：

$$
8.388608\text{ GB}\times\frac14
=2.097152\text{ GB}
$$

若使用 MQA：

```text
kv_heads = 1
```

则相对于 32-KV-head MHA：

$$
\frac{1}{32}
$$

上述 FP32 例子理论上约为：

$$
8.388608\text{ GB}\div32
=0.262144\text{ GB}
$$

因果链为：

```text
多个 Query Heads 共用更少的 K/V 投影
            ↓
独立 KV heads 数量下降
            ↓
每个历史 token 需要缓存的 K/V 数量下降
            ↓
显存占用和 Decode 内存带宽压力下降
```

MHA、GQA、MQA 的结构与共享 K/V 演算见 [01.04 Multi-Head Attention 与表达能力](./04_Multi-Head_Attention_与表达能力.md)。

## 9. Prefill 与 Decode 的性能差异

假设：

```text
prompt = 4000 tokens
output = 500 tokens
hidden_size = 4096
```

### 9.1 Prefill 更偏 Compute-bound

Prefill 的输入为：

$$
H^{(0)}\in\mathbb{R}^{4000\times4096}
$$

线性投影包含：

$$
[4000,4096]\times[4096,4096]
$$

Attention 的 $QK^T$ 包含：

$$
[4000,d]\times[d,4000]
$$

虽然 token 4000 依赖前 3999 个 token，但全部 prompt 已知，可以一次构造完整 $QK^T$，再用 causal mask 屏蔽上三角：

```text
       K1  K2  K3  K4
Q1     ✓   ×   ×   ×
Q2     ✓   ✓   ×   ×
Q3     ✓   ✓   ✓   ×
Q4     ✓   ✓   ✓   ✓
```

因此依赖关系存在于矩阵中，不要求按 token 写串行循环。大批 token 复用同一套权重，形成较大的矩阵乘法，GPU 计算单元较容易被充分利用，所以 Prefill 通常更偏 compute-bound。

### 9.2 Decode 更偏 Memory-bandwidth-bound

Decode 每步通常只有一个新 token：

$$
[1,4096]\times[4096,4096]
$$

单步有效计算规模小，但仍需读取大量模型权重；Attention 还要逐层读取随上下文增长的 KV Cache：

```text
当前只计算 1 个新 token
        +
读取各层模型权重
        +
读取各层历史 K/V
```

因此瓶颈常从“算术单元算不完”转为“显存数据搬运不够快”，即更偏 memory-bandwidth-bound。KV Cache 减少了历史投影和中间层的重复计算，但没有消除当前 Q 读取历史 K/V 的成本。

## 10. 单次 KV Cache 与跨请求 Prefix Cache

### 10.1 区别

```text
KV Cache：
单次请求的自回归生成内部，复用已经处理的历史 K/V

Prefix Cache / Prompt Cache：
把已计算前缀对应的 KV blocks 跨请求保存，供后续请求命中复用
```

假设：

```text
请求 A：[System Prompt][10000-token 文档][问题 A]
请求 B：[System Prompt][10000-token 文档][问题 B]
```

B 可以复用共同的连续前缀：

```text
[System Prompt][10000-token 文档]
```

不要求整个 A 是整个 B 的前缀，只要求两个请求**从第一个 token 开始**存在完全相同的连续 token prefix。

### 10.2 为什么只能自然复用连续前缀

缓存请求：

```text
A B C D E F
```

新请求：

```text
A B X D E F
```

`A B` 的前缀相同，可以复用。第一次差异之后，即使 `D E F` 的 token id 再次相同，也不能直接复用旧 K/V。

原因是 hidden state 依赖左侧前缀：

$$
h_D^{old}=f(A,B,C,D)
$$

$$
h_D^{new}=f(A,B,X,D)
$$

通常：

$$
h_D^{old}\neq h_D^{new}
$$

所以：

$$
K_D^{old}\neq K_D^{new},qquad
V_D^{old}\neq V_D^{new}
$$

更极端地：

```text
旧请求：A B C D E F
新请求：X Y C D E F
```

虽然后缀 `C D E F` 的 token 完全相同，但它们的左侧 prefix 不同：

$$
h_C^{old}=f(A,B,C),qquad
h_C^{new}=f(X,Y,C)
$$

所以后缀对应的 K/V 通常全部不同，不能搬用旧缓存。工程实现通常按固定大小的 KV block 做 hash 和匹配；前序 block 的差异会使后继 block 失去连续前缀命中。

## 11. 常见误区

### 误区一：新 token 会更新历史 token 的语义

decoder-only 模型的 causal attention 不允许历史位置看到右侧未来位置。新关系被编码进新位置的表示，而不是反向刷新历史位置。

### 误区二：Decoder 永远只计算最后一个 Q

Prefill 会计算并使用 prompt 中所有位置的 Q；只有带缓存的增量 Decode 通常只需要新位置的 Q。

### 误区三：只要有 Causal Mask 就自动有 KV Cache

Causal Mask 是注意力可见性约束，KV Cache 是推理实现中的复用策略。可以有 causal attention 而关闭缓存，只是推理会重复计算历史部分。

### 误区四：KV Cache 缓存的是最终 hidden state

标准 KV Cache 缓存的是**每一层注意力模块的 K/V 张量**，不是只保存最后一层 hidden state，也不是保存一份跨层通用的 K/V。

### 误区五：两个请求只要有相同后缀，就能复用后缀 KV

相同 token 在不同左侧前缀下会得到不同 hidden state 和 K/V。Prefix Cache 能自然复用的是从序列开头连续命中的前缀，而不是任意相同子串。

### 误区六：KV Cache 让 Decode 不再随上下文长度增长

缓存避免了历史位置的重复投影与逐层重算，但当前 query 仍要读取历史 K/V；缓存显存和单步 Attention 的读取量仍随有效上下文增长。

## 12. 本次讨论中的理解推进

1. 从“新 token 到来后，前文 V 是否应随新上下文改变”，明确为历史位置受 causal mask 约束，Q/K/V 都不受未来 token 影响；
2. 从“模型怎么理解‘吃苹果’”，明确为该组合关系编码在较右位置“苹果”的 hidden state 中；
3. 从“前文 Q 为什么不需要变”，修正为“历史 Q 不变但后续不再使用，因此无需缓存”；
4. 从“Decoder 是否只用最后一个 Q”，进一步区分 Prefill 与启用 KV Cache 的 Decode；
5. 通过 32 层、8000 token、4096 hidden size 的逐项乘法，明确传统 MHA 下 FP32/FP16 KV Cache 的实际数量级；
6. 从“GQA 让多组头的 $W_K/W_V$ 相同”，推进到“模型只产生并缓存更少的独立 KV heads”，并由公式得到 $1/4$、$1/32$ 的理论缓存比例；
7. 区分单次请求 KV Cache 与跨请求 Prefix Cache，并用“前缀变化导致后续 hidden state 全部变化”解释只能连续命中前缀；
8. 最终形成完整链路：Causal Mask 保证历史表示不变，KV Cache 复用每层历史 K/V，当前 Q 逐层查询缓存并产生下一个 token 所需的最新位置表示。

## 13. 参考资料

- [Attention Is All You Need](https://arxiv.org/abs/1706.03762)
- [Hugging Face Transformers：How caching works](https://huggingface.co/docs/transformers/main/cache_explanation)
- [Hugging Face Transformers：Cache strategies](https://huggingface.co/docs/transformers/kv_cache)
- [vLLM：Automatic Prefix Caching](https://docs.vllm.ai/en/latest/design/prefix_caching/)
- [GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints](https://arxiv.org/abs/2305.13245)
- [Fast Transformer Decoding: One Write-Head is All You Need](https://arxiv.org/abs/1911.02150)
