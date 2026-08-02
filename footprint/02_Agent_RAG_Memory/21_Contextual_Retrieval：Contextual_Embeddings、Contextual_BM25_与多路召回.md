# 02.21 Contextual Retrieval：Contextual Embeddings、Contextual BM25 与多路召回

## 1. 核心结论

Contextual Retrieval 与 BM25 的结合**不是修改 BM25 打分公式**，而是：

1. 为每个 Chunk 生成一段说明它在原文中位置和含义的简短上下文；
2. 把 `上下文说明 + 原始 Chunk` 同时用于稠密向量编码和 BM25 建库；
3. 查询时让 Contextual Embeddings 与 Contextual BM25 作为两路召回；
4. 合并、去重或融合候选，之后才可选择 Reranker 精排。

Anthropic 将两条建库路径分别称为 **Contextual Embeddings** 和 **Contextual BM25**。

## 2. 传统 Chunk 的上下文丢失问题

假设原文是一份 ACME 公司 2023 年第二季度财报，其中一个 Chunk 只有：

```text
公司的收入较上一季度增长了 3%。
```

查询是：

```text
ACME 公司 2023 年第二季度收入增长率是多少？
```

原始 Chunk 没有 `ACME`、`2023 年`、`第二季度` 等词项。BM25 可能无法召回它；独立编码过短 Chunk 时，向量也缺少实体和章节语境。问题来自切块丢失原文上下文，不代表 BM25 的词频、逆文档频率或长度归一化公式本身有错。

## 3. 为每个 Chunk 生成检索上下文

Contextual Retrieval 把完整文档与当前 Chunk 一起交给模型，让模型生成专属于该 Chunk 的简短说明。提示词结构可概括为：

```xml
<document>
完整文档
</document>

<chunk>
当前 Chunk
</chunk>

请生成一段简短上下文，说明这个 Chunk 在完整文档中的位置和含义，
用于改善检索；只输出该上下文。
```

模型可能生成：

```text
该内容来自 ACME 公司 2023 年第二季度财务报告，
描述该公司本季度与上一季度之间的收入变化。
```

随后与原始 Chunk 拼接：

```text
该内容来自 ACME 公司 2023 年第二季度财务报告，
描述该公司本季度与上一季度之间的收入变化。
公司的收入较上一季度增长了 3%。
```

Anthropic 的示例将上下文放在原始 Chunk 前面，通常控制在约 50～100 Token。长度不是固定协议；目标是补齐文档、章节、实体、时间和指代语境，而不是让模型重写原文。

## 4. 两条上下文化建库路径

```text
原始文档
  ↓ 切分 Chunk
完整文档 + 当前 Chunk
  ↓ LLM 生成简短上下文
context + original_chunk
  ├─ Embedding Encoder → 向量索引      # Contextual Embeddings
  └─ 分词 → 倒排索引 / BM25            # Contextual BM25
```

普通 BM25 与 Contextual BM25 的差异只有被索引的内容：

```text
普通 BM25：      original_chunk → BM25 索引
Contextual BM25：context + original_chunk → BM25 索引
```

上下文化后，倒排索引中会增加 `ACME`、`2023`、`第二季度`、`财务报告` 等可搜索词项。标准 Lucene、Elasticsearch 或其他 BM25 实现仍可直接使用。

## 5. BM25 是多路召回，不是 Reranker

典型在线链路是：

```text
用户查询
  ├─ Contextual BM25 关键词召回
  └─ Contextual Embedding 语义召回
                 ↓
             合并候选集
                 ↓
           去重 / RRF 融合
                 ↓
       可选 Cross-Encoder / LLM Rerank
                 ↓
             Top-K Chunk
```

各阶段职责不同：

- **BM25**：稀疏检索召回通道，擅长专有名词、数字、代码与精确短语；
- **Embedding**：稠密检索召回通道，擅长同义表达和表面措辞不同的语义匹配；
- **融合算法**：合并不同通道的候选与排名；
- **Reranker**：对已经召回的较小候选集做更昂贵、更细粒度的相关性判断。

因此不能把典型结构理解成 `向量召回 → BM25 Rerank`。工程上可以把任意评分函数用于二次排序，但那不是 Anthropic Contextual Retrieval 描述的标准职责分工。

例如查询 `LangGraph 如何恢复中断任务`：BM25 可能命中包含 `LangGraph`、`恢复`、`任务` 的 Chunk；向量召回还可能命中 `检查点允许 Agent 在异常后继续执行`，即使它没有逐字出现查询短语。

## 6. RRF 融合

BM25 分数与向量相似度不在同一量纲，不能直接相加。Reciprocal Rank Fusion 使用名次融合：

$$
\operatorname{RRF}(d)=
\frac{1}{k+r_{\mathrm{BM25}}(d)}+
\frac{1}{k+r_{\mathrm{vector}}(d)}
$$

其中 $r(d)$ 是文档在相应召回列表中的名次，$k$ 是平滑常数。候选可能只出现在一路结果中，实际实现应把缺失通道视为无贡献，并在融合前后按稳定的 `chunk_id` 或 `parent_id` 去重。

## 7. 最小 Contextual BM25 示例

下面只展示 Contextual BM25。真实系统中的 `context` 应在离线建库时根据完整文档生成并持久化。

