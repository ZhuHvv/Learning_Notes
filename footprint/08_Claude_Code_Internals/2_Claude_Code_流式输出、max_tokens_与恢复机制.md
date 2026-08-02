# 08.02 Claude Code 流式输出、max_tokens 与恢复机制

## 1. 先区分两种长度限制

| 限制 | 含义 | 典型处理 |
|---|---|---|
| Context window | 一次请求可容纳的输入上下文与输出预算总空间 | 压缩、清理、减少输入或切换更大上下文模型 |
| `max_tokens` / max output tokens | 一次模型响应最多允许生成多少输出 token | 提高单次上限、重试或拆成多次响应续写 |

两者有关联，但不是同一个概念。提高 `max_tokens` 会为输出预留更多空间，也可能使 Claude Code 更早触发上下文压缩；然而一次输出触顶并不等于整个会话上下文已经耗尽。

## 2. 单次输出仍然是流式返回

Anthropic Messages API 的流式响应由多类结构化事件组成，概念顺序如下：

```text
message_start
  content_block_start
  content_block_delta      # 文本、thinking 或工具参数增量
  content_block_stop
message_delta              # 整条消息的最终 stop_reason 和 usage
message_stop               # 本条消息的事件流结束
```

`message_delta` 不是正文中的特殊字符串，而是协议级事件。它携带整条消息的最终状态，例如：

```json
{
  "type": "message_delta",
  "delta": {
    "stop_reason": "max_tokens"
  },
  "usage": {
    "output_tokens": 32000
  }
}
```

`message_stop` 才表示该消息对应的流正式结束。可以简化理解为：

```text
content_block_delta = 正文或结构化内容持续增加
message_delta       = 给出整条回复的结束原因和最终用量
message_stop        = 宣告传输收尾
```

## 3. 谁负责统计输出长度

模型服务端逐 token 生成，因此由服务端维护权威的输出 token 计数：

```text
生成 token 1 → token 2 → ... → token N
                                ↓
                    N 达到请求的 max_tokens
                                ↓
                停止采样并返回 stop_reason=max_tokens
```

网络 chunk 只是传输分片，不是 token 计量单位：

```text
模型 token： t1  t2  t3  t4  t5  t6
网络 chunk：[t1,t2] [t3] [t4,t5,t6]
```

一个 chunk 可能包含一个或多个 token，也可能只是文本、thinking 或工具调用 JSON 的增量片段。Claude Code 会累计 chunk 以展示内容和组装消息，但没有必要通过“chunk 数量”或“字符总数”判断是否触顶。

权威判断条件是流结束时收到：

```text
message_delta.delta.stop_reason == "max_tokens"
```

而不是判断某个普通内容 chunk 的文字是否等于 `max_tokens`。

## 4. 常见 stop reason

| stop reason | 含义 |
|---|---|
| `end_turn` | 模型认为本轮自然完成 |
| `tool_use` | 模型请求执行客户端工具 |
| `max_tokens` | 本次响应达到请求设置的输出上限，可能被截断 |
| `stop_sequence` | 命中了调用方配置的停止序列 |
| `pause_turn` | 服务端工具循环达到单次迭代限制；把 assistant 响应原样加入历史后再次调用 |
| `refusal` | 模型拒绝完成请求 |
| `model_context_window_exceeded` | 响应先填满模型上下文窗口，而不是先达到请求的 `max_tokens` |

因此，Claude Code 不能仅凭“输出恰好停在半句话”判断错误；它应该根据协议提供的 `stop_reason` 做状态迁移。

`pause_turn` 不适用于等待客户端工具结果的普通 `tool_use`：客户端工具仍以 `stop_reason=tool_use` 结束，并由宿主回填 `tool_result`。`pause_turn` 主要出现在 Web Search、Web Fetch 等服务端工具的内部循环。

`max_tokens` 与 `model_context_window_exceeded` 也必须分开：前者表示达到了请求设置的单次输出上限；后者表示输入加输出先耗尽了模型上下文空间。两者都可能产生截断内容，但调参方向不同。

## 5. 恢复策略一：提高上限并重试原调用

从特定 Claude Code 构建的第三方还原分析看，当首次遇到可恢复的 max-output 条件、且当前模型仍允许更高输出上限时，Claude Code 曾采用提高 `max_tokens` 后重新执行原调用的策略。该分支不是 Agent SDK 或 Claude Code 官方文档承诺的公共接口，应用开发者不应仅凭这份内部还原复制固定阈值或重试次数。

```text
第一次调用：
[原输入上下文] --较低 max_tokens--> 截断输出 A

扩容重试：
[原输入上下文] --较高 max_tokens--> 重新生成输出 B
```

