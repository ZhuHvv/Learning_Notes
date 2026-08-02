# LLM 幻觉：成因、边界与系统级治理

## 1. 总体性概念

LLM 产生幻觉的根本原因，是它的基础训练目标是“给定已有 Token，预测训练分布中更可能出现的下一个 Token”，而不是对每个自然语言命题执行事实校验：

```text
高概率续写 ≠ 已验证事实
语言流畅度 ≠ 事实可信度
引用格式正确 ≠ 引用真实存在且支持结论
```

因此需要区分两个目标：

- **模型层面零幻觉**：要求开放领域通用模型对任意问题、上下文和输出都绝对真实；目前没有通用方法能够保证。
- **系统层面阻断幻觉**：让未经权威数据、确定性工具或验证器确认的内容不能进入最终业务结果；在受限任务中可以把错误压得很低，某些明确定义的任务可达到工程意义上的“零幻觉”。

更准确的结论不是“只要写好 Prompt 或接入 RAG 就不会幻觉”，而是：

> Prompt、RAG、微调和自我验证都只能降低部分风险；可靠系统依靠权威证据、确定性工具、约束输出、独立验证、拒答和人工审核形成多层防线。

## 2. 原理性解释

### 2.1 训练目标不等于事实正确性

自回归语言模型的典型训练目标是最小化下一 Token 的负对数似然：

```text
L(θ) = -Σ_t log Pθ(x_t | x_1, ..., x_{t-1})
```

训练数据反复出现“法国的首都是巴黎”时，模型会提高“法国的首都是 → 巴黎”的续写概率，但并不等于内部执行了数据库断言：

```python
assert world_database["法国"]["首都"] == "巴黎"
```

它更接近学习一个条件概率分布：

```python
next_token_probability = {
    "巴黎": 0.97,
    "里昂": 0.01,
    "伦敦": 0.005,
}
```

如果高概率模式本身错误，贪心解码反而会稳定地输出错误答案。

### 2.2 训练数据同时包含真实、错误与虚构分布

互联网语料包含错误和过时信息、相互矛盾的说法、小说与虚构内容、缺少上下文的片段、低质量复制，以及人类普遍持有的错误认知。模型学习的是整个文本分布，并不会天然只保留正确事实：

```text
常见说法的概率 > 正确但少见说法的概率
```

TruthfulQA 的实验说明，扩大模型并不必然同步提高真实性；更强的模式学习能力也可能更好地复现人类文本中的常见误解。

### 2.3 参数化知识不是可精确查询的数据库

数据库可以按键查询并返回确定记录：

```sql
SELECT capital
FROM countries
WHERE country = 'France';
```

LLM 则把大量模式压缩在参数中，再根据当前上下文重构答案。这种存储方式会带来：

- 高频知识通常更稳定，长尾知识更容易混淆；
- 相近实体的属性可能串联；
- 数字、日期、版本号和标识符容易出错；
- 训练截止后的变化无法自然写回参数；
- 参数知识不能天然携带可核验出处；
- 多个人物或事件的片段可能被拼成一个内部自洽但不存在的叙述。

### 2.4 信息不足时仍会继续生成

传统程序可以显式失败：

```python
record = database.find(name)
if record is None:
    raise NotFoundError(name)
```

语言模型的基础机制则仍会继续预测 Token。指令微调可以教会模型说“不知道”，但拒答是后训练获得的行为，不是基础语言建模目标的硬保证。让模型自报置信度或判断“自己是否知道”可以提供信号，却不能作为唯一安全边界。

### 2.5 自回归过程会让早期错误累积

每个已生成 Token 都会进入后续上下文：

```text
初始小错误
  → 成为后续前提
  → 后续内容围绕错误前提保持自洽
  → 形成完整、流畅、可信的错误故事
```

模型不会自动回到开头访问权威来源重新核实，因此幻觉经常不是零散乱码，而是结构完整的错误叙述。

### 2.6 解码策略控制随机性，不保证真实性

降低 `temperature` 会降低输出波动，提高确定性和可复现性，但如果概率最高的答案就是错的，贪心或低温解码只会产生“稳定幻觉”：

```python
probabilities = {
    "错误答案": 0.70,
    "正确答案": 0.25,
    "其他": 0.05,
}

token = max(probabilities, key=probabilities.get)
assert token == "错误答案"
```

### 2.7 流畅度和格式会制造虚假可信感

模型学会了论文语气、新闻写法、API 文档风格、作者与机构名称的组合规律，也能生成看似正规的 DOI 和引用格式。这只能说明它掌握了“引用长什么样”，不能证明作者、论文、期刊和论据真实存在，更不能证明引用支持对应结论。

## 3. 机制流程

### 3.1 Prompt 是软约束

Prompt 可以要求仅依据上下文回答、证据不足时拒答、逐项引用来源：

```python
prompt = f"""
你是严格的资料问答系统。
1. 只能依据 <context> 回答。
2. 证据不足时输出“证据不足”。
3. 每个事实标注资料编号。
4. 不得编造引用，也不得用模型记忆补充。

<context>
{context}
</context>

问题：{question}
"""
```

