# Claude Code Agent Loop、Query 生命周期与工具编排

> 所属分类：Claude Code 源码与机制解读  
> 整理日期：2026-07-26；审查更新：2026-07-26  
> 核心问题：Claude Code 的一轮任务怎样在模型、工具、权限、上下文与流式事件之间循环，哪些结论是公开契约，哪些只是特定构建的实现还原？

## 1. 先给结论

Claude Code 的稳定核心不是某个名为 `queryLoop` 的函数，而是一条由结构化协议驱动的 Agent Loop：

```text
用户目标 + 系统指令 + 项目上下文 + 历史消息 + 工具定义
                         ↓
                      调用模型
                         ↓
          ┌──────────────┴──────────────┐
          │                             │
     返回 tool_use                 没有 tool_use
          │                             │
   权限检查并执行工具                 结束本轮
          │
   追加 tool_result
          │
          └──────────→ 再次调用模型
```

Anthropic 官方 Agent SDK 文档将同一循环描述为：

1. 接收 prompt、system prompt、tools 和历史；
2. 模型返回文本、一个或多个工具调用，或两者同时返回；
3. 运行工具并把结果送回模型；
4. 重复，直到模型不再请求工具。

这套循环由两部分组成：

```text
模型：根据当前上下文决定下一步
Harness：提供工具、执行环境、权限、消息编排、上下文管理与错误恢复
```

## 2. “Tool-Use Loop”与 ReAct 不应画成绝对对立

博客把 Claude Code 描述为“不使用 ReAct，而使用没有显式 Thought 的 Tool-Use Loop”。这个说法有启发性，但需要收紧。

如果把 ReAct 严格限定为论文中的显式文本轨迹：

```text
Thought → Action → Observation
```

Claude API 的原生工具调用确实不要求应用从自由文本中解析 `Action`，也不要求把可见的 `Thought:` 文本写入历史。模型可以直接返回结构化 `tool_use`。

但如果把 ReAct 广义理解为：

```text
推理/决策 → 行动 → 获取新观察 → 再决策
```

Claude Code 的 Agent Loop 仍然属于这种行动—观察闭环。更准确的结论是：

> Claude Code 使用 API 原生工具调用实现 Agent Loop，不依赖经典 ReAct 的自由文本 `Thought/Action/Observation` 解析格式；这不等于系统没有推理，也不等于它在广义上脱离了“行动后观察再决策”的范式。

Extended Thinking 解决“模型在一次调用中怎样推理”，Agent Loop 解决“系统怎样通过外部工具获得新信息并继续”。两者位于不同层次，可以同时存在。

## 3. 公共协议中的一轮工具调用

Claude Messages API 对客户端工具的公共契约是：

```text
assistant:
  tool_use(id, name, input)
        ↓
应用执行对应工具
        ↓
user:
  tool_result(tool_use_id, content, is_error?)
        ↓
下一次模型调用
```

简化消息示例：

```json
[
  {
    "role": "assistant",
    "content": [
      {
        "type": "tool_use",
        "id": "toolu_123",
        "name": "read_file",
        "input": {"path": "src/app.ts"}
      }
    ]
  },
  {
    "role": "user",
    "content": [
      {
        "type": "tool_result",
        "tool_use_id": "toolu_123",
        "content": "..."
      }
    ]
  }
]
```

`tool_result` 使用 `user` role 是 Anthropic 消息协议的承载方式，不代表该内容来自真实用户。工具调用与结果通过 ID 配对。

协议还要求注意消息顺序：

- 对一个 assistant 响应中的每个客户端 `tool_use`，后续都要提供对应的 `tool_result`；
- 多个结果应放在同一条紧随其后的 `user` 消息中；
- 这些 `tool_result` block 必须位于该条 `user` 消息内容的最前面，普通文本放在其后；
- `tool_use_id` 必须与原调用 ID 一一匹配。

这不仅是风格建议。若插入无关消息、漏掉结果或配错 ID，下一次 API 请求可能因消息结构非法而失败。

## 4. 终止条件必须同时看“协议原因”和“是否有工具调用”

最小 API 工具循环通常写成：

```text
while stop_reason == "tool_use":
    执行 tool_use
    追加 tool_result
    再次请求
```

Claude Agent SDK 的更高层描述则是“直到响应中没有工具调用”。两种表述服务于不同抽象层：

| 信号 | 作用 |
|---|---|
| `tool_use` 内容块 | 告诉宿主要执行什么工具及其参数 |
| `stop_reason = "tool_use"` | 告诉客户端本次响应停下来等待客户端工具结果 |
| 没有工具调用 | 高层 Agent Loop 可把本轮视为无需继续执行客户端工具 |
| `end_turn` | 模型自然结束当前回合 |
| `max_tokens`、`model_context_window_exceeded`、`refusal`、`stop_sequence` | 不是“正常完成工具任务”，应进入各自的恢复或终止分支 |
| `pause_turn` | 常见于服务端工具循环暂停，需按协议把响应带回继续 |

