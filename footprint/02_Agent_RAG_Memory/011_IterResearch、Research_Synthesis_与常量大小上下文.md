# IterResearch、Research Synthesis 与常量大小上下文

> 所属分类：Agent / RAG / Memory  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释迭代式研究和上下文压缩，不复用 ReAct、Reflection 或 Memory 的原理段。

## 1. 总体性概念

IterResearch 是一种面向长研究任务的 Agent 范式：系统不是把每一步搜索结果全部塞进上下文，而是在每轮研究后进行 **Research Synthesis（研究综合）**，把已有发现压缩成稳定的中间状态，再进入下一轮。

“常量大小上下文”指的是：随着研究轮次增加，输入给 LLM 的上下文不会线性增长，而是保持在一个相对固定的大小范围内。


## 2. 原理性解释

朴素 ReAct 的问题是：每执行一步，就把 Thought、Action、Observation 拼进上下文。步数越多，上下文越长，最终会遇到：

- token 成本上升；
- 注意力被噪声稀释；
- 早期关键信息被截断；
- 模型难以区分“已证实结论”和“待验证假设”。

IterResearch 的核心机制是把上下文拆成两层：

1. **Raw Evidence Store**：保存原始资料、来源、片段、工具结果。
2. **Synthesis State**：保存压缩后的研究状态，例如已确认结论、冲突点、证据缺口、下一步问题。

每一轮只把 `Synthesis State + 少量最相关 evidence` 送入 LLM，而不是把所有历史全部送入。

### IterResearch 的核心不是“总结”，而是“迭代式状态压缩”

朴素 ReAct 会把每一步 observation 不断拼进上下文，任务越长 prompt 越大，注意力被噪声稀释。IterResearch 的思路是把研究过程拆成多轮：每轮检索/阅读后，不是保留全部原文，而是更新一个结构化 research state，例如已知事实、证据、冲突点、待查问题、下一步计划。

“常量大小上下文”不是说信息不增长，而是说每次喂给模型的工作上下文被控制在固定规模附近。历史细节被外部存储或摘要状态承接，模型每轮看到的是压缩后的高价值信息。

## 3. 机制流程

```text
初始化研究问题
  ↓
生成第一批检索 query
  ↓
搜索 / 读取 / 抽取证据
  ↓
Research Synthesis：
    - 新发现是什么
    - 与旧结论是否冲突
    - 哪些证据可靠
    - 还缺什么信息
  ↓
更新固定大小的 synthesis_state
  ↓
生成下一轮 query
  ↓
循环直到信息充分或达到预算
  ↓
生成最终报告
```

### IterResearch / Research Synthesis 流程

```python
state = ResearchState(question=question, facts=[], gaps=[], sources=[])
for i in range(max_rounds):
    queries = llm_plan_queries(state)
    docs = retrieve_and_read(queries)
    new_notes = extract_claims(docs)
    state = synthesize(state, new_notes)  # 合并事实、标注冲突、更新 gaps
    if answer_ready(state):
        break
answer = write_answer_from_state(state)
```

关键是 `synthesize` 不应只是压缩字数，而要做结构化归并：哪些事实被多个来源支持，哪些仍然缺证据，哪些问题需要下一轮检索。这样才能避免“摘要越压越丢关键约束”。

## 4. 类比理解

普通 ReAct 像把所有草稿纸都摊在桌上，越写越乱。IterResearch 像研究员每读完一批资料就更新一页“研究备忘录”：原始资料放档案柜，桌上只保留最新的研究框架和关键证据。

## 5. 应用举例 / 代码或伪代码

```python
class ResearchState(dict):
    # 固定大小状态，而不是无限增长的 messages
    pass

def synthesize(state, new_evidence):
    prompt = {
        "research_question": state["question"],
        "current_claims": state["claims"],
        "open_questions": state["open_questions"],
        "new_evidence": new_evidence,
        "output_schema": {
            "updated_claims": "list",
            "resolved_questions": "list",
            "new_open_questions": "list",
            "conflicts": "list",
            "next_queries": "list"
        }
    }
    return llm_json(prompt)

def iter_research(question, max_rounds=5):
    state = ResearchState(
        question=question,
        claims=[],
        open_questions=[question],
        conflicts=[],
        next_queries=[question],
    )
    evidence_store = []

    for _ in range(max_rounds):
        new_evidence = []
        for q in state["next_queries"]:
            docs = search(q)
            snippets = extract_relevant_snippets(docs, question)
            new_evidence.extend(snippets)
            evidence_store.extend(snippets)

        update = synthesize(state, new_evidence)

        state["claims"] = compress(update["updated_claims"], max_items=12)
        state["open_questions"] = compress(update["new_open_questions"], max_items=6)
        state["conflicts"] = compress(update["conflicts"], max_items=6)
        state["next_queries"] = update["next_queries"][:4]

        if not state["open_questions"]:
            break

    return write_report(state, evidence_store)
```

## 6. 你在讨论中的理解推进

你曾经总结：**ReAct 会因为上下文不断变长出现问题；IterResearch 会周期性整理、总结现有上下文，保持上下文长度在定长范围内。**

这个理解是正确的，但要补充两点：

1. 常量大小上下文不是丢弃原始资料，而是把原始资料放到外部 evidence store。
2. Synthesis 不是普通摘要，而是结构化研究状态：结论、证据、冲突、缺口、下一步 query。

## 7. 常见误区与排查思路

- **误区 1：Research Synthesis 等于总结全文。**  
  它更像研究状态更新，不只是压缩文字。

- **误区 2：常量大小上下文意味着不需要原始证据。**  
  原始证据仍要保存，否则最终报告无法追溯来源。

- **误区 3：每轮都重新开始搜索。**  
  应该根据 open questions 和 evidence gap 生成下一轮 query。

## 8. 关联知识点

- `014 ReAct 与 Plan-and-Execute`：IterResearch 可作为长任务的执行策略。
- `023 RAG 完整链路`：检索证据是 IterResearch 的输入来源。
- `016 ReAct 提前终止检测`：研究循环也需要停止条件。
- `017 语义缓存`：重复 query 可以缓存，减少无效检索。

## 9. 复习检查问题

1. 常量大小上下文到底“常量”的是什么？
2. Research Synthesis 和普通摘要有什么区别？
3. 为什么要保留 evidence store？
4. IterResearch 适合什么任务，不适合什么任务？

