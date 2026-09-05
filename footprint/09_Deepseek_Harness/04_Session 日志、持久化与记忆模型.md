# DeepSeek Harness：Session 日志、持久化与记忆模型

## 1. 一句话结论

dsh 的核心记忆模型是追加式 Session event log：模型历史、工具结果、流式输出、请求头、压缩替换、todo 和许多产品状态均可从日志或其投影恢复。它不是把“聊天数组”和“UI 状态”分别作为没有关联的真相来源。

## 源码阅读路线

按以下顺序打开源码；链接固定到本次核对时的实际行号。

1. [逻辑格式版本与读取类型](<D:/codes/deepseek-harness/packages/core/session/src/types.ts#L86>)：packages/core/session/src/types.ts。
2. [构建期相邻迁移目录](<D:/codes/deepseek-harness/packages/session/session-format-catalog/src/generated.ts#L13>)：packages/session/session-format-catalog/src/generated.ts。
3. [物理 generation 与 handle 实现](<D:/codes/deepseek-harness/packages/session/session-persistence-jsonl/src/index.ts#L146>)：packages/session/session-persistence-jsonl/src/index.ts。
4. [共享增量投影](<D:/codes/deepseek-harness/packages/session/session-projection/src/index.ts#L199>)：packages/session/session-projection/src/index.ts。

## 2. SessionEventMap 是什么

core/session/src/types.ts 的 SessionEventMap 定义了可扩展的 durable 事件词汇。核心与插件扩展事件包括（todo/write 由 Todo 插件补充）：

    turn/start, turn/end
    step/start, step/end
    user/message
    assistant/message, assistant/attempt
    tool/call, tool/result
    request/header, request/context
    todo/write

user/message、assistant/message、tool/result 是 model-visible surface 的主要节点。它们带有 surfaceOp：普通 append，或由压缩等操作发起的 replace。sourceEventSeqs 连接可见节点与生成它们的原始事件，例如 tool/result 对应的 tool/call。Assistant 自己的 chunk 位于内嵌 stream 中，不再用顶层 chunk seq 关联。

## 3. “模型可见即已记录”

Loop 先在 durable log 中写入用户消息、结算后的 assistant message/attempt 和工具结果，再由 deriveMessages() 将当前 surface 投影给下一请求；assistant/attempt 留作日志证据，不进入模型历史。request 的有效 config、system prompt、tool schemas 同样记录在 request/header。

因此重新打开 session、fork、Web UI 的工具卡片、导出 transcript、snapshot replay、token 计量、标题、统计和 telemetry projection 共享同一个事实基础。一个新功能若只把信息偷偷附加在内存 prompt 字符串上，会破坏这条不变量：恢复后的模型再也无法看到同一事实。

## 4. “记忆”至少分四类

| 类型 | dsh 的代表机制 | 适用问题 |
| --- | --- | --- |
| 对话/任务轨迹 | Session log 和 derived messages | 发生了什么、模型见过什么？ |
| 可恢复产品状态 | JSONL persistence、checkpoint policy | 进程退出后如何继续？ |
| 派生视图 | projection、title、stats、query | UI/查询如何不重做业务状态？ |
| 工作区知识 | AGENTS/CLAUDE instructions、skills、文件工具 | 当前任务应遵循什么规则、去哪取知识？ |

这不是对“向量记忆”的否定。当前仓库中可直接证明的是 Session Query 的逻辑 corpus 与 SQLite 全文检索，以及 session reference 等机制；没有证据时，不应宣称其已经提供通用 embedding/vector memory。

## 5. 持久化与格式边界

当前 `SESSION_FORMAT_VERSION = 2`。`dsh-session-persistence` 定义 `create/open/flush/stat/list` 和每 Session 的 handle（读写句柄）；当前 session 包组提供 JSONL 持久化实现。SQLite 用在领域存储、投影缓存或全文检索时，不等于存在可切换的 SQLite Session 日志 provider。

`open(id, 'read')` 不占写所有权；`open(id, 'write')` 要取得独占写所有权。`stat/list` 读头部与存储身份，不读完整正文，也不为了列会话创建 Agent。创建可以延迟到首次 append/flush 才物化，硬崩溃前尚未物化的 Session 不会凭空恢复。

历史读取分为两条链：

```text
stat/list → 扫描每个 Session 的最高规范版本 → 翻译可支持的 header → 返回元数据
open 正文 → 选择同一最高版本 → 拒绝未来格式
          → 静态 v0→v1→v2 相邻迁移 → 验证当前逻辑记录
          → 独占发布当前版本 successor → 返回 handle
```

v0 文件名为 `session.jsonl[.zstd]`，v1 及以后为 `session.vN.jsonl[.zstd]`。迁移保留已提交的旧 generation，不覆盖、改名或删除前代；当前读取选择最高规范版本，不能把旧文件存在解释为读取失败时自动回退或支持降级。默认物理压缩为 Zstandard：独立 header frame 与 append batch frames；配置 none 才写未压缩 JSONL。

迁移目录由 `session-format-catalog/src/generated.ts` 的静态导入定义，不靠用户是否挂载迁移插件。未知 ordinary event 仍受 `ignorable: true` 规则约束；结构版本可迁移不代表未知必读事件可以忽略。

物理撕裂尾部恢复、逻辑格式迁移和语义 interrupted-turn repair 是三件事。最后一种由 handle 的使用方补齐未闭合 turn/step/tool 调用。`session-checkpoint-policy` 在请求或副作用附近 flush，不能保证外部副作用 exactly-once（恰好一次）；恢复遇到 `TOOL_OUTCOME_UNKNOWN` 时仍应核对外部状态。

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
2. live chunk、assistant/message 和 assistant/attempt 各自满足什么需求？
3. 为什么 projection 应是日志派生值而不是 UI 的独立真相？

## Session 的读取位置与投影状态

`SessionSeq` 表示实际事件位置，`SessionLogOffset` 表示间隙、前缀长度或读取偏移，可等于事件总数；`SessionSeqCursor` 还允许 -1 表示尚无事件。不要把这些数值因为底层都是 number 就混用。

按位置读取用 `eventAt(seq)`，完整或区间快照用 `snapshotEvents()`；不要再依赖公开可变 `session.events` 数组。v2 的 `isSeeded` 与 inherited prefix/带标记的 `session/end-seed` 一起表达 fork 来源；父历史 seed 和 child 自有事件需要明确区分。

`sessionProjections` 主动增量折叠已提交事件。`stateOf()` 提供 Host 所需完整类型状态，`snapshot()` 提供裁剪后的客户端视图。共享 `turnBoundary` 是多个生命周期 consumer 的依赖，projection cache 只是加速，不能让缺失的必需投影静默变成空值。

## 10. 证据索引

- [packages/core/session/src/types.ts](<D:/codes/deepseek-harness/packages/core/session/src/types.ts#L1>)
- [packages/core/session/src/index.ts](<D:/codes/deepseek-harness/packages/core/session/src/index.ts#L1>)
- [packages/session/README.md](<D:/codes/deepseek-harness/packages/session/README.md#L1>)
- [packages/session/session-persistence-jsonl/README.md](<D:/codes/deepseek-harness/packages/session/session-persistence-jsonl/README.md#L1>)
- [packages/session/session-checkpoint-policy/README.md](<D:/codes/deepseek-harness/packages/session/session-checkpoint-policy/README.md#L1>)
- [packages/session-query/README.md](<D:/codes/deepseek-harness/packages/session-query/README.md#L1>)
- [docs/subsystems/session.md](<D:/codes/deepseek-harness/docs/subsystems/session.md#L1>)
