# 02.20 Late Chunking：全文上下文化、Mean Pooling 与边界对齐

## 1. 总体性概念

传统 Chunk Embedding 先切文本，再让每个 Chunk 独立进入 Embedding 模型：

```text
文档
  → 切成 C1、C2、C3
  → 每个 Chunk 独立执行 Transformer + Pooling
  → 得到 e1、e2、e3
```

Late Chunking 先让整篇文档或一个长文档窗口完成 Transformer 编码，再按 Chunk 对应的 Token 区间分别池化：

```text
整篇文档
  → Tokenizer
  → 全部 Token 一起进入长上下文 Embedding 模型
  → 每个 Token 的全文上下文化向量
  → 按 Chunk Token 区间分别 Mean Pooling
  → 得到 e1、e2、e3
```

“Late”不是最后才决定在哪里切文本，而是 **Chunk 边界在 Transformer 之后、Pooling 之前才作用于最终向量生成**。边界可以提前计算，但不会先把 Chunk 分开送入 Transformer。

Late Chunking 没有把整篇文档压成一个向量后再拆分，也没有取消 Chunk。它改变的是 Chunk 向量的生成方式：属于某个 Chunk 的 Token 向量在池化前已经看过更大的文档上下文。

## 2. 原理性解释

### 2.1 传统独立编码会丢失跨 Chunk 语境

假设原文为：

```text
C1：柏林是德国的首都。
C2：它拥有超过 385 万居民。
C3：这座城市同时也是德国的一个州。
```

传统方式分别编码：

```python
e1 = embedding_model.encode("柏林是德国的首都。")
e2 = embedding_model.encode("它拥有超过 385 万居民。")
e3 = embedding_model.encode("这座城市同时也是德国的一个州。")
```

模型处理 C2 时看不到 C1，“它”的上下文化表示无法利用前文中的“柏林”；处理 C3 时也无法从前文继承实体主题。这会削弱代词指代、实体继承、章节主题和相邻段落依赖。

### 2.2 Transformer 输出不是“一个文档向量”

Token 在 Transformer 之前由 Tokenizer 产生；Transformer 之后得到的是每个 Token 对应的上下文化隐藏向量：

```text
文本
  → Tokenizer
  → Token / token_id
  → Transformer
  → 每个 Token 一个上下文化向量
```

设整篇文档包含 `L` 个 Token，隐藏维度为 `d`：

```text
H = Transformer(x1, x2, ..., xL)
H.shape = [L, d]
H = [h1, h2, ..., hL]
```

例如：

```text
输入：1000 个 Token
隐藏维度：768
Transformer 输出：[1000, 768]

Chunk 区间：
[(0, 200), (200, 400), (400, 650), (650, 1000)]

分段池化后：
[4, 768]
```

最终向量库通常仍只保存 4 个 Chunk 向量，而不保存 1000 个 Token 隐藏向量。Token-level hidden states 只在建库计算期间临时存在。

### 2.3 Mean Pooling：把可变数量的 Token 向量聚合成固定维度

假设一个 Chunk 有 `n` 个 Token，每个 Token 的上下文化向量为 `h_i ∈ R^d`，Mean Pooling 逐维求平均：

```text
v_chunk = (1 / n) Σ_i h_i
```

例如三个 4 维 Token 向量：

```python
import torch

token_embeddings = torch.tensor([
    [1.0, 2.0, 3.0, 4.0],
    [2.0, 4.0, 6.0, 8.0],
    [3.0, 6.0, 9.0, 12.0],
])

chunk_embedding = token_embeddings.mean(dim=0)

assert token_embeddings.shape == (3, 4)
assert chunk_embedding.shape == (4,)
assert chunk_embedding.tolist() == [2.0, 4.0, 6.0, 8.0]
```

`dim=0` 表示沿 Token 数量这一维聚合：

```text
[chunk_token_count, hidden_size]
             ↓ mean(dim=0)
[hidden_size]
```

求平均的不是 token id、字符或 Token 文本，而是 Transformer 已经生成的上下文化向量。Jina 官方实现中的核心计算：

```python
embeddings[start:end].sum(dim=0) / (end - start)
```

与下面的写法数学等价：