这一步属于**重试**，不是续写：

- 截断输出 A 不作为续写起点；
- 模型从原输入重新生成，B 不保证逐字等于 A 的前半段；
- A 已消耗的输出 token 不能撤销，且一般不会作为最终正式回复保留；
- 原输入前缀相同，服务端 Prompt Cache 仍可能减少第二次调用的输入预填充成本。

为什么先重试？因为第一次触顶可能只是默认上限偏保守。若提高到模型允许的更大单次响应上限，一次调用就可能完整结束，避免拼接多段回复。

## 6. 恢复策略二：保留断点并发起续写调用

同一版本还原还显示：若更高上限仍然得到 `max_tokens`，可以把截断结果作为历史中的 assistant 内容，再追加一条内部用户消息：

```text
[原输入]
[assistant：已经生成的前半段]
[user/meta：从刚才停止的位置直接继续]
                         ↓
                  发起下一次模型调用
```

这一步属于 Agent Loop 中的**下一次模型调用**，不一定需要用户亲自发送“继续”。新调用拥有新的单次输出预算，而前半段作为输入告诉模型目前完成到了哪里。

伪代码如下：

```python
response = call_model(messages, max_tokens=normal_limit)

if response.stop_reason == "max_tokens" and can_escalate():
    # 重试：不把第一次截断输出加入续写上下文
    response = call_model(messages, max_tokens=larger_limit)

continuations = 0
while response.stop_reason == "max_tokens" and continuations < limit:
    # 续写：保留已经生成的内容，追加内部恢复提示
    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": "Resume directly from where you left off."})
    response = call_model(messages, max_tokens=larger_limit)
    continuations += 1
```

具体提示词、上限常量和最大续写次数会随 Claude Code 版本、模型及服务提供方变化，不能把示例值视为稳定 API 契约。

## 7. 为什么“已经很长”还要续写

因为 `max_tokens` 是**单次响应上限**，而不是整个任务的总输出上限：

```text
每次调用最多 N 个输出 token
不等于
整个 Agent 任务最多只能产生 N 个输出 token
```

类似分页：一页写满并不表示整篇文档必须结束，而是需要另开一页继续。续写后总生成量确实更长，但每一次 API 响应都没有突破自己的硬上限。

续写尤其适合：

- 模型仍在进行多步工具调用，任务状态尚未完成；
- thinking 消耗了大量输出预算，尚未来得及产生最终工具调用或答案；
- 任务本身确实需要跨多个模型调用完成。

如果每次续写都持续触顶，则可能是任务粒度过大、工具参数异常膨胀、输出要求不合理或模型陷入循环。工程上应限制恢复次数，随后向上层报告错误、拆分任务或调整提示，而不是无限续写。

## 8. 输出 token 不只包含可见正文

在 Agent 调用中，本次输出预算可能用于：

- 模型 reasoning / thinking；
- 文本回复；
- 工具调用名称和参数；
- 同一响应中的多个内容块。

因此，出现 `max_tokens` 不一定意味着终端已经显示了极长文章。模型可能在 thinking 中消耗大部分预算，或正在生成大型工具参数时被截断。诊断时应查看 API usage、stop reason、内容块类型和工具调用状态。

## 9. 一条完整恢复链路

```text
Claude Code 发起流式请求
  ↓
接收 content_block_delta，累计并展示内容
  ↓
收到 message_delta
  ├─ end_turn     → 正常结束
  ├─ tool_use     → 执行工具并进入下一轮 Agent Loop
  ├─ model_context_window_exceeded
  │                 → 将结果视为截断，压缩或减少输入后再决定是否继续
  └─ max_tokens
       ├─ 尚可提高单次上限 → 丢弃截断结果，扩容重试原调用
       └─ 已无法继续扩容   → 保留断点，追加恢复消息并续写
                              ↓
                       超过恢复次数则暴露错误
  ↓
收到 message_stop，完成本次流收尾
```

这条图只描述单次模型流与输出恢复。完整 Query 生命周期还包括权限、工具执行、上下文压缩、取消、最大轮数和后台任务，详见 `006_Claude_Code_Agent_Loop、Query_生命周期与工具编排.md`。

## 10. 博客 Query Loop 表述的事实边界

Query Loop 博客展示了 `ask → QueryEngine.submitMessage → query → queryLoop`、异步生成器和内部 `needsFollowUp` 等结构。应分层理解：