```python
from dataclasses import dataclass

import jieba
from rank_bm25 import BM25Okapi


@dataclass
class Chunk:
    chunk_id: str
    original_text: str
    context: str

    @property
    def contextualized_text(self) -> str:
        return f"{self.context}\n{self.original_text}"


def tokenize(text: str) -> list[str]:
    # 中文 BM25 需要分词，不能简单依赖空格。
    return [
        token.strip().lower()
        for token in jieba.cut_for_search(text)
        if token.strip()
    ]


chunks = [
    Chunk(
        chunk_id="revenue",
        context=(
            "该内容来自 ACME 公司 2023 年第二季度财务报告，"
            "描述本季度与上一季度之间的收入变化。"
        ),
        original_text="公司的收入较上一季度增长了 3%。",
    ),
    Chunk(
        chunk_id="hiring",
        context=(
            "该内容来自 ACME 公司 2023 年第二季度财务报告，"
            "描述公司的员工招聘情况。"
        ),
        original_text="本季度新增员工 120 人。",
    ),
]

corpus = [tokenize(chunk.contextualized_text) for chunk in chunks]
bm25 = BM25Okapi(corpus)
scores = bm25.get_scores(tokenize("ACME 公司 2023 年第二季度收入增长率"))

ranked_ids = sorted(range(len(chunks)), key=scores.__getitem__, reverse=True)
for index in ranked_ids:
    print(scores[index], chunks[index].chunk_id, chunks[index].original_text)
```

系统用 `contextualized_text` 检索，却仍保存并返回 `original_text`。补充文本提高可发现性，原始 Chunk 保留可引用的真实内容。

## 8. 与 metadata 的区别

假设存储：

```json
{
  "company": "ACME",
  "quarter": "2023 Q2",
  "text": "公司的收入较上一季度增长了 3%。"
}
```

如果 `company` 和 `quarter` 只是 metadata，BM25 默认不会自动把它们作为全文词项使用；必须显式配置查询字段或把字段内容加入索引。Contextual BM25 则把这些信息生成为可搜索文本。

两者也可以并用：

- metadata 保存结构化值，用于权限、租户、时间或类别过滤；
- 上下文说明补充自然语言语境，用于稀疏和稠密相关性检索。

## 9. 与 Late Chunking 的区别

两者都在解决小 Chunk 丢失上下文，但注入上下文的位置不同：

| 方法 | 怎样产生 Chunk 表示 | 是否生成补充文本 | 对 BM25 的影响 |
|---|---|---:|---|
| Contextual Retrieval | LLM 先生成上下文说明，再把它与原始 Chunk 一起编码 | 是 | 补充文本也可进入倒排索引 |
| Late Chunking | 长文先经过 Embedding Encoder，再按原 Chunk 边界池化 Token 向量 | 否 | 不会自然增加新的可检索词项 |

它们不是同一算法。Contextual Retrieval 改变输入文本，Late Chunking 改变向量生成时的编码与池化顺序；是否组合使用应以检索评估和建库成本为准。

## 10. 证据边界与工程约束

- LLM 生成的上下文可能出错，应把它视为**检索辅助文本**，不能自动当作回答证据；
- 索引记录应同时保存 `context`、`original_text`、`chunk_id`、`parent_id` 和来源信息，便于审计与回取；
- 最终回答引用原文，必要时回取父块核实，不把上下文说明中的新增事实直接输出；
- 为上下文生成过程做版本化与缓存，文档或 Prompt 变化时能够重建索引；
- 评估普通与上下文化方案的 Recall@K、MRR、nDCG、延迟、索引大小和生成成本，不只看最终答案；
- 生成的上下文若堆入无关关键词，会制造假召回，应限制长度并抽样检查实体与章节归属。

## 11. 你在讨论中的理解推进

- 起点：先理解 Contextual Retrieval 如何把文档级语境补到 Chunk 上，再建立 Contextual BM25。
- 第一次修正：BM25 不是这里的 Reranker；倒排索引负责从词项定位候选，BM25 使用词频等统计为候选打分。
- 最终确认：BM25 是多路召回中的稀疏通道，与 Embedding 稠密通道并行；融合发生在两路召回之后，Rerank 是可选的后续精排阶段。

## 12. 关联知识点

- [倒排索引与稀疏检索](../01_LLM_Transformer/12_倒排索引与稀疏检索.md)
- [稠密向量、稀疏向量与多向量表示及检索](../01_LLM_Transformer/11_稠密向量、稀疏向量与多向量表示及检索.md)
- [Bi-encoder、Cross Encoder 与重排](../01_LLM_Transformer/13_Bi-encoder、Cross_Encoder_与重排.md)
- [RAG 完整链路：召回、融合、重排、生成](18_RAG_完整链路：召回、融合、重排、生成.md)
- [Late Chunking：全文上下文化、Mean Pooling 与边界对齐](20_Late_Chunking：全文上下文化、Mean_Pooling_与边界对齐.md)
- [父子分块：层级切分、ID 映射与父块回取](19_父子分块：层级切分、ID_映射与父块回取.md)

## 13. 参考资料

- [Anthropic：Introducing Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
- [Apache Lucene：BM25Similarity](https://lucene.apache.org/core/9_12_3/core/org/apache/lucene/search/similarities/BM25Similarity.html)
- [Elasticsearch：Full-text search](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/full-text-search.html)
- [Elasticsearch：Re-ranking](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/re-ranking-overview.html)
