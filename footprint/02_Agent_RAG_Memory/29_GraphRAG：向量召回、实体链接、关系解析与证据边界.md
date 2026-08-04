# 02.29 GraphRAG：向量召回、实体链接、关系解析与证据边界

## 1. 总体性概念

在“向量数据库 + 图数据库”的 RAG 架构中，两类检索解决的问题不同：

```text
向量检索：哪些文本或实体与 Query 语义相近？
图检索：已经命中的实体之间能沿哪些显式关系连接？
```

向量数据库返回的通常不是答案，而是带 ID、文本和分数的候选记录：

```python
[
    {
        "chunk_id": "chunk_001",
        "text": "在智能手机市场，小米与 Apple 等厂商存在竞争关系。",
        "score": 0.91,
        "entity_ids": ["xiaomi", "apple"],
    }
]
```

召回的 Chunk 可以同时承担三种角色：

1. 定位与 Query 相关的知识区域；
2. 通过 `chunk_id` 或 `entity_id` 映射到图节点，作为图遍历入口；
3. 作为最终回答的原文证据，和图查询结果一起交给 LLM。

图数据库不是脱离原始资料的额外知识来源。它把 Chunk 中已抽取、已对齐的实体和关系结构化，便于精确遍历；原始资料不存在的事实，图数据库不能自行补出。

## 2. 原理性解释

### 2.1 以 Chunk 节点作为图查询入口

向量库返回 `chunk_001` 后，图中可以存在对应节点及提及关系：

```text
(:Chunk {id: "chunk_001"})-[:MENTIONS]->(:Company {id: "xiaomi"})
(:Chunk {id: "chunk_001"})-[:MENTIONS]->(:Company {id: "apple"})
```

先按 Chunk ID 定位，再向外扩展：

```cypher
MATCH (chunk:Chunk {id: $chunk_id})
MATCH (chunk)-[:MENTIONS]->(company:Company)
RETURN company
```

若图中已有业务关系，可以继续遍历：

```cypher
MATCH (chunk:Chunk {id: $chunk_id})
MATCH (chunk)-[:MENTIONS]->(xiaomi:Company {name: "Xiaomi"})
MATCH (xiaomi)-[:COMPETES_WITH]->(competitor:Company)
MATCH (ceo:Person)-[:CEO_OF]->(competitor)
RETURN competitor.name, ceo.name
```

### 2.2 直接召回实体或文档节点

系统不一定先命中 Chunk。若实体节点本身带有描述 Embedding，向量检索可直接返回 `Xiaomi`：

```text
(:Company {
    id: "xiaomi",
    name: "Xiaomi",
    description: "一家生产智能手机、汽车和智能硬件的公司",
    embedding: [...]
})
```

随后把命中的节点作为 `node` 执行图扩展：

```cypher
MATCH (node)-[:COMPETES_WITH]->(competitor:Company)
MATCH (ceo:Person)-[:CEO_OF]->(competitor)
RETURN competitor.name, ceo.name
```

Neo4j GraphRAG 的 `VectorCypherRetriever` 就采用这类结构：向量搜索得到的节点进入后续 Cypher，向量相似度作为 `score` 返回。外部向量库场景也可以先取得外部记录 ID，再映射回 Neo4j 节点并通过 `retrieval_query` 扩展。

### 2.3 实体与关系的确定方式不同

Query：

```text
小米的竞争对手 CEO 是谁？
```

“小米”需要映射到具体图节点，这一步是**实体识别与实体链接**，可使用：

- 精确名称、别名表；
- 全文检索；
- 实体描述向量检索；
- LLM 识别实体后再做受约束匹配。

关系通常不是由向量数据库“命中”，而是由查询理解模块结合自然语言和图 Schema 确定：

```text
Query 中的“竞争对手” + Schema 中的 COMPETES_WITH
Query 中的“CEO”       + Schema 中的 CEO_OF
```

若 Schema 是：

```text
(:Company)-[:COMPETES_WITH]->(:Company)
(:Person)-[:CEO_OF]->(:Company)
```

