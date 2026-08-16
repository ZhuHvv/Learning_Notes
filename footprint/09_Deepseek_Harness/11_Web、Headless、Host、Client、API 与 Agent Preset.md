# DeepSeek Harness：Web、Headless、Host、Client、API 与 Agent Preset

## 1. 一句话结论

Web 与 Headless 不是两套 Agent 内核，而是同一 `dsh-base` 上的两个 product surface：Headless 直接创建一个 Agent、提交一次用户任务并打印 durable 结果；Web 在 Host 进程中组合 HTTP/API/Session/Agent 服务，在 Browser 中加载 Cordis Client 插件，并用 Agent Preset 把模型可见的 tools/prompt/projections 放到 per-preset scope，Host/Client/API 负责交互与传输而不拥有 Agent Loop。

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

Web patch 在 base 上加入：

- storage、workspace registry、session projection cache/stats；
- directory picker、plugin inventory；
- legacy `host-apiproxy` BFF 与 base 已挂载的 Typert `api-gateway`；
- `webserver` 作为纯 route carrier；
- `connection` node half 把 `/api` HTTP/WS carrier 接到 gateway；
- `api-remotes` 选择当前应用暴露的 Typert business contributions；
- web runtime/static frontend/HMR；
- browser plugin roster 与 Agent Preset roster。

`webserver` 只维护 exact/prefix/upgrade/fallback route，不理解 Session 或 Agent。`connection` 拥有 browser trust fence、unary POST、双 WebSocket downlink 与 reconnect generation。`api-gateway` 读取 Typert descriptor、解析 lookup identity、校验 args/result 并调用 business Service。`api-remotes` 是 BFF selection/identity policy assembly；`host-apiproxy` 仍承载尚未迁移的 legacy domains，并与 Remote path 共享 Agent/Session resolver。

### 2.4 Client plane

```text
HTML boot metadata
  → client/modules 加载浏览器 bundle roster
  → browser Cordis runtime
  → connection client 建立 /api unary + events.mux/events.host
  → api-gateway/client 提供 ctx.remote
  → api-remotes/client mount 业务 contribution
  → ui-* plugins 向 slots 注册 conversation/sidebar/settings/... UI
```

Client package 不能导入 Host runtime types/Services 的具体实现；Host/Client faces 通过 generated descriptors、client-safe type subpaths 和 wire codecs 相连。UI tool rendering 主要消费 Session log、projection 与 tool-owned presentation intent，不重新实现 Agent Loop。

### 2.5 Browser trust boundary

每个 `/api` HTTP/upgrade request 先检查 Host authority：loopback 或明确 `trustedHosts`；有 Origin 时还必须与 Host authority 一致，`sec-fetch-site: cross-site` 被拒绝。配置 plane、原生目录/打开路径、preset authoring 等 privileged methods 进一步 pin 到 loopback。这个 fence 防 DNS rebinding 和意外 LAN 暴露，但 README 明确说它是 reachability policy，不是 authentication；当前 CLI 也拒绝 `--host 0.0.0.0`。

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
| `code`（PTC 模式） | 与 standard 同能力，但把工具通过 Code Mode TypeScript SDK 收敛到 `run_code` |
| `minimal`（极简模式） | 完整固定 prompt，只暴露持久 `bash` 与 `str_replace_editor`；抑制 runtime context，不挂 compaction，并在 preset realm 使用 bare `fs-local` |
| `cordis`（创造模式） | 在 standard 上增加运行时检查、临时插件执行和 preset 创作 Skill；自修改工具与 shell 同属高权限能力 |

极简模式的 bare `fs-local` 是 composition 事实，不是“更安全”的模式；它绕开 host 的 sandboxed FS provider，适用时必须按完整高权限编码 Agent 看待。standard/code/cordis 中的 Codex、Claude Code tool rows 默认也仍是 disabled template，不能仅因配置文件出现它们就声称已启用。

## 3. 设计取舍

