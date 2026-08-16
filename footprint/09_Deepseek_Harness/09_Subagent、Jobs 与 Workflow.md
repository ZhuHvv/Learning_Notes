# DeepSeek Harness：Subagent、Jobs 与 Workflow

## 1. 一句话结论

dsh 把并发拆成三种不同对象：Subagent 是有独立 Agent/Session 与 provider transport 的委派，Jobs 是进程内、按 owner 隔离的后台工作注册表，Workflow 是 worker thread 中运行的模型编写 orchestration script 并通过 Subagent seam 扇出子任务；它们可组合但生命周期、持久性、结果回传和安全边界互不替代。

## 2. 源码调用链与数据流

### 2.1 Subagent provider seam

```text
tool-subagent(provider="spawn" | "fork" | ...)
  → ctx.subagents.start() / startContinuable()
  → provider
      spawn-in-process：新 Session，无父历史 seed
      fork-in-process：以父 Session 已完成前缀为 seed
      acp / dsh-sdk / codex / claude-code：外部 transport
  → SubagentRun 或 durable continuable child
```

`ctx.subagents` 是多 provider registry。`inheritsParentContext` 只说明 child 是否看到父会话已完成历史：fork 是，spawn 和外部 one-shot 通常不是；它不说明继承工具、service 或 authority。model-facing `tool-subagent` 的绝对 `maxDepth` 默认是 3，顶层 agent 记作 depth 0，尝试创建的 child depth 超过上限即拒绝；只有声明 `depthLimit` capability 的 provider 才能接收数值上限，预算由外部 child harness 自己管理的 provider 必须显式使用 `provider-managed`。in-process child 通过 `applyChildComposition()` 绑定父 agent 当前实际运行的 preset generation，再叠加 child persona/toolFilter，避免在 Web agent-plane 架构下得到空 tool registry。

每个 session-backed child 写入 versioned `subagent/descriptor`：provider、`one-shot`/`continuable` mode、label，以及 continuable 冷恢复所需的 provider/model/persona/toolFilter。父 Session id、delegation depth 与 preset id 在 child header 中持久化。descriptor/log 是重建依据，进程内 `Agent` 对象不是。

### 2.2 One-shot 与 continuable

One-shot `start()` 在 provider 发布真实 run 后才转移所有权。caller 必须无论成功失败都 `run.dispose()`；`run.result` 的普通 child failure 以非 `completed` stop reason 返回，只有 seam 无法表示的 infrastructure fault 才 reject。foreground tool 等结果并回收；one-shot background tool 把 run 适配成 generic Job。

Continuable child 的一次 durable Session 可跨多个 FIFO turn：

```text
startContinuable()
  → prepareContinuable()
  → reserve child identity + compose scope + create Agent
  → child inbox 接受 initial prompt
  → 返回 childId/messageId，不等待 child 完成

send_message
  → exact live direct parent authority
  → resident: inbox followup
  → absent: 从 persistence cold resume
  → 接受后成为未来 FIFO turn，不 steer 当前 turn
```

continuation manager 只允许一个 process-local Activation，依据 Agent quiescence 与 owned children 推导 running/waiting/settled。`interrupt_agent` 只取消目标当前 turn，保留 queued inbox 与 descendants；`list_agents` 从 durable descriptor、session tree 与 live registry 组合出 running/idle/ready。

child-to-parent 的 `report` 是仅安装在 continuable child scope 的独立工具。默认 `wakeup` 通过 parent.followup() 开新父 turn；`quiet` 只 inject context。report 是 child 自愿机制，可能零次或多次；无论 report 与否，Activation settle 前 manager 都会发一条 service-owned settlement notice，避免 token limit、cancel、failure 等无法主动报告的结局无声丢失。

### 2.3 委派权限

in-process child 创建时快照父 session 的显式 sandbox override，并在 child log 写入；若 approval service 存在，child 固定为 `approval: never`。因此 delegated child 只能在已继承的 sandbox scope 内行动，不能无人值守地弹 escalation 审批。未切换过的父没有 `sandbox/mode` event 时，不复制 deployment default；child 仍按部署默认解析。cold resume 重放创建时的 delegation events，不重新读取父当前政策。

`toolFilter` 是 child tool view 配置，不是父 authority 的形式化上限。安全依赖 sandbox、approval 和各 capability 的 owner checks。

### 2.4 Jobs

```text
producer（bash / terminal send / one-shot subagent）
  → ctx.jobs.start(spec)
  → jobs-local 分配 <kind>-N，绑定 ownerSession
  → producer.run({ output, done, cancel ... })
  → job_output / job_list / job_kill
  → terminal settlement notice
```

Jobs registry 默认每 owner 最多 10 个 running/stopping job，超限在 producer 执行和 id 分配前失败。stream job 的 `read()` 使用单一 consuming cursor；final-output job 终态读取幂等。`kill()` 先调用 producer cancellation，成功后转为 `stopping`；只有 producer `done` 才释放容量。

Jobs 是 process-local：service/owner dispose 会 cancel、等待并移除，但进程重启后 registry 不恢复。owner fence 比较 SessionId；可预测 id 本身不是 authority。`tool-jobs` 还是 background producer 的 controller admission：某 agent/preset 没挂载 controller，即使同一进程其他 preset 有，也不能启动后台 job。

completion notice 对 busy owner 走 inject，对 idle owner 默认 wakeup；每个 owner 连续自动 wake 最多 3 次，只有新的 user-authored message 重置预算，防止后台任务完成→自动 turn→再启动任务的自激循环。

### 2.5 Workflow

