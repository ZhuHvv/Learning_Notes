# RAG Query Rewrite：查询改写

> 所属分类：Agent / RAG / Memory  
> 修订版本：v10 LLM/RAG 评估增量版  
> 核心问题：用户原始问题不适合检索时，怎样在不改变真实意图的前提下生成一个更可检索的查询？

## 1. 总体性概念

Query Rewrite 是在执行检索前，把用户问题改写成更明确、更独立、更符合搜索语料表达方式的查询。

它通常仍然输出 **一个主查询**：

```text
原问题：它挂掉以后怎么选？
上下文：正在讨论 Kafka partition leader
改写后：Kafka partition leader 所在 broker 故障后，KRaft 如何从 ISR 中选举新 leader？
```

Query Rewrite 不是回答问题，也不是凭空扩展事实。它的目标是减少代词、省略、口语表达、上下文依赖和词汇不匹配对检索的影响。

## 2. 原理性解释

### 2.1 用户问题与文档表达之间存在“查询鸿沟”

真实用户经常这样问：

- “这个是存在 broker 上的吗？”
- “它和前一个有什么区别？”
- “挂了以后怎么办？”

这些句子在人类对话中有上下文，但单独送进检索器时缺少实体。文档则可能写成：

```text
The partition leader maintains the ISR and the controller elects a replacement leader...
```

Query Rewrite 要把对话上下文中的实体、关系和限制条件恢复出来，使查询自包含。

### 2.2 改写的核心是“保持语义约束，优化检索表达”

一个合格的改写需要同时满足：

1. **意图不漂移**：不能把“ISR 谁维护”改成“ISR 如何选举”。
2. **补足省略信息**：解析“它”“这个”“前者”等指代。
3. **保留限制条件**：时间、版本、系统、业务范围不能丢。
4. **适配检索语料**：加入常见技术同义词或英文术语，但不能杜撰结论。

可以把它看成一个受约束的转换：

```text
rewrite(query, conversation_context) → standalone_search_query
```

### 2.3 Query Rewrite 与问题分解不同

查询改写通常把一个问题变成一个更好的问题；问题分解则把复杂问题拆成多个子问题：

```text
改写：Kafka 中 offset 属于 consumer 还是 partition？
分解：
  1. offset 在 Kafka 中记录什么？
  2. offset 由哪个实体维护？
  3. 不同 consumer group 是否共享 offset？
```

两者可以组合：先改写成自包含问题，再判断是否需要分解。

### 2.4 改写也可能降低效果

过度改写会引入模型先验，把用户未说的假设写进 query。例如用户问“这个方案安全吗”，模型不应擅自改成“OAuth2 PKCE 是否绝对安全”。因此工程上应保留原始 query，并让原始 query 与 rewritten query 都参与检索或做 A/B 评估。


### 2.5 改写使用哪些对话上下文

把整段历史对话全部交给改写模型并不一定更好：历史太长会把已经结束的话题重新带入 query。常见做法是组合三类上下文：

- 最近若干轮原始对话，用于解析即时指代；
- 当前会话主题摘要，用于确定正在讨论的实体；
- 已确认的结构化槽位，例如 `system=Kafka`、`concept=ISR`、`version=3.x`。

```python
rewrite_context = {
    "recent_turns": messages[-6:],
    "topic_summary": state.topic_summary,
    "confirmed_entities": state.entities,
}
```

敏感信息和无关个人数据不应为了“补足上下文”被写入检索 query，因为 query 可能进入日志、缓存或第三方搜索服务。改写阶段也要执行数据最小化与权限边界。

### 2.6 改写结果应包含可解释差异

除了输出 rewritten query，还可以让模型返回哪些信息来自上下文、哪些词只是检索同义词：

```json
{
  "rewritten_query": "Kafka ISR 由谁维护以及 KRaft controller 的职责边界",
  "resolved_references": {"它": "ISR"},
  "added_search_terms": ["in-sync replicas", "controller"],
  "assumptions": []
}
```

这样才能在召回异常时判断，是指代解析错了，还是同义词扩展造成偏移。

## 3. 机制流程

