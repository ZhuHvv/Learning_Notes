# 02.20 RAG HyDE：假设文档嵌入

## 1. 总体性概念

HyDE（Hypothetical Document Embeddings）先让生成模型根据问题写出一段**假设性文档或假设答案**，再对这段文本做 Embedding，用它去检索真实文档。

```text
用户问题 q
  ↓ LLM
假设文档 h（可能不完全正确）
  ↓ Embedding
向量 e(h)
  ↓ 相似度检索
真实文档集合 D
```

HyDE 的假设文档不是最终证据，也不能直接作为答案。它只是一个“检索桥梁”，用于把短 query 转换成更接近真实文档语言分布的文本。

## 2. 原理性解释

### 2.1 查询和文档在表达形态上不对称

用户查询往往很短：

```text
Kafka ISR 谁维护？
```

技术文档通常是一段完整说明：

```text
Each partition leader tracks follower fetch progress and maintains the in-sync replica set...
```

即使含义相关，“短问题向量”和“解释性文档向量”仍可能存在分布差异。HyDE 先生成类似文档风格的文本：

```text
Kafka 中每个 partition 的 leader 根据 follower 的同步进度维护 ISR；KRaft controller 管理集群元数据并负责 leader 选举决策……
```

然后用这段文本检索，更容易靠近真实说明文档。

### 2.2 HyDE 利用的是生成模型的语言先验，不是它的事实可靠性

假设文档可能有事实错误，但它仍可能包含正确的主题词、关系词和文档风格，从而改善召回。真正回答时必须只使用检索到的可信文档。

所以需要严格区分：

```text
HyDE text = retrieval query representation
Retrieved documents = evidence
Final answer = grounded generation based on evidence
```

不能把 HyDE 文本混进证据列表并让模型引用，否则会把模型自己的猜测伪装成外部资料。

### 2.3 为什么它可能比直接扩写关键词更有效

关键词扩展只增加若干词项；HyDE 生成完整语义结构，包含实体之间的关系、可能出现的解释句式和上下文。例如“消费者断线后如何恢复”可能扩展出 `consumer group`、`rebalance`、`committed offset`、`partition assignment` 等相互关联的表达。

Embedding 模型对一段连贯说明的表示，可能比对零散关键词更稳定。

### 2.4 HyDE 的主要风险

1. **主题偏移**：假设文档朝错误方向展开，导致召回整体偏离。
2. **错误细节污染**：生成了错误版本号、组件关系或结论。
3. **成本增加**：检索前多一次生成调用。
4. **重复性**：多个问题可能生成相似的模板答案，降低区分度。

缓解方式包括：

- 同时保留原 query 检索；
- 生成多个假设文档后做多路融合；
- 提示模型避免具体数值和未经确认的事实；
- 只把 HyDE 用于召回困难的查询，而不是所有查询。


### 2.5 单个 HyDE、多个 HyDE 与向量聚合

最简单方案只生成一段 hypothetical document。为了降低一次生成偏向，可以生成多个不同视角的假设文档：

```text
h1：定义与基本机制
h2：工程实现与组件关系
h3：常见边界与失败条件
```

随后有两种处理方式：

1. **分别检索后融合**：保留每个假设文档的独立排名，便于观察贡献，通常更稳健；
2. **向量平均后检索**：将多个 embedding 求均值，只执行一次查询，成本低，但不同视角可能互相抵消。

```python
hyde_vector = sum(encoder(h) for h in hypos) / len(hypos)
```

工程上更推荐先分别检索并使用 RRF，因为可以追踪哪个假设方向带来了正确证据。

### 2.6 HyDE 的触发器应基于检索困难，而非固定开启

可使用以下信号判断是否触发：query token 很少、缺少领域实体、历史相似查询的 dense Recall 较低、初次检索最高分低或候选分布过于平坦。也可以先直接检索，只有结果置信度不足时再执行 HyDE 作为第二阶段补召回。

```text
直接检索 → 置信度足够 → 跳过 HyDE
         → 置信度不足 → HyDE 补检索 → 融合重排
```

这种级联策略能减少不必要的生成成本。

## 3. 机制流程

```python
def hyde_retrieve(question, llm, encoder, vector_db):
    hypothetical = llm.invoke({
        "instruction": (
            "写一段可能出现在专业资料中的说明，用于检索。"
            "不要声称它是真实证据，不要编造具体来源。"
        ),
        "question": question,
    })

    original_hits = vector_db.search(encoder(question), top_k=30)
    hyde_hits = vector_db.search(encoder(hypothetical), top_k=30)

    candidates = rrf_merge([original_hits, hyde_hits])
    return rerank(question, candidates)[:8], hypothetical
```