因此博客中“只看有没有 `tool_use`，没有复杂状态机”的说法只适合解释正常路径。工业实现还必须处理取消、权限拒绝、工具失败、输出触顶、最大轮数、上下文压缩、服务端错误和后台任务等终止原因。

公开 Agent SDK changelog 已暴露 `terminal_reason`，示例包括：

```text
completed
aborted_tools
max_turns
blocking_limit
...
```

这也说明 Query 生命周期不能只压缩成一个布尔量。

## 5. 流式输出：传输事件不等于循环状态

流式响应会产生文本、thinking、工具参数增量和消息收尾事件。Harness 可以边接收边向 UI 转发：

```text
模型内容增量
  ├─ 文本增量 → 立即展示
  ├─ thinking 增量 → 按产品策略展示或隐藏
  └─ tool input JSON 增量 → 累积成完整工具参数
```

但必须区分：

- “收到一段流式增量”只表示内容正在传输；
- “完整 `tool_use` 块可执行”要求工具名和参数已满足协议；
- “消息流结束”由收尾事件确认；
- “Agent 任务完成”还取决于 stop reason、工具结果和外层预算。

博客展示的 `async function* query()`、`yield* queryLoop()`、`ask → QueryEngine.submitMessage → query → queryLoop` 调用链来自特定构建还原。异步迭代器很适合表达事件流，官方 Agent SDK 的 `query()` 也公开为异步迭代接口；但这些内部函数名、层数和行数不是稳定 API。

## 6. 多工具调用与并发

一次 assistant 响应可以包含多个 `tool_use` 块。公共 API 不规定调用方必须并行或串行；执行策略由 Harness 根据工具语义决定：

```text
独立、只读、无共享副作用
  → 通常适合并行

写文件、修改共享状态、存在顺序依赖
  → 通常应串行或显式建立依赖
```

所有并行调用的结果应在同一条后续 `user` 消息中作为多个 `tool_result` 返回，并用 `tool_use_id` 一一配对。

博客进一步声称某版 Claude Code 使用 `StreamingToolExecutor`，在模型仍流式输出时就启动已完整识别的工具调用，并由工具的只读属性决定并发。这是可能的特定版本优化，但当前官方公开文档没有把以下细节承诺为稳定接口：

- 内部类名一定是 `StreamingToolExecutor`；
- 所有只读工具一定立即并行；
- 所有带副作用工具一定按同一种规则串行；
- 工具块尚未完成时就一定可以安全执行。

可稳定迁移的原则是：

> 并发单位必须确实独立；权限检查、工具参数完整性、共享状态与结果顺序都应先于“抢跑”优化。

## 7. 工具错误为什么必须回填

当模型请求了客户端工具，下一次消息历史必须为相应 `tool_use` 提供匹配的 `tool_result`。如果工具不存在、权限被拒绝或运行失败，也应返回结构化错误：

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_123",
  "is_error": true,
  "content": "Permission denied: write access was not granted."
}
```

不能简单丢掉失败工具调用，否则历史中会出现孤立的 `tool_use`，后续请求可能违反消息协议。把错误作为观察送回模型，模型才有机会缩小范围、换只读方案、向用户请求权限或停止。

并行批次中，即使某个前置写操作失败，未执行的后续调用也应各自收到错误结果，而不是直接从历史中消失。

## 8. 权限、安全与工具定义是 Harness 的核心

模型只提出工具调用，真正执行由 Claude Code 或 SDK 宿主负责。稳定的安全边界包括：

```text
模型建议行动
    ↓
权限规则 / Hook / Sandbox / 工作目录边界
    ↓
宿主允许、拒绝或要求用户确认
    ↓
实际工具执行
```

因此不能把“模型知道不要做危险操作”当成安全机制。`CLAUDE.md` 和 prompt 是行为指导；权限规则、Hook 与沙箱才是执行层约束。

博客对 Claude Code 内部“安全治理层”的总结方向正确，但“四层架构”更适合作为解释模型，不是 Anthropic 公布的模块边界。公开事实是 Claude Code 作为 agentic harness 提供工具、上下文管理和执行环境，并通过权限规则、Hook 与沙箱约束工具执行。

## 9. Plan Mode 不需要第二套 Agent Loop

Plan Mode 可以理解为对同一循环施加能力约束：

```text
正常模式：可读取、搜索、编辑、执行
Plan Mode：主要读取、搜索、设计方案
退出 Plan：提交计划并等待批准
批准后：恢复可写能力并继续同一任务
```

这说明“模式”未必需要复制一套循环。它可以通过工具可用性、权限模式、系统指令和状态转换改变同一 Agent Loop 的行为。

从缓存角度看，普通权限模式切换不会改变 system prompt 或工具定义，因此是 cache-safe；但若使用会在 Plan 与执行阶段切换模型的 `opusplan` 设置，则模式切换同时是模型切换，会建立另一套模型缓存。

但博客中“每 5 轮注入提醒”“计划固定写入某路径”等细节若没有当前官方文档或当前构建验证，只能标记为版本相关。

## 10. Query Loop 的状态模型

一个更接近生产实现的概念状态应至少包含：

```text
messages / session id
turn count / token 与成本预算
当前模型与 thinking/effort 配置
权限模式与可用工具
已发起工具调用及结果
取消信号
压缩与恢复状态
后台任务注册表
终止原因
```

概念状态迁移：

```text
ready
  └─ submit_prompt → streaming_model

