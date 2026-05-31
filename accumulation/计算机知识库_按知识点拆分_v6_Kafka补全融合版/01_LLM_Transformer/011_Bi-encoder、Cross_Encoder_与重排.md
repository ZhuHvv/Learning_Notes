# Bi-encoder、Cross Encoder 与重排

> 所属分类：LLM / Transformer  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Bi-encoder 快速召回，Cross Encoder 精细重排。前者分别编码 query/doc，后者把 query-doc pair 一起输入判断相关性。


## 2. 原理性解释

- Bi-encoder 可提前计算文档向量。
- Cross Encoder 成本高但精度好。
- 典型流程是先召回几十条，再重排取少量。
- 重排后还要压缩上下文。

### Bi-encoder 快，Cross-Encoder 准

Bi-encoder 把 query 和 document 分别编码成向量，提前离线存储文档向量，查询时只需要向量相似度，因此适合大规模召回。Cross-Encoder 把 query 和 document 拼在一起输入模型，让二者在 Transformer 内部充分交互，因此排序更准但成本高。

```text
Bi-encoder: encode(q) · encode(doc)
Cross-Encoder: model([q, doc]) → relevance_score
```

在 RAG 中常见组合是：Bi-encoder 先从百万文档中召回 top100，Cross-Encoder 再重排 top100 得到 top5。这是“召回率”和“精确率”的折中。

## 3. 机制流程

1. 向量召回候选。
2. 对每个 query-doc pair 打分。
3. 按分数排序。
4. 取前若干条生成。

### 两阶段检索流程

```python
candidates = vector_db.search(embed(query), top_k=100)
reranked = []
for doc in candidates:
    score = cross_encoder_score(query, doc.text)
    reranked.append((score, doc))
final_docs = sorted(reranked, reverse=True)[:5]
```

排查时如果“找不到相关文档”，先看召回；如果“召回有相关文档但最终引用错误”，重点看重排、chunk 拼接和 prompt 证据约束。

## 4. 类比理解

先用地图粗筛餐厅，再逐家看菜单评价。

## 5. 应用举例 / 代码或伪代码

```python
candidates = vector_db.search(embed(query), top_k=50)
scored = [(reranker.score(query, c.text), c) for c in candidates]
top_docs = [c for _, c in sorted(scored, reverse=True)[:8]]
```

## 6. 你在讨论中的理解推进

你从“向量库搜一下”推进到“召回只是第一步，重排决定上下文质量”。

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

理解 **Bi-encoder、Cross Encoder 与重排** 时，不要只停留在“名词解释”，而要追踪张量和信息流：

1. **输入形态**：一段文本先变成 token id，再查 embedding table 得到向量。
2. **中间变换**：Transformer 层反复做注意力聚合、残差连接、归一化和 FFN 非线性变换。
3. **输出用途**：生成模型会把最后一层 hidden state 投影到词表 logits；Embedding/RAG 模型则会把向量用于相似度检索。
4. **调试方式**：看 shape 是否一致、mask 是否正确、logits 是否异常、相似度分布是否过于集中。

### 最小验证实验

```python
# 伪代码：用 shape 跟踪 Bi-encoder、Cross Encoder 与重排 是否真的理解到位
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

## 11. 针对 `Bi-encoder、Cross Encoder 与重排` 的专项排查

学习或实现 **Bi-encoder、Cross Encoder 与重排** 时，可以用下面的方式检查自己是否真正掌握：

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

当被问到 `Bi-encoder、Cross Encoder 与重排` 时，可以按“定义 → 数据流 → 为什么需要 → 工程影响”回答，避免只背名词。