```python
embeddings[start:end].mean(dim=0)
```

普通 Embedding 模型的“文本 → 一个向量”内部也常包含 Transformer、Pooling、可选投影层和归一化。Late Chunking 的区别是对多个 Token 子区间分别池化。

### 2.4 Chunk 文本与 Chunk Embedding 是两条并行线路

Chunk 文本不是从隐藏向量中恢复出来的，而是在分块时从原文范围直接保留：

```text
文本线路：
原始文档
  → 字符边界切片
  → Chunk 文本
  → 保存为向量记录的 text 字段，命中后返回给 LLM

向量线路：
原始文档
  → Tokenizer
  → 整体 Transformer
  → Token 上下文化向量
  → 按 Token 边界分组
  → 每组 Mean Pooling
  → Chunk Embedding
```

两条线路通过同一个 `chunk_id` 和边界记录合并：

```python
record = {
    "chunk_id": "C2",
    "text": "它拥有超过385万居民。",
    "char_span": (10, 23),
    "token_span": (6, 12),
    "embedding": [0.013, -0.284, ...],
}
```

下面的设想确实多此一举，而且会退化为传统独立分块：

```text
全文 Transformer
  → Token 向量
  → 映射回 Chunk 文本
  → 每个 Chunk 再进一次 Transformer
```

第二次单独编码时，Chunk 又看不到全文语境。正确流程是在第一次得到的上下文化 Token 向量上直接做分段 Mean Pooling。

### 2.5 Mean Pooling 有效依赖 Embedding 训练

Mean Pooling 本身只是算术平均。它能形成适合检索的文本向量，是因为 Embedding 模型经过对比学习或检索目标训练，使相似文本的池化向量靠近。不能随便拿任意生成模型的隐藏状态求平均，就假设一定得到高质量 Embedding。

标准 Late Chunking 通常要求：

- 模型支持足够长的上下文；
- 能访问 Pooling 前的 Token-level hidden states；
- 模型支持或适合对局部 Token 表示做 Mean Pooling；
- 模型已针对语义检索训练，且遵循其查询前缀、任务指令、池化和归一化规则。

如果服务 API 只返回一个最终向量：

```json
{"embedding": [0.1, 0.2, 0.3]}
```

并且不提供 Late Chunking 参数或 Token hidden states，客户端不能把这个最终文档向量重新切成多个 Chunk 向量。

## 3. 机制流程

### 3.1 字符边界不天然等于 Token 边界

中文一个字可能对应一个 Token、多个字合成一个 Token，或一个生僻字/Emoji 被拆成多个 Token；空格、标点和规范化也会影响边界。

假设原文为：

```text
人工智能技术
```

某个 Tokenizer 可能得到：

```python
tokens = [
    ("人工", (0, 2)),
    ("智能", (2, 4)),
    ("技术", (4, 6)),
]
```

字符区间 `(0, 4)` 可以精确映射到 Token 区间 `(0, 2)`。但字符区间 `(0, 1)` 只想取“人”，边界却落在 Token“人工”的内部；不存在只表示“人”的那一半 Token 向量。

所以可靠实现不能假设：

```text
字符索引 == Token 索引
```

而应使用目标 Tokenizer 的 `offset_mapping` 保存：

```text
Token i ↔ 原文字符区间 [start_i, end_i)
```

### 3.2 用 `offset_mapping` 建立两套边界

Hugging Face Fast Tokenizer 可以返回字符范围：

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained(
    "model-name",
    use_fast=True,
)

text = "人工智能技术"
encoded = tokenizer(
    text,
    add_special_tokens=False,
    return_offsets_mapping=True,
)

tokens = tokenizer.convert_ids_to_tokens(encoded["input_ids"])

for index, (token, (start, end)) in enumerate(
    zip(tokens, encoded["offset_mapping"])
):
    print(index, token, (start, end), repr(text[start:end]))
```

Chunk 记录应同时维护：

```python
chunk = {
    "char_span": (0, 4),
    "token_span": (0, 2),
}
```

如果边界已经对齐，可以直接取出对应文本和 Token 向量：

```python
char_start, char_end = 2, 6
token_start, token_end = 1, 3