它能改变生成倾向，但不能把自然语言规则变成程序级禁止。模型仍可能忽略规则、误读证据、拼接两段资料、编造引用编号，或在证据不足时强行作答。

### 3.2 RAG 提供外部证据，也引入新的失败链路

RAG 主要缓解参数知识过时、私有知识不可见、长尾事实不稳定、答案缺少出处和更新模型成本高等问题，但其质量取决于一条完整链路：

```text
问题
  → 查询改写是否保留原意
  → 是否召回正确且最新的资料
  → 重排是否保留正确资料
  → Chunk 是否保留完整语境
  → 模型是否正确理解证据
  → 结论是否严格落在证据范围内
  → 引用是否真的支持对应声明
```

典型 RAG 幻觉包括：

- 没检索到答案时，模型使用自身记忆补充；
- 检索到错误或过时资料，形成“有依据的错误”；
- 证据只支持小规模实验，回答却外推到普遍生产环境；
- 引用了真实文档，但文档并不蕴含对应结论。

完整的召回、融合、重排、上下文构建和评估流程见 [RAG 完整链路](../02_Agent_RAG_Memory/18_RAG_完整链路：召回、融合、重排、生成.md)。

### 3.3 可靠系统采用多层防线

```text
用户请求
  → 意图识别与风险分类
  → 权威数据检索 / 确定性工具调用
  → 生成候选答案
  → 拆分事实声明
  → 为每条声明检索独立证据
  → 验证证据是否蕴含声明
  → 删除或改写无证据内容
  → 置信度与拒答判断
  → Schema / 规则校验
  → 高风险场景人工审批
  → 最终回答
```

| 方法 | 主要解决的问题 | 单独无法保证 |
| --- | --- | --- |
| Prompt | 规范回答行为 | 模型一定遵守 |
| 降低 temperature | 降低随机波动 | 答案真实 |
| RAG | 提供外部知识与出处 | 检索一定正确、生成一定忠实 |
| Fine-tuning | 强化领域模式与拒答行为 | 未见问题绝不出错 |
| 工具调用 | 把查询和计算交给确定性系统 | 工具选择和参数一定正确 |
| 结构化输出 | 保证 JSON、字段和类型 | 字段值符合事实 |
| 约束解码 | 禁止非法格式或选项 | 被允许的选项一定正确 |
| 验证器 | 拦截无证据或不一致声明 | 验证器自身绝不出错 |
| 人工审核 | 处理高风险与复杂歧义 | 无限规模、低成本实时处理 |

### 3.4 自我验证不能代替独立证据

让同一个模型生成后再问“是否正确”存在同源错误：第一次相信的错误事实，第二次仍可能相信。更可靠的做法是把声明拆开并引入独立检索、验证器和程序规则：

```python
draft = generator.generate(question)
claims = claim_extractor.extract(draft)

for claim in claims:
    evidence = retriever.search(claim.text)
    if not evidence:
        claim.status = "unsupported"
    else:
        claim.status = verifier.verify(
            claim=claim.text,
            evidence=evidence,
        )
```

Chain-of-Verification 通过草稿、验证问题、独立回答和修订减少幻觉；SelfCheckGPT 通过多次采样的不一致性发现可疑内容。二者都是降低风险的信号：模型可能多次稳定地给出同一个错误答案，所以一致性本身不等于真实性。

## 4. 类比理解

LLM 更像擅长语言理解、规划和写作的非确定性助手，而不是事实数据库。可靠业务系统应像有审计制度的组织：

- 助手可以理解问题、规划和提出候选结果；
- 数据库、搜索、计算器、编译器和 API 提供事实；
- 类型系统、规则引擎、权限系统和验证器负责硬约束；
- 高风险结论由人工审批；
- 证据不足时允许拒答。

真正应追求的是“模型犯的错不能通过系统校验”，而不是假设“模型永远不会犯错”。

## 5. 应用举例 / 代码或伪代码

### 5.1 接近工程“零幻觉”的四类任务

1. **封闭选项**：只允许“通过 / 拒绝 / 人工复核”。约束解码能消除选项外文本，但不能保证选对。
2. **纯抽取任务**：最终答案必须是原文中的合法 span。它能阻止凭空生成，但仍可能抽错位置。
3. **确定性工具任务**：计算交给计算器，余额交给数据库，天气交给 API，语法交给编译器，SQL 合法性交给解析器。
4. **严格证据绑定**：每个声明必须绑定有效来源，并进一步检查证据是否真的蕴含该声明，而不只检查引用 ID 存在。

```python
ALLOWED_OUTPUTS = {"通过", "拒绝", "人工复核"}


def validate_choice(output: str) -> str:
    if output not in ALLOWED_OUTPUTS:
        raise ValueError("非法选项")
    return output


def extract_answer(text: str, start: int, end: int) -> str:
    if not 0 <= start <= end <= len(text):
        raise ValueError("invalid span")
    return text[start:end]


def calculate_total(
    price: float,
    count: int,
    tax_rate: float,
) -> float:
    if price < 0 or count < 0 or tax_rate < 0:
        raise ValueError("invalid input")
    return round(price * count * (1 + tax_rate), 2)
```

