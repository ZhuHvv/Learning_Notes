# 02.21 RAG Multi-Query Expansion：多查询扩展

## 1. 总体性概念

Multi-Query Expansion 使用模型把一个用户问题生成多个语义相关但关注点不同的查询，然后分别检索、合并和重排结果。

```text
原问题：Kafka 为什么只能提高吞吐，不能直接提高消费者业务处理能力？

Query 1：Kafka 削峰和消费者处理能力之间是什么关系？
Query 2：增加 Kafka partition 是否一定提升业务消费速度？
Query 3：consumer lag 由哪些下游瓶颈决定？
```

它的目标是提高 Recall：避免原始 query 的一种措辞恰好没有命中文档。

## 2. 原理性解释

### 2.1 单一查询只覆盖语义空间中的一个投影

一个复杂问题通常包含多个方面：概念定义、机制原因、边界条件和对比关系。Embedding 或 BM25 对单个 query 的表示可能偏向其中一部分。

Multi-Query 通过生成多个视角，让检索器在语义空间和词项空间中形成多个入口：

```text
同义改写：消费者组如何分配分区？
术语扩展：group coordinator、rebalance、partition assignment
机制视角：consumer 加入/离开时如何重新分配？
边界视角：consumer 数量超过 partition 数量会怎样？
```

### 2.2 多查询的价值在“差异性”，不在数量本身

如果生成的五个 query 只是轻微替换同义词，它们会返回高度重复的结果，却增加五倍成本。高质量扩展应覆盖不同但仍属于原问题的检索面。

可用结构化角色约束：

```text
1. 术语精确查询
2. 机制解释查询
3. 边界条件查询
4. 对比查询
```

### 2.3 检索结果必须融合、去重和重排

每个查询返回一份 topK，不能直接拼接后截断，否则先执行的查询会占优势。常见流程：

1. 为每个 query 独立检索；
2. 使用 RRF 按排名融合；
3. 按 chunk id 或父文档去重；
4. 用原始用户问题做 cross-encoder rerank。

最后一步必须使用原始问题，因为多个扩展 query 只是召回工具，最终相关性仍应以用户真实意图为准。

### 2.4 多查询也可能引入噪声

扩展 query 可能把一个窄问题扩大成泛主题。例如用户只问 Kafka 的 ISR，扩展模型却生成“Kafka 高可用架构”，召回大量不相关文档。工程上应限制每个 query 的意图，并设置最大查询数、并发限制和候选上限。


### 2.5 怎样保证扩展查询真的不同

可以从语义角色和向量相似度两层控制差异：

1. 提示模型按“术语、机制、边界、对比”生成，而不是自由给出四个同义句；
2. 计算候选 queries 两两相似度，若高于阈值则删除或重新生成；
3. 检查每条 query 的关键词集合和命中文档集合，避免只在表面上不同。

```python
def select_diverse_queries(candidates, encoder, threshold=0.92):
    selected = []
    vectors = []
    for q in candidates:
        v = encoder(q)
        if all(cosine(v, old) < threshold for old in vectors):
            selected.append(q)
            vectors.append(v)
    return selected
```

Query 的文本差异并不等于检索差异。如果四条 query 最终返回几乎相同的 top20，它们没有提供增量召回价值。

### 2.6 多查询与问题分解的关系

多查询可以是同一问题的多种检索表达，也可以包含子问题，但不能把子问题答案简单拼接。对于真正的复合问题，应先构建依赖图：

```text
主问题
 ├─ 子问题 A：概念定义
 ├─ 子问题 B：机制原因（依赖 A）
 └─ 子问题 C：边界情况
```

每个子问题独立检索和生成中间证据，最后再 synthesis。否则不同 query 返回的片段可能互相矛盾或缺少共同前提。

## 3. 机制流程

```text
原始问题
  ↓ 生成 N 个不同检索视角
  ↓ 并行执行 dense/sparse retrieval
  ↓ 收集每路 topK
  ↓ RRF / 加权融合
  ↓ chunk 与父文档去重
  ↓ 以原始问题 rerank
  ↓ 选择最终上下文
```

### 3.1 异步并行伪代码

