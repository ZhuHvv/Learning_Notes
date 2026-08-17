# 02.33 RAG 冲突证据：事实级检测、信源依赖与仲裁

## 1. 总体性概念

RAG 中的“多篇材料说同一件事”不等于存在多个独立证据；“两条材料数值不同”也不等于它们真正冲突。可靠的系统要先把 Chunk 转换为带来源、时间、版本和适用范围的原子事实，再分别处理：

1. 是否在说同一个事实；
2. 是否在同一条件下互相矛盾；
3. 支持或反对的证据是否来自独立传播链；
4. 冲突是否可按时间、版本、范围或可信度仲裁；
5. 无法仲裁时如何保留不确定性。

```text
Top-K Chunk
  ↓
Atomic Claim Extraction
  ↓
Normalize + Comparable Grouping
  ↓
Conflict Detection
  ↓
Source Dependency + Evidence Clustering
  ↓
Conflict Resolution + Uncertainty
  ↓
Resolved Evidence Set → LLM
```

## 2. 为什么不能直接比较 Chunk 或按文章数投票

一个 Chunk 往往混合多个事实。比如“2024 款续航 800 km”和“2025 款续航 835 km”同时包含相同车型与不同数值，但因版本不同可以同时成立。直接比较整段文字会把一致信息、时间演化和真正矛盾混为一谈。

同样，新华社原文被多个门户转载后，`5 篇支持 : 1 篇反对` 可能实际是 `1 条独立支持链 : 1 条独立反对链`。这类“虚假多数”的根源是 Source Dependence（信源依赖），不是普通文本重复。

## 3. 原子事实与标准化

先将候选文本拆成可比较的 Claim：

```json
{
  "subject": "小米 SU7 Max",
  "predicate": "CLTC 续航",
  "value": 835,
  "unit": "km",
  "time": "2025",
  "version": "2025款",
  "scope": null,
  "condition": null,
  "source_id": "doc_17"
}
```

标准化至少包括实体别名、单位、日期/时间范围、版本和范围。`835公里`、`835 km` 应统一；“雷军”“Lei Jun”应映射到同一实体。缺失 `time`、`scope`、`condition` 会显著提高误判率。

之后按 `(subject, predicate, scope)` 等 Conflict Key 分组，只在同组内比较，避免 $O(N^2)$ 的无意义全量两两检测。

## 4. 冲突检测：规则、NLI、LLM 三层

| 层次 | 适合的问题 | 典型输出 |
| --- | --- | --- |
| 规则 | 同实体、谓词、时间、范围和单位下的不同数值 | `CONTRADICTION` |
| NLI | “支持”与“不支持”一类语义反向陈述 | `ENTAILMENT` / `CONTRADICTION` / `NEUTRAL` |
| LLM Judge | 部分支持、隐含条件、复杂范围差异 | `PARTIAL_CONTRADICTION` / `NOT_COMPARABLE` 等 |

Embedding 相似度只适合筛出“可能相关或可能冲突”的事实，不能最终裁定。例如“支持城市辅助驾驶”和“不支持城市辅助驾驶”向量很接近，却语义相反。

判定结果应至少区分：

```text
SUPPORT / CONTRADICTION / PARTIAL_CONTRADICTION
TEMPORAL_EVOLUTION / VERSION_DIFFERENCE / SCOPE_DIFFERENCE
NEUTRAL / NOT_COMPARABLE
```

信息不同不等于冲突。只有在时间、版本、范围、条件和度量标准兼容时的互斥主张，才是静态真冲突。

## 5. 信源依赖检测与证据簇

入库时保存 provenance：

```json
{
  "url": "...",
  "canonical_url": "...",
  "publisher": "网易",
  "publish_time": "...",
  "original_source": "新华社",
  "cited_sources": ["..."],
  "content_hash": "...",
  "source_cluster_id": "cluster_123"
}
```

判断复制关系时，显式“转载自”、`canonical`、引用链接是强信号。没有显式来源时，再综合：