chunk_text = text[char_start:char_end]              # 智能技术
chunk_tokens = token_embeddings[token_start:token_end]
chunk_embedding = chunk_tokens.mean(dim=0)
```

### 3.3 边界落在 Token 内部时必须选择策略

对于候选边界 `1` 和 Token“人工”覆盖的 `[0, 2)`，不存在完美映射。可选策略包括：

1. **跨界 Token 分给左 Chunk**：把边界向右吸附到 `2`；
2. **跨界 Token 分给右 Chunk**：把边界向左吸附到 `0`；
3. **两侧都包含跨界 Token**：允许 Token overlap，保留更多语义但引入重复；
4. **Token 原生分块**：先 Tokenize，只在合法 Token 间隙处分块，再由 offset 反推文本；这是最干净的方案。

生产实现应先收集所有全局候选字符边界，再统一映射到 Token 间隙。不能对每个 Chunk 的起点和终点独立采用不一致规则，否则容易产生遗漏、重叠或不连续区间。

下面把落在 Token 内部的 Token 整体分给左 Chunk：

```python
from bisect import bisect_left
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenSpan:
    token_start: int
    token_end: int


def char_boundary_to_token_boundary(
    char_boundary: int,
    offsets: list[tuple[int, int]],
) -> int:
    """
    假设 offsets 已排除特殊 Token 的 (0, 0)，并按原文顺序排列。
    返回 Token 间隙 k：
    左侧 Token 为 [0:k)，右侧 Token 为 [k:n)。
    若字符边界落入 Token 内部，将该 Token 整体分给左侧。
    """
    token_starts = [start for start, _ in offsets]
    return bisect_left(token_starts, char_boundary)


def char_spans_to_token_spans(
    char_spans: list[tuple[int, int]],
    offsets: list[tuple[int, int]],
) -> list[TokenSpan]:
    if not char_spans:
        return []

    char_boundaries = [char_spans[0][0]]
    char_boundaries.extend(end for _, end in char_spans)

    token_boundaries = [
        char_boundary_to_token_boundary(boundary, offsets)
        for boundary in char_boundaries
    ]

    return [
        TokenSpan(token_boundaries[i], token_boundaries[i + 1])
        for i in range(len(char_spans))
    ]
```

边界吸附后，原始字符 Chunk 可能已经改变，必须从调整后的 Token 区间反推实际字符范围：

```python
def token_span_to_char_span(
    token_start: int,
    token_end: int,
    offsets: list[tuple[int, int]],
) -> tuple[int, int]:
    if token_start >= token_end:
        raise ValueError("空 Token 区间")

    return offsets[token_start][0], offsets[token_end - 1][1]
```

不能继续保存“文本是‘人’，向量却由 Token‘人工’得到”这种不一致记录。最终必须严格保持：

```text
Chunk 文本
  ↕
调整后的 char_span
  ↕
token_span
  ↕
Chunk Embedding
```

### 3.4 一个字符被拆成多个 Token

生僻字符、Emoji 或 byte-level BPE 可能让多个 Token 对应同一或重叠字符范围：

```python
offsets = [
    (0, 1),
    (0, 1),
    (0, 1),
]
```

这些 Token 共同表示同一原始片段，边界不能切在其中。映射后应检查 Token 边界两侧的 offset 是否重叠：

```python
def boundary_splits_same_character(
    token_boundary: int,
    offsets: list[tuple[int, int]],
) -> bool:
    if token_boundary <= 0 or token_boundary >= len(offsets):
        return False

    left_start, left_end = offsets[token_boundary - 1]
    right_start, right_end = offsets[token_boundary]

    return left_start < right_end and right_start < left_end
```

若返回 `True`，应继续按统一策略移动边界，直到不再拆开同一字符或规范化片段对应的 Token 组。

### 3.5 Fixed、Sentence 与 Semantic 三类边界

Jina 官方实现提供 `fixed`、`sentences` 和 `semantic` 等策略：

- **Fixed Chunking**：直接按 Token 索引每 `chunk_size` 个切分，天然位于 Token 间隙；
- **Sentence Chunking**：在 Token 序列中寻找句号、问号和感叹号等句末标记，再以 Token 位置建立区间；
- **Semantic Chunking**：语义分块器先产生字符位置，再利用 `offset_mapping` 和二分查找转换成 Token 范围。

```python
# Fixed：直接在 Token 空间切分
for start in range(0, len(token_offsets), chunk_size):
    end = min(start + chunk_size, len(token_offsets))
    chunk_spans.append((start, end))

