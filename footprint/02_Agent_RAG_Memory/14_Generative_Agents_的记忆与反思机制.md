# Generative Agents 的记忆与反思机制

## 1. 总体性概念

Generative Agents 提出了一种让智能体表现出“持续生活感”的记忆机制：Agent 会把观察、行为和对话写入 **memory stream**，在需要行动时从记忆流中检索相关记忆，并周期性进行 **reflection**，把低层事件提炼成高层 insight。

它解决的问题是：如果 Agent 只依赖当前 prompt，就没有连续人格、长期目标和历史经验；如果把所有历史都塞进 prompt，又会爆上下文。因此需要“外部记忆 + 检索 + 反思”。


## 2. 原理性解释

### 2.1 Memory Stream

memory stream 可以看成一个不断追加的事件日志：

```python
memory = {
    "text": "Sam told me he will run for mayor.",
    "created_at": "2026-05-30 09:10",
    "last_accessed_at": "2026-05-30 09:10",
    "importance": 8,
    "embedding": embed(text),
}
```

每条记忆通常包含：

- 原始文本；
- 创建时间；
- 最近访问时间；
- 重要性 importance；
- 向量 embedding；
- 可选标签或来源。

### 2.2 记忆检索：relevance + recency + importance

Generative Agents 的关键不是“随机取最近几条记忆”，而是综合三个分数：

1. **Relevance（相关性）**：当前情境 query 与记忆 embedding 的相似度。
2. **Recency（新近性）**：越近发生的记忆分数越高，随时间衰减。
3. **Importance（重要性）**：越重要的事件越容易被召回。

一个常见抽象公式是：

```text
score(memory, query) =
    α * relevance(query, memory)
  + β * recency(memory)
  + γ * importance(memory)
```

伪代码：

```python
def retrieve_memories(query, memories, now, top_k=5):
    q_emb = embed(query)
    scored = []
    for m in memories:
        relevance = cosine(q_emb, m["embedding"])
        # 按论文（Park et al. 2023 §4.1），recency 以 last_accessed_at（最后被访问/检索时间）衰减，
        # 论文使用每游戏小时 0.995 的指数衰减；这里的 half_life 是等价的工程写法
        hours = (now - m["last_accessed_at"]).total_seconds() / 3600
        recency = exp_decay(hours, half_life=24)
        importance = m["importance"] / 10.0

        # 论文默认等权（α=1），此处为可调工程示例
        score = 0.45 * relevance + 0.25 * recency + 0.30 * importance
        scored.append((score, m))

    hits = sorted(scored, key=lambda x: x[0], reverse=True)[:top_k]

    for _, m in hits:
        m["last_accessed_at"] = now

    return [m for _, m in hits]
```

这就是你指出的关键点：**Generative Agents 的记忆检索方案必须讲 relevance、recency、importance 的组合，而不能只说“有记忆和反思”。**

### 2.3 Reflection：从事件到 Insight

当一段时间内累积的 importance 超过阈值，就触发 reflection：

```python
def maybe_reflect(agent):
    if sum(m["importance"] for m in agent.recent_memories) < agent.reflect_threshold:
        return

    questions = llm_generate_reflection_questions(agent.recent_memories)
    related = []
    for q in questions:
        related.extend(retrieve_memories(q, agent.memories, now()))

    insights = llm_summarize_insights(related)
    for insight in insights:
        agent.memories.append({
            "text": insight,
            "created_at": now(),
            "importance": 9,
            "embedding": embed(insight),
            "type": "reflection_insight",
        })
```

Reflection 不是简单摘要，它会产生更抽象的认知，例如：

- “Sam 很重视社区政治活动。”
- “Alice 最近对工作变动感到焦虑。”
- “我应该在明天提醒 Bob 准备会议材料。”

这些 insight 会重新写回 memory stream，成为未来检索的对象。

### 检索分数的工程细节

Generative Agents 的记忆检索常把 relevance、recency、importance 归一化后加权。这里的难点是三个分数的尺度不同：embedding 相似度可能在 `[-1,1]` 或 `[0,1]`，recency 通常用指数衰减，importance 可能是 LLM 打的 1~10 分。因此工程实现必须先归一化，否则某一项会压倒其它项。