查询意图可以表示为：

```json
{
  "anchor_entity": "小米",
  "anchor_type": "Company",
  "relation_path": [
    {
      "relation": "COMPETES_WITH",
      "target_type": "Company"
    },
    {
      "relation": "CEO_OF",
      "direction": "inverse",
      "target_type": "Person"
    }
  ]
}
```

完整路径是：

```text
Xiaomi -[:COMPETES_WITH]-> Company <-[:CEO_OF]- Person
```

`CEO_OF` 在图中从 Person 指向 Company，所以从竞争公司寻找 CEO 时需要反向遍历。

### 2.4 关系缺失必须区分“未抽取”与“无证据”

关系查询为空时有两种完全不同的原因：

1. 原始 Chunk 明确包含该关系，但抽取、实体对齐或写图失败；
2. 原始 Chunk 本身就没有该关系的证据。

第一种是索引质量问题，可以退回原文、修复抽取或增量更新图谱。第二种是知识缺口，GraphRAG 不能仅凭现有知识库可靠回答。

图查询为空时可以退化为普通文本向量 RAG。Microsoft GraphRAG 的 Local Search 会混合图结构与原始文本单元，而 Basic Search 可以直接对原始文本块做向量检索；但回退只会扩大文本证据搜索范围，不会让不存在的关系自动变成事实。Neo4j GraphRAG 也可通过 `response_fallback` 在上下文不足时返回明确的兜底回答。

例如图中只有：

```text
(Xiaomi)-[:PRODUCES]->(Smartphone)
(Apple)-[:PRODUCES]->(iPhone)
(TimCook)-[:CEO_OF]->(Apple)
```

缺少：

```text
(Xiaomi)-[:COMPETES_WITH]->(Apple)
```

即使向量检索同时召回“小米做手机”“Apple 生产 iPhone”“Tim Cook 是 Apple CEO”，这些文本也没有明确支持“Apple 是小米竞争对手”。直接补出这条关系属于未被检索上下文支撑的生成。

### 2.5 规则推导不等于原文事实

如果图中存在：

```text
(Xiaomi)-[:OPERATES_IN]->(SmartphoneMarket)
(Apple)-[:OPERATES_IN]->(SmartphoneMarket)
```

业务规则可以把同市场公司列为“候选竞争者”：

```cypher
MATCH (xiaomi:Company {name: "Xiaomi"})
      -[:OPERATES_IN]->(market:Market)
      <-[:OPERATES_IN]-(candidate:Company)
WHERE candidate <> xiaomi
RETURN candidate
```

但“同属一个市场”不逻辑等价于“必然互为竞争对手”。除非领域本体明确规定该推导，否则输出必须标为候选或推导结果，并保留推导规则和输入证据。

### 2.6 三种关系路径确定方案

#### 固定意图模板

```python
RELATION_TEMPLATES = {
    "competitor_ceo": """
        MATCH (company:Company {id: $company_id})
              -[:COMPETES_WITH]-(competitor:Company)
        MATCH (ceo:Person)-[:CEO_OF]->(competitor)
        RETURN competitor.name, ceo.name
    """
}
```

分类器或 LLM 只选择已审核模板。优点是稳定、可控；缺点是只能覆盖预先设计的意图。

#### Text-to-Cypher

把 Query 与图 Schema 一起交给模型动态生成 Cypher。Neo4j 的 `Text2CypherRetriever` 使用 `neo4j_schema` 约束自然语言到图查询的转换。生成后仍需限制只读操作、标签、属性和关系类型：

```python
ALLOWED_RELATIONSHIPS = {"COMPETES_WITH", "CEO_OF"}


def validate_relations(generated: set[str]) -> None:
    unknown = generated - ALLOWED_RELATIONSHIPS
    if unknown:
        raise ValueError(f"非法关系类型: {unknown}")
```

否则模型可能生成 Schema 中不存在的 `HAS_COMPETITOR`，或产生越权、昂贵甚至有副作用的查询。