# Sentence：检测到句末 Token 时关闭当前区间
if token_id in sentence_end_token_ids:
    chunk_spans.append((chunk_start, token_index + 1))
    chunk_start = token_index + 1
```

句号、换行、Markdown 标题、段落、空格和语义节点等边界通常比任意字符位置更容易对齐，但“通常”不等于理论保证，仍应显式检查。

```python
def is_exact_token_boundary(
    char_boundary: int,
    offsets: list[tuple[int, int]],
) -> bool:
    valid_boundaries = {0}
    for start, end in offsets:
        valid_boundaries.update((start, end))
    return char_boundary in valid_boundaries
```

## 4. 类比理解

传统 Chunk Embedding 像把书的一页页撕开后，让读者分别理解；代词“它”和短语“这座城市”可能失去前文对象。

Late Chunking 像先让读者读完整章，再为每一页写摘要。每页最终仍有独立摘要，但摘要来自读完整章后的上下文化理解。

Mean Pooling 则像把属于这一页的所有 Token 注释按维度求平均，形成固定长度的页摘要向量。原页文本一直保存在原文里，不需要从摘要向量逆向恢复。

## 5. 应用举例 / 代码或伪代码

### 5.1 完整的建库核心流程

```python
from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn.functional as F


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    char_start: int
    char_end: int
    token_start: int
    token_end: int


def masked_mean(
    token_embeddings: torch.Tensor,
    attention_mask: torch.Tensor,
) -> torch.Tensor:
    mask = attention_mask.unsqueeze(-1).to(token_embeddings.dtype)
    summed = (token_embeddings * mask).sum(dim=0)
    count = mask.sum(dim=0).clamp(min=1e-9)
    return summed / count


@torch.inference_mode()
def build_late_chunk_records(
    document: str,
    chunks: list[Chunk],
    tokenizer,
    model,
) -> list[dict]:
    encoded = tokenizer(
        document,
        return_tensors="pt",
        add_special_tokens=True,
        return_offsets_mapping=True,
        truncation=True,
        max_length=model.config.max_position_embeddings,
    )

    offsets = encoded.pop("offset_mapping")[0].tolist()
    outputs = model(**encoded)

    # [batch, token_count, hidden_size] → [token_count, hidden_size]
    token_embeddings = outputs.last_hidden_state[0]
    attention_mask = encoded["attention_mask"][0]

    records = []
    for chunk in chunks:
        start, end = chunk.token_start, chunk.token_end
        current_tokens = token_embeddings[start:end]
        current_mask = attention_mask[start:end]

        if current_tokens.shape[0] == 0:
            raise ValueError(f"{chunk.chunk_id} 没有对应 Token")

        chunk_embedding = masked_mean(current_tokens, current_mask)

        # 是否归一化必须服从模型官方接口。
        chunk_embedding = F.normalize(chunk_embedding, p=2, dim=0)

        records.append({
            "chunk_id": chunk.chunk_id,
            "text": chunk.text,
            "embedding": chunk_embedding.cpu().tolist(),
            "metadata": {
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "token_start": start,
                "token_end": end,
            },
        })

    return records
```

真实实现需要保证 `chunks` 的 Token 索引与 `add_special_tokens` 的策略一致。`[CLS]`、`[SEP]`、`[PAD]` 和 `(0, 0)` offset 不应无条件参与 Chunk 平均；批处理时还必须使用 `attention_mask` 排除 Padding。

### 5.2 建库变化，查询流程基本不变

```text
建库：
Document
  → 长上下文 Transformer
  → 分段 Pooling
  → Chunk Vectors
  → Vector DB

查询：
Query
  → Query Embedding
  → ANN / cosine similarity
  → 命中 Chunk
  → 返回 Chunk 文本给 LLM
