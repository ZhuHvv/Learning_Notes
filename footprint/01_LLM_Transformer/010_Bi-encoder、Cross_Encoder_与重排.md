# Bi-encoder、Cross Encoder 与重排

> 所属分类：LLM / Transformer  
> 修订版本：v9 昨日今日增量版  
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

