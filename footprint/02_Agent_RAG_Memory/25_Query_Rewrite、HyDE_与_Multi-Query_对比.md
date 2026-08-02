# 02.25 Query Rewrite、HyDE 与 Multi-Query 对比

## 1. 总体性概念

三者都用于改善 RAG 的召回，但输出对象不同：

| 方法 | 输入 | 主要输出 | 核心目的 |
|---|---|---|---|
| Query Rewrite | 原问题 + 对话上下文 | 一个更独立、更明确的问题 | 消除指代、口语和表达不完整 |
| HyDE | 原问题 | 一段假设性答案/文档 | 缩小短 query 与真实文档的表示差距 |
| Multi-Query | 原问题 | 多个不同检索视角的问题 | 扩大召回覆盖、降低单一表达失效 |

一句话区分：

```text
Rewrite：把问题说清楚
HyDE：先写一段“可能的资料”再去找真资料
Multi-Query：从多个角度分别去找资料
```

## 2. 原理性解释

### 2.1 它们解决的是不同类型的失败

#### Query Rewrite 解决“输入不完整”

```text
用户：它为什么不在 KRaft 里维护？
```

检索器不知道“它”是什么，需要从对话恢复为：

```text
Kafka partition 的 ISR 为什么由 leader broker 根据 follower 同步进度维护，而不是由 KRaft controller 直接维护？
```

#### HyDE 解决“查询与文档表达形态不匹配”

问题很短，文档很长；先生成说明性文本，再对说明文本做 embedding。

#### Multi-Query 解决“单一表达覆盖不足”

原问题可能同时涉及定义、机制和边界，一个 query 的 topK 无法覆盖全部证据，所以生成多路查询。

### 2.2 三者的主要风险也不同

| 方法 | 主要风险 | 控制方式 |
|---|---|---|
| Query Rewrite | 意图漂移、丢失原始关键词 | 保留原 query；校验新增假设 |
| HyDE | 假设文档事实错误、主题偏移 | 只作为检索表示；不当证据；双路召回 |
| Multi-Query | 查询重复、噪声和成本膨胀 | 限制数量；差异度过滤；RRF + rerank |

### 2.3 它们可以串联，但不能无脑全部开启

一种组合：

```text
对话问题
  ↓ Rewrite 成自包含问题
  ↓ 判断召回困难程度
  ├─ 语义短且抽象 → 生成 HyDE
  └─ 多方面复杂问题 → 生成 Multi-Query
  ↓ 原 query / rewritten / HyDE / multi-query 多路召回
  ↓ 融合、去重、rerank
```

每增加一条检索路径，都增加延迟、token 成本和噪声。系统应通过 query 分类器或离线评估决定触发策略。

### 2.4 查询增强只解决召回入口，不解决全部 RAG 问题

即使 query 很好，仍可能因为以下问题失败：

- 文档切分破坏上下文；
- 索引中没有正确资料；
- metadata 过滤错误；
- topK 太小或融合不合理；
- reranker 把正确文档降权；
- prompt 没有要求基于证据回答。

因此不能看到答案错误就立即增加 query expansion，应先定位正确 chunk 是否进入候选集。


### 2.5 组合顺序为什么通常先 Rewrite

如果原问题含有“它”“前者”等指代，直接生成 HyDE 或 Multi-Query 会把歧义放大：每条扩展都可能围绕不同实体展开。因此组合时通常先完成上下文化 Rewrite，再基于自包含问题决定是否 HyDE 或 Multi-Query。

但对已经精确的关键词查询，Rewrite 可能没有必要；系统可以把原 query 直接送入 sparse retrieval，同时仅对 dense 路径使用语义扩展。不同召回通道不必共享完全相同的查询文本。

## 3. 机制流程

### 3.1 决策树

```text
查询是否依赖多轮上下文或含指代？
 ├─ 是 → Query Rewrite
 └─ 否
      ↓
查询是否短、抽象，且 dense retrieval 与文档措辞差距大？
 ├─ 是 → HyDE（同时保留原 query）
 └─ 否
      ↓
问题是否包含多个检索角度或单路召回不稳定？
 ├─ 是 → Multi-Query
 └─ 否 → 直接混合检索
```

### 3.2 统一编排伪代码