#### 邻居扩展后排序

另一种方案不先生成一条精确路径，而是以相关实体为入口，取回附近的候选实体、关系和文本单元，再按 Query 排序、过滤。Microsoft GraphRAG Local Search 更接近这种模式：先确定相关实体，再把候选实体、关系、社区报告和文本单元构造成受 token 预算约束的上下文。

## 3. 机制流程

### 3.1 完整检索与生成链路

```text
用户 Query
  ↓ 实体识别 / 实体链接 / 文本向量召回
相关 Chunk 或实体节点
  ↓ Query 关系语义 + 图 Schema
关系路径、模板或候选邻居
  ↓ 图数据库执行
结构化实体与关系结果
  ↓ 回取原始 Chunk
图结果 + 原文证据
  ↓ grounded prompt
LLM 生成答案
```

原始 Chunk 不只用于向量召回。它还解释图边为什么成立，并让最终答案能回溯到原文，而不是只依赖内部结构：

```python
retriever_result = retriever.search(query_text=query)

context = "\n".join(
    item.content
    for item in retriever_result.items
)

prompt = prompt_template.format(
    query_text=query,
    context=context,
)

answer = llm.invoke(prompt)
```

### 3.2 证据不足时的控制链路

```python
def answer(query: str) -> str:
    graph_result = graph_retriever.search(query)

    if graph_result.has_complete_path:
        return generate_answer(query, graph_result.context)

    chunks = vector_retriever.search(query)
    if relation_is_explicitly_supported(query, chunks):
        return generate_answer(query, chunks)

    derived = rule_engine.try_derive(query)
    if derived.is_valid:
        return generate_answer(
            query,
            derived.evidence,
            label="derived",
        )

    if external_search_is_allowed(query):
        return search_and_answer_with_new_evidence(query)

    return "当前知识库没有足够证据回答该问题。"
```

判断重点不是“是否召回了若干相关 Chunk”，而是这些 Chunk 是否支持 Query 要求的**完整关系链**。对于“小米 → 竞争对手 → CEO”，至少需要分别支持竞争关系和任职关系。

若允许查询外部数据源，新资料可以仅供本次回答临时使用；若要写回知识库，则应经过来源校验，再执行“新资料入库 → Chunk 切分 → 实体关系抽取 → 图谱增量更新”。这属于补充知识，不是图数据库从空结果中推理出了缺失关系。

## 4. 类比理解

向量检索像根据描述找到可能相关的档案盒；实体链接像确认“这个名字对应哪一个人或公司”；图 Schema 像规定档案系统里允许存在的关系字段；图遍历则沿已登记关系查找。档案中根本没有登记且原文也没有证据的关系，不能因为几个实体看起来有关就补写进去。

## 5. 应用举例 / 代码或伪代码

### 5.1 从 Chunk 映射到图节点

```cypher
MATCH (chunk:Chunk {id: $chunk_id})
MATCH (chunk)-[:MENTIONS]->(xiaomi:Company {id: "xiaomi"})
MATCH (xiaomi)-[:COMPETES_WITH]-(competitor:Company)
MATCH (ceo:Person)-[:CEO_OF]->(competitor)
RETURN competitor.name AS competitor,
       ceo.name AS ceo,
       chunk.text AS source_text
```

### 5.2 直接以向量命中的实体为入口

```python
retrieval_query = """
MATCH (node)-[:COMPETES_WITH]-(competitor:Company)
MATCH (ceo:Person)-[:CEO_OF]->(competitor)
RETURN competitor.name AS competitor, ceo.name AS ceo
"""

retriever = VectorCypherRetriever(
    driver=driver,
    index_name="company_embedding_index",
    retrieval_query=retrieval_query,
    embedder=embedder,
)
```

具体构造参数和返回结构随 Neo4j GraphRAG 版本变化，应以所用版本的官方 API 为准。

### 5.3 Schema 无法表达 Query 关系

Query：