```

Late Chunking 主要改变文档索引阶段的 Chunk 向量生成，不要求更换向量数据库。查询通常较短，也不需要切块。

```python
query_vector = embedding_model.encode("柏林有多少人口？")
similarities = chunk_vectors @ query_vector
```

### 5.3 与父子分块可以组合

[父子分块：层级切分、ID 映射与父块回取](19_父子分块：层级切分、ID_映射与父块回取.md) 先切父块，再在每个父块内部切子块；子块在入库时记录 `parent_id`。它解决：

```text
用小 Chunk 检索
  → 命中 child_id
  → 通过 parent_id 返回更大父块
```

Late Chunking 解决：

```text
整篇文档或父块产生 Token 上下文化向量
  → 按子块范围池化
  → 子块向量包含更完整的上文语境
```

二者可以组合：

```text
父块/长文档窗口整体编码
  → 子块范围 Late Pooling
  → 用子块向量精确检索
  → 根据 parent_id 返回更完整父块
```

这同时获得子块精确召回、上下文化表示和更完整的生成上下文，但仍需控制 `parent_id` 去重、父块排序和 token budget。父子映射的建库、存储、回取与排查细节统一放在独立的 `025` 中，本篇只保留二者的边界和组合方式。

## 6. 你在讨论中的理解推进

- 起点：你先把 Late Chunking 理解为“全文得到若干 Token/向量，按区间分组后是否要恢复文本并再次向量化”。
- 术语修正：Token 在 Transformer 前产生；Transformer 后得到的是每个 Token 的上下文化向量。
- 关键推进：Mean Pooling 直接把一组 Token 向量变成最终 Chunk Embedding，不需要恢复文本再编码；Chunk 文本由原文字符范围独立保留。
- 边界追问：你指出中文一个字未必对应一个 Token，因此初始字符边界不能天然等于 Token 边界。
- 最终连接：候选字符边界必须通过 `offset_mapping` 映射或吸附到合法 Token 间隙，再由调整后的 Token 边界反推实际 Chunk 文本，确保文本、字符范围、Token 范围和向量一致。

## 7. 限制、误区与排查思路

### 7.1 主要限制

- **文档不能无限长**：超出模型上下文时，需要先切成较大的窗口，再在窗口内 Late Chunking；此时 Chunk 只能获得窗口范围内的上下文。Long Late Chunking 是面向超长文档的扩展方向。
- **长序列计算可能更贵**：标准全注意力的矩阵规模近似为 `L × L`。8 个 512 Token Chunk 的传统计算近似 `8 × 512²`，一次 4096 Token 的全文注意力近似 `4096²`；显存和速度取决于模型、批大小、Flash Attention 等实现，不能假设 Late Chunking 必然更快。
- **模型接口有要求**：只返回最终单向量的 API 无法在客户端实现标准 Late Chunking。
- **不是万能上下文修复**：它不能保证边界合理、远距离注意力一定有效、固定维度向量保存全部信息、检索一定正确或生成一定忠实。
- **不替代 RAG 其它环节**：仍需要合理分块、混合检索、父文档去重、重排序、权限过滤、上下文构建和回答验证。

### 7.2 与传统方式的边界对比

| 对比项 | 传统 Chunk Embedding | Late Chunking |
| --- | --- | --- |
| Transformer 输入 | 每个 Chunk 独立输入 | 整篇文档或长窗口输入 |
| Chunk 边界作用位置 | Transformer 之前 | Transformer 之后、Pooling 之前 |
| Token 是否能利用其它 Chunk | 否 | 能，在模型有效上下文范围内 |
| 每个 Chunk 最终向量 | 1 个 | 通常仍为 1 个 |
| 最终向量维度 | `d` | `d` |
| 向量库存储量 | `n` 个 Chunk 向量 | 通常仍为 `n` 个 Chunk 向量 |
| 是否要求长上下文模型 | 否 | 是 |
| 是否替代分块器 | 否 | 否 |
| 是否需要额外生成式 LLM | 否 | 否 |
| 是否自动返回父级上下文 | 否 | 否 |

### 7.3 常见误区

- **全文先变成一个向量，再把向量切开**：最终单向量没有文本位置轴，不能还原多个 Chunk。
- **Late Chunking 不需要分块器**：它仍需要 boundary cues，只是边界在池化阶段作用。
- **一个字符等于一个 Token**：必须使用目标 Tokenizer 的 offset。
- **字符边界和 Token 边界分别独立取整**：可能造成遗漏或重叠，应映射全局边界序列。
- **边界吸附后仍保存原始 Chunk 文本**：文本与向量语义不一致，应反推并保存调整后的字符范围。
- **对所有 hidden states 直接平均**：要排除 Padding、特殊 Token 和不属于当前 Chunk 的位置。
- **任意 Transformer 隐藏状态都适合检索**：必须服从 Embedding 模型的训练目标与官方池化规则。

建议按以下顺序排查：

```text
模型是否支持长上下文和 Token hidden states
  → Tokenizer、特殊 Token 与 offset 是否一致
  → 全局边界是否连续且合法
  → 是否切开重叠 offset 的 Token 组
  → 文本、char_span、token_span 是否一致
  → Pooling 是否正确应用 mask
  → 向量归一化和查询前缀是否服从模型要求
  → 领域 Recall@K 是否真的改善