```python
def score_memory(q_emb, m, now):
    relevance = normalize_cosine(cosine(q_emb, m.embedding))
    recency = math.exp(-hours_since(m.last_accessed_at, now) / 24)
    importance = m.importance / 10.0
    return 0.45 * relevance + 0.25 * recency + 0.30 * importance
```

Reflection 的触发也不是定时摘要，而是 importance 累积达到阈值后，生成“我应该思考什么问题”，再检索相关记忆，最后归纳 insight 写回 memory stream。

## 3. 机制流程

```text
观察环境 / 发生对话 / 执行动作
  ↓
写入 memory stream
  ↓
需要决策时，根据当前情境构造 query
  ↓
用 relevance + recency + importance 检索记忆
  ↓
把相关记忆放入 prompt，生成行动/对话
  ↓
累计 importance 达到阈值
  ↓
触发 reflection，生成高层 insight
  ↓
insight 写回 memory stream
```

### 完整行为生成循环

```text
Observe：观察事件并写入 memory stream
  ↓
Score：LLM 或规则给事件打 importance
  ↓
Retrieve：当前情境触发 relevance/recency/importance 检索
  ↓
Plan/Act：把检索记忆放入 prompt，生成行为或对话
  ↓
Accumulate：近期 importance 累积
  ↓
Reflect：生成反思问题，检索相关事件，提炼 insight
  ↓
Write-back：insight 作为高重要性记忆写回
```

如果要落地到普通 Agent，可以把 memory stream 存在数据库中，embedding 存向量库，importance 存结构化字段，reflection insight 单独打 `type=insight`，避免和普通 observation 混淆。

## 4. 类比理解

memory stream 像日记本；retrieval 像你遇到某件事时大脑自动想起“相关、最近、重要”的经历；reflection 像晚上复盘日记，把零散事件总结成“某个人的性格”“某个目标的变化”“下一步计划”。

## 5. 应用举例 / 代码或伪代码

```python
class GenerativeAgent:
    def __init__(self, name):
        self.name = name
        self.memories = []
        self.reflect_threshold = 100

    def observe(self, text, importance):
        self.memories.append({
            "text": text,
            "created_at": now(),
            "last_accessed_at": now(),
            "importance": importance,
            "embedding": embed(text),
            "type": "observation",
        })

    def act(self, situation):
        memories = retrieve_memories(situation, self.memories, now(), top_k=8)
        prompt = build_prompt(
            identity=f"My name is {self.name}.",
            situation=situation,
            memories=[m["text"] for m in memories],
        )
        action = llm(prompt)
        self.observe(f"I decided to: {action}", importance=5)
        return action

    def reflect(self):
        maybe_reflect(self)
```

## 6. 你在讨论中的理解推进

你最关心的问题是：Agent 的长期记忆到底是不是“把历史消息存起来”。这里的结论是：

1. 不能只存消息，必须存可检索的 memory item。
2. 检索不能只靠最近时间，要综合相关性、新近性、重要性。
3. 反思不是日志压缩，而是把低层事件变成高层 insight。
4. insight 也要回写 memory stream，未来可以被再次检索。

## 7. 常见误区与排查思路

- **误区 1：长期记忆等于聊天记录。**  
  聊天记录只是原材料，真正可用的是结构化、可检索、可评分的 memory item。

- **误区 2：只用向量相似度检索。**  
  重要事件即使语义不完全相似，也可能应该被召回；最近事件也可能影响当前行为。

- **误区 3：反思越多越好。**  
  反思会产生高层结论，如果没有触发条件和质量过滤，会生成错误人格设定或虚假经验。

## 8. 关联知识点

- `013 Reflection、Insight 与执行后反思`
- `012 Agent Memory 四类`
- `015 MemGPT：上下文窗口作为有限内存`
- `017 Mem0 与 A-Mem：生产级长期记忆管理`

## 9. 复习检查问题

1. Generative Agents 的 memory stream 每条记录应包含哪些字段？
2. relevance、recency、importance 分别解决什么问题？
3. Reflection 触发条件为什么常和 importance 累积有关？
4. Insight 为什么要写回 memory stream？