```python
import asyncio

async def retrieve_one(query):
    dense, sparse = await asyncio.gather(
        dense_search(query, top_k=30),
        bm25_search(query, top_k=30),
    )
    return rrf_merge([dense, sparse])

async def multi_query_retrieve(original_query, queries):
    lists = await asyncio.gather(*(retrieve_one(q) for q in queries))
    merged = rrf_merge(lists)
    deduped = deduplicate_by_chunk_and_parent(merged)
    return cross_encoder_rerank(original_query, deduped)[:8]
```

## 4. 类比理解

像你请几位研究员从不同角度帮你找资料：一位查精确术语，一位查原理，一位查反例。最后不是把所有资料原样堆给你，而是合并去重，再围绕你的原问题挑出最有用的部分。

## 5. 应用举例 / 代码或伪代码

### 5.1 生成结构化查询组

```python
from pydantic import BaseModel

class QuerySet(BaseModel):
    lexical: str
    semantic: str
    mechanism: str
    boundary: str

query_set = llm.with_structured_output(QuerySet).invoke({
    "question": user_question,
    "instruction": "四个查询必须保持原意，但检索角度不同。",
})
queries = [query_set.lexical, query_set.semantic,
           query_set.mechanism, query_set.boundary]
```

### 5.2 什么时候使用

适合：

- 问题包含多个子意图；
- 语料表达多样；
- 单 query 的 Recall@K 不稳定；
- 需要跨中文/英文术语检索。

不适合：

- 查询已经是精确 ID、函数名或错误码；
- 延迟预算极低；
- 语料很小，单次检索已能覆盖；
- 扩展模型容易偏离专业边界。

### 5.3 成本控制

```python
MAX_QUERIES = 4
MAX_HITS_PER_QUERY = 20
MAX_MERGED_CANDIDATES = 80

queries = distinct_queries(queries)[:MAX_QUERIES]
hits = parallel_retrieve(queries, top_k=MAX_HITS_PER_QUERY)
candidates = rrf_merge(hits)[:MAX_MERGED_CANDIDATES]
```

还可以先计算 query 间的 embedding 相似度，删除几乎重复的扩展。


### 5.4 运行时可观测性

每条扩展 query 应记录：生成角色、检索耗时、候选数量、独有正确命中、与其它 query 的结果重叠率。一个实用指标是：

```text
Unique Contribution(query_i)
= query_i 命中且其它 query 未命中的相关文档数量
```

长期贡献接近 0 的 query 角色可以删除。这样 Multi-Query 从“感觉上多搜几次”变成可持续优化的召回策略。

## 6. 你在讨论中的理解推进

- 起点：你把多查询扩展理解为“把一个问题换几种说法”。
- 推进：你进一步认识到有效扩展应提供不同检索视角，而不是机械同义改写。
- 区分：Query Rewrite 重点是生成一个更标准的 query；Multi-Query 重点是增加召回覆盖；HyDE 则先生成假设文档再做向量检索。
- 工程化理解：多查询只负责召回，最后必须用原始用户问题统一重排和回答。

## 7. 常见误区与排查思路

- **误区：查询越多召回越好。** 查询数量增加也会增加噪声和重复。
- **误区：把多个结果列表直接拼接。** 应进行公平融合和去重。
- **误区：最终 rerank 使用扩展 query。** 最终排序应回到原始用户意图。
- **排查：** 统计扩展 query 的差异度、每路新增正确文档数、重复率、整体 Recall@K 与延迟。

## 8. 关联知识点

- `019_RAG_Query_Rewrite_查询改写.md`
- `020_RAG_HyDE_假设文档嵌入.md`
- `022_Query_Rewrite、HyDE_与_Multi-Query_对比.md`
- [知识图谱、HyDE、RRF 与检索增强](../01_LLM_Transformer/13_知识图谱、HyDE、RRF_与检索增强.md)
- [Task 聚合、取消、超时与 asyncio.wait](../03_Python/8_Task_聚合、取消、超时与_asyncio.wait.md)

## 9. 复习检查问题

1. Multi-Query 为什么能提高召回率？
2. 多个 query 应该追求怎样的差异性？
3. 为什么最终 rerank 要使用原始 query？
4. 如何控制多查询带来的延迟和噪声？
5. Query Rewrite、Multi-Query 与问题分解的边界分别是什么？