```

## 8. 关联知识点

- [Token、Embedding、Seq Len 与 Hidden Size](../01_LLM_Transformer/02_Token、Embedding、Seq_Len_与_Hidden_Size.md)
- [稠密向量、稀疏向量与多向量表示及检索](../01_LLM_Transformer/11_稠密向量、稀疏向量与多向量表示及检索.md)
- [Bi-encoder、Cross Encoder 与重排](../01_LLM_Transformer/13_Bi-encoder、Cross_Encoder_与重排.md)
- [RAG 完整链路：召回、融合、重排、生成](18_RAG_完整链路：召回、融合、重排、生成.md)
- [RAGAS 评估指标与 Ground Truth 来源](26_RAGAS_评估指标与_Ground_Truth_来源.md)
- [父子分块：层级切分、ID 映射与父块回取](19_父子分块：层级切分、ID_映射与父块回取.md)
- [Contextual Retrieval：Contextual Embeddings、Contextual BM25 与多路召回](21_Contextual_Retrieval：Contextual_Embeddings、Contextual_BM25_与多路召回.md)

## 9. 参考资料与复习问题

### 参考资料

- [Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models](https://arxiv.org/abs/2409.04701)
- [Jina AI Late Chunking 官方仓库：chunked pooling](https://github.com/jina-ai/late-chunking/blob/main/chunked_pooling/__init__.py)
- [Jina AI Late Chunking 官方仓库：边界策略](https://github.com/jina-ai/late-chunking/blob/main/chunked_pooling/chunking.py)
- [Jina AI：What Late Chunking Really Is and What It’s Not](https://jina.ai/news/what-late-chunking-really-is-and-what-its-not-part-ii/)
- [Jina Embeddings v3：Late Chunking 与 Pooling 讨论](https://huggingface.co/jinaai/jina-embeddings-v3/discussions/108)
- [Hugging Face Tokenizers：Encoding 与 offsets API](https://huggingface.co/docs/tokenizers/python/latest/api/reference.html)
- [Hugging Face Tokenizers：Pipeline 与对齐跟踪](https://huggingface.co/docs/tokenizers/python/latest/pipeline.html)
- [本次技术讨论记录](https://chatgpt.com/share/6a6b66aa-f208-83ec-a530-74a18a19083b)

### 复习检查问题

1. Late Chunking 的“Late”具体发生在 Transformer、边界和 Pooling 的哪个位置？
2. 为什么全文 Transformer 输出是 `[L, d]`，而不是一个可再次切分的 `[d]` 文档向量？
3. Mean Pooling 为什么不需要把 Token 向量恢复为文本再编码？
4. 字符边界落在多字符 Token 内部时有哪些处理策略？
5. 为什么边界吸附后必须重新生成实际 Chunk 文本？
6. 一个字符被拆成多个 Token 时，怎样防止切开同一字符的 Token 组？
7. Late Chunking 与父子分块分别解决什么问题，怎样组合？
8. 为什么 Late Chunking 不一定比传统分块更快，也不能替代 RAG 的其它环节？
