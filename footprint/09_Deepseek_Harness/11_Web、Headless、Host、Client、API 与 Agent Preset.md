# DeepSeek Harness：Web、Headless、Host、Client、API 与 Agent Preset

## 1. 一句话结论

Web 与 Headless 不是两套 Agent 内核，而是同一 `dsh-base` 上的两个 product surface：Headless 直接创建一个 Agent、提交一次用户任务并打印 durable 结果；Web 在 Host 进程中组合 HTTP/API/Session/Agent 服务，在 Browser 中加载 Cordis Client 插件，并用 Agent Preset 把模型可见的 tools/prompt/projections 放到 per-preset scope，Host/Client/API 负责交互与传输而不拥有 Agent Loop。

## 源码阅读路线

按以下顺序打开源码；链接固定到本次核对时的实际行号。

1. [浏览器认证](<D:/codes/deepseek-harness/packages/client/connection/src/browser-auth.ts#L185>)：packages/client/connection/src/browser-auth.ts。
2. [类型化 Remote 调度](<D:/codes/deepseek-harness/packages/api/gateway/src/index.ts#L133>)：packages/api/gateway/src/index.ts。
3. [会话业务入口](<D:/codes/deepseek-harness/packages/api/session-controller/src/index.ts#L83>)：packages/api/session-controller/src/index.ts。
4. [流式 Assistant 与持久结算](<D:/codes/deepseek-harness/packages/api/session-controller/src/assistant-stream.ts#L1>)：packages/api/session-controller/src/assistant-stream.ts。
5. [独立 webhook 验签入口](<D:/codes/deepseek-harness/packages/webhook/webhook-github/src/handler.ts#L1>)：packages/webhook/webhook-github/src/handler.ts。

## 2. 源码调用链与数据流

### 2.1 Profile 到 surface

```text
dsh launcher
  → composeProfile(base bundle + surface bundle + user patch + CLI overlay)
  → Cordis Loader
      base：Agent/Session/LLM/tools/sandbox/skills/subagent/goal/compaction...
      headless：startup + code-runtime + headless-runner
      web：Host services + connection + browser plugin roster + preset roster
```

因此回答“Web 有什么工具”不能只读 `web-app/cordis.patch.yml` 的 Host rows；模型能力可能已从 base global layer disable，再由选中的 `agent.cordis.yml` preset 重新挂载。

### 2.2 Headless

```text
dsh --profile headless "task"
  → headless-startup 解析唯一 positional task
  → Loader settle
  → headless-runner
  → ctx.agents.create(default model, persisted Session)
  → agent.followup(task as ordinary user message)
  → wait quiescence
  → sessions.flush()
  → fold owned durable interval
  → stdout 最后一个非空 assistant text
  → appExit(0/1)
```

Headless 不挂 Host、HTTP server、Web runtime 或 browser plugin，也不监听端口。它只有一次 submitted task，没有交互式 follow-up UI；模型 prompt/tools 仍来自 base + headless bundle/preset composition，而不是 runner 自己注入特殊消息。

### 2.3 Web Host plane

Web 的 Host 运行时挂载 webserver、connection、api-gateway、api-remotes、session-controller、workspace-controller、settings-controller，以及它们依赖的领域服务。

```text
浏览器 Remote 调用
  → connection：/api carrier、来源检查、Cookie 认证
  → api-gateway：Typert descriptor、参数/结果校验、Remote dispatch
  → session-controller / workspace-controller / settings-controller / 领域服务
  → Agent、Session、工作区或设置的实际操作
```

`webserver` 只维护路由。`api-remotes` 装配应用选中的事件转发，业务行为由对应 Remote service/controller 持有。当前没有 host-apiproxy legacy fallback；按已删除路径理解业务入口会读错责任归属。

Session Controller 的 prompt 路径可恢复普通冷 Session；list、history、follow、skills 等读取各有明确是否激活 Agent 的策略。prompt admission 用 requestId 识别已排队或已记录的请求，避免重试重复插入消息；这不等于所有 RPC 自动具备幂等语义。

### 2.4 Client plane

浏览器加载 `client/modules` 与客户端插件，通过 connection 的 RPC（远程过程调用）和 Gateway 暴露的 `ctx.remote` 访问 Host。Gateway 拥有单个 `/api/remote.mux` WebSocket，多个逻辑流复用这个连接；不能继续按 events.mux/events.host 两条物理下行描述。

| 流/数据 | 语义 |
| --- | --- |
| `$events` | 先注册增量观察，再发 ready；作为连接 generation 来源 |
| SessionEventStream / RemoteJournalStream | 连续 durable seq、历史页、缺口修复和恢复 |
| SessionControlStream / RemoteSnapshotStream | 每个 generation 用完整 baseline 替换队列、jobs、投影等进程态 |
| Assistant live frame | 无 durable cursor 的临时 start/chunk/end，与持久 settlement 配对 |

Session history 每个 durable event 占一条记录，Assistant chunk 留在内嵌 stream。Web 客户端临时生成 assistant/live-chunk 行；结算时接收命名 delta 退休临时行并接纳 message/attempt。重连不能把旧临时 token 当成日志已提交内容。

物理 carrier 断开可触发恢复；业务、持久化或无法修复的连续性错误应显式结束流。UI 消费日志、投影和已持久化 tool meta，不在前端复制 Agent Loop。

### 2.5 Browser trust boundary

浏览器入口同时做来源检查与会话认证：

1. Host 必须是 loopback 或匹配 trustedHosts；Origin 若存在必须匹配 Host，cross-site 请求拒绝。
2. Web 启动生成随机 launch token，根页面 GET / 的 token query 可交换 authority-bound 签名 Cookie，然后重定向到干净的 /。
3. RPC 和 WebSocket 要求有效 Cookie；来源检查失败是 403，可信来源但缺少有效认证是 401。

签名 secret 由 credentials 的 client-connection/browser-session grant 持有；Cookie 带绝对过期时间，默认配置 30 天，HttpOnly、SameSite=Strict，绑定 hostname 与 port。当前 loopback HTTP Cookie 不带 Secure。API 路由不接受拿 query token 或 Authorization header 代替这次 Cookie 认证。

所有 Host RPC/流统一要求浏览器会话，不再按某些方法额外固定 loopback 的旧分级描述。trustedHosts 仍是来源允许表，不是用户账号体系；本地浏览器认证也不能扩大成多租户 RBAC（基于角色的访问控制）。

### 2.6 Agent Preset

一个 preset 是目录中的 `agent.cordis.yml`。roster 每个 generation 在 process 内只 mount 一次到 standing scope；Agent scope 的 parent chain 是：

```text
agent → preset standing scope → global host scope
```

同 preset 的多个 session 共享 plugin instance，但插件按 Agent/Session 区分状态；兄弟 preset 的 listener 和 tool layer 互不可见。host reader 没有 live Agent 时可通过 `standingKeyFor(presetId)` 重建同一工具/展示语义。

session header 记录创建时 preset；blank session 可 recompose 到另一 preset，并追加 `agent-preset/selected` durable event。产生过内容后禁止切换，因为历史里可能已有旧工具调用，新 composition 无法承接。child agent 使用 `composeFrom(parentCtx)` 绑定父当前 generation，而不是按 id 重新 mount 最新磁盘版本，避免父子在一次委派中使用不同 tool/prompt generation。

preset discovery 每次重读 roots，broken composition 仍列出并带原因。用户 authoring 只允许从已有 preset copy 整目录，不允许浏览器直接提交 composition text；user preset 与其命名插件同等高权限，`trust` 是展示事实而非沙箱。

随发行版提供的四个 preset 不是只换 persona，而是不同的可执行 composition：

| Preset | 当前能力差异 |
| --- | --- |
| `standard`（标准模式） | 完整编码 Agent：文件、Shell、搜索、Skills、计划/目标、Subagent 与 Workflow 等 |
| `ptc`（程序化工具调用） | 与 standard 同能力，但把工具通过 PTC TypeScript 工具 SDK 收敛到 `run_code` |
| `minimal`（极简模式） | 完整固定 prompt，只暴露持久 shell（POSIX bash / Windows pwsh）与 `str_replace_editor`；抑制 runtime context，不挂 compaction，并在 preset realm 使用 bare `fs-local` |
| `cordis`（创造模式） | 在 standard 上增加运行时检查、临时插件执行和 preset 创作 Skill；自修改工具与 shell 同属高权限能力 |

极简模式的 bare `fs-local` 是 composition 事实，不是“更安全”的模式；它绕开 host 的 sandboxed FS provider，适用时必须按完整高权限编码 Agent 看待。standard/ptc/cordis 中的 Codex、Claude Code tool rows 默认也仍是 disabled template，不能仅因配置文件出现它们就声称已启用。

## 3. 设计取舍

- surface 与 core 分离：Headless、Web、未来 TUI 共享 Agent/Session/LLM 能力，front door 只实现输入、输出和交互。
- Host/Client 两个 Cordis 世界：Browser 也能插件化，但通过明确 Remote/Connection 边界接触 Host。
- Agent-plane preset：不同 session 可拥有不同工具与 prompt，不在 Host global layer 污染所有 Agent。
- standing mount 而非 per-session plugin instance：降低重复初始化/监听器成本，同时通过 scope key 隔离语义。
- blank-only preset switch：牺牲 mid-session 灵活性，换取 durable history 与 executable tool catalog 一致。
- Controller 与 carrier 分工：业务决定是否激活 Agent，Gateway 负责类型化调用和流，Connection 负责浏览器接入。

## 4. 不能推出的结论

- Web UI 有某个按钮不代表所有 preset 都向模型暴露对应工具；UI capability 与 Agent capability 分属不同 plane。
- Headless 无 HTTP 不代表不持久化；runner 创建 persisted Session 并 flush 后读 durable interval。
- Host trust fence 与浏览器 Cookie 认证不能推出多用户角色授权或加密传输。
- preset `trust: system` 不能证明其插件安全；它只表示 root 来源，composition 仍以 host 进程权限执行。
- header.agentPreset 不能总是代表当前运行 preset；blank switch 后要 fold `agent-preset/selected`。
- Client Remote capability set 不是运行时自动发现所有 Host Services；`api-remotes` 显式 build-time mount 当前应用选择。

## 5. 常见误区

- 把 session-controller、api-gateway、connection 都叫 API 层而不区分业务操作、类型化调度与传输。
- 只看 base composition 就断言 Web Agent 的工具，因为 web patch 会把模型侧 rows 移到 preset。
- 新建 child 时重新按 preset id mount，导致磁盘更新后 child 与 parent generation 漂移。
- 把 UI slot/plugin 当作后端 service；browser Cordis 只运行 client face。
- 认为用户 preset 是低权限主题配置；它是完整插件 composition，与 shell access 同一信任级别。

## 6. 源码阅读任务

1. 从 CLI profile composition 追踪 base + headless/web patch 的叠加顺序，列出两个 surface 的新增与禁用 rows。
2. 画出一次 Web `session.prompt` 从 Browser connection 到 Host resolver、Agent inbox、Session stream 再回 Browser 的路径。
3. 对照 session-controller 的 Remote 方法与 Gateway descriptor，追踪参数校验、冷会话读取和 Agent 激活。
4. 阅读 `agent-presets` 的 mount/composeFrom/recompose，解释 standing generation、scope parent 与 durable selected event。
5. 找一个 `ui-*` package，确认它通过 slot/Remote/Session presentation 工作，而不是直接 import Agent Loop。

## Webhook 的独立入口

Webhook（外部事件回调）不是浏览器 RPC。GitHub provider 的 handler 读取有界 UTF-8 JSON body，并通过 @octokit/webhooks 校验签名；验证后的 delivery 才交给 WebhookRuntime。可信程序化 rule 返回 Session request 或 null，Session 创建再走 Workspace、preset、permission 与 Agent 的组合。

该 runtime 是 fire-and-forget 调度：HTTP 接收成功不是 Agent 已完成。delivery id 的存在也不能自动推出持久重试队列或跨重启去重保证。相关实现分别在 [packages/webhook/webhook-github/src/handler.ts](<D:/codes/deepseek-harness/packages/webhook/webhook-github/src/handler.ts#L1>)、[packages/webhook/webhook/src/index.ts](<D:/codes/deepseek-harness/packages/webhook/webhook/src/index.ts#L1>) 和 [packages/webhook/webhook/src/session.ts](<D:/codes/deepseek-harness/packages/webhook/webhook/src/session.ts#L1>)；挂载模板位于 [apps/cli/config/examples/github-review/cordis.yml](<D:/codes/deepseek-harness/apps/cli/config/examples/github-review/cordis.yml#L1>)。

## 7. 证据索引

- [apps/cli/src/profile-boot.ts](<D:/codes/deepseek-harness/apps/cli/src/profile-boot.ts#L1>)
- [packages/bundle/base/cordis.patch.yml](<D:/codes/deepseek-harness/packages/bundle/base/cordis.patch.yml#L1>)
- [packages/bundle/headless/cordis.patch.yml](<D:/codes/deepseek-harness/packages/bundle/headless/cordis.patch.yml#L1>)
- [packages/bundle/headless/src/index.ts](<D:/codes/deepseek-harness/packages/bundle/headless/src/index.ts#L1>)
- [packages/bundle/web-app/cordis.patch.yml](<D:/codes/deepseek-harness/packages/bundle/web-app/cordis.patch.yml#L1>)
- [packages/bundle/web-app/src/index.ts](<D:/codes/deepseek-harness/packages/bundle/web-app/src/index.ts#L1>)
- [packages/host/webserver/src/index.ts](<D:/codes/deepseek-harness/packages/host/webserver/src/index.ts#L1>)
- [packages/client/connection/src/index.ts](<D:/codes/deepseek-harness/packages/client/connection/src/index.ts#L1>)
- [packages/api/gateway/src/index.ts](<D:/codes/deepseek-harness/packages/api/gateway/src/index.ts#L1>)
- [packages/api/remotes/src/index.ts](<D:/codes/deepseek-harness/packages/api/remotes/src/index.ts#L1>)
- [packages/api/session-controller/src/index.ts](<D:/codes/deepseek-harness/packages/api/session-controller/src/index.ts#L1>)
- [packages/preset/agent-presets/src/index.ts](<D:/codes/deepseek-harness/packages/preset/agent-presets/src/index.ts#L1>)
- [packages/preset/agent-presets/presets/standard/agent.cordis.yml](<D:/codes/deepseek-harness/packages/preset/agent-presets/presets/standard/agent.cordis.yml#L1>)
- [packages/preset/agent-presets/presets/ptc/agent.cordis.yml](<D:/codes/deepseek-harness/packages/preset/agent-presets/presets/ptc/agent.cordis.yml#L1>)
- [packages/preset/agent-presets/presets/minimal/agent.cordis.yml](<D:/codes/deepseek-harness/packages/preset/agent-presets/presets/minimal/agent.cordis.yml#L1>)
- [packages/preset/agent-presets/presets/cordis/agent.cordis.yml](<D:/codes/deepseek-harness/packages/preset/agent-presets/presets/cordis/agent.cordis.yml#L1>)
- [packages/client/modules/src/index.ts](<D:/codes/deepseek-harness/packages/client/modules/src/index.ts#L1>)
- [packages/api/gateway/src/client/index.ts](<D:/codes/deepseek-harness/packages/api/gateway/src/client/index.ts#L1>)
- [docs/architecture.md](<D:/codes/deepseek-harness/docs/architecture.md#L1>)
