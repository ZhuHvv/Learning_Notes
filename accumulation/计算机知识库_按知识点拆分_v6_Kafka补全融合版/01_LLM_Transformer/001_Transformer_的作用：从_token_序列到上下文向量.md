# Transformer 的作用：从 token 序列到上下文向量

> 所属分类：LLM / Transformer  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Transformer 的作用是把 token 序列变成带上下文语义的向量序列；训练和推理都使用同一套结构。它不是单独的“训练工具”，而是模型本身的计算骨架。


## 2. 原理性解释

- 输入 token id 经 embedding 变成矩阵 X。
- 每层 block 先通过 attention 做 token 间信息交互，再通过 FFN 做逐 token 非线性加工。
- 层与层串行堆叠，第 n 层输出是第 n+1 层输入。
- decoder-only 最后把隐藏向量映射到词表 logits。

### Transformer 到底“变换”了什么

Transformer 并不是把一句话整体当成一个黑盒字符串处理，而是把输入拆成 token 后，让每个 token 的向量在多层网络中不断吸收上下文信息。第 0 层的 token 向量主要表示“这个 token 自己是什么”；经过若干层 Attention 和 FFN 后，同一个 token 位置上的向量会逐渐包含“它在当前句子里是什么意思”。例如“苹果发布新品”和“我吃了苹果”里的“苹果”，初始 embedding 可以相同，但经过上下文交互后会变成不同的上下文向量。

可以把每一层看成一次“全班讨论 + 个人加工”：Attention 负责让每个 token 向其它 token 询问信息，FFN 负责对自己融合后的信息做非线性加工。层数越深，不代表简单地重复同一件事，而是让表示从局部词义逐步过渡到句法关系、语义关系、任务意图等更高层特征。

一个极简抽象：

```python
X = token_embedding(tokens) + position_embedding(tokens)
for block in transformer_blocks:
    X = X + block.self_attention(norm(X))   # 跨 token 交换信息
    X = X + block.ffn(norm(X))              # 每个 token 独立做特征变换
return X  # [seq_len, hidden_size]，每一行都是上下文化后的 token 表示
```

## 3. 机制流程

1. 文本分词。
2. 查 embedding。
3. 经过多层 attention + FFN。
4. 输出 logits 或语义向量。
5. 生成、分类或检索使用输出。

### 从输入到输出的逐层机制

更细地看，Transformer 的主流程可以拆成 6 步：

1. 文本被 tokenizer 切成 token id。
2. token id 查表得到 embedding，并加上位置编码。
3. 每层先通过自注意力计算 token 之间的依赖关系。
4. 再通过 FFN 对每个位置的表示做非线性投影。
5. 多层堆叠后，每个位置都得到上下文化表示。
6. 对于 decoder-only 模型，最后一个位置的 hidden state 会接 LM Head，预测下一个 token 的概率分布。

```python
def transformer_forward(token_ids):
    x = embed[token_ids] + pos_embed[:len(token_ids)]
    for layer in layers:
        attn_out = layer.attention(layer.norm1(x))
        x = x + attn_out
        ffn_out = layer.ffn(layer.norm2(x))
        x = x + ffn_out
    logits = x @ lm_head.T
    return logits
```

## 4. 类比理解

像多人会议纪要：每个词先带着自身含义入场，注意力听别人说什么，FFN 整理自己的理解。

## 5. 应用举例 / 代码或伪代码

```python
ids = tokenizer.encode(prompt)
for _ in range(max_new_tokens):
    x = embedding(ids)
    for block in blocks:
        x = block(x)
    next_id = sample(lm_head(x[-1]))
    ids.append(next_id)
```

## 6. 你在讨论中的理解推进

你从“Transformer 是否只是训练用”推进到：它是模型结构，训练时学习参数，推理时用参数逐步计算输出。

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

理解 **Transformer 的作用：从 token 序列到上下文向量** 时，不要只停留在“名词解释”，而要追踪张量和信息流：

1. **输入形态**：一段文本先变成 token id，再查 embedding table 得到向量。
2. **中间变换**：Transformer 层反复做注意力聚合、残差连接、归一化和 FFN 非线性变换。
3. **输出用途**：生成模型会把最后一层 hidden state 投影到词表 logits；Embedding/RAG 模型则会把向量用于相似度检索。
4. **调试方式**：看 shape 是否一致、mask 是否正确、logits 是否异常、相似度分布是否过于集中。

### 最小验证实验

```python
# 伪代码：用 shape 跟踪 Transformer 的作用：从 token 序列到上下文向量 是否真的理解到位
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

## 11. 针对 `Transformer 的作用：从 token 序列到上下文向量` 的专项排查

学习或实现 **Transformer 的作用：从 token 序列到上下文向量** 时，可以用下面的方式检查自己是否真正掌握：

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

当被问到 `Transformer 的作用：从 token 序列到上下文向量` 时，可以按“定义 → 数据流 → 为什么需要 → 工程影响”回答，避免只背名词。
