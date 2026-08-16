# DeepSeek Harness：Agent Loop、流式输出与工具编排

## 1. 一句话结论

dsh 的默认 `ReactLoopAgent` 用显式的 `turn` 和 `step` 驱动 Agent：一个 turn 可含零到多个 step；一个 step 是“一次模型请求，加上该请求产生的工具调用”。所有对模型可见的输入、输出和工具结果都写入 Session，再从 Session 导出下一次模型历史。

## 2. 先区分 Turn、Step 和 Stream

| 名词 | 含义 | 是否一定发生模型调用 |
| --- | --- | --- |
| Turn | 从一次唤醒开始到没有未偿工作 | 不一定；拒绝或空输入也会形成 turn 边界 |
| Step | 一次 request + 它触发的 tool executions | 是 |
| Stream chunk | provider 返回的一个增量块 | 属于某个 step；不是独立循环状态 |

把这三者混为“一轮对话”会造成恢复、取消、并发工具和 UI 呈现的错误设计。

## 3. 输入如何进入 Loop

`ReactLoopAgent` 维护一个 `Inbox` 和 `idle / maintenance / running` phase。公开方法表达了三种不同意图：

- `followup(input)`：写入 `next-turn` 并唤醒，适合新的用户追问。
- `steer(input)`：写入 `next-step` 并唤醒，适合把新信息插入当前工作之后。
- `inject(input)`：同样写入 `next-step`，但不唤醒；它等待下一次被允许进入的请求。

取消会 abort 当前活动，也可以清空 inbox。被取消后尚未开始的工具调用不会无声丢失：调度器会将它们记录为“dispatch 前已中止”的合成错误结果，以保持会话回放的结构完整。

## 4. 一个 Turn 的真实顺序

```text
turn/start
  └─ Inbox.claim(next-turn 或 next-step)
  └─ SystemPrompt.assemble()
  └─ agent/pre-step waterfall
       ├─ reject：以 blocked 结束 turn
       └─ enter(messages)
            └─ step/start
                 └─ 追加 user/message
                 └─ Session.deriveMessages()
                 └─ 组装请求；初始、恢复或 envelope 变化时记录 request/header
                 └─ LLM stream
                       ├─ assistant/chunk*
                       └─ assistant/message
                 └─ tool call 处理，结果进入 next-step
            └─ step/end
  └─ agent/turn-stopping（没有下一 step 输入时）
turn/end
```

`agent/pre-step` 是非常强的扩展点。它可改写这一步进入模型的消息，或直接拒绝；但它不替代 Session 记录。真正进入的消息仍在 step 内被写成 `user/message`，所以之后可以重放。

## 5. Prompt、历史与请求头不是一件事

请求构建时有三类数据：

1. **系统输入**：`SystemPrompt.assemble()` 得到 section、动态 context 和工具 schema，再渲染为 system prompt。
2. **历史消息**：`session.deriveMessages()` 从 durable surface 投影。
3. **路由与调用参数**：provider、model、reasoning effort、max tokens 等，先经 `agent/request` waterfall，再交给 LLM adapter 解析默认值。

最终有效的 config、system prompt 和工具 schema 由最新 `request/header` 完整快照重建，但稳定 step 不会重复写相同 header：首次请求记录 `initial`，新 Loop 从既有历史恢复时记录 `resume`，非历史 request envelope 真正改变时记录 `change`。`request/context` 也只在精确 provider/model route 或 adapter 公布的 context capacity 改变时追加。这样既能重建请求，又不会把不变的 system/tool 前缀逐步复制进日志。

## 6. 流式输出与错误恢复

Loop 用 `BlockAssembler` 吸收 provider stream。每个 chunk 先写为 `assistant/chunk`，完成后汇总成 `assistant/message`；后者才是下一步模型历史的主要 assistant 消息。这样同时满足：

