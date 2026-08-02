# 知识图谱、HyDE、RRF 与检索增强

## 1. 总体性概念

知识图谱、HyDE 和 RRF 分别作用在检索链路的不同位置：

- **知识图谱**：提供显式实体与关系的结构化检索；
- **HyDE**：在检索前生成假设文档，改善 query 的向量表示；
- **RRF**：在多路召回后根据排名融合候选结果。

```
Query enhancement（HyDE）
        ↓
Dense / Sparse / Graph 多路召回
        ↓
Rank fusion（RRF）
        ↓
Rerank 与生成
```

它们互补而非替代：HyDE 不能代替知识图谱的精确关系，知识图谱不能覆盖全部非结构化语义，RRF 只负责融合已有排名，不会凭空产生正确文档。

## 2. 原理性解释

### 2.1 知识图谱：把实体关系显式建模

向量检索回答“哪些文本语义相似”，知识图谱更适合回答“实体之间通过什么关系连接”。

```
KafkaTopic ─hasPartition→ Partition
Partition ─hasLeader→ Broker
Partition ─hasReplica→ Broker
ConsumerGroup ─commitsOffsetFor→ Partition
```

查询“consumer group 的 offset 对应哪个层级”时，图谱可以沿关系直接定位到 partition；查询“如何理解 offset 语义”时，仍需要非结构化文档提供解释。

图谱检索常包含：实体识别、实体链接、邻居扩展、路径搜索和属性过滤。它的质量高度依赖 schema、实体对齐和数据更新。

### 2.2 HyDE：改善查询表示，不提供事实证据

HyDE 先生成一段假设文档，再对它做 Embedding 检索真实文档。它适合短 query 与长文档表达差异大的情况。

```
q → LLM → hypothetical document h → embedding(h) → vector search
```

假设文档可能不准确，所以只能作为检索表示，不能作为最终引用。详细机制见 [RAG HyDE：假设文档嵌入](../02_Agent_RAG_Memory/20_RAG_HyDE_%E5%81%87%E8%AE%BE%E6%96%87%E6%A1%A3%E5%B5%8C%E5%85%A5.md)。

### 2.3 RRF：用排名而不是原始分数融合

BM25、余弦相似度、图谱路径得分的量纲不同，直接相加没有稳定意义。Reciprocal Rank Fusion 根据每个文档在各列表中的名次累加：

```
RRF(d) = Σ_r 1 / (k + rank_r(d))
```

如果一个文档在多条召回路径中都排名靠前，它会获得较高融合分；某一路分数异常也不容易完全主导结果。

```python
def rrf(rank_lists, k=60):
    scores = {}
    for ranked_docs in rank_lists:
        for rank, doc in enumerate(ranked_docs, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)
```

RRF 不理解 query 与文档内容，因此融合后仍需要 reranker 判断细粒度相关性。

## 3. 机制流程

```
用户问题
  ├─ 原始 query → BM25 / sparse retrieval
  ├─ query embedding → dense retrieval
  ├─ HyDE document embedding → dense retrieval
  └─ entity linking → knowledge graph traversal
          ↓
多路候选列表
          ↓
RRF 融合排名
          ↓
父文档去重、权限与 metadata 过滤
          ↓
Cross-Encoder rerank
          ↓
上下文构建与 grounded generation
```

每个候选应保留来源：

```python
Candidate(
    chunk_id="c42",
    route="hyde_dense",   # bm25 / raw_dense / graph / hyde_dense
    rank=3,
    source_doc="kafka-design.md",
)
```

这使系统能分析某种增强路径到底带来了正确文档还是噪声。

## 4. 类比理解

- 知识图谱像关系清晰的组织架构图；
- HyDE 像先写一段“目标资料可能长什么样”；
- RRF 像综合多个评委的排名，而不是直接相加不同评分标准的分数。

## 5. 应用举例 / 代码或伪代码

```python
def enhanced_retrieve(question):
    sparse = bm25.search(question, top_k=40)
    dense = vector_db.search(embed(question), top_k=40)

    hypothetical = generate_hyde(question)
    hyde = vector_db.search(embed(hypothetical), top_k=40)

    entities = entity_linker(question)
    graph = graph_retrieve(entities, top_k=40)

    fused = rrf([sparse, dense, hyde, graph])
    filtered = permission_filter(deduplicate(fused))
    return cross_encoder_rerank(question, filtered)[:8]
```

如果知识库没有图谱，就不要为了“技术齐全”强行增加图谱路径；如果 query 是精确配置项，也可以跳过 HyDE。

## 6. 你在讨论中的理解推进

- 你先分别接触了知识图谱、HyDE 和 RRF，随后把它们放入一条完整检索链路中比较。
- 关键区分：HyDE 发生在召回前，知识图谱是一条独立召回路径，RRF 发生在多路召回之后。
- 进一步理解：RRF 解决分数不可比和多路融合，不负责判断最终语义相关性；因此后面仍需 rerank。

## 7. 常见误区与排查思路

- 把 HyDE 文本当作证据引用；
- 把知识图谱当成所有非结构化问答的替代品；
- 直接相加 BM25 与 cosine 原始分数；
- 融合后不做父文档去重，导致一个文档占满 topK；
- 不记录 retrieval route，无法定位增强路径的真实贡献。

## 8. 关联知识点

- [稠密向量、稀疏向量与多向量表示及检索](10_%E7%A8%A0%E5%AF%86%E5%90%91%E9%87%8F%E3%80%81%E7%A8%80%E7%96%8F%E5%90%91%E9%87%8F%E4%B8%8E%E5%A4%9A%E5%90%91%E9%87%8F%E8%A1%A8%E7%A4%BA%E5%8F%8A%E6%A3%80%E7%B4%A2.md)
- [倒排索引与稀疏检索](11_%E5%80%92%E6%8E%92%E7%B4%A2%E5%BC%95%E4%B8%8E%E7%A8%80%E7%96%8F%E6%A3%80%E7%B4%A2.md)
- [Bi-encoder、Cross Encoder 与重排](12_Bi-encoder%E3%80%81Cross_Encoder_%E4%B8%8E%E9%87%8D%E6%8E%92.md)
- [RAG HyDE：假设文档嵌入](../02_Agent_RAG_Memory/20_RAG_HyDE_%E5%81%87%E8%AE%BE%E6%96%87%E6%A1%A3%E5%B5%8C%E5%85%A5.md)
- [Query Rewrite、HyDE 与 Multi-Query 对比](../02_Agent_RAG_Memory/22_Query_Rewrite%E3%80%81HyDE_%E4%B8%8E_Multi-Query_%E5%AF%B9%E6%AF%94.md)

## 9. 复习检查问题

1. HyDE、知识图谱和 RRF 分别位于检索链路的哪个阶段？
2. RRF 为什么不直接使用不同检索器的原始分数？
3. 为什么 RRF 后仍需要 rerank？
4. 知识图谱最适合回答哪类问题？
5. 如何判断某条增强路径是否真正改善了召回？
