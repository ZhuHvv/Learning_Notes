# 01.17 Rerank 方法：ColBERT、Pooling 与评分头

## 1. 总体性概念

Rerank 的职责是在第一阶段召回出的候选中，重新判断每个 Query-Chunk 对的相关性。它不是单一算法：Cross-Encoder、ColBERT 一类 Late Interaction 模型、LLM 或规则/多信号模型都可以承担这一职责。

需要始终区分三个粒度：

- Token 是模型内部的匹配或表征粒度；
- Chunk 是检索、排序和传给 LLM 的证据粒度；
- Candidate ID 是工程上把排序分数可靠写回候选的标识。

因此，Token-to-Token 匹配的结果不会作为检索结果直接返回；它们只用于计算某个完整 Chunk 的分数。

## 2. 三类重排方式

| 方法 | 文本交互方式 | 如何得到 Chunk 分数 | 主要特点 |
| --- | --- | --- | --- |
| Cross-Encoder | Query 和 Chunk 在同一 Transformer 中完整交互 | `[CLS]`、池化向量或特定 token 经评分头输出 | 交互最充分，通常精度高、成本高 |
| ColBERT / Late Interaction | 分别编码，但保留 token 向量，随后做细粒度匹配 | Query token 对 Chunk token 的 MaxSim 聚合 | 比单向量细致，通常比完整交叉编码更易扩展 |
| Bi-Encoder | 分别编码后压成单向量 | 余弦相似度或点积 | 适合大规模召回，通常不是精排首选 |

Cross-Encoder 与 Bi-Encoder 的基本区别见[01.13 Bi-encoder、Cross Encoder 与重排](13_Bi-encoder%E3%80%81Cross_Encoder_%E4%B8%8E%E9%87%8D%E6%8E%92.md)。

## 3. ColBERT：Token 级评分，Chunk 级排序

ColBERT 保留 Query 与文档的多个 token 向量。对每一个 Query token，在某个 Chunk 内找最匹配的文档 token，再把这些最大相似度相加：

$$
\operatorname{Score}(Q,D)=\sum_{q_i\in Q}\max_{d_j\in D}\operatorname{sim}(q_i,d_j)
$$

例如 Query 为“`小米的竞争对手是谁`”，某个 Chunk 同时含有“小米”“竞争”“对手”“特斯拉”。每个 Query token 可分别找到最合适的 Chunk token，最后只产生一个 `Score(Query, Chunk)`，用于和其他 Chunk 排序。

```text
Query token ─┐
Query token ─┼─ MaxSim + 求和 ─→ Chunk score ─→ Chunk 排序
Query token ─┘
```

这避免了单向量在过早 Pooling 时丢失细粒度词项关系，但最终仍应返回完整 Chunk：只有完整上下文才可作为回答证据、保留实体关系并支持引用。

## 4. Cross-Encoder：从 Token 表示到分数

典型 BERT 风格输入为：

```text
[CLS] Query [SEP] Chunk [SEP]
```

经过多层 Transformer 后，模型得到每个 token 的 hidden state。之后需要一个 readout（读出）步骤，将多个 token 表示压缩为一个用于评分的向量 $h$，常见方式如下。

| 读出方式 | 做法 | 含义 |
| --- | --- | --- |
| CLS Pooling | 取最终 `h_cls` | 让 `[CLS]` 在训练中学习汇聚整个文本对信息 |
| Mean Pooling | 对有效 token 向量逐维平均 | 用固定规则汇总 token 表示 |
| Max Pooling | 每一维取 token 表示中的最大值 | 突出某些强激活特征 |
| 特定 token / logit | 取模型指定位置的表示或输出 | Decoder-only/LLM reranker 常见变体 |

`[CLS]` 不是天然“代表全文”的魔法向量；它之所以能承担整体表示，是因为在联合注意力和下游相关性训练中被赋予了这一职责。`[SEP]` 的职责则是分隔序列，不能与 `[CLS]` 混淆。

评分头通常很简单：

$$
z=W\cdot h+b
$$

其中 $z$ 是 logit。二分类模型可能再使用：

$$
\operatorname{score}=\sigma(z)
$$

例如 $h=[0.8,0.4,-0.2]$、$W=[2.0,1.5,-1.0]$、$b=-0.5$ 时：

```text
z = 2.0×0.8 + 1.5×0.4 + (-1.0)×(-0.2) - 0.5 = 1.9
sigmoid(z) ≈ 0.870
```

但排序只要求单调的相对顺序，因此许多 API 直接返回 logit 或回归分数。不要把分数默认解释成概率，也不要跨模型、跨版本比较绝对值。

## 5. 完整检索链路中的位置

```text
BM25 / 向量召回 / 图检索
           ↓
RRF 或其他融合
           ↓
候选 Top-N
           ↓
Cross-Encoder / ColBERT 等 Rerank
           ↓
去重、来源约束、MMR、上下文预算
           ↓
互补证据集
           ↓
LLM 生成
```

Rerank 只回答“这个候选与 Query 是否相关”。它不自动保证来源独立、事实正确、版本最新或结果多样；这些分别由来源处理、事实核验、时间过滤和 MMR 负责。

## 6. 工程实现要点

```python
def rerank(query, candidates, reranker):
    pairs = [
        {"id": item.id, "query": query, "document": item.text}
        for item in candidates
    ]
    scores_by_id = reranker.score(pairs)
    return sorted(candidates, key=lambda item: scores_by_id[item.id], reverse=True)
```

- 通过稳定 ID 映射结果，不能假设批量 API 的返回索引永远与输入一致；
- 先限制候选规模，再调用 Cross-Encoder；
- 使用 token 级模型时，仍以 Chunk 作为结果与引用单位；
- 分数高不代表内容真实、权威、时效正确或足以回答问题；
- Rerank 后还应控制重复、相邻分块和总 token 预算。

## 7. 关联知识点

- [Bi-encoder、Cross Encoder 与重排](13_Bi-encoder%E3%80%81Cross_Encoder_%E4%B8%8E%E9%87%8D%E6%8E%92.md)
- [MMR：相关性与多样性选择](../02_Agent_RAG_Memory/34_MMR%EF%BC%9A%E7%9B%B8%E5%85%B3%E6%80%A7%E4%B8%8E%E5%A4%9A%E6%A0%B7%E6%80%A7%E9%80%89%E6%8B%A9.md)
- [RAG 完整链路：召回、融合、重排、生成](../02_Agent_RAG_Memory/18_RAG_%E5%AE%8C%E6%95%B4%E9%93%BE%E8%B7%AF%EF%BC%9A%E5%8F%AC%E5%9B%9E%E3%80%81%E8%9E%8D%E5%90%88%E3%80%81%E9%87%8D%E6%8E%92%E3%80%81%E7%94%9F%E6%88%90.md)
