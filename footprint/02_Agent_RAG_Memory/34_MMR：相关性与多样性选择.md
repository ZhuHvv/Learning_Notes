# 02.34 MMR：相关性与多样性选择

## 1. 总体性概念

MMR（Maximal Marginal Relevance，最大边际相关性）是一种结果集合选择算法：在保持 Query 相关性的同时，惩罚与已选结果的重复，从而让有限的上下文窗口覆盖更多互补信息。

它要解决的不是“哪个 Chunk 最相关”，而是“最终 Top-K 应该是哪一组既相关又不重复的 Chunk”。

## 2. 公式与直觉

每轮从未选候选中选择 MMR 分数最大的项：

$$
\operatorname{MMR}(D_i)=
\lambda\operatorname{Sim}(D_i,Q)
-(1-\lambda)\max_{D_j\in S}\operatorname{Sim}(D_i,D_j)
$$

其中：

- $Q$：用户 Query；
- $D_i$：当前候选 Chunk；
- $S$：已选 Chunk 集合；
- 第一项：与 Query 的相关性奖励；
- 第二项：与已选结果最相似的冗余惩罚；
- $\lambda$：相关性与多样性的权衡。

例如已选“芯片升级”后，另一个也讲“芯片升级”的候选即使 Query 分数稍高，也可能输给“激光雷达变化”或“软件能力变化”的候选，因为后两者能补充新的信息维度。

## 3. 它是迭代贪心选择，不是一次独立打分

```text
候选集 A B C D E
      ↓
先选与 Query 最相关的 A
      ↓
对 B/C/D/E：相关性 - 与 A 的重复度
      ↓
选择下一项 C
      ↓
对剩余项：相关性 - 与 {A, C} 中最像者的重复度
      ↓
直到选满 K 项
```

普通 reranker 的分数近似为 `score(query, chunk)`，每个 Chunk 独立；MMR 的分数是 `score(query, chunk, selected_set)`，已选结果会改变下一轮选择。

## 4. λ 的取值

| λ | 行为 |
| --- | --- |
| `1` | 退化为按 Query 相似度取 Top-K，不去重 |
| 接近 `1` | 更重相关性，轻度多样化 |
| 约 `0.5` 到 `0.8` | 常见的相关性与多样性折中区间，需按评估调参 |
| `0` | 基本只追求彼此不同，可能偏离 Query |

数值不是通用最佳实践。上下文预算很紧、候选高度重复时可提高多样性权重；事实问答需要精准单点证据时应偏向相关性。

## 5. 在 RAG 链路中的位置

```text
多路召回 → RRF/融合 → Rerank → MMR → 上下文打包 → LLM
```

| 机制 | 主要问题 |
| --- | --- |
| RRF | 多个召回器的结果如何融合 |
| Rerank | 单个候选与 Query 是否真正相关 |
| MMR | 最终候选集合是否冗余、是否覆盖互补信息 |
| 来源去重 | 多篇材料是否来自同一传播链 |

MMR 不等于来源去重：两篇来自不同来源但谈论同一细节，仍可能被 MMR 判为冗余；多篇转载也应由信源依赖检测另外限流。

## 6. 伪代码

```python
def mmr_select(query, candidates, k, lambda_mult=0.7):
    selected = []
    remaining = list(candidates)

    while remaining and len(selected) < k:
        def score(candidate):
            relevance = similarity(query, candidate)
            redundancy = max(
                (similarity(candidate, chosen) for chosen in selected),
                default=0.0,
            )
            return lambda_mult * relevance - (1 - lambda_mult) * redundancy

        best = max(remaining, key=score)
        selected.append(best)
        remaining.remove(best)

    return selected
```

实际系统可使用向量相似度、交叉编码器分数或业务特征作为相关性项。应先做权限、版本和来源约束，之后再在高质量候选中做 MMR。

## 7. 关联知识点

- [Rerank 方法：ColBERT、Pooling 与评分头](../01_LLM_Transformer/17_Rerank%20%E6%96%B9%E6%B3%95%EF%BC%9AColBERT%E3%80%81Pooling%20%E4%B8%8E%E8%AF%84%E5%88%86%E5%A4%B4.md)
- [RAG 冲突证据：事实级检测、信源依赖与仲裁](33_RAG%20%E5%86%B2%E7%AA%81%E8%AF%81%E6%8D%AE%EF%BC%9A%E4%BA%8B%E5%AE%9E%E7%BA%A7%E6%A3%80%E6%B5%8B%E3%80%81%E4%BF%A1%E6%BA%90%E4%BE%9D%E8%B5%96%E4%B8%8E%E4%BB%B2%E8%A3%81.md)
