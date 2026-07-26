# Claude Code 上下文压缩、Microcompact 与状态恢复

> 所属分类：Claude Code 源码与机制解读  
> 整理日期：2026-07-25；审查更新：2026-07-26  
> 核心问题：Claude Code 如何先清理旧工具结果、再做全量摘要，并在压缩后恢复仍然有效的文件、任务与规则状态？

## 1. 先区分三类动作

长会话的上下文管理不是单一的“把聊天缩短”，而是三个不同层次：

| 层次 | 处理对象 | 主要目的 |
|---|---|---|
| 工具结果清理 / Microcompact | 较早的 `tool_result` 载荷 | 删除可丢弃的大块原始输出，尽量不生成新摘要 |
| 全量压缩 / Compact | 旧消息历史 | 用结构化摘要替换大段历史 |
| 压缩后状态恢复 | 规则、文件、任务、Skills、Hook 等 | 把仍然有效的当前状态重新注入上下文 |

可以概括为：

```text
先删低价值原始载荷
    ↓
仍不够时总结历史语义
    ↓
再从权威状态源恢复“现在是什么状态”
```

Claude Code 官方文档确认的稳定行为是：接近上下文上限时，先清理较旧工具输出，必要时再摘要会话；项目根 `CLAUDE.md`、auto memory 等会在压缩后重新加载。精确的内部函数、阈值、保留数量和占位符属于版本相关实现。

## 2. 先掌握官方公开契约

如果目标是理解和使用当前 Claude Code，先记住以下公开行为：

1. `/compact [instructions]` 用摘要替换旧消息历史，可指定摘要重点；
2. 自动上下文管理会先清理较旧工具输出，必要时再总结会话；
3. system prompt 与 output style 不属于消息历史，压缩时不被摘要替换；
4. 项目根 `CLAUDE.md`、无作用域 rules、auto memory 会从磁盘重新注入；
5. 带 `paths:` 的 rules 与嵌套目录 `CLAUDE.md` 要等再次读取匹配文件后重载；
6. 已调用 Skill 的正文按最近调用优先恢复，单项最多 5,000 tokens、总计最多 25,000 tokens；
7. `SessionStart` Hook 会以 `source: "compact"` 再次触发；较新版本还公开了独立的 `PostCompact` Hook；
8. `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 控制压缩计算采用的有效容量，`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` 再按百分比调整触发点。

后文的固定占位符、20K 摘要上限、最近文件数量、内部函数名与“缓存热/冷”分支，属于第三方对特定构建的还原。它们用于理解设计权衡，不能覆盖上述公共契约。

## 3. 版本实现：Microcompact 不是“给每个结果写摘要”

讨论中引用的特定版本还原源码显示，时间型 Microcompact 会把旧工具结果正文替换为固定占位文本：

```text
[Old tool result content cleared]
```

它不是让 LLM 新生成类似下面的语义摘要：

```text
[已清理：Read 读取了 src/app.ts，共 500 行，结论是路由顺序错误]
```

典型工具调用原本由两个块配对：

```json
{
  "type": "tool_use",
  "id": "toolu_123",
  "name": "Read",
  "input": {
    "file_path": "/project/src/app.ts"
  }
}
```

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_123",
  "content": "文件的完整内容……"
}
```

