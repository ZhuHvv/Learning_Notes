# DeepSeek Harness：Prompt、运行时上下文与 Workspace Instructions

## 1. 一句话结论

dsh 的 prompt 不是启动时固定的字符串。每个 step 都由 SystemPrompt 收集插件注册的 section、动态 context、变量和可见工具 schema；随后 ReactLoopAgent 把当次 runtime context 加入模型输入。工作区指令则是另一条、可追溯的 durable user-message 注入链。

## 源码阅读路线

按以下顺序打开源码；链接固定到本次核对时的实际行号。

1. [组装 scope 内提示词](<D:/codes/deepseek-harness/packages/core/system-prompt/src/index.ts#L536>)：packages/core/system-prompt/src/index.ts。
2. [用共享投影判断可注入时机](<D:/codes/deepseek-harness/packages/context/agent-instructions/src/index.ts#L284>)：packages/context/agent-instructions/src/index.ts。
3. [将请求序列变化写入 header](<D:/codes/deepseek-harness/packages/core/agent-loop/src/agent.ts#L549>)：packages/core/agent-loop/src/agent.ts。

## 2. Prompt 的四种成分

| 成分 | 来源 | 何时确定 | 是否写入日志 |
| --- | --- | --- | --- |
| Prompt section | SystemPrompt.section() | 每次 assemble | 渲染后进入 request/header.system |
| Tool schema | SystemPrompt.tools() | 每次 assemble | 进入 request/header.tools |
| 动态 runtime context | SystemPrompt.context() | 每次 assemble | 变化时写成带 source 的 durable `user/message` 快照；最新可见快照覆盖旧快照 |
| Workspace instruction | dsh-agent-instructions | 首步、文件工具触达、恢复或压缩后 | 以 user/message 持久记录 |

SystemPrompt.assemble() 处理 scope 可见性、同名 section/variable 的 shadow、排序、严格变量插值以及 tool order。它不是字符串 append 工具，而是将多插件贡献变成一次模型输入的组装边界。

## 3. 为什么工具 schema 属于 Prompt 系统

模型是否知道一个工具、工具参数长什么样，和 persona 一样会改变模型的下一步决策。因此 dsh 将 schema 当作 PromptAssembly 的字段，并在 request header 中持久化有效 schema。新工具在 registry 中可执行但没有成为可见 schema，等同于模型无法规划调用它；反之只修改 schema 而不改变执行策略，会制造模型可见承诺与实际能力的错配。

在 PTC 模式下，工具可见性还会改变：配置 `mode: ptc` 时模型只直接看到 `run_code`，实际工具通过 SDK 在程序内调用。这个差异应从 dsh-tools 的 mode 和具体 composition 阅读，不能把 native mode 的工具目录直接当成每个 session 的 prompt。

## 4. runtime context 的位置

Agent Loop 在 preStep() 中先 assemble prompt，再渲染 context sections。RuntimeContextProjection 把发生变化的当前 context 写成有 source 的 user-role Session message；surface fold 采用“最新可见快照覆盖早期 runtime context snapshot”的语义，所以动态状态不会无限叠加成彼此冲突的提示。它在语义上表示请求时现状，但物化结果仍属于 durable conversation surface：恢复和 fork 能看到当时真正送给模型的快照，而下一次可重新计算的新快照再取代它。

这给 Harness 开发者一个明确选择：

- 一个事实必须在恢复、UI、fork 后仍能重建时，新增 session event。
- 一个事实表示每次请求的运行时现状、且可以重新计算时，注册 prompt context；Loop 仍负责把实际可见快照日志化。
- 一个事实会影响后续代码操作的工作区规则时，使用 instructions 的可追溯 durable 注入。

## 5. Workspace Instructions 的实现语义

dsh-agent-instructions 先读取用户全局 `$DSH_HOME/AGENTS.md`，再从最近 `.git` 项目根到 Session header 中 cwd 的每级目录读取所有存在的 `AGENTS.md`、`CLAUDE.md`，随后读取 `AGENTS.local.md`、`CLAUDE.local.md` overlay。同目录内容在裁掉首尾空白后重复时保留候选顺序更早者；不同内容的同级文件都会生效。更具体目录的规则拥有更高的指导优先级，但插件明确声明这些规则不能覆盖 system、developer 或直接用户指令。

首次可进入的 step 会将基线规则放入同一批 durable user message；成功的 first-party read、write、edit 触达更深目录后，插件在下一请求前补充、替换或撤销已加载的规则。它不靠解析 shell cd：每次本地 shell 都可能是独立进程，通用 shell 文法也不是可靠的 filesystem 观察接口。

## 6. 预算、刷新和安全

该插件要求显式 `maxBytes`，单个来源另受默认 1 MiB 的 `maxSourceBytes` 限制，并优先保留最具体的规则；宽泛规则会先被整体省略，最具体文件才可能截断。内容通过 bounded stream 读取，过大的文件不会被模型自动总结。完整 baseline 还记录由项目根、候选顺序和预算等生成的 `baselineIdentity`；恢复时只有 identity 兼容才复用旧 baseline，否则写入明确取代旧 baseline 的完整当前版本。

刷新是触达驱动而不是文件监听器：外部更改在下一次成功的文件工具操作、恢复时的基线对比，或压缩后重建时进入可见上下文。文件内容的 SHA-1/digest 与 provider version 仅用于去重和刷新判断；真正模型可见的变更仍写入带类型 source 的 session message。

从安全角度，指令文本是仓库控制的低权限内容。插件会转义框架边界文本，但仍应通过 FS policy/OS sandbox 限制不可信仓库中符号链接和文件读取的影响范围。

## 7. 不能由源码推出的结论

- 当前实现不等同于某一厂商的“三级 prompt”或固定 cache breakpoint 协议。
- 模型 provider 是否对 append-only 消息命中 KV cache，是 provider 行为；dsh 可以尽量稳定前缀和记录 token 用量，不能替 provider 保证命中。
- dsh 默认不解释 .claude/rules、@path import 或任意 Markdown 的特殊语法；不要从“兼容读取 CLAUDE.md”扩大为完全兼容 Claude Code 的指令语义。

## 8. 源码阅读任务

1. 阅读 SystemPrompt.assemble()，区分 scoped shadow 与全局 tool provider 的合并方式。
2. 阅读 ReactLoopAgent.preStep()，确认 prompt assembly 在何处发生。
3. 在 dsh-agent-instructions README/源码中追踪一条 read 工具结果如何触发下一 step 的规则更新。

## 与共享投影、请求序列的连接

工作区指令插件显式依赖 `sessionProjections`，用共享 `turnBoundary` 判断 step 是否仍开放。缺少必需 registry 或投影时直接失败，不能退回自己维护的一套不完整 turn 状态。

指令与 Skill 的 pre-step listener 在修改消息时保留整个 enter decision，包括 `startsRequestSeries`。这一字段连接“输入如何改变”与“请求头为何新增”，应沿 `agent-instructions → agent/pre-step → buildRequest` 一起读。PTC 内部文件调用还要等执行祖先和 step 提交时机，不能在嵌套工具未结算时抢先注入观察结果。

## 9. 证据索引

- [packages/core/system-prompt/src/index.ts](<D:/codes/deepseek-harness/packages/core/system-prompt/src/index.ts#L1>)
- [packages/core/agent-loop/src/agent.ts](<D:/codes/deepseek-harness/packages/core/agent-loop/src/agent.ts#L1>)
- [packages/context/agent-instructions/README.md](<D:/codes/deepseek-harness/packages/context/agent-instructions/README.md#L1>)
- [packages/context/agent-instructions/src/index.ts](<D:/codes/deepseek-harness/packages/context/agent-instructions/src/index.ts#L1>)
- [packages/core/tools/src/index.ts](<D:/codes/deepseek-harness/packages/core/tools/src/index.ts#L1>)
