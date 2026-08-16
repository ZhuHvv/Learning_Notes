# DeepSeek Harness：Session 日志、持久化与记忆模型

## 1. 一句话结论

dsh 的核心记忆模型是追加式 Session event log：模型历史、工具结果、流式输出、请求头、压缩替换、todo 和许多产品状态均可从日志或其投影恢复。它不是把“聊天数组”和“UI 状态”分别作为没有关联的真相来源。

## 2. SessionEventMap 是什么

core/session/src/types.ts 的 SessionEventMap 定义了可扩展的 durable 事件词汇。核心事件包括：

    turn/start, turn/end
    step/start, step/end
    user/message
    assistant/chunk, assistant/message
    tool/call, tool/result
    request/header, request/context
    todo/write

user/message、assistant/message、tool/result 是 model-visible surface 的主要节点。它们带有 surfaceOp：普通 append，或由压缩等操作发起的 replace。sourceEventSeqs 连接可见节点与生成它们的原始事件，例如 assistant message 对应的 chunk。

## 3. “模型可见即已记录”

Loop 先在 durable log 中写入用户消息、assistant chunks/message 和工具结果，再由 deriveMessages() 投影给下一请求。request 的有效 config、system prompt、tool schemas 同样记录在 request/header。

因此重新打开 session、fork、Web UI 的工具卡片、导出 transcript、snapshot replay、token 计量、标题、统计和 telemetry projection 共享同一个事实基础。一个新功能若只把信息偷偷附加在内存 prompt 字符串上，会破坏这条不变量：恢复后的模型再也无法看到同一事实。

## 4. “记忆”至少分四类

| 类型 | dsh 的代表机制 | 适用问题 |
| --- | --- | --- |
| 对话/任务轨迹 | Session log 和 derived messages | 发生了什么、模型见过什么？ |
| 可恢复产品状态 | JSONL/SQLite persistence、checkpoint | 进程退出后如何继续？ |
| 派生视图 | projection、title、stats、query | UI/查询如何不重做业务状态？ |
| 工作区知识 | AGENTS/CLAUDE instructions、skills、文件工具 | 当前任务应遵循什么规则、去哪取知识？ |

这不是对“向量记忆”的否定。当前仓库中可直接证明的是 Session Query 的逻辑 corpus 与 SQLite 全文检索，以及 session reference 等机制；没有证据时，不应宣称其已经提供通用 embedding/vector memory。

## 5. 持久化与格式边界

dsh-session-persistence 定义 persistence seam，默认 base composition 使用 JSONL backend；SQLite backend 是可选 provider。持久化 backend 把连续事件按固定窗口批量 append，`session/flush` 是立即排空并等待持久化完成的 quiescence barrier。`session-checkpoint-policy` 不写“完整状态快照”，而是在模型请求、顶层工具副作用和下一 step 之前选择必须 flush 的语义屏障；缺少该 policy 的 backend 仍可工作，但硬崩溃可能丢失尚在批处理窗口或进行中写入里的事件。

Session header 记录 id、创建时间、cwd、fork lineage、delegation depth、agent preset 等元数据。当前 SESSION_FORMAT_VERSION 是 0：开发预览阶段没有跨版本迁移承诺，版本不匹配会在加载时拒绝。同一版本内的事件词汇扩展另有精确例外：本构建不认识的事件只有在事件 envelope 明确带 `ignorable: true` 时才可跳过；未知的 required-on-read 事件仍以 `SessionFormatUnsupportedError` 拒绝，不能静默猜测含义。

默认 JSONL artifact 是 `.jsonl.zstd`：一个带校验的 header frame，加上每个 durable append batch 的独立 Zstandard frame；`compression: none` 才使用原始 `.jsonl`。首次 `create()` 可以延迟到第一批 append 才物化文件，后续已 flush 的事件只追加、不重写。冷加载只丢弃撕裂的尾部碎片；已提交损坏会拒绝，而未闭合的最后 turn 会保留已有事件并追加合成的 `tool/result`、`step/end` 和 `turn/end { interrupted }` 使 transcript 恢复平衡。

## 6. Projection 是第二个关键抽象

projection 不是新的事实库，而是从 event log 计算出的每 session 当前值。典型例子包括会话统计、token 计量、标题、子代理目录和 UI 所需状态。缓存可保存 projection checkpoint 以降低重放成本，但其语义应仍能由日志验证或重建。

这让产品开发避免两个坏选择：每个 UI 页面都自行扫全日志，或为 UI 建一套与 Agent 运行时逐渐漂移的可变状态。

## 7. Fork、Resume 与可重放性的代价

fork 不是复制一个 JavaScript 对象；它创建带 lineage/seed metadata 的 session，并以完整、连续、没有悬挂 turn/step/tool-call 的事件前缀作为 seed。resume 则从 persistence 读取，重新建立 live Agent scope，但历史的有效模型输入仍由日志投影。

由此产生的约束是：记录的数据必须是 lossless JSON，sequence 必须连续；工具私有的 UI meta 也必须序列化，否则回放无法重建相同工具呈现。

## 8. 常见误区

- 事件日志不是 audit-only 附件；它是模型历史和产品状态的上游数据源。
- 所有 event 都不是模型消息；应通过 surface event 和 projection 语义判断。
- persistence 与 telemetry 不同：前者为本地会话恢复，后者是可配置的对外报告边界。
- 长期保存日志并不自动解决上下文窗口问题；压缩专题处理的是“当前模型可见 surface”的长度。
- checkpoint 只能保证“调用意图先持久化再执行”，不能提供外部副作用 exactly-once；side-effecting provider 仍需在支持时使用 `callId` 做幂等键，恢复时也可能得到 `TOOL_OUTCOME_UNKNOWN` 并要求先核对外部状态。

## 9. 复习问题

1. 为什么 request/header 也要记录，而不只记录 message？
2. assistant/chunk 与 assistant/message 各自满足什么需求？
3. 为什么 projection 应是日志派生值而不是 UI 的独立真相？

## 10. 证据索引

- D:/codes/deepseek-harness/packages/core/session/src/types.ts
- D:/codes/deepseek-harness/packages/core/session/src/index.ts
- D:/codes/deepseek-harness/packages/session/README.md
- D:/codes/deepseek-harness/packages/session/session-persistence-jsonl/README.md
- D:/codes/deepseek-harness/packages/session/session-checkpoint-policy/README.md
- D:/codes/deepseek-harness/packages/session-query/README.md
- D:/codes/deepseek-harness/docs/subsystems/session.md
