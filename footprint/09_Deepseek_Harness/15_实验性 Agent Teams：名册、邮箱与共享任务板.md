# DeepSeek Harness：实验性 Agent Teams

## 1. 适用范围

Agent Teams（代理团队）位于 packages/experimental，通过普通 continuable subagent 承载队友，再增加名册、成员间消息和共享任务板。它是私有、显式选择的实验能力，不属于官方发布保证，也不是 base 默认启用的通用分布式调度器。

阅读前先理解第 09 篇的 child Session、cold resume 和 settlement。Teams 解决的是多成员协作状态与消息恢复；Jobs 仍是进程内后台记录，Todo 仍是单 Session 清单。

## 源码阅读路线

按以下顺序打开源码；链接固定到本次核对时的实际行号。

1. [团队服务依赖](<D:/codes/deepseek-harness/packages/experimental/agent-team/src/index.ts#L59>)：packages/experimental/agent-team/src/index.ts。
2. [Lead 日志串行事务](<D:/codes/deepseek-harness/packages/experimental/agent-team/src/journal.ts#L12>)：packages/experimental/agent-team/src/journal.ts。
3. [排队、投递与恢复](<D:/codes/deepseek-harness/packages/experimental/agent-team/src/mailbox.ts#L55>)：packages/experimental/agent-team/src/mailbox.ts。
4. [共享任务和 revision](<D:/codes/deepseek-harness/packages/experimental/agent-team/src/task-board.ts#L32>)：packages/experimental/agent-team/src/task-board.ts。

## 2. 数据拥有者

```text
tool-agent-team → ctx.agentTeams
  ├─ TeamRoster：成员身份、创建、恢复
  ├─ TeamMailbox：排队、投递、回执
  ├─ TeamTaskBoard：依赖与 revision 更新
  └─ TeamJournal：按 Lead Session 串行事务、append、flush
        → Lead Session 中 team/* 事件
        → team projection → 成员/任务/消息视图
```

Lead（主代理）的 Session 日志是团队状态来源，队友继续拥有自己的模型历史。`TeamService` 显式依赖 agents、sessions、sessionPersistence、sessionProjections、subagents。仅挂 tool consumer 不足以提供完整能力。

成员名唯一且保留，创建失败也不能随意复用同名身份。只有 Lead 可创建和中断队友；普通成员可在团队规则内交换消息和操作任务。不要把普通 send_message 的直接父子规则直接套在团队成员通信上。

## 3. 消息持久化链

```text
send → 校验成员/目标/预算
     → Lead 日志 team/message/queued + flush
     → 向目标 steer，必要时 cold resume
     → 目标接收 team-message 来源的 user/message
     → Lead 日志 team/message/delivered + flush
```

queued 表示消息已进入可恢复待投递状态，accepted 表示观察到本次目标接收。目标 temporarily unavailable 时不要因为没立即接受就重发一份业务消息。`recoverFor()` 读取 queued-minus-delivered 记录并结合目标侧 receipt 处理重试；过程内还有按目标串行的 dispatch tail 和 in-flight message 集合。

这一机制比普通内存通知多出两端日志确认，但不能不看故障窗口就宣称对任意外部系统都恰好一次。尤其不能用进程内锁推导多个 Host 同时协调同一 Team 的安全性。

## 4. 任务板与协作冲突

TaskBoard 用任务 id、revision 和依赖关系表达状态。创建任务可带描述、依赖和拟触及文件提示；claim 要求依赖已满足，更新采用 compare-and-set（比较版本后再更新），陈旧 revision 必须失败。

文件范围提示用于报告重叠，不是文件锁，也不阻断真实 FS 写入。队友被 interrupt 或进程消失，不会自动释放其任务所有权；需要成员通过任务 API 处理。任务完成状态是参与者写入的协作事实，不是独立测试通过证明。

## 5. 限制与阅读问题

当前配置含 maxMembers=8、maxTasks=256、maxPendingMessagesPerMember=64、maxMessageBytes=65,536、disposalTimeoutMs=5,000，均由 Config 验证。成员共享工作目录，没有自动分配独立 worktree，也没有自动回收 owner 的租约机制。wait 观察团队变化，超时后需要重新读状态。

阅读时分别找出：哪个事件先 flush，哪个 receipt 防止重复投递，哪个成员能执行操作，哪个 revision 防止覆盖，哪个错误只意味着暂时不能送达。本轮依据源码静态核对，未运行多进程故障或崩溃重投实验。

## 6. 证据索引

- [packages/experimental/agent-team/src/index.ts](<D:/codes/deepseek-harness/packages/experimental/agent-team/src/index.ts#L1>)
- [packages/experimental/agent-team/src/journal.ts](<D:/codes/deepseek-harness/packages/experimental/agent-team/src/journal.ts#L1>)
- [packages/experimental/agent-team/src/roster.ts](<D:/codes/deepseek-harness/packages/experimental/agent-team/src/roster.ts#L1>)
- [packages/experimental/agent-team/src/mailbox.ts](<D:/codes/deepseek-harness/packages/experimental/agent-team/src/mailbox.ts#L1>)
- [packages/experimental/agent-team/src/task-board.ts](<D:/codes/deepseek-harness/packages/experimental/agent-team/src/task-board.ts#L1>)
- [packages/experimental/agent-team/src/projection.ts](<D:/codes/deepseek-harness/packages/experimental/agent-team/src/projection.ts#L1>)
- [packages/experimental/tool-agent-team/src/index.ts](<D:/codes/deepseek-harness/packages/experimental/tool-agent-team/src/index.ts#L1>)
- [packages/experimental/agent-team/package.json](<D:/codes/deepseek-harness/packages/experimental/agent-team/package.json#L1>)