- UI 可以显示 token 级/块级流；
- 回放能保留流信息；
- 普通对话历史不必把每个传输 chunk 当作一条消息。

若 stream 结束为 provider error 或 aborted，`agent/request-error` waterfall 可以决定是否 retry；否则 Loop 抛出结构化 `LlmError`。若到达 output token 上限，step 返回 `max-tokens`，该状态在该 turn 内保持 sticky，不能被随后正常 step 隐藏。

源码没有证明一个固定的“自动续写提示词”策略；能证明的是 Loop 把 retry 和后续 step 的策略开放为事件/插件扩展点。

## 7. 模型工具调用如何变成下一步上下文

assistant message 中的 `tool-call` block 被送给 `executeToolCalls()`：

1. 原始参数字符串尽量解析 JSON；解析失败时保留原始文本给工具策略处理。
2. 每个调用先记录 `tool/call`。
3. 工具 registry 决定它当前是 `parallel` 还是 `exclusive`。
4. parallel 调用使用受 `maxParallelToolCalls` 限制的滚动池；exclusive 调用形成 barrier。
5. 执行完成的结果按**模型原始调用顺序**提交，即使底层执行并发完成顺序不同。
6. 每个结果记录为 `tool/result`，并转成 user-role 的 tool-result message 排入 `next-step`。

这一设计解决一个常见 Agent 工程问题：并发能缩短墙钟时间，但不能让模型在下一请求看到随机顺序的 observation。

## 8. 工具执行管线与 Loop 的边界

Loop 只做“何时调度”和“如何把结果写回日志/下一 step”。工具 registry 决定“是否允许及如何执行”：

```text
tools/pre-execute  →  approval / deny / allow
tools/execute      →  timeout、retry、metrics 等 around wrapper
工具 body
tools/post-execute →  接受、替换、丰富或阻止结果
```

这使 sandbox、权限、重试和业务工具实现无需侵入 `ReactLoopAgent`。一个新工具通常注册 schema 与 body；一个横切策略通常监听工具事件；二者都不应复制整个 loop。

## 9. 结束条件和失败路径

一个 turn 结束于以下可观察原因之一：正常完成、max-tokens、blocked、取消、错误，或持久化加载时修复出的 interrupted。空的首次输入、被 `pre-step` 拒绝的输入和中途取消不应被错误地解释成“模型自然回答结束”。

`turn/end` 与 `step/end` 放在 `finally` 路径中记录，目的不是掩盖错误，而是把已经开始的生命周期完整地留给恢复、UI 和测试观察。

## 10. 常见误区

- ReAct 是一种解释模型行为的范式，不是 dsh 源码中的唯一状态名；应以 turn/step/event 为准。
- 并发 tool call 不等于并发写模型历史；dsh 明确按模型顺序提交。
- chunk 并非最终 assistant message；不能只保存 chunk 或只保存最终文本而忽略工具块。
- Plan Mode 不需要第二套 Loop；它通过能力、prompt 和交互政策影响同一运行时。

## 11. 源码阅读任务

1. 在 `turn()` 中找出空首次输入为何仍有 `turn/start`/`turn/end`。
2. 在 `step()` 中追踪 `assistant/chunk` 到 `assistant/message` 的转换。
3. 在 `runGroup()` 中说明为什么 `commitReady()` 必须按 index 提交。
4. 选一个工具插件，继续追到 `tools/pre-execute` 的实际策略监听器。

## 12. 证据索引

- `D:/codes/deepseek-harness/packages/core/agent-loop/src/agent.ts`
- `D:/codes/deepseek-harness/packages/core/agent-loop/src/tool-calls.ts`
- `D:/codes/deepseek-harness/packages/core/tools/src/index.ts`
- `D:/codes/deepseek-harness/packages/core/system-prompt/src/index.ts`
- `D:/codes/deepseek-harness/packages/core/session/src/types.ts`
- `D:/codes/deepseek-harness/docs/architecture.md`
