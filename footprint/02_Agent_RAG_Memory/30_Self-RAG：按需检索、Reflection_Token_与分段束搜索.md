# 02.30 Self-RAG：按需检索、Reflection Token 与分段束搜索

## 1. 总体性概念

Self-RAG 不是固定执行一次“检索 Top-K → 全部拼进 Prompt → 生成答案”，而是在生成过程中反复执行：

```text
判断是否需要检索
  → 检索多个 passage
  → 基于每个 passage 分别生成下一段候选
  → 用 Reflection Token 自我评价
  → 保留高分生成路径
  → 继续生成
```

核心有两点：

1. **按需检索**：问题或当前生成阶段不需要外部证据时可以跳过检索；
2. **边生成边反思**：模型评价文档相关性、生成内容的事实支持度和回答效用，并用这些信号指导解码。

先区分四个对象：

| 对象 | 含义 |
|---|---|
| `query` | 用户问题或指令 |
| `chunk / passage` | Retriever 返回的文档片段 |
| `segment` | 模型生成的一句话或一小段 continuation |
| `path` | 多个 segment 累积形成的回答路径 |

论文实验通常以句子为 segment，但生成单位在实现上可以调整。

## 2. 原理性解释

### 2.1 四类 Reflection Token

Self-RAG 把反思标签加入模型词表，由模型像生成普通 token 一样预测：

| 类型 | 评价问题 | 论文中的典型结果 |
|---|---|---|
| `Retrieve` | 当前是否需要检索 | Retrieve / No Retrieve / Continue |
| `IsRel` | 当前 passage 与输入是否相关 | Relevant / Irrelevant |
| `IsSup` | passage 是否支持生成 segment | Fully / Partially / No support |
| `IsUse` | 当前回答对任务是否有用 | 1～5 |

它们不是运行时由另一个评分服务返回的 JSON，而是最终 Generator 自己生成的特殊 token。模型输出在概念上可能类似：

```text
[Retrieval]
<paragraph>
公司 A 的年度收入为 100 亿元。
</paragraph>
[Relevant]
公司 A 的收入为 100 亿元。
[Fully supported]
[Utility:5]
```

### 2.2 评价对象不是单纯的 passage

若一次检索返回 `d1、d2、d3`，模型分别生成：

```text
query + history + d1 → y1
query + history + d2 → y2
query + history + d3 → y3
```

随后评价的是不同关系：

```text
IsRel：query / 当前任务 与 passage 的关系
IsSup：passage 与 candidate segment 的关系
IsUse：candidate segment 与 query 的关系
```

因此 Self-RAG 不是先给检索 Chunk 做一次统一排序，再返回分数最高的 Chunk。它为每个 passage 生成对应的候选 continuation，再对“passage + 候选 segment”进行多维评价。

一条内容可能真实且完全支持生成片段，但仍与当前问题无关：

```text
Query：比较公司 A、B 的收入
Passage：公司 A 成立于 2010 年
Segment：公司 A 成立于 2010 年

IsRel = Irrelevant
IsSup = Fully supported
IsUse = 2
```

### 2.3 Critic 与 Generator 的分工

训练阶段区分两个模型：

```text
Critic C：学习产生 Reflection Token 标签
Generator M：学习普通回答与 Reflection Token 的联合生成
```

最终推理只需要 Generator、Retriever 和解码逻辑，不需要单独运行 Critic。

#### 构造 Critic 训练数据

作者先用 GPT-4 为样本标注：是否需要检索、文档是否相关、回答是否有证据支持、回答是否有用。然后用这些标签训练 Critic：

```python
critic_input = {
    "query": query,
    "passage": passage,
    "answer": answer,
}

critic_target = [
    "[Retrieval]",
    "[Relevant]",
    "[Fully supported]",
    "[Utility:5]",
]
```

#### 用 Critic 标注 Generator 数据

Critic 与 Retriever 把普通指令—回答样本增强为：

```text
query
→ Retrieve token
→ passage
→ IsRel token
→ answer segment
→ IsSup token
→ IsUse token
```

每个 segment 若需要检索，就召回 passage，判断相关性与支持度，并插入对应反思标签。

#### 训练最终 Generator

Generator 仍使用标准 next-token prediction，同时学习：

```text
普通回答 token
+ Retrieve / IsRel / IsSup / IsUse token
```

检索到的 passage 作为上下文输入，但 passage token 对应的语言模型 loss 被 mask；模型要学习利用证据并生成回答与反思信号，而不是把外部 passage 当作需要预测的目标文本。

```python
loss = next_token_loss(
    tokens=[
        query,
        retrieve_token,
        passage,
        relevance_token,
        answer_segment,
        support_token,
        utility_token,
    ],
    masked_tokens=passage_tokens,
)
```

训练完成后，Generator 已能预测 Reflection Token，因此推理阶段不再调用 Critic。这不是 PPO，也不是每个解码步骤运行独立奖励模型。

### 2.4 候选分数来自生成概率与反思概率

候选分数可概括为：

```text
segment_score = generation_score
              + w_rel × relevance_score
              + w_sup × support_score
              + w_use × utility_score
```