```text
workflow tool(meta, script, args)
  → ctx.workflowEngine.start()
  → workflow-worker-thread 为本 run 创建 Worker
  → vm 运行 orchestration script
      agent(prompt, options)
      parallel(thunks)
      pipeline(items, stages)
      phase(title) / log(message)
  ↔ typed host/worker protocol
  → Host 通过 ctx.subagents.start() 创建真实 child
  → script final plain JSON
  → parent tool result
```

默认 `provider = spawn`、`maxTotalAgents = 1000`、每次 `parallel/pipeline` 最多 4096 items、同步 script slice 5000 ms、dispose grace 5000 ms；`maxConcurrentAgents = 0` 表示按 CPU parallelism 解析。Worker 解决同步死循环阻塞 host event loop，并能被 terminate，但 `node:vm` 不是安全沙箱；model-written script 与已有 shell access 处于同一信任前提。

Host/worker value boundary 只接受 plain lossless JSON，拒绝函数、cycle、稀疏数组、非有限数字和 exotic prototype。Workflow 本身 foreground collection：parent turn 等待整个 run，取消或 child 普通失败不把 partial output 当成功。top-level run 的 `workflow/start/agent-start/agent-end/end` 可记录到父 Session；script、child progress 与中间值没有 durable resume/journaling。

### 2.6 默认 composition

`dsh-base` 挂载 jobs-local、tool-jobs、Subagent registry、spawn/fork in-process provider、control/report tools、workflow-worker-thread 与 workflow tool。base 中默认 `subagent` 工具绑定 spawn + continuable background，`subagent_fork` 绑定 fork + one-shot；Web 会把模型侧 consumer rows 移入选中 preset，而随附 standard/code/cordis preset 把两者都配置成 continuable background。因此“fork 是否 one-shot”也必须按有效 surface/preset composition 回答。随附 preset 还保留了 Codex 与 Claude Code 工具的模板行，但它们带 `disabled: true`，复制 preset 后显式启用才会暴露；ACP 等外部 provider 同样需要 overlay/preset 组装，不能从 package 或禁用行存在推断默认可用。

## 3. 设计取舍

- Session-backed child 而非把所有输出拷回父 transcript：并发工作有独立可恢复历史，父只接收选定 report/settlement。
- one-shot 与 continuable 分开：前者是 holder-owned result，后者是 durable addressable conversation，避免一个模糊对象同时承担两套生命周期。
- Jobs 做通用后台控制：Shell、PTY、Subagent producer 共享 id、output、kill、notice，不重复实现轮询协议。
- Workflow script 在 worker，child 在 Host：脚本可并发编排且 host loop 不被同步阻塞，同时所有 Agent 创建仍走同一 Subagent contract。
- settlement notice 独立于 report：机制层保证父至少知道 child 如何结束，语义结果仍由 child 自主报告或单独查看 transcript。

## 4. 不能推出的结论

- `fork` 继承已完成历史，不等于继承父当前未完成 turn、所有内存状态或权限。
- continuable `send_message` 接受不等于 child 已执行，更不返回 child answer。
- `report accepted` 不等于端到端 durable exactly-once receipt；进程故障与 post-execute veto 仍可造成歧义。
- Jobs 不持久化，不能用 job id 在重启后恢复后台进程。
- Workflow worker/vm 不是 hostile-code sandbox，清空 env 也不能证明脚本无法恢复 Node authority。
- child 或 Ralph/Goal 自报 complete 不是独立 evaluator 的验证结论。

## 5. 常见误区

- 用 background one-shot job 与 continuable child 混用 collection 方式：前者 `job_output`，后者读 child Session、等 report/settlement 或发 followup。
- 对正在工作的 child 调 `send_message` 期待 steer 当前 turn；它排到下一 FIFO turn。
- 看到 child id 就尝试跨 sibling 控制；authority 由 exact parent/ancestor 与 durable lineage 检查。
- 忘记 foreground Subagent/Workflow 的 `dispose()`，导致 child 或 worker 未达到 quiescence。
- 把 workflow 中间 child output 全部返回给父模型；只有 script final JSON 进入 parent tool result。

## 6. 源码阅读任务

1. 跟踪 one-shot `start()` 的 publication ownership boundary，列出 publish 前后失败分别由谁清理。
2. 从 `startContinuable()` 到 `followup()` 和 cold resume，画出 Session、Activation、Agent inbox 三者关系。
3. 对比 `report`、settlement notice 与 one-shot result 的发送者、调度 lane、持久位置和失败语义。
4. 从 bash background start 跟到 jobs-local、tool-jobs notice，验证 owner fence 与 consuming cursor。
5. 阅读 workflow worker protocol，找出哪些值经过 plain JSON boundary，哪些 Agent 操作仍留在 Host。

## 7. 证据索引

- `packages/subagent/subagent/src/index.ts`
- `packages/subagent/subagent/src/continuation.ts`
- `packages/subagent/subagent/src/descriptor.ts`
- `packages/subagent/subagent-in-process-driver/src/index.ts`
- `packages/subagent/tool-subagent/src/index.ts`
- `packages/subagent/tool-subagent-control/src/index.ts`
- `packages/subagent/tool-subagent-report/src/index.ts`
- `packages/jobs/jobs/src/index.ts`
- `packages/jobs/jobs-local/src/index.ts`
- `packages/jobs/tool-jobs/src/index.ts`
- `packages/workflow/workflow/src/index.ts`
- `packages/workflow/workflow-worker-thread/src/host.ts`
- `packages/workflow/workflow-worker-thread/src/worker.ts`
- `packages/workflow/tool-workflow/src/index.ts`
- `packages/bundle/base/cordis.patch.yml`
