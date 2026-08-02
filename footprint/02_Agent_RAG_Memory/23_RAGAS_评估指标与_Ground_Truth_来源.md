# 02.23 RAGAS 评估指标与 Ground Truth 来源

## 1. 总体性概念

一个典型 RAG 评估样本包含：

```python
{
    "question": "Kafka offset 属于什么粒度？",
    "retrieved_contexts": ["..."],
    "answer": "offset 是 partition 内的位置……",
    "ground_truth": "offset 标识 partition 日志中的位置；不同 consumer group 维护各自消费进度。"
}
```

> 版本注记：`question / retrieved_contexts / answer / ground_truth` 是 RAGAS 0.1 时代的列名；RAGAS 0.2+ 使用 `SingleTurnSample`，对应字段为 `user_input / retrieved_contexts / response / reference`。

四个字段的来源不同：

| 字段 | 含义 | 通常来源 |
| --- | --- | --- |
| Question | 用户问题/测试问题 | 真实日志、人工设计、数据集、合成问题 |
| Retrieved Contexts | RAG 实际召回的文档片段 | 被测检索链路运行结果 |
| Answer | 被测系统生成的回答 | RAG 应用输出 |
| Ground Truth / Reference | 经过验证的参考答案 | 人工/专家/已有数据集/审核后的合成答案 |

Ground Truth 不是从本次被测 Answer 自动复制出来的。否则相当于拿系统自己的输出作为标准，无法判断对错。

## 2. 原理性解释

### 2.1 RAG 评估必须区分“检索质量”和“生成质量”

最终答案失败可能有两类原因：

```
A. 正确证据没有被检索出来
B. 正确证据已经存在，但模型没有忠实使用
```

因此指标要分别观察：

- contexts 是否包含需要的信息；
- contexts 的排序是否合理；
- answer 是否由 contexts 支持；
- answer 是否真正回答 question；
- answer 与 reference 是否覆盖相同关键事实。

### 2.2 Ground Truth 从哪里来

#### 方式一：领域专家人工编写

质量最高，适合医疗、法律、金融、企业制度等高要求场景。专家不仅写答案，还可标注必要事实、可接受变体和引用来源。

#### 方式二：已有 QA 数据集

公开数据集或企业既有测试集已经提供 question-answer 对，可以直接转成评估样本。但必须确认答案仍适用于当前知识库版本。

#### 方式三：从权威文档构造

人工从一段确定的文档中设计问题并写参考答案，同时保存 reference contexts。这种方式便于计算 context recall 和做定位分析。

#### 方式四：历史业务标准回复

客服知识库、内部 SOP、审核通过的专家回复可作为参考答案，但要清洗过期版本和不一致答案。

#### 方式五：LLM 合成 + 人工审核

用高质量模型从权威文档生成问题和参考答案，再由人工抽检或全量审核。它适合扩大测试集，但未经审核的合成答案不应被视为绝对真值。

### 2.3 没有 Ground Truth 能不能评估

可以评估一部分指标。例如 Faithfulness 主要检查回答中的声明是否被 retrieved contexts 支持；Answer Relevancy 主要判断回答是否切题。这些指标可由模型评审，不一定依赖 reference answer。

但 Context Recall 或答案事实覆盖类指标通常需要 reference answer/reference contexts，因为系统需要知道“哪些必要信息本来应该被召回或回答”。

因此，RAGAS 并非所有指标都强制使用相同字段。具体字段名和计算实现可能随版本变化，但概念边界不变：**有些指标是无参考评估，有些指标需要参考答案。**

### 2.4 常见指标的核心思想

#### Faithfulness（忠实度）

把 answer 拆成若干事实声明，检查每条声明是否能从 retrieved contexts 推出：

```
Faithfulness ≈ 被上下文支持的回答声明数 / 回答声明总数
```

它主要识别“模型是否在证据之外编造”。

#### Answer Relevancy（回答相关性，现行文档名为 Response Relevancy）

判断回答是否围绕 question，是否遗漏主题或包含大量无关内容。某些实现会从 answer 反向生成可能的问题，再与原问题计算相似度。

#### Context Precision（上下文精确率/排序质量）

检查检索到的片段中有多少真正有用，以及相关片段是否排在前面。topK 中充满无关 chunk 会降低该指标。

#### Context Recall（上下文召回率）

以 reference answer 中的必要事实为基准，检查 retrieved contexts 是否包含支持这些事实的信息：

```
Context Recall ≈ 能被检索上下文覆盖的参考事实 / 参考事实总数
```

它回答的是：“应该找到的证据是否找齐了？”

### 2.5 LLM-as-a-Judge 不是客观测量仪

RAGAS 常借助 LLM 做事实拆分、蕴含判断和相关性评分。评审模型也会有偏差：

- 对长上下文遗漏；
- 对措辞差异敏感；
- 自身知识干扰证据判断；
- 同一输入多次评分波动。

因此重要评估集要配合人工抽检、固定评审模型和 prompt、记录版本，并结合传统 IR 指标（Recall@K、MRR、nDCG）。