- 稀有连续短语的 shingling、MinHash/Jaccard 或 SimHash；
- 语义相似度和版式/实体重合；
- 发布时间与更新的先后关系；
- 是否共享罕见错误值。

时间只能辅助判断复制方向：早发布不必然原创。文本相似也只说明可能在说同一事实，不证明不是独立信源。

必须区分两个聚类：

| 对象 | 问题 | 不应混淆为 |
| --- | --- | --- |
| Claim Cluster | 是否表达同一原子事实 | 独立来源数量 |
| Evidence Cluster | 是否属于同一传播链 | 语义相似文章集合 |

依赖关系可形成图，阈值筛边后用连通分量或并查集初步分簇；生产系统还应做簇一致性检查，避免一条误边把两条传播链错误合并。

## 6. 来源感知聚合与冲突仲裁

不要按文档数投票。最稳妥的实现是每个独立证据簇只允许贡献一次，例如取簇内质量最高代表：

$$
\operatorname{Score}(cluster)=\max_{d\in cluster}\operatorname{Score}(d)
$$

单篇证据或证据簇可综合相关性、来源权威性、一手来源、时效、独立性与上下文一致性：

$$
\operatorname{Score}(C)=
\alpha A+\beta F+\gamma P+\delta I+\epsilon K-\lambda D
$$

其中 $A$ 是权威性、$F$ 是新鲜度、$P$ 是一手来源、$I$ 是独立支持、$K$ 是一致性、$D$ 是依赖惩罚。具体权重需要结合业务和标注数据校准。

检测之后，仲裁不应只有“删掉一方”。合理的 resolution 包括：

```text
MERGE                 两者可合并
TEMPORAL              分时间保留
SCOPE_SPLIT           分适用范围保留
RESOLVE_A / RESOLVE_B 依据证据选择一方
UNRESOLVED            高质量证据仍无法裁定
```

`UNRESOLVED` 是正确结果的一种。系统应把争议和不确定性传给生成层，而不是强行编造唯一答案。

## 7. 交给生成模型的是已仲裁证据集

```json
[
  {
    "fact": "2025款 SU7 Max CLTC 续航为 835 km",
    "status": "CONFIRMED",
    "confidence": 0.96,
    "sources": ["一手官方资料"]
  },
  {
    "fact": "2024款 SU7 Max CLTC 续航为 800 km",
    "status": "HISTORICAL"
  },
  {
    "fact": "某二手来源称 2025款仍为 800 km",
    "status": "REJECTED",
    "reason": "与同版本一手资料冲突"
  }
]
```

生成约束应明确：`CONFIRMED` 可作为事实；`HISTORICAL` 必须带时间；`UNRESOLVED` 必须说明分歧；`REJECTED` 不得作为结论依据。这样冲突检测负责找问题，冲突仲裁负责构造可信证据集，LLM 才负责表达结论。

## 8. 关联知识点

- [时间感知 RAG：版本、as_of 与硬过滤](32_%E6%97%B6%E9%97%B4%E6%84%9F%E7%9F%A5%20RAG%EF%BC%9A%E7%89%88%E6%9C%AC%E3%80%81as_of%20%E4%B8%8E%E7%A1%AC%E8%BF%87%E6%BB%A4.md)
- [MMR：相关性与多样性选择](34_MMR%EF%BC%9A%E7%9B%B8%E5%85%B3%E6%80%A7%E4%B8%8E%E5%A4%9A%E6%A0%B7%E6%80%A7%E9%80%89%E6%8B%A9.md)
- [RAG 完整链路：召回、融合、重排、生成](18_RAG_%E5%AE%8C%E6%95%B4%E9%93%BE%E8%B7%AF%EF%BC%9A%E5%8F%AC%E5%9B%9E%E3%80%81%E8%9E%8D%E5%90%88%E3%80%81%E9%87%8D%E6%8E%92%E3%80%81%E7%94%9F%E6%88%90.md)