反思项通常来自模型对某类 Reflection Token 的归一化概率，而不是仅把最终离散标签当作 0 或 1。例如：

```text
P(Relevant)   = 0.9
P(Irrelevant) = 0.1

relevance_score = 0.9 / (0.9 + 0.1)
```

权重可以在推理时调整：提高支持度权重会更强调证据一致性，提高效用权重会更强调回答任务完成度。还可同时采用：

```text
软约束：把 Reflection Token 概率加入分数
硬约束：例如直接丢弃 No support 候选
```

### 2.5 Segment-level Beam Search

若每一层只保留单个最高分 segment，早期一次错误就无法恢复。Self-RAG 使用 segment 级束搜索维护多个回答路径：

```text
K 个 passage
  ↓ K 个候选 segment
评分
  ↓ 保留 Top-B path
继续检索和生成下一层
  ↓ 再评分、再保留 Top-B
最后返回累计得分最高的完整 path
```

官方长文本推理示例默认 `beam_width=2`、`max_depth=6`；这些是参考实现参数，不是 Self-RAG 概念上的固定常量。

### 2.6 它不预先枚举 Chunk 排列组合

假设首轮召回 `chunk1、chunk2`：

```text
query + chunk1 → segment1_A → Path A
query + chunk2 → segment1_B → Path B
```

若两条路径都保留，下一轮分别基于各自历史再次决定是否检索，可能形成：

```text
Path A：chunk1 → segment1_A；chunk2 → segment2_A
Path B：chunk2 → segment1_B；chunk1 → segment2_B
```

形式上出现不同 Chunk 使用顺序，但原因是逐层扩展的 beam search，不是预先穷举：

```text
chunk1 → chunk2 → chunk3
chunk1 → chunk3 → chunk2
chunk2 → chunk1 → chunk3
……
```

每一层立即剪枝，只扩展当前 Top-B 路径，因此避免完整排列组合的指数级爆炸。

### 2.7 多个 Chunk 如何共同支撑答案

原始 Self-RAG 的一次候选 segment 通常基于：

```text
query + 已生成回答历史 + 当前一个 passage
```

而不是把所有 Top-K passage 同时拼接后生成一个候选。多个 Chunk 主要通过多个生成步骤进入最终答案：

```text
segment1(chunk1)
+ segment2(chunk2, previous_segments)
+ segment3(chunk3, previous_segments)
```

这适合不同证据分别支撑不同句子。对于必须同时读取多个原始 Chunk 才能在一个步骤内完成的复杂联合推理，历史中保留的是已生成文本而非全部原始证据，可能产生信息损失。这是生成结构带来的工程边界，不应把 Self-RAG 描述为天然解决所有多跳推理。

## 3. 机制流程

### 3.1 训练流程

```text
GPT-4 标注 Reflection Token 训练数据
  ↓
训练 Critic C
  ↓
Critic + Retriever 标注原始指令数据
  ↓
构造带 passage 与 Reflection Token 的样本
  ↓
训练 Generator M：普通 next-token prediction
  ↓
推理阶段不再需要 Critic C
```

### 3.2 推理流程

```text
输入 query + 已生成回答
  ↓
Generator 判断是否检索
  ├─ No Retrieval → 直接生成 segment
  └─ Retrieval
       ↓ Retriever 返回 K passages
       ↓ 每个 passage 生成一个候选 segment
       ↓ 生成 IsRel / IsSup / IsUse
       ↓ 计算候选分数
  ↓
Segment-level beam search 保留 Top-B paths
  ↓
回到“是否检索”继续生成
  ↓
结束 token 或达到最大深度
  ↓
返回最高累计分的完整路径
```

检索决策可由 `[Retrieval]` 概率阈值控制。无需检索的创作或常识型请求可以走 `[No Retrieval]` 分支；需要检索时，检索 Query 可以结合原问题与当前回答历史。论文实验使用 Contriever，官方仓库示例使用 `facebook/contriever-msmarco`，但框架并不绑定某一个检索器。

## 4. 类比理解

Self-RAG 像边写报告边查资料：每写一段前判断是否需要查证；若查到多份资料，就分别尝试写下一段，评价资料相关性、文字是否被资料支持、这段是否真正回答问题；随后保留几条最有前景的报告草稿继续写，而不是一开始枚举所有资料顺序。

## 5. 应用举例 / 代码或伪代码

### 5.1 两轮分段束搜索

Query：

```text
比较公司 A 和公司 B 的收入，并说明谁更高。
```

首轮 Passage：

```text
chunk1：公司 A 收入为 100 亿元。
chunk2：公司 B 收入为 80 亿元。
chunk3：公司 A 成立于 2010 年。
```

生成并评分：

```text
Path A：[公司 A 收入为 100 亿元] score=8.5
Path B：[公司 B 收入为 80 亿元]  score=8.2
Path C：[公司 A 成立于 2010 年]  score=4.0
```

`beam_width=2` 时保留 A、B。第二轮从两条历史分别检索并生成，可能都得到“公司 A 比 B 高 20 亿元”，再按累计分保留最佳完整路径。

