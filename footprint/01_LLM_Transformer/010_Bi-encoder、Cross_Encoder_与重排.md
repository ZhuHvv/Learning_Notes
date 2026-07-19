# Bi-encoder、Cross Encoder 与重排

> 所属分类：LLM / Transformer  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Bi-encoder 负责大规模快速召回，Cross-Encoder 负责对少量 query-document pair 精细重排。召回决定候选集合的上限，重排改善候选内部顺序，之后还要做权限、去重、预算和证据构建。

## 2. 原理性解释

- Bi-encoder 分别编码 query 和 document，文档向量可提前计算并建立 ANN 索引；
- Cross-Encoder 联合编码 query 和 candidate，交互更细但每个候选都要重新计算；
- rerank 是职责，不一定都由 Cross-Encoder 实现，也可以是 late interaction、LLM、规则或多信号融合；
- 不同 reranker 的分数范围和顺序契约未必一致；
- 高相关性不等于真实、权威、时效或足以支持答案；
- 外部 API 返回结果应通过稳定 candidate ID 映射，不能盲信输入输出索引一致。

### Bi-encoder 快，Cross-Encoder 准

```text
Bi-encoder:
document → doc vector ─┐
                      ├─ similarity
query    → query vector┘

Cross-Encoder:
(query, candidate_1) → score_1
(query, candidate_2) → score_2
```

Bi-encoder 吞吐高，适合从大库召回几十到几百条；代价是 query/document 编码时没有逐 token 交互，对否定、数字、限定条件和实体关系可能不敏感。

Cross-Encoder 联合交互通常更准确，但成本随候选数增长，不能像文档 embedding 一样离线复用。典型流程是先召回 top100，再精排到 top5～10；具体数量应由 Recall@K、nDCG、成本和延迟评估确定。

### 分数和结果映射的边界

Reranker 分数不保证位于 0～1，也不应跨模型/版本直接比较。若供应商返回已重排结果，再按索引把 score 写回原列表，可能把分数配错文档；应使用 candidate ID，阅读版本契约，并用打乱顺序的测试验证。

### 相关性分数不能证明什么

高分不能证明内容真实、来源权威、时间有效、上下文完整或足以支持结论。完整质量还包括召回覆盖、权限过滤、来源质量、事实核验和答案引用一致性。

## 3. 机制流程

1. 用向量、关键词等方式召回较大候选集；
2. 权限过滤并保留稳定 candidate ID；
3. 对 query-candidate pair 重新评分；
4. 按 ID 映射分数并排序；
5. 去重、合并相邻 chunk、控制 token 预算；
6. 把互补证据交给生成模型并保留引用。

### 两阶段检索流程

```text
大规模索引
  ↓ Bi-encoder / BM25 快速召回
候选集合
  ↓ Cross-Encoder / reranker 精排
高相关候选
  ↓ 去重、权限、预算、引用
生成上下文
```

排查时先问正确文档是否进入召回 topK；若已召回但最终引用错误，再检查融合、分数映射、重排、上下文构建和 grounding。

## 4. 类比理解

先用地图和筛选条件粗选一批餐厅，再逐家看菜单和评价重新排名。候选名单中没有某家餐厅，精排阶段无法凭空补回来。

## 5. 应用举例 / 代码或伪代码

```python
candidates = vector_index.search(embed_query(query), top_k=100)
pairs = [
    {"id": item.id, "query": query, "document": item.text}
    for item in candidates
]
scores_by_id = reranker.score(pairs)

reranked = sorted(
    candidates,
    key=lambda item: scores_by_id[item.id],
    reverse=True,
)
top_docs = pack_context(reranked, token_budget=6000)
```

Top-N 只限制数量，不限制长度。过长候选应回取相关章节或语义压缩，字符硬截断只适合作为最后保险。

## 6. 你在讨论中的理解推进

你从“向量库搜一下”推进到两阶段检索：召回决定覆盖，rerank 决定候选顺序，candidate ID 保证分数映射正确，最终质量还依赖来源、预算和引用一致性。