- surface 与 core 分离：Headless、Web、未来 TUI 共享 Agent/Session/LLM 能力，front door 只实现输入、输出和交互。
- Host/Client 两个 Cordis 世界：Browser 也能插件化，但通过明确 Remote/Connection 边界接触 Host。
- Agent-plane preset：不同 session 可拥有不同工具与 prompt，不在 Host global layer 污染所有 Agent。
- standing mount 而非 per-session plugin instance：降低重复初始化/监听器成本，同时通过 scope key 隔离语义。
- blank-only preset switch：牺牲 mid-session 灵活性，换取 durable history 与 executable tool catalog 一致。
- legacy BFF 与 Typert Remote 渐进共存：统一 resolver 后逐步迁移，不强制一次重写所有协议。

## 4. 不能推出的结论

- Web UI 有某个按钮不代表所有 preset 都向模型暴露对应工具；UI capability 与 Agent capability 分属不同 plane。
- Headless 无 HTTP 不代表不持久化；runner 创建 persisted Session 并 flush 后读 durable interval。
- Host trust fence 不能推出多用户认证、授权或加密传输。
- preset `trust: system` 不能证明其插件安全；它只表示 root 来源，composition 仍以 host 进程权限执行。
- header.agentPreset 不能总是代表当前运行 preset；blank switch 后要 fold `agent-preset/selected`。
- Client Remote capability set 不是运行时自动发现所有 Host Services；`api-remotes` 显式 build-time mount 当前应用选择。

## 5. 常见误区

- 把 `host-apiproxy`、`api-gateway`、`connection` 都叫“API 层”而不区分 BFF policy、typed dispatch 与 transport carrier。
- 只看 base composition 就断言 Web Agent 的工具，因为 web patch 会把模型侧 rows 移到 preset。
- 新建 child 时重新按 preset id mount，导致磁盘更新后 child 与 parent generation 漂移。
- 把 UI slot/plugin 当作后端 service；browser Cordis 只运行 client face。
- 认为用户 preset 是低权限主题配置；它是完整插件 composition，与 shell access 同一信任级别。

## 6. 源码阅读任务

1. 从 CLI profile composition 追踪 base + headless/web patch 的叠加顺序，列出两个 surface 的新增与禁用 rows。
2. 画出一次 Web `session.prompt` 从 Browser connection 到 Host resolver、Agent inbox、Session stream 再回 Browser 的路径。
3. 对照 `api-gateway` 与 `host-apiproxy`，找出 migrated Remote endpoint 与 legacy fallback 如何共享 resolver。
4. 阅读 `agent-presets` 的 mount/composeFrom/recompose，解释 standing generation、scope parent 与 durable selected event。
5. 找一个 `ui-*` package，确认它通过 slot/Remote/Session presentation 工作，而不是直接 import Agent Loop。

## 7. 证据索引

- `apps/cli/src/profile-boot.ts`
- `packages/bundle/base/cordis.patch.yml`
- `packages/bundle/headless/cordis.patch.yml`
- `packages/bundle/headless/src/index.ts`
- `packages/bundle/web-app/cordis.patch.yml`
- `packages/bundle/web-app/src/index.ts`
- `packages/host/webserver/src/index.ts`
- `packages/client/connection/src/index.ts`
- `packages/api/gateway/src/index.ts`
- `packages/api/remotes/src/index.ts`
- `packages/host/apiproxy/src/api-proxy.ts`
- `packages/preset/agent-presets/src/index.ts`
- `apps/cli/config/agent-presets/standard/agent.cordis.yml`
- `apps/cli/config/agent-presets/code/agent.cordis.yml`
- `apps/cli/config/agent-presets/minimal/agent.cordis.yml`
- `apps/cli/config/agent-presets/cordis/agent.cordis.yml`
- `packages/client/modules/src/index.ts`
- `packages/client/runtime/src/index.ts`
- `docs/architecture.md`