### 5.2 等价推理伪代码

```python
beams = [
    {
        "text": "",
        "score": 0.0,
        "finished": False,
    }
]

for step in range(max_depth):
    expanded = []

    for beam in beams:
        if beam["finished"]:
            expanded.append(beam)
            continue

        need_retrieval = model.predict_retrieval(
            query=query,
            history=beam["text"],
        )

        if not need_retrieval:
            segment = model.generate_without_context(
                query=query,
                history=beam["text"],
            )
            expanded.append({
                "text": beam["text"] + segment.text,
                "score": beam["score"] + segment.score,
                "finished": segment.finished,
            })
            continue

        passages = retriever.search(
            query=query,
            history=beam["text"],
            top_k=top_k,
        )

        for passage in passages:
            candidate = model.generate_with_context(
                query=query,
                history=beam["text"],
                passage=passage,
            )

            score = (
                candidate.generation_score
                + w_rel * candidate.relevance_score
                + w_sup * candidate.support_score
                + w_use * candidate.utility_score
            )

            if candidate.no_support and hard_filter:
                continue

            expanded.append({
                "text": beam["text"] + candidate.segment,
                "score": beam["score"] + score,
                "finished": candidate.finished,
            })

    beams = sorted(
        expanded,
        key=lambda item: item["score"],
        reverse=True,
    )[:beam_width]

answer = max(beams, key=lambda item: item["score"])["text"]
```

这段代码是对论文算法的等价伪代码，不是官方仓库源码的逐行复制。

## 6. 你在讨论中的理解推进

- 起点：把 Self-RAG 理解为“为召回 Chunk 打分，然后选择最高分 Chunk”。
- 第一次修正：每个 passage 会产生一个对应的候选 segment；相关性、支持度和效用评价围绕 passage 与候选输出的不同关系展开。
- 第二次推进：后续可能出现 `chunk1 → chunk2` 与 `chunk2 → chunk1` 两条生成路径，但不是预先做全排列，而是每层扩展、评分和剪枝。
- 完整理解：Self-RAG 同时维护单个 segment 的评价和整条 path 的累计分数，通过按需检索与 segment-level beam search 逐步完成回答。

## 7. 常见误区与排查思路

- **误区：Self-RAG 只给 Passage 打分。** 实际还评价 passage 对 segment 的支持度以及 segment 对任务的效用。
- **误区：每轮把 Top-K 全部拼接后只生成一个候选。** 原论文算法按 passage 生成 continuation candidates。
- **误区：先穷举所有 Chunk 顺序再择优。** 实际是逐层 beam search 与即时剪枝。
- **误区：推理阶段仍要运行 Critic。** Critic 用于训练数据标注；最终 Generator 已学习 Reflection Token。
- **误区：Reflection Token 是额外 JSON 评分。** 它们是扩展词表中的生成 token，其概率参与解码。
- **误区：Self-RAG 自动解决复杂多跳推理。** 单步只看到当前 passage，跨步主要依赖生成历史，可能损失原始证据细节。
- **排查：** 记录检索触发概率、每轮 passages、Reflection Token 概率、候选分项分数、剪枝原因、路径累计分和停止原因。

## 8. 关联知识点

- [RAG 完整链路：召回、融合、重排、生成](18_RAG_完整链路：召回、融合、重排、生成.md)
- [ReAct 提前终止检测](08_ReAct_提前终止检测.md)
- [Reflection、Insight 与执行后反思](13_Reflection、Insight_与执行后反思.md)
- [Query Rewrite、HyDE 与 Multi-Query 对比](25_Query_Rewrite、HyDE_与_Multi-Query_对比.md)
- [RAGAS 评估指标与 Ground Truth 来源](26_RAGAS_评估指标与_Ground_Truth_来源.md)

## 9. 参考资料与事实边界

- [Self-RAG 论文：Learning to Retrieve, Generate, and Critique through Self-Reflection](https://arxiv.org/pdf/2310.11511)
- [Self-RAG 官方代码仓库](https://github.com/AkariAsai/self-rag)
- [论文的结构化阅读页](https://www.alphaxiv.org/abs/2310.11511)

Reflection Token 类型、训练数据构造和分段束搜索来自论文与官方仓库。本文分数函数和 Python 控制流是为说明数据流而写的等价伪代码。`beam_width=2`、`max_depth=6` 是官方长文本参考实现中的默认配置，不是算法定义要求的固定值；不同版本与任务应以源码和评估结果为准。

## 10. 复习检查问题

1. `passage`、`segment` 与 `path` 分别是什么？
2. `IsRel`、`IsSup` 与 `IsUse` 的评价对象有何不同？
3. Critic 为什么在训练阶段需要，而推理阶段不需要？
4. Passage token 的训练 loss 为什么要 mask？
5. Segment score 如何结合生成概率与 Reflection Token 概率？
6. 为什么 segment-level beam search 不等于 Chunk 全排列？
7. 多个 Chunk 如何通过多个 segment 共同进入最终答案？
8. Self-RAG 在复杂多跳联合推理中可能有什么信息损失？