这些程序分别保证“输出在允许集合内”“答案来自原文合法范围”“数值来自确定性计算”，但仍需验证模型是否选对选项、抽对位置和传对参数。

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Claim:
    text: str
    source_ids: list[str]


def validate_claims(
    claims: list[Claim],
    valid_source_ids: set[str],
) -> None:
    for claim in claims:
        if not claim.source_ids:
            raise ValueError(f"无证据声明：{claim.text}")

        unknown = set(claim.source_ids) - valid_source_ids
        if unknown:
            raise ValueError(f"引用了不存在的资料：{sorted(unknown)}")
```

### 5.2 工具事实、生成解释、外部验证

```python
def agent_answer(question: str) -> str:
    plan = planner.create_plan(question)
    evidence = []

    for call in plan.tool_calls:
        args = validate_arguments(call)
        evidence.append(execute_tool(call.name, args))

    draft = generator.generate(
        question=question,
        evidence=evidence,
        allow_external_knowledge=False,
    )

    result = verifier.verify(answer=draft, evidence=evidence)
    if not result.supported:
        return "现有证据不足，无法可靠回答。"

    return draft
```

余额、订单状态等关键字段还可以直接使用程序模板渲染，避免模型重新生成事实值。工具接入和参数边界见 [Function Calling 与 MCP](../02_Agent_RAG_Memory/3_Function_Calling_与_MCP_工具接入.md)。

## 6. 你在讨论中的理解推进

- 起点：你提出“幻觉是否无法消灭，只能通过 Prompt、RAG 等措施减少”。
- 保留的正确部分：对于开放领域通用 LLM，本身的幻觉目前无法被普遍、绝对地消灭。
- 关键修正：Prompt 和 RAG 都不是真实性保证；RAG 还可能在改写、召回、重排、切片、证据质量和生成忠实度等环节失败。
- 最终连接：受限业务系统不必等待模型变成绝对可靠，而应让权威事实来自外部系统，并用“检索 → 生成 → 验证 → 拒答/人工审批”阻断未经证实的输出。

## 7. 常见误区与排查思路

- **低 temperature 等于更真实**：它只让结果更稳定，应核查证据而不是只调采样参数。
- **有引用就可信**：检查引用是否存在、是否最新，以及是否蕴含对应声明。
- **RAG 一定优于模型记忆**：先检查数据源质量、召回、重排、Chunk 语境和权限过滤。
- **结构化输出保证事实正确**：Schema 只能限制结构和类型，字段值仍需业务校验。
- **让模型反思一次就完成验证**：检查是否引入了独立证据和异源验证器。
- **拒答等于失败**：在证据不足或高风险场景中，可靠拒答是正确的系统行为。

建议按层排查：

```text
事实源是否正确
  → 正确证据是否进入候选集
  → 证据是否被上下文完整保留
  → 回答声明是否被证据支持
  → 无证据声明是否被拦截
  → 高风险输出是否进入人工审批
```

## 8. 关联知识点

- [预训练、SFT、RLHF 与 LoRA](9_预训练、SFT、RLHF_与_LoRA.md)
- [Prompt 工程：User Prompt 与 System Prompt](../02_Agent_RAG_Memory/1_Prompt_工程：User_Prompt_与_System_Prompt.md)
- [Agent 的端到端任务能力](../02_Agent_RAG_Memory/2_Agent_的端到端任务能力.md)
- [Function Calling 与 MCP：模型决策和工具接入](../02_Agent_RAG_Memory/3_Function_Calling_与_MCP_工具接入.md)
- [RAG 完整链路：召回、融合、重排、生成](../02_Agent_RAG_Memory/18_RAG_完整链路：召回、融合、重排、生成.md)
- [RAGAS 评估指标与 Ground Truth 来源](../02_Agent_RAG_Memory/23_RAGAS_评估指标与_Ground_Truth_来源.md)

## 9. 参考资料与复习问题

### 参考资料

- [GPT-3: Language Models are Few-Shot Learners](https://arxiv.org/abs/2005.14165)
- [TruthfulQA: Measuring How Models Mimic Human Falsehoods](https://arxiv.org/abs/2109.07958)
- [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401)
- [Language Models (Mostly) Know What They Know](https://arxiv.org/abs/2207.05221)
- [Chain-of-Verification Reduces Hallucination in Large Language Models](https://arxiv.org/abs/2309.11495)
- [SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection](https://arxiv.org/abs/2303.08896)
- [本次技术讨论记录](https://chatgpt.com/share/6a6b66aa-f208-83ec-a530-74a18a19083b)

### 复习检查问题

1. 为什么下一 Token 预测目标不能天然保证事实正确？
2. 低 temperature 为什么可能只产生“稳定幻觉”？
3. Prompt、RAG、工具调用和约束解码分别提供软约束还是硬边界？
4. 为什么同一个模型的自我验证可能产生同源错误？
5. 在什么条件下可以把一个受限任务定义为工程“零幻觉”？
6. 如何验证“引用存在”与“引用支持声明”这两个不同问题？
