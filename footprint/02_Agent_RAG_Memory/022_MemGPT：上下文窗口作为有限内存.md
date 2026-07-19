# MemGPT：上下文窗口作为有限内存

> 所属分类：Agent / RAG / Memory  
> 核心问题：上下文窗口为什么是工作内存，MemGPT 又怎样把有限窗口扩展为可调度的记忆系统？

## 1. Context Window

上下文窗口是模型在一次推理中能够直接参考的 token 容量。Token 不等于字符或单词，不同 tokenizer 对同一文本的计数可能不同。

需要区分：

- **Context window**：一次调用的输入与输出总边界；
- **输入预算**：system、history、memory、retrieval、tool schema 和用户输入所占 token；
- **输出上限**：API 允许模型最多生成多少 token；
- **实际输出**：模型可能提前遇到结束条件。

完整预算近似为：

```text
system + user + history + memory + retrieved context
  + tool/schema 开销 + 预留输出 ≤ model context window
```

仅设置输出上限不能防止输入超窗。窗口也不是越大越好：无关、重复和冲突信息会增加成本、延迟和注意力干扰。

上下文窗口常被称为模型能“记住”的文本量，但它不是持久记忆。未放进当前请求的内容无法直接读取；历史被裁剪或未持久化后也不会自动保留。

## 2. MemGPT 的总体概念

MemGPT 把上下文窗口视为有限内存，借鉴操作系统内存管理，将信息分为：

- **Main Context**：system instructions、working context 和近期消息，模型可直接看到；
- **External Context**：Recall Storage 与 Archival Storage，需要通过工具检索。

> 项目命名说明：MemGPT 开源项目已于 2024-09 更名为 Letta；MemGPT 仍用于指论文和这套架构思想。

## 3. 内存分层

- **近期工作上下文**：当前目标、指令、证据和近期对话；
- **Recall Storage**：可搜索的历史交互；
- **Archival Storage**：长期知识和档案；
- **Memory Tools**：显式读写、检索、摘要和归档；
- **Heartbeat**：系统提供的内部维护机会。

因此它不只是“FIFO 把旧对话弹出保存”。FIFO 只决定近期消息怎样淘汰，MemGPT 的核心是按用途和检索方式决定常驻、换出和取回。

长期记忆常采用“原文保留在外部存储，摘要/洞察作为可检索索引”。摘要不是无损压缩，可能丢失限定词、例外和证据，也可能引入错误。可靠记忆应保留原文定位、摘要版本、生成时间、来源范围和适用时间；摘要用于导航，原文用于核验。

压缩可按 token 阈值、会话结束、主题切换或显式操作触发。仅定义判断函数不表示触发器已接入工作流。

## 4. 调度流程

上下文治理通常先按任务结构选择信息，再做 token 预算，最后用硬截断兜底：

| 层面 | 常见手段 | 主要代价 |
| --- | --- | --- |
| 选择 | Top-N、阈值、去重、MMR | 可能丢失候选 |
| 预算 | 目标 tokenizer 计算完整 Prompt | 多模型适配复杂 |
| 压缩 | 摘要、结构化抽取 | 细节损失和偏差 |
| 架构 | 分阶段、map-reduce、层级 memory | 状态更复杂 |
| 存储 | 原文外置、按需检索 | 依赖召回质量 |

对话历史常按最近优先逆序扫描，遇到一条放不下就 `break`，保留连续近期窗口；RAG 候选按相关性排序，某篇过长时可 `continue`，让后面的短文档使用剩余预算。Top-N 不限制长度，字符切片也不等于 token 控制。

### MemGPT 风格内存调度流程

```python
while chatting:
    event = receive_event()
    working_context.add(event)

    if near_context_limit(working_context):
        old_messages = select_evictable_messages(working_context)
        summary = summarize_with_source_links(old_messages)
        recall_storage.write(old_messages, summary)
        working_context.evict(old_messages)
        working_context.add(summary)

    if need_historical_information(working_context):
        hits = search_recall_and_archival(working_context.current_query)
        working_context.add(pack_relevant_hits(hits))

    response = llm(working_context)
```

实现还要处理来源、时间、版本、权限、新旧记忆冲突和检索结果 token 预算。

## 5. 类比理解

上下文窗口像 RAM：容量有限、读取直接；外部记忆像磁盘：容量更大，但需要检索换入。`break` 的近期对话选择像保留连续的最近几页，`continue` 的 RAG 选择像跳过装不下的大册子，继续放入短而相关的资料。

## 6. 常见误区与关联知识点

- 长上下文不表示所有信息都被同等有效利用；
- 配置文件里写了 token 值，不表示调用链已经实际使用，应沿参数传递验证；
- 列表前 N 条不一定最重要，并发追加顺序也不等于相关性排序；
- 摘要不能替代原文和证据引用；
- 检索到的历史可能过时或越权；
- 记忆写入应依据用途、重要性、隐私和保留策略筛选。

关联阅读：

- `019_IterResearch、Research_Synthesis_与常量大小上下文.md`
- `020_Agent_Memory_四类：短期、情景、语义、程序性.md`
- `023_Mem0_与_A-Mem：生产级长期记忆管理.md`
- `024_RAG_完整链路：召回、融合、重排、生成.md`
