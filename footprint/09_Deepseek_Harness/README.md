# DeepSeek Harness 学习笔记

本专题依据 `D:/codes/deepseek-harness` 当前本地源码，按“整体模型 → 实际入口 → 调用链 → 数据变化 → 副作用与失败”组织。核对日期：2026-09-05；源码基线：`d347e703908d0406b7a7ef80e3a0e594d86b2215`。这是本地工作树核对，不宣称与远端最新版本一致。

## 阅读索引

先读 00、01、02、04 建立运行时与日志模型，再按问题进入专题。英文术语在各自专题结合用途解释；源码链接以当前 checkout 的绝对路径和 `#L行号` 定位。

| 专题 | 阅读目标 |
| --- | --- |
| [00_证据边界与项目地图](<00_证据边界与项目地图.md>) | 证据基线、实际组合与源码地图 |
| [01_Profile、Bundle 与 Cordis 插件组合](<01_Profile、Bundle 与 Cordis 插件组合.md>) | Profile 层次、启动入口与重载策略 |
| [02_Agent_Loop、流式输出与工具编排](<02_Agent_Loop、流式输出与工具编排.md>) | turn/step、v2 流结算与工具有序提交 |
| [03_Prompt、运行时上下文与 Workspace Instructions](<03_Prompt、运行时上下文与 Workspace Instructions.md>) | Prompt、请求序列与工作区指令 |
| [04_Session 日志、持久化与记忆模型](<04_Session 日志、持久化与记忆模型.md>) | Session v2、相邻迁移、读写 handle 与投影 |
| [05_上下文压力、Token Meter 与 Compaction](<05_上下文压力、Token Meter 与 Compaction.md>) | 请求压力、失败尝试用量与压缩 |
| [06_工具注册表、审批、沙箱与错误模型](<06_工具注册表、审批、沙箱与错误模型.md>) | 工具管线、权限、审批与沙箱 |
| [07_Skills：发现、目录投影、按需加载与资源边界](<07_Skills：发现、目录投影、按需加载与资源边界.md>) | Skill 发现、目录、正文与冷会话入口 |
| [08_文件检索、FS、Shell、Terminal 与 LSP](<08_文件检索、FS、Shell、Terminal 与 LSP.md>) | 文件搜索、执行世界、图片、持久终端与 LSP |
| [09_Subagent、Jobs 与 Workflow](<09_Subagent、Jobs 与 Workflow.md>) | 子代理相邻消息、模型选择、Jobs 与 Workflow |
| [10_Plan、Goal、Todo 与用户交互](<10_Plan、Goal、Todo 与用户交互.md>) | Plan、Goal、Todo 的状态与自动继续边界 |
| [11_Web、Headless、Host、Client、API 与 Agent Preset](<11_Web、Headless、Host、Client、API 与 Agent Preset.md>) | Web Remote 流、Cookie 认证、preset 与 webhook |
| [12_快照回放、E2E、Invariant 与 Harness 评估](<12_快照回放、E2E、Invariant 与 Harness 评估.md>) | 版本化回放、工作区结果证据与测试边界 |
| [13_PTC：程序化工具调用与代码运行时](<13_PTC：程序化工具调用与代码运行时.md>) | PTC 与 Worker 代码运行时 |
| [14_TypeScript 与 Python SDK：启动、活动区间与结果](<14_TypeScript 与 Python SDK：启动、活动区间与结果.md>) | 双语言 SDK、启动和高层 run 活动区间 |
| [15_实验性 Agent Teams：名册、邮箱与共享任务板](<15_实验性 Agent Teams：名册、邮箱与共享任务板.md>) | 实验性团队的共享任务板和持久邮箱 |

## 本轮纠错与扩展

| 旧笔记的关键问题 | 本轮对应修订 |
| --- | --- |
| Session 格式写成 v0、无迁移 | v2、静态 v0→v1→v2 链、保留历史 generation |
| 顶层 assistant/chunk 持久化 | 内嵌 stream 的 message/attempt 与进程内 live frame |
| 所有 profile 都叠 base、都监控 patch | sdk-minimal 独立树；live/startup 按 profile 区分 |
| 工具结果重新排作 user message | 普通结果写 Session；additionalContexts 才另入 inbox |
| 子代理 send_message 仅下一 FIFO turn、独立 report | 相邻父子统一 steer 消息与 service settlement |
| code preset 及旧 preset 目录 | ptc preset、packages/preset/agent-presets/presets |
| Web legacy apiproxy、双下行、只有来源检查 | Controllers、remote.mux、浏览器 token/Cookie 认证 |
| 每个包都必须有 invariant | 仅独立运行关系需要 companion，无关系则省略并说明 |
| examples 内部 driver 是快照入口 | shipped dsh profiles、版本化 Session owners、workspace.expected |

原有 13 篇专题逐篇复核并补充源码路线；新增 PTC、双语言 SDK 和实验性 Agent Teams 三篇。保留仍与源码一致的压缩策略、Skill 渐进加载、FS 观察策略等内容，不按版本变化无差别重写。

## 如何核验一条结论

1. “有这个能力”：查 Service/Provider/Consumer，再查当前 profile/preset 是否挂载，检查 disabled、平台条件、凭据和模型能力。
2. “模型见过什么”：从请求头、当前 surface 和 message/attempt 的区别追踪；raw log 存在不代表进入模型历史。
3. “重启可以恢复”：区分 durable log、派生缓存、进程内 activation、外部对象和持有的资源。
4. “任务已完成”：检查外部世界或独立 expected 文件；模型自报、Todo completed、Goal complete 都不是独立验证器。

## 验证记录与限制

本轮进行了全文核读、关键源码/配置差异核对、源码文件及行号链接验证、专题导航链接验证、失效路径扫描和修改差异检查。本轮共 17 篇 Markdown，252 处源码行号链接、16 处专题导航链接通过静态检查。

没有执行真实模型 E2E（端到端测试）、全库测试、覆盖率、浏览器交互或跨平台恢复实验。引用测试文件表示可继续核验的入口，不代表测试已在本轮通过。项目内 doc-sync 不扫描本笔记目录，因此采用针对本目录的链接和内容检查。

用户提供路径在本机对应的实际目录是 `D:/codes/Learning_Notes/footprint/09_Deepseek_Harness`。本轮只修订此专题，不修改其他学习笔记或项目业务源码。
