# MemGPT：上下文窗口作为有限内存

> 所属分类：Agent / RAG / Memory  
> 修订版本：v11  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

MemGPT 把上下文窗口视为有限内存，借鉴操作系统内存管理，把信息分为两层：**main context**（system instructions + working context + FIFO queue，模型可直接看到）与 **external context**（recall storage + archival storage，需通过工具检索），并通过工具主动换入/换出。

> 注：MemGPT 开源项目已于 2024-09 更名为 Letta；MemGPT 保留为论文/架构名。


## 2. 原理性解释

- 主上下文类似 RAM，模型可直接看到。
- Recall storage 保存对话历史。
- Archival storage 保存长期知识和可检索档案。
- 模型可通过函数调用主动读写记忆。
- Heartbeat 可触发模型检查是否需要管理记忆。

### MemGPT 把上下文窗口当作“有限内存”来调度

MemGPT 的关键想法是：LLM 的上下文窗口类似操作系统里的主存，容量有限但访问快；外部存储类似磁盘，容量大但需要主动检索。系统通过函数调用让模型决定何时把信息写入长期存储、何时从外部记忆取回信息、何时压缩当前上下文。

你之前对 FIFO 队列、Recall Storage、Archival Storage 的理解可以再修正为：不是简单把旧对话弹出保存，而是用显式内存管理策略区分“近期对话上下文”“可搜索历史记录”“更长期的档案知识”。

## 3. 机制流程

1. 新消息进入上下文。
2. 上下文接近上限时摘要/换出。
3. 需要信息时检索外部记忆。
4. 检索结果换入上下文。
5. 继续回答。

### MemGPT 风格内存调度流程

```python
while chatting:
    if context_window_near_limit():
        summary = summarize_old_messages()
        recall_storage.write(old_messages, summary)
        trim_context()
    if user_query_requires_old_info():
        hits = recall_storage.search(user_query)
        insert_into_context(hits)
    response = llm(current_context)
```

心跳机制可以理解为系统给 Agent 的一次“内部维护机会”：即使没有用户新输入，也能检查是否需要归档、检索、反思或更新状态。

## 4. 类比理解

像操作系统：上下文是内存，外部记忆是硬盘，模型决定页面换入换出。

## 5. 应用举例 / 代码或伪代码

```python
if context_tokens(messages) > LIMIT:
    summary = summarize(messages[:-10])
    archival_store.add(summary)
    messages = messages[-10:] + [summary]

if need_memory(query):
    messages += archival_store.search(query, top_k=5)
```

## 6. 你在讨论中的理解推进

你用 FIFO 理解 MemGPT 接近但不完整；更准确是 LLM 主动参与内存管理。