streaming_model
  ├─ tool_use → awaiting_or_running_tools
  ├─ end_turn → completed
  ├─ max_tokens → recovering_output
  ├─ model_context_window_exceeded → compacting_or_truncated
  ├─ context_limit → compacting
  ├─ refusal → refused
  └─ cancel/error → cancelled/failed

awaiting_or_running_tools
  ├─ results_ready → ready
  ├─ permission_denied → ready 或 aborted_tools
  └─ cancel/error → cancelled/failed

compacting
  ├─ restored → ready
  └─ failure_limit → failed
```

具体枚举随版本变化，但“状态、事件、合法迁移、副作用”这四项是可靠 Agent Loop 的通用结构。

## 11. 对六篇博客相关表述的修正

| 博客表述 | 核验后的表述 |
|---|---|
| Claude Code 不使用 ReAct | 不依赖经典 ReAct 的自由文本格式；广义上仍是行动—观察循环 |
| 没有工具调用就一定正常完成 | 正常路径可以这样理解，但还要区分 `max_tokens`、拒绝、取消、限制与错误 |
| 内部固定是 `ask → QueryEngine → query → queryLoop` | 属于特定构建还原，不是公开稳定 API |
| 只读工具都并行、写工具都串行 | 是合理策略；API 只规定可返回多个工具调用，实际调度由 Harness 决定 |
| Extended Thinking 不占上下文、没有 token 成本 | thinking token 属于模型输出计算与预算的一部分；是否在后续历史中保留、如何计费应以当前模型/API文档为准 |
| Agent 的复杂度主要不在 `while(true)` | 这是可靠的工程判断：复杂度主要来自状态、权限、并发、恢复、上下文与可观测性 |

## 12. 与专题其它文档的关系

```text
006 Agent Loop
  ├─ 001 Prompt Cache：循环如何复用稳定请求前缀
  ├─ 002 流式与 max_tokens：单次模型响应怎样结束和恢复
  ├─ 003 Grep/ripgrep：搜索工具怎样为循环提供外部观察
  ├─ 004 Compact：消息滚雪球后怎样释放并恢复上下文
  ├─ 005 Multi-Agent：怎样把子任务交给独立循环
  └─ 007 Memory：怎样跨会话恢复项目规则与学习结果
```

## 13. 参考资料与事实边界

### 官方资料与公开代码

- [Claude Code 工作机制](https://code.claude.com/docs/en/how-claude-code-works)
- [Claude Agent SDK Agent Loop](https://code.claude.com/docs/en/agent-sdk/agent-loop)
- [Claude Code Tools Reference](https://code.claude.com/docs/en/tools-reference)
- [Claude Tool Use 工作机制](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works)
- [Claude Parallel Tool Use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/parallel-tool-use)
- [Claude Tool Call Handling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
- 官方 Claude Agent SDK Python：`https://github.com/anthropics/claude-agent-sdk-python`
- 官方 Claude Agent SDK TypeScript：`https://github.com/anthropics/claude-agent-sdk-typescript`

### 本次梳理的博客

- 源码架构：`https://xiaolinnote.com/claudecode/source/cc_source.html`
- Query Loop：`https://xiaolinnote.com/claudecode/source/cc_query_loop.html`

Claude Code 当前核心发行物不是一个完整公开源码仓库。官方 GitHub 仓库、SDK、类型定义、changelog 与文档可以验证公共行为，但不能验证闭源 CLI 内部每个函数名、行数、常量和调度优化。博客中的 `query.ts`、`QueryEngine`、`StreamingToolExecutor` 等应视为特定构建/source map 还原线索。

## 14. 复习检查问题

1. 为什么 API 原生 `tool_use` 不等于系统在广义上脱离 ReAct？
2. `tool_use` 内容块与 `stop_reason=tool_use` 分别承担什么职责？
3. 为什么工具失败也必须返回匹配的 `tool_result`？
4. 多个工具调用能否并行，最终由谁决定？
5. 为什么 `while(true)` 不是工业 Agent Loop 的主要复杂度来源？
6. 哪些 Query Loop 结论可以由官方 SDK 验证，哪些只能算版本相关实现？