清理后，`tool_use` 保留，`tool_result` 的正文被替换：

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_123",
  "content": "[Old tool result content cleared]"
}
```

模型仍可通过：

```text
tool_use.id == tool_result.tool_use_id
```

知道调用过哪个工具、输入参数是什么、哪个结果已被清理；但它不再知道原始结果正文、行数、哈希或自动生成的简短结论。

## 4. 保留了什么，丢失了什么

| 信息 | 典型结果 | 原因 |
|---|---|---|
| 工具名称 | 保留 | 位于 `tool_use.name` |
| 工具输入参数 | 保留 | 位于 `tool_use.input` |
| 工具调用与结果的配对 ID | 保留 | `tool_use.id` / `tool_result.tool_use_id` |
| 是否错误等结构字段 | 版本相关，通常可保留 | 只覆盖 `content` 时其它字段不变 |
| 工具完整输出 | 删除 | 原 `tool_result.content` 被替换 |
| 工具输出摘要 | 不会因此自动生成 | Microcompact 不是一次摘要模型调用 |
| 后续 assistant 已写出的自然语言结论 | 通常保留 | 它不属于被清理的 `tool_result` |

所以更准确的表述是：

> 保留工具交互的结构骨架，清除较旧的结果载荷；是否还能知道旧结论，取决于后续消息是否已把结论写进会话。

## 5. “可清理”不等于“可无损重放”

文件读取、Shell、搜索、网页读取、编辑确认等工具结果可能被视为可清理，但不能据此推断它们都能确定性重放：

- 文件随后可能已修改，重新 `Read` 得到的是当前版本；
- Web 搜索排序和页面内容可能变化；
- `date` 等命令天然随时间变化；
- `Edit` / `Write` 不应为了恢复旧输出而盲目重放，当前文件系统才是权威状态。

因此“可重新获取”更严谨的含义是：

```text
旧结果可以从活动上下文丢弃
需要时从当前权威状态重新检查
≠
保证恢复当时完全相同的结果
```

Anthropic 当前的服务端 Context Editing 也采用类似原则：默认按时间清理较旧工具结果，用占位文本表示内容被移除，并默认保留工具调用参数；调用方可以配置是否连工具输入也一起清理。

## 6. 版本实现：缓存热时与缓存冷却后的两种思路

直接改写旧消息会改变请求前缀，从而破坏对应位置之后的 Prompt Cache。讨论中引用的特定版本实现因此区分两种思路：

### 6.1 时间型 Microcompact

当旧缓存价值已经较低时，直接修改本地消息，把旧 `tool_result.content` 换成占位符。

优点是后续请求体直接变小；代价是被修改位置之后的旧前缀不再相同。

### 6.2 Cached Microcompact

缓存仍值得复用时，本地 transcript 可暂时保持不变，在 API 层提交针对缓存视图的编辑信息，例如按工具调用 ID 清理旧结果。

这条路径的核心权衡是：

```text
减少上下文
    vs
保留已经建立的 Prompt Cache
```

具体字段名和分支条件来自版本相关实现，不应视为 Claude Code 的稳定公共接口。当前 Claude API 已公开 `context_management` 的工具结果清理能力，并会在响应的 `context_management.applied_edits` 中报告实际清理量；但该 API 功能与某一版 Claude Code 内部 Microcompact 不能直接画等号。

## 7. 全量压缩的语义部分来自旧消息

当工具结果清理仍不足以释放空间时，Claude Code 会对旧会话生成结构化摘要，用它替换大段历史。摘要负责保留：

- 用户的主要目标和约束；
- 已完成的工作和关键决策；
- 重要代码位置、错误及修复；
- 当前工作状态；
- 待办任务和下一步。

这部分确实来自压缩前的消息历史，是一次有损的语义提炼。详细工具输出、早期措辞和未被摘要选中的细节可能丢失，因此长期有效的强约束不应只存在于聊天中，而应放入项目根 `CLAUDE.md` 或其它可重新加载的规则文件。

## 8. 摘要请求为什么可以复用主会话缓存

当前 Claude Code Prompt Caching 文档公开说明：摘要请求使用与主会话相同的 system prompt、tools 和历史，并在末尾追加摘要指令。因而摘要请求共享主会话前缀，可以读取已有 Prompt Cache。

特定构建的第三方还原进一步把它描述为一次性的摘要 Agent，并显示它尽量继承主请求的：

```text
模型
工具定义
系统提示
thinking / effort 配置
原会话消息前缀
```

只在末尾追加摘要指令：

```text
[与主会话相同的大段前缀][请总结上述会话]
```

这样摘要请求有机会读取主会话已建立的 Prompt Cache，只重新处理新增的摘要指令。

该实现中的摘要 Agent 被限制为单轮且不能实际调用工具。这里的目标不是让它继续执行任务，而是让它只根据现有历史生成压缩摘要。

## 9. 版本实现：为什么缓存共享路径不一定单独设置 20K

讨论中最关键的因果链是：

```text
想复用主会话 Prompt Cache
    ↓
影响缓存的请求配置要尽量保持一致
    ↓
单独降低 max output tokens 可能连带压低 thinking budget
    ↓
thinking 配置变化可能使消息缓存失效
    ↓