| 内容 | 证据等级 |
|---|---|
| 模型请求工具、宿主执行、结果回填并继续 | Anthropic Messages API 与 Agent SDK 的公开契约 |
| SDK `query()` 以异步迭代方式返回消息 | 官方 SDK 公开接口与示例 |
| `message_delta`、`message_stop`、`stop_reason` | Messages API 公开流式协议 |
| Claude Code 内部恰好四层调用链 | 特定构建/source map 还原 |
| `needsFollowUp`、`StreamingToolExecutor` 等名称 | 特定版本内部实现 |
| “正常逻辑约 200 行、异常路径占 80%” | 作者的近似总结，不是可验证的软件指标 |

博客说“有 `tool_use` 就继续，没有就完成”适合解释正常路径；严格实现仍要对 `max_tokens`、`refusal`、`pause_turn`、权限拒绝、最大轮数和取消分别处理。

## 11. 你在讨论中的理解推进

- 起点：把上下文总长度和单次输出长度混为同一限制。
- 修正：Context window 管整体请求空间，`max_tokens` 管一次模型响应的生成预算。
- 追问：既然输出以 chunk 返回，客户端是否需要累计所有 chunk 长度判断超限。
- 关键理解：模型服务端逐 token 计数；chunk 只是网络分片，Claude Code 根据最终 `message_delta.stop_reason` 做权威判断。
- 协议深化：`message_delta` 是携带结束原因和 usage 的结构化状态事件，`message_stop` 才表示流正式结束。
- 最终理解：第一次扩容是从原输入重新生成的重试；之后续写是把已生成部分变成历史，使用新的单次输出预算继续同一任务。

## 12. 常见误区

- **误区：收到某个文本 chunk 写着 `max_tokens` 才算触顶。** 实际判断的是结构化 `message_delta.delta.stop_reason`。
- **误区：客户端按 chunk 数量控制模型停止。** 服务端逐 token 生成并执行上限，chunk 与 token 没有固定一一关系。
- **误区：扩容重试会从截断点继续。** 扩容重试从原输入重新生成；保留截断内容后再调用才叫续写。
- **误区：单次响应触顶等于上下文窗口耗尽。** 两者是不同限制和不同 stop/error 条件。
- **误区：所有截断都返回 `max_tokens`。** 新模型还可能返回 `model_context_window_exceeded`，表示上下文窗口先耗尽。
- **误区：续写没有额外成本。** 续写会产生新的输出 token，也会把之前内容作为输入；Prompt Cache 只能降低部分重复输入计算成本。
- **误区：没有 `tool_use` 就必然是正常完成。** 还要检查 stop reason 与外层 terminal reason。
- **误区：博客中的内部函数名就是 Agent SDK API。** SDK 公开 `query()` 和消息类型，不承诺 CLI 内部调用层次。

## 13. 关联知识点

- `001_Claude_Code_Prompt_前缀缓存与三级上下文.md`
- `004_Claude_Code_上下文压缩、Microcompact_与状态恢复.md`
- `006_Claude_Code_Agent_Loop、Query_生命周期与工具编排.md`
- `../01_LLM_Transformer/7_Causal_Mask、自回归生成与_KV_Cache.md`
- `../02_Agent_RAG_Memory/2_Agent_的端到端任务能力.md`
- `../02_Agent_RAG_Memory/11_LangGraph_状态更新、invoke_与_stream.md`
- `../04_Go/9_Go_SSE：text_event-stream_与流式响应.md`
- `../07_Backend_Deploy_Network/7_HTTP_Streaming、SSE、WebSocket_与_gRPC_Streaming.md`

## 14. 参考资料与事实边界

- [Anthropic Stop Reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons)
- [Claude Agent SDK Agent Loop](https://code.claude.com/docs/en/agent-sdk/agent-loop)
- [Claude Tool Use 工作机制](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works)
- [Claude Code 环境变量](https://code.claude.com/docs/en/env-vars)
- [Claude Code Prompt Caching](https://code.claude.com/docs/en/prompt-caching)
- 本次梳理的 Query Loop 博客：`https://xiaolinnote.com/claudecode/source/cc_query_loop.html`

官方文档可以确认流式事件、`stop_reason=max_tokens`、工具循环及输出上限配置。Claude Code 内部“先扩容再续写”的具体分支、内部提示词、常量、重试次数与函数名来自特定版本实现分析，未来版本可能变化。

## 15. 复习检查问题

1. `message_delta` 和 `message_stop` 的职责有什么区别？
2. 为什么不能通过累计 chunk 数量判断是否达到输出 token 上限？
3. 扩容重试与断点续写在消息历史上有什么差异？
4. 为什么续写不会突破模型的单次输出硬上限？
5. 模型没有显示很长正文时，为什么仍可能出现 `max_tokens`？
6. `max_tokens` 与 `model_context_window_exceeded` 分别说明哪一层预算先触顶？