完整流程：

```text
问题分类：是否语义过短/抽象/难召回？
  ├─ 否：直接检索
  └─ 是
      ↓ 生成 hypothetical document
      ↓ 原 query 与 HyDE 双路检索
      ↓ 候选融合、去重、重排
      ↓ 仅用真实文档生成答案
```

## 4. 类比理解

你不知道某本专业书的原句，只记得大概问题。于是先让熟悉该领域的人写一段“这本书可能会怎样解释”，再拿这段描述去图书馆匹配真正的书。那段描述只是找书线索，不是权威资料。

## 5. 应用举例 / 代码或伪代码

### 5.1 原查询和假设文档对比

```text
Query：为什么 Kafka 只能保证分区内有序？

HyDE：Kafka 将 topic 拆分为多个 partition，每个 partition 是独立追加日志，
消息在单个 partition 内按 offset 顺序写入和消费；不同 partition 并行处理，
因此系统没有天然的跨 partition 全局顺序……
```

假设文档包含了文档中常出现的 `append-only log`、`offset`、`parallelism`、`global order` 等语义结构。

### 5.2 多个 HyDE 样本

```python
def multi_hyde(question, n=3):
    hypos = llm.generate(question, n=n, temperature=0.7)
    hit_lists = [vector_db.search(encoder(h), top_k=20) for h in hypos]
    hit_lists.append(vector_db.search(encoder(question), top_k=20))
    return rrf_merge(hit_lists)
```

多个假设文档可增加覆盖面，但成本更高，也可能扩大噪声，需要 reranker 控制。

### 5.3 适用场景

- 问题很短但需要说明性文档；
- 用户语言与语料语言风格不同；
- 查询使用口语，文档使用专业术语；
- 直接 dense retrieval 的正确文档排名长期偏低。

对精确配置名、错误码、函数签名，BM25 往往比 HyDE 更直接。


### 5.4 HyDE 的离线评估

评估时至少记录原始 dense retrieval 与 HyDE retrieval 的增量贡献：

```text
HyDE Gain@K = 使用 HyDE 后新增进入 topK 的正确文档比例
```

还应观察主题漂移率、hypothetical document 的重复度、生成延迟和最终 rerank 结果。HyDE 提高初始 recall 但若候选噪声过多，最终答案不一定改善，所以必须同时看检索层和端到端指标。

## 6. 你在讨论中的理解推进

- 起点：你最初可能把 HyDE 理解为“让模型先回答，再把答案交给用户”。
- 修正：HyDE 的生成结果只服务于检索，不是标准答案，也不是证据。
- 推进：你进一步区分了 HyDE 与 Query Rewrite：Rewrite 输出更规范的问题，HyDE 输出更像文档的假设说明。
- 最终连接：HyDE 的价值来自缩小 query 与 document 的表达分布差距，但必须通过真实检索结果完成 grounding。

## 7. 常见误区与排查思路

- **误区：HyDE 生成得越准确越好。** 它首先需要语义覆盖，最终事实仍由真实文档决定。
- **误区：把 hypothetical document 当引用来源。** 这是模型生成内容，不能当外部证据。
- **误区：HyDE 一定提升召回。** 主题漂移时会变差，应离线评估并设置触发条件。
- **排查：** 保存 hypothetical text，比较原 query/HyDE 的命中文档、Recall@K 和 rerank 后排名。

## 8. 关联知识点

- [稠密向量、稀疏向量与多向量表示及检索](../01_LLM_Transformer/10_稠密向量、稀疏向量与多向量表示及检索.md)
- `019_RAG_Query_Rewrite_查询改写.md`
- `021_RAG_Multi-Query_Expansion_多查询扩展.md`
- `022_Query_Rewrite、HyDE_与_Multi-Query_对比.md`
- [知识图谱、HyDE、RRF 与检索增强](../01_LLM_Transformer/13_知识图谱、HyDE、RRF_与检索增强.md)

## 9. 复习检查问题

1. HyDE 的假设文档在系统中是什么角色？
2. 为什么短 query 与长文档之间可能存在表示分布差异？
3. 为什么最终回答不能引用 HyDE 文本？
4. 原 query 与 HyDE 双路召回有什么好处？
5. 哪些精确查询通常不适合优先使用 HyDE？