```text
小米最欣赏的竞争对手 CEO 是谁？
```

若 Schema 只有 `COMPETES_WITH` 与 `CEO_OF`，没有 `ADMIRES`，查询理解应返回无法映射，而不是发明新边：

```json
{
  "entity": "xiaomi",
  "requested_relation": "最欣赏",
  "schema_match": null
}
```

随后可以退回原始 Chunk 检索，检查文本是否直接出现该表述；仍无证据时返回不足。

## 6. 你在讨论中的理解推进

- 起点：向量数据库召回 Chunk 后，Chunk 是否直接交给 LLM，还是还承担图查询入口作用。
- 推进：Chunk 可以通过 `chunk_id` / `entity_id` 映射到图节点，也可以作为最终原文证据；实体节点本身也可以直接做向量检索。
- 关键修正：实体链接与关系解析不是同一动作。实体可通过名称、全文或向量命中；关系由 Query 语义结合 Schema、模板或候选邻居确定。
- 边界确认：若关系只是在图抽取阶段漏掉，可退回原文和修复索引；若原文根本没有证据，只能标记推导、外部补搜或明确回答不足。

## 7. 常见误区与排查思路

- **误区：向量库同时决定实体和关系。** 向量相似度不能直接保证某条图边存在。
- **误区：图查询为空就让 LLM 用常识补全。** 这会破坏 grounded answer 边界。
- **误区：图谱能弥补源文档缺失。** 图谱组织已有知识，不会创造缺失事实。
- **误区：规则推导就是原文事实。** 必须保留规则、输入证据和推导标签。
- **误区：Text-to-Cypher 生成后可直接执行。** 应限制为只读查询并校验 Schema、关系、属性、复杂度和权限。
- **排查：** 分别记录实体链接结果、关系意图、生成 Cypher、图查询空结果原因、回退路径和最终引用来源。

## 8. 关联知识点

- [知识图谱、HyDE、RRF 与检索增强](../01_LLM_Transformer/14_知识图谱、HyDE、RRF_与检索增强.md)
- [RAG 完整链路：召回、融合、重排、生成](18_RAG_完整链路：召回、融合、重排、生成.md)
- [父子分块：层级切分、ID 映射与父块回取](19_父子分块：层级切分、ID_映射与父块回取.md)
- [Contextual Retrieval](21_Contextual_Retrieval：Contextual_Embeddings、Contextual_BM25_与多路召回.md)
- [RAGAS 评估指标与 Ground Truth 来源](26_RAGAS_评估指标与_Ground_Truth_来源.md)

## 9. 参考资料与事实边界

- [Neo4j GraphRAG for Python：RAG user guide](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html)
- [Neo4j GraphRAG `GraphRAG` 生成链路源码](https://neo4j.com/docs/neo4j-graphrag-python/current/_modules/neo4j_graphrag/generation/graphrag.html)
- [Neo4j GraphRAG `Text2CypherRetriever` 源码](https://neo4j.com/docs/neo4j-graphrag-python/current/_modules/neo4j_graphrag/retrievers/text2cypher.html)
- [Microsoft GraphRAG：Local Search](https://microsoft.github.io/graphrag/query/local_search/)

本文的公司与关系数据是机制示例，不是对现实商业关系的事实声明。代码中统一控制回退与推导标签的部分是工程伪代码；Neo4j 和 Microsoft GraphRAG 的具体类名、参数与上下文构建策略以所用版本官方文档为准。

## 10. 复习检查问题

1. Chunk 在 GraphRAG 中可能同时承担哪三种角色？
2. 实体链接与关系解析分别解决什么问题？
3. Query 中的“CEO”为什么可能需要反向遍历 `CEO_OF`？
4. 图中缺边时，如何区分抽取失败与知识库无证据？
5. 为什么“同市场经营”只能推出候选竞争者，而不能自动当作竞争事实？
6. 固定模板、Text-to-Cypher 和邻居扩展各有什么取舍？
7. 为什么最终上下文仍应保留原始 Chunk？