## 3. 机制流程

### 3.1 建立评估集

```
权威文档 / 真实业务问答
  ↓ 选取代表性问题
  ↓ 编写或审核 reference answer
  ↓ 可选：标注 reference contexts / 必要事实
  ↓ 固化为版本化 evaluation dataset
```

### 3.2 运行被测 RAG

```
question
  ↓ 当前检索链路
retrieved_contexts
  ↓ 当前生成链路
answer
  ↓ 指标计算与人工抽检
faithfulness / relevancy / context precision / context recall / IR metrics
```

### 3.3 最小数据结构

```python
from dataclasses import dataclass

@dataclass
class EvalSample:
    question: str
    retrieved_contexts: list[str]
    answer: str
    reference_answer: str | None = None
    reference_contexts: list[str] | None = None
    metadata: dict | None = None
```

## 4. 类比理解

像考试评卷：

- Question 是题目；
- Retrieved Contexts 是考生翻到的参考资料；
- Answer 是考生写下的答案；
- Ground Truth 是阅卷标准或参考答案。

如果考生翻错书，是检索问题；翻对书却写错，是生成问题；答案里写了书上没有的内容，是忠实度问题。

## 5. 应用举例 / 代码或伪代码

### 5.1 构建一条可审计样本

```python
sample = {
    "question": "同一 consumer group 中，一条消息会被多个 consumer 同时处理吗？",
    "reference_answer": (
        "正常稳定分配下，同一 partition 在同一 consumer group 内同一时刻通常只由一个 consumer 处理；"
        "但 rebalance、处理完成前崩溃或 offset 未提交时，消息可能被重新投递，因此业务仍需幂等。"
    ),
    "reference_contexts": [
        "consumer group partition assignment documentation...",
        "offset commit and delivery semantics documentation...",
    ],
    "tags": ["kafka", "consumer-group", "duplicate-delivery"],
}
```

### 5.2 先做分层评估

```python
def diagnose(sample):
    if not correct_evidence_in_top_k(sample):
        return "retrieval_failure"
    if not answer_supported_by_context(sample):
        return "faithfulness_failure"
    if not answer_covers_reference_facts(sample):
        return "completeness_failure"
    return "pass"
```

### 5.3 Ground Truth 质量控制

```
草拟 reference answer
  ↓ 与权威文档逐条对齐
  ↓ 第二位审核者复核
  ↓ 标记版本、生效时间、适用范围
  ↓ 发现知识库更新时重新验证
```

## 6. 你在讨论中的理解推进

- 起点：你能理解 Question、Context 和 Answer 都来自被测流程，但疑惑“标准答案是哪来的”。
- 关键澄清：标准答案通常在评估前由人、专家、已有数据集或审核后的合成流程准备，不是 RAG 每次运行时临时产生的被测答案。
- 推进：你进一步认识到并非所有指标都需要 Ground Truth；Faithfulness 可以重点比较 Answer 与 Context，而 Context Recall 更依赖参考答案中的必要事实。
- 最终连接：评估不只是给最终答案一个总分，而是定位召回、排序、忠实度和覆盖度分别哪里失败。

## 7. 常见误区与排查思路

- **误区：用另一个 LLM 随便生成答案就叫 Ground Truth。** 未审核的模型答案只是 synthetic reference candidate。
- **误区：一个综合分数能说明全部问题。** 必须分层看检索和生成。
- **误区：Faithfulness 高就代表答案正确完整。** 回答可能完全忠于错误或不完整的 contexts。
- **误区：评估集永不过期。** 文档、产品和规则更新后，reference 也要版本化。
- **排查：** 人工抽查低分与高分样本，防止 LLM judge 误判。

## 8. 关联知识点

- `018_RAG_完整链路：召回、融合、重排、生成.md`
- [稠密向量、稀疏向量与多向量表示及检索](../01_LLM_Transformer/10_%E7%A8%A0%E5%AF%86%E5%90%91%E9%87%8F%E3%80%81%E7%A8%80%E7%96%8F%E5%90%91%E9%87%8F%E4%B8%8E%E5%A4%9A%E5%90%91%E9%87%8F%E8%A1%A8%E7%A4%BA%E5%8F%8A%E6%A3%80%E7%B4%A2.md)
- `022_Query_Rewrite、HyDE_与_Multi-Query_对比.md`
- [Bi-encoder、Cross Encoder 与重排](../01_LLM_Transformer/12_Bi-encoder%E3%80%81Cross_Encoder_%E4%B8%8E%E9%87%8D%E6%8E%92.md)

## 9. 复习检查问题

1. RAG 评估样本的四个核心字段通常分别来自哪里？
2. Ground Truth 为什么不能直接使用被测系统自己的 Answer？
3. Faithfulness 与 Context Recall 分别评估什么？
4. 哪些指标可以不依赖 reference answer？
5. 如何降低 LLM-as-a-Judge 的偏差和波动？