```python
def enhanced_retrieve(question, history, profile):
    queries = [question]

    if needs_contextualization(question, history):
        rewritten = rewrite_query(question, history)
        queries.append(rewritten)
    else:
        rewritten = question

    if profile.hyde_enabled and is_abstract_short_query(rewritten):
        hypothetical = generate_hypothetical_document(rewritten)
        queries.append(hypothetical)  # 仅走 dense retrieval

    if profile.multi_query_enabled and is_multi_aspect(rewritten):
        queries.extend(generate_distinct_queries(rewritten, max_queries=4))

    hit_lists = []
    for q in distinct(queries):
        hit_lists.append(search_by_query_type(q))

    merged = rrf_merge(hit_lists)
    return rerank(question, deduplicate(merged))[:8]
```

注意：HyDE 文本与普通 query 的检索策略可以不同。HyDE 通常主要用于 dense retrieval，而术语型 query 更适合 BM25。

## 4. 类比理解

你去图书馆找资料：

- Query Rewrite：把“刚才那个东西”改成完整书目需求；
- HyDE：先写一段你想找的内容大概长什么样，用它匹配相似资料；
- Multi-Query：分别从“定义、原因、边界、对比”四个角度请人查找。

## 5. 应用举例 / 代码或伪代码

### 5.1 同一个问题的三种处理

原问题：

```text
那同组是不是都能拉到？
```

Query Rewrite：

```text
Kafka 同一个 consumer group 中的多个 consumer 是否都会收到同一条 partition 消息？
```

HyDE：

```text
Kafka consumer group 会将 partition 分配给组内 consumer，单个 partition 在一个时刻通常只由组内一个 consumer 消费……
```

Multi-Query：

```text
1. Kafka consumer group 内消息如何分配？
2. 同一条 Kafka 消息何时会被多个 consumer 处理？
3. 不同 consumer group 是否各自消费同一条消息？
4. rebalance 或 offset 未提交为何可能导致重复消费？
```

三者看起来都“扩展了输入”，但用途明显不同。

### 5.2 简化选型表

| 场景 | 首选 |
|---|---|
| 多轮对话中的“它/这个/前一个” | Query Rewrite |
| 问题很短、文档是长篇解释 | HyDE |
| 问题多方面、术语表达多样 | Multi-Query |
| 精确配置字段或错误码 | 原始 query + Sparse Retrieval |
| 召回已正确但答案仍错 | 不要继续加查询增强，检查 rerank/prompt/generation |

## 6. 你在讨论中的理解推进

- 起点：你注意到三种方法都在“检索前处理 query”，容易把它们视为同一类改写。
- 修正：Query Rewrite 输出一个更好的问题；HyDE 输出一个假设文档；Multi-Query 输出多个问题。
- 推进：你进一步从“形式差异”走向“失败模式差异”：上下文缺失、query-document gap、召回覆盖不足分别对应不同方案。
- 最终理解：三种技术不是固定套餐，必须以检索评估数据决定是否启用和如何组合。

## 7. 常见误区与排查思路

- **误区：三个方法一起开一定最好。** 可能带来成本和噪声倍增。
- **误区：查询增强可以弥补知识库缺文档。** 索引中不存在的事实无法被召回。
- **误区：只看最终答案评价增强效果。** 应先看 Recall@K、MRR、正确 chunk 排名和来源分布。
- **排查：** 为每条候选记录 `retrieval_route`，对比原 query、rewrite、HyDE 和各 multi-query 的独立贡献。

## 8. 关联知识点

- `22_RAG_Query_Rewrite_查询改写.md`
- `23_RAG_HyDE_假设文档嵌入.md`
- `24_RAG_Multi-Query_Expansion_多查询扩展.md`
- [稠密向量、稀疏向量与多向量表示及检索](../01_LLM_Transformer/11_稠密向量、稀疏向量与多向量表示及检索.md)
- `26_RAGAS_评估指标与_Ground_Truth_来源.md`

## 9. 复习检查问题

1. 三种方法的输出分别是什么？
2. 哪种方法主要处理多轮指代？
3. 为什么 HyDE 文本不能作为事实证据？
4. Multi-Query 为什么必须做去重和统一 rerank？
5. 如何通过离线评估决定是否开启某种查询增强？
