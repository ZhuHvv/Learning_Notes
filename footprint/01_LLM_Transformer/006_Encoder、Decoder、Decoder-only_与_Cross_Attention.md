# Encoder、Decoder、Decoder-only 与 Cross Attention

> 所属分类：LLM / Transformer  
> 修订版本：v12 学习顺序审查版
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Encoder 适合双向理解，Decoder 适合自回归生成，Decoder-only 是主流生成式大模型架构；Cross Attention 是 decoder 查询 encoder 输出的机制。

这里描述的是典型用途而不是硬性边界：Embedding 模型也可以由 decoder-only LLM 改造，具体表示方式见 [010：稠密向量、稀疏向量与多向量表示及检索](010_稠密向量、稀疏向量与多向量表示及检索.md)。


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
