# DeepSeek Harness：Plan、Goal、Todo 与用户交互

## 1. 一句话结论

dsh 把“当前协作模式”“长期完成目标”“本 turn 的执行清单”“需要人类回答的问题”建成四套独立状态：Plan 是 durable mode + review interaction，Goal 是 event-sourced objective + process-local activation + round driver，Todo 是 Session 内 whole-list projection，User Questions/Commands 是前门交互 seam；它们共享 Agent/Session，但没有一个万能 planning state。

## 源码阅读路线

按以下顺序打开源码；链接固定到本次核对时的实际行号。

1. [完整目标投影状态](<D:/codes/deepseek-harness/packages/goal/goal/src/types.ts#L103>)：packages/goal/goal/src/types.ts。
2. [空闲时继续目标](<D:/codes/deepseek-harness/packages/goal/goal-round-driver/src/index.ts#L76>)：packages/goal/goal-round-driver/src/index.ts。
3. [协作模式与 review](<D:/codes/deepseek-harness/packages/plan/plan-mode/src/index.ts#L1>)：packages/plan/plan-mode/src/index.ts。
4. [人类问题权限](<D:/codes/deepseek-harness/packages/interaction/user-questions/src/index.ts#L34>)：packages/interaction/user-questions/src/index.ts。

## 2. 源码调用链与数据流

### 2.1 Plan mode

```text
/plan 或 ctx.planMode.set(agent, true)
  → idle：立即 append plan/mode
  → running：pending 到下一 accepted pre-step
  → foldPlanMode() 决定本 step system prompt 是否加入 plan:policy
  → exit_plan_mode(plan)
  → ctx.userQuestions.ask(intent=plan-review)
  → 明确 Approve 才 append/queue plan/mode=false
```

`plan/mode { active }` 是 log-only whole-value event，resume、fork 和 compaction 后都从 log fold。active 时 base composition 的 plan section 明确要求只做读、搜索、静态分析和检查，不实施修改，并要求最后以 `exit_plan_mode` 提交 decision-complete plan。工具 schema 在 active/inactive 两态保持稳定；执行 inactive 的 exit tool 会失败。

关键边界：Plan 是 soft guidance。它不会改写 tool registry，也不自动切 sandbox/approval；真正不可写必须由 permission policy、sandbox 或工具 gate 强制。

`/plan [message]` 是 command-plane 行为：先选 plan，再把 message 作为普通 user input steer；`/plan off` 只切状态。command lifecycle 自己写 `command/run/done`，handler 输出不进入 model history。

### 2.2 Goal domain

```text
create_goal(objective, max_goal_rounds?)
  → human-root authority 检查
  → goal/change revision=1, phase=active
  → process-local activation armed
  → goal-round-driver 在 whole-agent idle checkpoint
  → flush pending goal mutation
  → reserve round N
  → inbox user/message source=goal
  → admitted pre-step 后 roundsStarted++
  → 同一 Session 中继续工作
```

Goal mutation 写完整生命周期 snapshot，包括 id、revision、objective、phase、maxGoalRounds、blockedReason 等；当前 roundsStarted 由投影结合 admitted 的 goal-sourced user/message 推进，不能把它理解成只读最后一条 goal/change 就足够。update 使用 `{ id, revision }` compare-and-set，避免模型基于旧状态覆盖新 revision。phase 为 active/paused/blocked/complete；clear 使用 revisioned tombstone。

durable state 与 activation 有意分离。activation 不是持久化字段：fresh cache、session start、resume、fork、driver replacement 都会 disarm，即使 durable phase 仍为 active。人类明确要求继续时必须通过 `resume` mutation 再 armed，防止重启后无授权自动续跑。

round driver 只在 active + armed + idle + 未超 cap 时排下一条 `<goal_round>`。human message 不消耗 round；只有 admitted goal-sourced user/message 才增加 `roundsStarted`。goal change 在排工作前必须 flush 并 recheck，durability 不确定时 disarm。

### 2.3 Goal tool authority

- `create`、`edit`、`pause`、`resume`：必须处于 runtime-root agent 的当前 open turn，并有 direct human user/steering authority。
- `complete`、`blocked`：除 human authority 外，也允许与当前 goal id/revision/round 精确匹配的 goal round。
- autonomous `blocked` 至少达到 `blockedAfterConsecutiveRounds`，base 当前配置为 3；runtime 只验证轮数，是否“同一 blocker”仍由模型判断。
- autonomous complete/blocked 会 `concludeTurn()`，direct human mutation 不强制结束物理 turn。

默认 Goal round 上限由 Goal service 配置，当前 base 未覆盖时使用 256。它是轮数 cap，不是 token、费用、时间或 provider quota budget。

### 2.4 Todo

`todo_write` 每次提交整个 `[{ content, status }]`，追加一个 `todo/write` durable snapshot，last-write-wins。status 只有 pending/in_progress/completed。它属于 calling Agent 的 Session，没有 shared/swarm list。

`allowParallelInProgress` 是 composition 必选项：允许并发工作的 agent 可设 true；设 false 时 tool 拒绝多个 in_progress。durable invariant 不固化这个部署策略，因为旧日志必须能在策略变化后继续 replay。Web projection 在下一 `turn/start` 清空 standing todo view，但 raw `todo/write` 仍在 log。

### 2.5 User Questions 与 Commands

`ctx.userQuestions` 是 Service Definition：一个 provider、一个 `ask(request)`。可选项、custom text、multi-select 与 `plan-review` intent 都走同一 answer shape。提供 agent 时必须是 registry 中 exact live runtime root；live delegated child 被 `DELEGATED_CALLER` 拒绝，需把未决问题报告给 parent。

`ask_user_question` 只是 tool consumer：tool call await provider answer，等待本身不产生 token；答案以 compact JSON tool result 进入下一 step。没有 provider 时 `NO_PROVIDER`，不伪造默认答案。

`ctx.commands` 是 human/UI command registry。命令以 `/lowercase-name` 在 byte zero 解析，执行日志是 `command/run`/`command/done`，UI 直接展示结果，registry 不把 rawInput 自动提交模型。未知 command 由 shipped adapter 拒绝，不降级为普通 prompt。

## 3. 设计取舍

- Plan 与权限分离：协作模式可灵活表达，但部署仍用 sandbox/approval 实施不可绕过的限制。
- Goal state 与 activation 分离：目标可恢复，自动继续权不可在进程重启后悄悄继承。
- same-session rounds：保留同一历史、工具结果与工作区，不为每轮复制或新建 Agent；fresh-agent iteration 属于 Ralph 等其他插件。
- CAS revision：模型和 UI 必须先读后写，避免并发/陈旧状态静默覆盖。
- Todo whole-list replacement：数据模型极小且可 replay，代价是每次工具参数重复整表。
- Question intent 只控制 presentation：专用 Plan review UI 与 generic options provider 返回相同 answer contract。

## 4. 不能推出的结论

- Plan active 不能证明 mutation 工具不可调用；base prompt要求不调用，但强制性来自其他 policy。
- active Goal 不能证明会自动继续；activation 可能已 disarm，且 resume/fork 后必须显式 rearm。
- maxGoalRounds 不能推算 token 或费用上限。
- blocked 三轮门槛不能证明 blocker 语义相同；没有独立 evaluator。
- Todo 的 `completed` 不能证明任务在外部世界完成，它是模型写入的会话状态。
- 用户问题 UI 展示过程与 approval audit 都不是模型 context；模型只看到最终 tool outcome。

## 5. 常见误区

- 把 Todo 当 Plan mode：前者是执行清单，后者是协作状态与 review gate。
- 把 Goal 当后台 Job：Goal 是 durable objective 和同 Session scheduling；Job 是 process-local producer record。
- resume Session 后看到 active Goal 就期待它自动跑；activation 已被故意清除。
- delegated child 直接 `ask_user_question`；应报告给 parent，由 runtime root 与人交互。
- 将 `/command` handler 返回文本当用户消息；除非 handler 显式 steer/followup，否则不会进模型历史。

## 6. 源码阅读任务

1. 跟踪 Plan 在 idle set、mid-turn queued set 与 request-recovery retry 三种场景中的 commit 时机。
2. 从 `create_goal` 到 driver reserve、pre-step admit、round count 增加，找出每个 durable checkpoint。
3. 模拟 resume 一个 `phase=active` Goal，解释为何 `get_goal` 可见 active 但 activation 为 disarmed。
4. 对比 Plan review、ask_user_question 与 approval.request 的 caller authority、durable event 与 UI provider。
5. 比较 Todo projection 在 `turn/start` 清空与 raw log 保留的差别。

## 共享投影与 SDK 观察

Goal 的投影状态同时保留 current、seenGoalIds 和首次严格重放 failure。它需要拒绝非法 revision/复用身份等错误，而不是对任意 goal/change 做宽松 last-write-wins。Todo 的 whole-list 覆盖规则不能套到 Goal 上。

Web 的 Goal 控制和 SDK 的会话运行都需要区分 durable phase、进程内 activation 与 whole-agent idle。一个 physical turn/end 不一定意味着所有子代理和目标续跑工作都结束；自动化 consumer 应使用对应高层 run 的活动区间，而不是收到第一个 turn/end 就截断结果。

## 7. 证据索引

- [packages/plan/plan-mode/src/index.ts](<D:/codes/deepseek-harness/packages/plan/plan-mode/src/index.ts#L1>)
- [packages/goal/goal/src/index.ts](<D:/codes/deepseek-harness/packages/goal/goal/src/index.ts#L1>)
- [packages/goal/goal-round-driver/src/index.ts](<D:/codes/deepseek-harness/packages/goal/goal-round-driver/src/index.ts#L1>)
- [packages/goal/tool-goal/src/index.ts](<D:/codes/deepseek-harness/packages/goal/tool-goal/src/index.ts#L1>)
- [packages/todo/tool-todo/src/index.ts](<D:/codes/deepseek-harness/packages/todo/tool-todo/src/index.ts#L1>)
- [packages/interaction/user-questions/src/index.ts](<D:/codes/deepseek-harness/packages/interaction/user-questions/src/index.ts#L1>)
- [packages/interaction/tool-ask-user/src/index.ts](<D:/codes/deepseek-harness/packages/interaction/tool-ask-user/src/index.ts#L1>)
- [packages/interaction/commands/src/index.ts](<D:/codes/deepseek-harness/packages/interaction/commands/src/index.ts#L1>)
- [packages/interaction/user-approval/src/index.ts](<D:/codes/deepseek-harness/packages/interaction/user-approval/src/index.ts#L1>)
- [packages/bundle/base/cordis.patch.yml](<D:/codes/deepseek-harness/packages/bundle/base/cordis.patch.yml#L1>)
- [packages/client/ui-plan/README.md](<D:/codes/deepseek-harness/packages/client/ui-plan/README.md#L1>)
- [packages/client/ui-goal/README.md](<D:/codes/deepseek-harness/packages/client/ui-goal/README.md#L1>)