```text
用户当前问题 + 最近对话
        ↓
识别指代、实体、约束和用户目标
        ↓
生成一个自包含查询
        ↓
校验：是否新增未经用户提供的事实？
        ↓
原 query 与 rewritten query 选择性并行检索
        ↓
融合、重排
```

### 3.1 结构化输出可以降低漂移

```python
from pydantic import BaseModel

class RewriteResult(BaseModel):
    original_intent: str
    rewritten_query: str
    preserved_constraints: list[str]
    added_assumptions: list[str]


def rewrite_query(question, history, llm) -> RewriteResult:
    result = llm.with_structured_output(RewriteResult).invoke({
        "question": question,
        "history": history[-6:],
        "instruction": "仅补足上下文和检索术语，不回答问题，不新增事实假设。",
    })
    if result.added_assumptions:
        return RewriteResult(
            original_intent=question,
            rewritten_query=question,
            preserved_constraints=[],
            added_assumptions=[],
        )
    return result
```

## 4. 类比理解

Query Rewrite 像图书管理员听到你说“刚才那本书的作者是谁”，先根据对话确认“刚才那本书”指哪一本，再把请求改写成完整的馆藏查询，而不是直接猜答案。

## 5. 应用举例 / 代码或伪代码

### 5.1 多轮对话改写

```text
历史：我们正在讨论 RabbitMQ 的 multiple ack。
用户：那范围是怎么确定的？
改写：RabbitMQ consumer 手动确认中，basic.ack 的 multiple=true 如何根据 delivery tag 确定批量确认范围？
```

### 5.2 保留原查询做双路召回

```python
def retrieval_with_rewrite(query, history):
    rewritten = rewriter(query, history)
    raw_hits = retriever.search(query, top_k=30)
    rewritten_hits = retriever.search(rewritten, top_k=30)
    return rerank(query, rrf_merge([raw_hits, rewritten_hits]))[:8]
```

这样可以降低“改写错误导致正确原始关键词丢失”的风险。

### 5.3 什么时候不必改写

- 查询已经包含明确实体和约束；
- 用户输入是精确错误码、类名、配置项；
- 改写成本高于直接检索；
- 检索器本身对该表达召回稳定。

可以先用启发式或轻量分类器判断是否需要 rewrite，而不是每次都调用大模型。


### 5.4 如何评估 Rewrite 是否真正有效

不能只检查句子是否更通顺，应比较：

- 正确文档 Recall@K 是否上升；
- 第一个正确 chunk 的排名是否提前；
- 原意中的实体、时间和范围约束是否保留；
- 改写后无关候选比例是否增加；
- 额外模型调用带来的 P95 延迟和成本。

建议建立三组对照：原 query、只用 rewritten query、原 query + rewritten query 融合。很多系统最终采用第三种，因为它兼顾上下文补全与原始精确词项。

## 6. 你在讨论中的理解推进

- 起点：你把 Query Rewrite 理解为“换一种说法再搜”。
- 推进：你进一步意识到它最重要的作用是恢复上下文、消解指代和补足检索所需实体。
- 区分：它通常生成一个更标准的查询；Multi-Query 生成多个视角；HyDE 生成的则是假设性答案/文档。
- 工程化理解：改写结果不能直接替换原问题而不留痕，应保留原 query、改写 query、检索来源和效果指标。

## 7. 常见误区与排查思路

- **误区：改写越长越好。** 冗余词会稀释关键词和语义中心。
- **误区：改写模型可以补充事实。** 它只能补足上下文中已有的信息。
- **误区：所有查询都必须改写。** 精确术语查询可能被改坏。
- **排查：** 对比原始 query 与改写 query 的 Recall@K、正确 chunk 排名和意图保持率。

## 8. 关联知识点

- `020_RAG_HyDE_假设文档嵌入.md`
- `021_RAG_Multi-Query_Expansion_多查询扩展.md`
- `022_Query_Rewrite、HyDE_与_Multi-Query_对比.md`
- `018_RAG_完整链路：召回、融合、重排、生成.md`

## 9. 复习检查问题

1. Query Rewrite 主要解决哪几类查询问题？
2. 如何判断改写是否发生了意图漂移？
3. Query Rewrite 和问题分解有什么区别？
4. 为什么工程上常保留原始 query 双路召回？
5. 什么类型的查询不适合让 LLM 自由改写？