缓存共享摘要路径不随意覆盖输出上限
```

因此，“没有单独设置 20K”不等于“摘要可以无限输出”。缓存共享路径仍受到：

- 模型和主请求继承的输出上限；
- 一次模型调用；
- 结构化摘要提示目标；
- 上下文窗口与服务端限制。

讨论中的版本还存在独立摘要回退路径：它使用摘要专用 system/tools、关闭或改变 thinking，并显式把摘要输出限制在 `min(20K, modelMax)`。因为这条路径本来就不能完整复用主请求前缀，所以无需为了缓存一致性保留全部主请求参数。

| 项目 | 缓存共享摘要路径 | 独立摘要回退路径 |
|---|---|---|
| 主要目标 | 复用主会话前缀缓存 | 稳定生成摘要 |
| system / tools | 尽量与主请求一致 | 使用摘要专用配置 |
| thinking | 继承主请求 | 可显式关闭或调整 |
| 单独 20K 上限 | 版本中未覆盖 | 版本中显式设置 |
| 输入成本与延迟 | 命中时较低 | 通常需重处理更多输入 |

`20K`、具体函数和回退条件都是特定版本实现值，不是 Anthropic API 的永久契约。当前 Claude Code 官方文档可确认：截至 v2.1.198，摘要请求会继承会话的 extended thinking 开关；它不能证明所有更早或更晚版本都采用完全相同的内部调用结构。

## 10. 压缩后恢复的信息来自哪里

压缩后的上下文不只是：

```text
newContext = [summary]
```

更接近：

```text
newContext = [
  compactBoundary,
  summary,
  reloadedProjectRules,
  currentFileOrTaskAttachments,
  invokedSkills,
  freshSessionStartOrPostCompactHookResults,
]
```

来源应分开理解：

| 压缩后内容 | 主要来源 | 是否由旧消息语义推断 |
|---|---|---|
| 会话摘要 | 压缩前消息历史 | 是，由模型总结 |
| 项目根 `CLAUDE.md` / 无作用域规则 | 当前磁盘 | 否，重新注入 |
| Auto memory | 当前持久化内容 | 否，重新注入 |
| 最近读取文件的路径候选 | 会话运行时文件状态 | 通常不是模型推断 |
| 恢复时的文件正文 | 当前磁盘重新读取 | 否 |
| 异步任务状态 | 当前任务注册表/运行时状态 | 否 |
| Plan、已调用 Skills | 对应运行时状态或持久化内容 | 否 |
| Hook 结果 | 压缩后执行 `SessionStart(source=compact)`；配置了 `PostCompact` 时也会触发 | 否 |
| 少量已发现工具或关联元数据 | 可能扫描旧消息 | 部分是 |

这形成一个重要分工：

```text
摘要负责保存“发生过什么”
附件和重注入负责恢复“现在是什么状态”
```

## 11. 版本实现：“最近五个文件”具体是什么意思

讨论中引用的版本实现不是让 LLM 从聊天语义中选出“最重要的五个文件”，而是：

1. 从压缩前的文件读取状态中取得路径和访问时间；
2. 按最近访问排序；
3. 选取最多若干个文件；
4. 压缩后从磁盘重新读取这些文件的当前内容。

所以：

```text
恢复哪些文件：由压缩前运行时状态提供候选
恢复什么内容：由压缩时的当前文件系统提供
```

如果文件在首次读取后被修改，压缩恢复时看到的是新内容；如果文件已删除或不可访问，不能假定系统会从旧聊天中的副本兜底。

“5 个”属于所讨论版本的实现常量。官方文档确认项目根规则、auto memory、Skills 等机制的压缩后行为，但没有把“永远恢复最近 5 个普通文件”承诺为稳定接口。

## 12. 版本实现：异步任务状态为什么不是从对话猜出来的

压缩后若要提示某个后台任务仍在运行，更可靠的来源是当前任务注册表，而不是扫描旧消息看到“曾经调用过 Agent”后猜测。

因此可能出现：

- 启动任务的原始消息已被摘要，但运行时任务仍存在，于是状态可以重新注入；
- 任务在摘要生成期间从 `running` 变成 `completed`，附件反映的是稍后的当前状态；
- 进程重启后任务注册表没有恢复，仅靠 transcript 中的旧调用记录不能自动重建真实任务。

这也说明摘要和附件不一定是同一瞬间的严格原子快照。设计更偏向恢复最新权威状态，而不是机械复制压缩开始时的旧视图。

## 13. 对固定阈值公式的修正

Claude API 已公开服务端 Compaction 与 Context Editing。这些能力证明“摘要块”和“清理旧工具结果”是公开的上下文管理范式，但不能反向证明 Claude Code CLI 某版本内部所有函数名、常量和执行顺序。

博客给出过“原始窗口先减约 20K，再减 13K，因此约提前 33K 触发”的推导，并列出最近 5 个文件、50K 文件预算、25K Skill 预算等常量。

这些数字可作为特定构建的源码还原记录，但不能写成当前普遍公式：

- 模型可能使用不同上下文窗口；
- Auto compact 的有效容量可由环境变量调整；
- 百分比覆盖项会影响计算；
- 官方 Context Window 文档只公开了部分恢复预算，例如已调用 Skill 的单项和总量限制；
- 官方没有承诺永远恢复 5 个普通文件或固定保留 33K。

稳定结论应写成：

> Claude Code 会在接近有效上下文容量时先清理旧工具结果，必要时再生成结构化摘要，并从磁盘或运行时状态重新注入部分长期规则和当前状态；精确阈值与恢复预算必须按版本、模型和当前配置核验。

## 14. 常见误区

- **误区：Microcompact 会为每个旧工具结果生成摘要。** 版本实现中的占位符只是固定清理标记。
- **误区：占位符中包含工具名和参数。** 工具信息来自保留下来的 `tool_use`，不是占位符正文。
- **误区：可清理工具结果一定可以无损重放。** 重新读取或搜索通常只获得当前状态。
- **误区：全量压缩后只剩一段摘要。** 规则、memory、Skills、任务和 Hook 等可从其它状态源恢复。
- **误区：最近文件由 LLM 判断重要性。** 所讨论版本依据运行时访问状态选择，并重新读取当前磁盘。
- **误区：缓存共享摘要路径没有 20K 就没有输出上限。** 它继承其它输出约束，只是没有单独覆盖为该常量。
- **误区：第三方还原源码等同于官方稳定 API。** 它适合解释某版本行为，不适合承诺未来实现。
- **误区：Auto compact 永远在原始窗口剩余约 33K 时触发。** 当前官方配置允许改变有效压缩容量和百分比阈值。

## 15. 关联知识点

- `001_Claude_Code_Prompt_前缀缓存与三级上下文.md`
- `002_Claude_Code_流式输出、max_tokens_与恢复机制.md`
- `003_Claude_Code_代码检索：ripgrep_与_grep.md`
- `006_Claude_Code_Agent_Loop、Query_生命周期与工具编排.md`
- `007_Claude_Code_记忆体系：CLAUDE.md、Rules_与_Auto_Memory.md`
- `../02_Agent_RAG_Memory/006_Agent_的端到端任务能力.md`
- `../02_Agent_RAG_Memory/012_Agent_Memory_四类：短期、情景、语义、程序性.md`
- `../02_Agent_RAG_Memory/014_MemGPT：上下文窗口作为有限内存.md`

## 16. 参考资料与事实边界

### 官方资料

- [Claude Code 工作机制](https://code.claude.com/docs/en/how-claude-code-works)
- [Claude Code Context Window](https://code.claude.com/docs/en/context-window)
- [Claude Code Hooks](https://code.claude.com/docs/en/hooks)
- [Claude Code 环境变量](https://code.claude.com/docs/en/env-vars)
- [Claude Code Prompt Caching](https://code.claude.com/docs/en/prompt-caching)
- [Claude API Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Claude API Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction)
- [Claude API Context Editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)

### 本次讨论记录与版本相关实现线索

- 讨论记录：`https://chatgpt.com/share/6a6456f3-8e58-83ec-9243-aa2fc5b735c9`
- 第三方 Claude Code 还原源码分析：`https://github.com/liuup/claude-code-analysis`
- 第三方 Claude Code source map 还原：`https://github.com/JERRY-SYSTEM/claude-code-source`
- 本次梳理的 Compact 博客：`https://xiaolinnote.com/claudecode/source/cc_compact.html`

官方资料支持压缩、工具结果清理、缓存前缀、规则重注入等行为边界。`runForkedAgent`、`maxTurns: 1`、固定占位符、20K 回退上限、最近文件数量及具体状态字段来自第三方对特定版本的还原或分析，应作为“版本相关实现证据”，不能写成官方长期承诺。

## 17. 复习检查问题

1. Microcompact 为什么不等同于对每个工具结果做语义摘要？
2. 工具结果正文被清理后，模型为什么仍可能知道工具名和参数？
3. 为什么“可重新获取”不等于“可以无损重放”？
4. 缓存共享摘要路径为什么不宜随意修改 thinking 和输出参数？
5. 压缩后，摘要、文件内容和异步任务状态分别来自什么来源？
6. 为什么“最近五个文件”不能视为长期稳定的 Claude Code 契约？
