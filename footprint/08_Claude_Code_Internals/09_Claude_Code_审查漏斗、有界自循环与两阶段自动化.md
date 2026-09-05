# 08.09 Claude Code 仓库中的审查漏斗、有界自循环与两阶段自动化

> 审查日期：2026-09-05
> 仓库版本：`d7dbd9a09f59775726ed14bbea8fc9dfdff62f7b`

## 1. 先给结论

在 01～08 已讨论的 Prompt Cache、流式输出、检索、上下文压缩、Subagent、Agent Loop、记忆和 Skills 之外，当前公开仓库中仍有四组很值得 agent/harness 开发者学习的机制：

1. **高召回候选发现 + 独立逐项复核 + 延迟副作用**：`code-review` 不是把多个 reviewer 的输出直接相加，而是把“发现问题”和“确认问题”拆成两道不同的关。
2. **Stop Hook 驱动、可配置上限的外部自循环**：`ralph-wiggum` 把“是否继续”放在模型之外，由 Hook、状态文件、transcript 和终止条件共同决定。
3. **按认知阶段和正交视角组织多 Agent**：`feature-dev` 先探索、再澄清、再设计、后实现；子 Agent 返回证据索引，主 Agent 必须重新读取关键文件，而不是盲信二手摘要。
4. **建议、冷静期、人工否决、再执行的两阶段自动化**：issue 维护脚本不会在检测到候选后立即关闭，而是等待、检查后续人工活动和否决信号，再实施外部副作用。

它们共同表达了一个比“多调用几次模型”更重要的 harness 原则：

```text
模型擅长扩大候选集、解释语义和提出方案
                    │
                    ▼
宿主负责状态、预算、门控、复核、幂等和副作用时机
```

这些都是本仓库内插件或维护脚本的可观察实现，不代表 Claude Code CLI 内核一定采用同样架构。

## 2. 高信号审查漏斗：把 recall 与 precision 分开优化

### 2.1 不是简单“多数投票”

`plugins/code-review/commands/code-review.md` 的流程可以压缩成：

```text
廉价预检
  ├─ PR 已关闭？
  ├─ 草稿？
  ├─ 明显无需审查？
  └─ 已经审查过？
          │都不是
          ▼
发现适用的局部规则 + 建立 PR 意图摘要
          │
          ▼
多个 reviewer 并行提出候选问题
          │
          ▼
第 3/4 个 bug reviewer 的候选交给新 validator 复核
          │
          ▼
只保留验证通过的问题
          │
          ▼
用户显式要求时才发布评论
```

关键不在于用了几个 Agent，而在于把两种目标分开：

- **候选发现阶段提供多个视角**：但本命令同时要求高信号，甚至排除依赖特定输入或状态的问题；它并不是无约束追求高召回。
- **复核阶段追求精确率**：验证具体事实、规则作用域和 PR 意图，过滤似是而非的问题。

如果直接汇总多个 reviewer，Agent 数量越多，误报通常也越多；“再加一个 reviewer”并不会自动提高可信度。这里增加的是一个角色不同的 validator，相当于在生成器之后放置判别器。

仓库证据：

- 预检命中任一条件就停止：[plugins/code-review/commands/code-review.md:14](D:/codes/claude-code/plugins/code-review/commands/code-review.md#L14)。
- 四个 Agent 并行提出候选：同文件 `:30-53`。
- 每个候选再启动独立 Agent 验证：同文件 `:55`。
- 未通过复核的候选全部过滤：同文件 `:57`。
- 只有传入 `--comment` 才产生 GitHub 评论副作用：同文件 `:59-77`。

### 2.2 规则作用域发现被拆成独立步骤

该流程先让一个便宜 Agent 只返回相关 `CLAUDE.md` 的**路径**，而不是让每个 reviewer 各自遍历全部规则。审查文件时，只允许使用该文件所在目录或祖先目录中的规则。

这体现了两个可迁移设计：

1. **先求作用域，再求内容**：先建立“哪些规则适用”的映射，减少无关上下文和错误套用。
2. **路径层级就是策略作用域**：规则不是全局平铺的文本集合，而是与资源位置绑定。

对于通用 harness，可把这一步做成确定性函数，而不是交给模型：

```ts
type Scope = {
  target: string
  applicablePolicyFiles: string[]
}

function resolvePolicyScope(target: string, repoRoot: string): Scope {
  // 从 target 所在目录向上走到 repoRoot，收集策略文件
}
```

模型随后只解释已解析出的规则，宿主负责路径归属，能进一步降低错误。

### 2.3 候选 finding 应有显式生命周期

这个流程暗含但没有代码化的一组状态很适合 harness 直接建模：

```text
proposed → validating → confirmed → published
                   └──→ rejected
```

建议不要只传 Markdown，而使用结构化 finding：

```ts
type Finding = {
  id: string
  target: { path: string; line: number }
  claim: string
  evidence: string[]
  ruleRef?: string
  severity: "critical" | "important"
  proposer: string
  status: "proposed" | "confirmed" | "rejected" | "published"
  validation?: {
    verdict: "confirm" | "reject"
    reason: string
    checkedEvidence: string[]
  }
}
```

这样才能做到去重、重试、审计、统计各 reviewer 的准确率，并保证发布动作幂等。

### 2.4 “高置信阈值”只是第一层，不是验证本身

`pr-review-toolkit/agents/code-reviewer.md:24-32` 还采用了 0～100 的置信分数，并只报告 `>= 80` 的问题。它有利于要求 reviewer 主动压制低价值输出，但分数仍是模型自报，不能替代独立验证。

更可靠的组合是：

```text
自报置信度门槛
    + 可定位证据
    + 独立 validator
    + 确定性检查（编译、测试、lint、schema）
```

### 2.5 值得借鉴，也要防止“伪独立”

多个 Agent 使用相同模型、相同上下文和近似提示词时，错误可能高度相关，不能把数量当作统计独立性。改进方法包括：

- proposer 与 validator 使用不同提示词、不同允许工具和不同上下文；
- validator 不看 proposer 的长篇推理，只接收原子 claim 和证据位置，避免锚定；
- 能由编译器、测试、类型检查或静态分析确认的事实，优先交给确定性工具；
- 对无法复现的风险明确输出 `unverified`，不要硬凑“已确认”；
- 发布前用稳定 finding ID 去重，避免多个 reviewer 重复报告同一根因。

## 3. Stop Hook 作为 continuation：把自循环放到模型外部

### 3.1 Ralph Loop 的最小状态机

`ralph-wiggum` 没有在主 prompt 中只写一句“请不断继续”。它在 `.claude/ralph-loop.local.md` 保存：

- 当前迭代数；
- 最大迭代数；
- completion promise；
- 启动时间；
- 原始任务 prompt。

当 Agent 尝试结束时，Stop Hook 读取 transcript 的最后一条 assistant 文本。以下是正常与显式保护分支；不涵盖所有异常：

```text
没有状态文件 ───────────────► allow stop
      │
      ▼
命中显式异常保护分支 ──────► 清理状态并 allow stop
      │
      ▼
达到 max_iterations ─────────► 清理状态并 allow stop
      │
      ▼
提取结果等于 completion promise ► 清理状态并 allow stop
      │
      ▼
iteration + 1，原子更新状态文件
      │
      ▼
返回 decision=block + 原始 prompt ─► 下一轮
```

仓库证据：

- Setup 脚本创建 YAML frontmatter + prompt 的本地状态文件：[plugins/ralph-wiggum/scripts/setup-ralph-loop.sh:130](D:/codes/claude-code/plugins/ralph-wiggum/scripts/setup-ralph-loop.sh#L130)。
- Hook 先校验迭代数字段，再检查最大轮数：[plugins/ralph-wiggum/hooks/stop-hook.sh:20](D:/codes/claude-code/plugins/ralph-wiggum/hooks/stop-hook.sh#L20)。
- 最后一条 assistant 消息从 JSONL transcript 提取，而不是依赖当前进程内变量：同文件 `:57-111`。
- completion promise 做标准化后的字面量相等比较：同文件 `:114-127`。
- 迭代数通过临时文件 + `mv` 更新，避免半写状态：同文件 `:152-156`。
- 未完成时用结构化 `decision: block` 和 `reason` 把原任务重新注入：同文件 `:165-174`。

### 3.2 巧妙之处：稳定意图，变化的是环境

每轮重放的是**同一个 prompt**，但 Agent 能看到上一轮留下的文件和 Git 历史。因此跨轮记忆不必全部塞进越来越长的自然语言总结，而可以分成：

```text
稳定意图：原始任务、验收标准、预算
可变世界：文件、测试结果、Git diff、外部状态
控制状态：iteration、run_id、取消标志、检查点
```

这是 agent harness 很重要的分层。对长任务来说，文件系统和结构化状态通常比让模型“记住自己刚才做过什么”更可靠。

### 3.3 巧妙之处：坏状态默认结束，而不是无限阻塞

Ralph 对非法数字、缺失 transcript、空文本等设置了清理分支。但脚本启用 `set -euo pipefail`：缺失字段导致 grep 失败，或赋值中的 jq 返回非零时，可能在后续检查前退出，因此不能保证所有坏状态都会被清理。这是一个很务实的 **fail-open for liveness** 选择：循环控制器自身故障时，优先避免会话被永久困住。

安全控制不一定都应 fail-open。例如执行付款或删库的权限校验更适合 fail-closed。harness 应按风险显式选择：

| 控制目标 | 故障时更合理的默认值 |
|---|---|
| 防止危险副作用 | fail-closed：拒绝执行 |
| 防止无限循环、保证可退出 | fail-open：允许退出 |
| 只影响提示或可选提醒 | 降级并记录 |

### 3.4 completion promise 的局限：它是自我声明，不是外部证明

源码用 Perl 替换提取 `<promise>`，但没有先验证标签存在：替换不匹配时会保留原文本，所以裸文本刚好等于 completion promise 也可能命中。不能称为严格 XML 校验。即使正确提取，“模型输出了完成声明”仍不等于任务真的完成。提示词强调“不要撒谎”仍属于软约束。更成熟的 harness 应将终止条件分层：

```text
硬终止：预算耗尽、人工取消、超时、策略拒绝
验证终止：测试通过、目标文件存在、指标达标、validator 通过
软终止：模型声明完成或无法继续
```

建议的停止判定：

```ts
const stop =
  cancelled(run) ||
  budgetExceeded(run) ||
  (modelClaimsDone(lastMessage) && await verifierPasses(run))
```

### 3.5 不应原样照搬的地方

- 默认 `max_iterations=0` 表示无限循环，生产 harness 应默认有界；
- 固定状态路径不含 session/run ID，并发会话可能互相覆盖；
- 状态更新没有跨进程锁；
- 通过 grep 识别 transcript 行依赖当前 JSONL 形状；
- 只读最后一条 assistant 文本，工具结果本身不参与完成验证；
- 同一 prompt 反复重放可能陷入策略不变的局部循环；
- 没有 token、费用、墙钟时间、失败次数和无进展次数预算；
- completion promise 来自模型自身，缺少独立验收器。

一个可投入生产的版本至少应补充：`run_id`、锁或 CAS、取消通道、最大轮数、最大费用、最大无进展轮数、外部 verifier、幂等副作用键和结构化 checkpoint。

## 4. 按认知阶段编排：子 Agent 提供索引，主 Agent 保留证据所有权

### 4.1 `feature-dev` 的阶段不是形式主义

`plugins/feature-dev/commands/feature-dev.md` 将开发拆成：

```text
需求发现
  → 代码库探索
  → 澄清歧义
  → 多方案架构设计
  → 用户批准
  → 实现
  → 多视角质量审查
  → 总结
```

这里最值得借鉴的不是“固定七步”，而是**不同阶段允许不同类型的不确定性**：

- 探索阶段可以发散，目标是建立证据地图；
- 澄清阶段冻结需求歧义；
- 设计阶段比较实现策略，但不写代码；
- 实现阶段只执行已选择的方案；
- 审查阶段重新打开质疑空间，但不悄悄改变需求。

这比让一个 Agent 在同一上下文中不停切换“探索者、架构师、实现者、审查者”更容易控制偏差。

### 4.2 并行要按正交问题拆，不要机械切文件

探索 Agent 的示例焦点分别是：相似功能、整体架构、现有实现、UI/测试/扩展点；架构 Agent 则分别考虑最小改动、干净架构和务实折中。它们按**问题视角**分工，而不是简单地“一人读三分之一文件”。

适合并行的拆分轴通常是：

- 不同证据源；
- 不同风险类型；
- 不同架构目标；
- 互不写同一状态的实现单元。

不适合并行的是有强前后依赖的决策，或多个 Agent 同时修改同一事实源。

### 4.3 子 Agent 的摘要只是导航，不是最终证据

该命令明确要求 explorer 返回 5～10 个关键文件，并要求主 Agent 在子 Agent 完成后亲自读取这些文件（[plugins/feature-dev/commands/feature-dev.md:41](D:/codes/claude-code/plugins/feature-dev/commands/feature-dev.md#L41)）。这解决了常见的“摘要套摘要”问题：

```text
错误模式：文件 → 子 Agent 摘要 → 主 Agent 再摘要 → 设计
更稳模式：文件 → 子 Agent 给出索引 ─┐
                   主 Agent 读取原文 ─┴→ 设计
```

主 Agent 因而保留最终证据所有权；子 Agent 主要承担搜索空间压缩和候选定位。

### 4.4 用户确认是 commit point

实现前的显式批准，不只是交互礼貌，而是事务意义上的 commit point：在此之前产生的是候选设计，可廉价撤销；在此之后才允许产生大规模文件副作用。

通用 harness 可以为阶段声明能力：

```ts
const capabilities = {
  discovery: ["read", "search"],
  design: ["read", "search", "write-plan"],
  implementation: ["read", "search", "edit", "test"],
  review: ["read", "search", "test"]
}
```

这样“尚未批准就不能实现”由工具能力门控，而不只是 prompt 中的大写警告。

### 4.5 提示词流程不等于宿主状态机

仓库里的 `feature-dev.md` 是编排提示，宿主并未从这份文件中得到一个强制、可恢复的七阶段状态机。模型可能跳步，压缩后也可能丢失局部进度。

生产 harness 若需要严格流程，应把阶段做成持久化状态，并为每一步声明：

- 进入条件；
- 允许工具；
- 必需产物；
- 退出条件；
- 可否重试；
- 是否需要人工批准；
- 恢复时从哪里重建状态。

## 5. 两阶段自动化：让模型的判断先成为“候选”，而不是立即成为副作用

### 5.1 duplicate 关闭流程中的冷静期与否决权

`scripts/auto-close-duplicates.ts` 处理的不是“模型说重复，所以立即关闭”。它寻找 bot 留下的 duplicate 候选评论，然后：

1. 等待至少三天；
2. 检查候选评论之后是否出现任何新评论；
3. 检查 issue 作者是否用 `-1` reaction 明确反对；
4. 只有无人补充、无人否决且能解析出目标 issue 编号时才关闭。

仓库证据：

- 三天冷静期：[scripts/auto-close-duplicates.ts:112](D:/codes/claude-code/scripts/auto-close-duplicates.ts#L112)；
- 后续评论会阻止关闭：同文件 `:203-216`；
- 作者点踩可否决：同文件 `:218-241`；
- 通过所有门后才执行关闭：同文件 `:243-261`。

这是很适合高风险 agent 自动化的模式：

```text
AI proposal
   ↓
可见、可解释、可否决的 pending 状态
   ↓ 等待窗口
重新读取最新事实
   ↓
execute / cancel
```

它把 AI 的输出降级成**可撤销提案**，把最终副作用交给确定性条件。这通常比要求模型一次判断就绝对正确更现实。

### 5.2 人类活动是状态变化，不是噪声

`scripts/sweep.ts` 对 stale/autoclose 也做了类似的第二次确认：根据“标签实际添加时间”计算超时，而不是只看 issue 创建时间；标签后出现非 bot 评论就跳过关闭；高赞 issue 也不会被自动处理。

可迁移结论是：自动化决策必须在执行前重新读取世界状态。proposal 时的事实可能已经过期，不能把旧 snapshot 当成执行授权。

### 5.3 dry-run 是副作用系统的第一等能力

[scripts/sweep.ts:8](D:/codes/claude-code/scripts/sweep.ts#L8) 提供 `--dry-run`，让同一套选择逻辑可以只报告“将要做什么”。好的 agent tool 也应把 `plan` 与 `apply` 设计成同一语义的两个模式：

```ts
await cleanup({ mode: "plan" })  // 返回候选、原因和影响
await cleanup({ mode: "apply", proposalId })
```

`apply` 应引用先前 proposal 的 ID，并在执行前重新验证前置条件，避免 plan/apply 漂移。

### 5.4 配置单一事实源

`scripts/issue-lifecycle.ts` 集中保存 label、等待天数、原因和提示文本，`sweep.ts` 只消费这份配置。这避免“提示用户的等待期”和“实际执行的等待期”分散在多个脚本中逐渐漂移。

对 harness 来说，策略的机器可读值和用户可见解释也应来自同一个 policy object，而不是分别硬编码在 prompt 与执行器中。

### 5.5 仍需注意的工程缺口

- duplicate issue 编号从自然语言评论中用正则提取，格式变化可能误解析；
- “bot 评论包含特定短语”是脆弱协议，最好输出结构化 metadata；
- proposal 与执行之间没有不可变 proposal ID 和版本号；
- 关闭前没有验证被引用的目标 issue 是否仍存在、是否真是同一问题；
- 网络调用序列不是事务，关闭成功但评论失败时可能出现部分完成；
- 自动关闭脚本虽限制分页，但没有通用速率预算、checkpoint 和断点续跑状态。

这些缺口反过来提示：长期运行的 agent automation 需要结构化事件、幂等键、重试分类、补偿动作和执行前的 compare-and-swap 条件。

## 6. 四组机制放在一起看

| 问题 | 仓库中的做法 | Harness 可抽象出的能力 |
|---|---|---|
| 多 Agent 审查误报累积 | 候选发现后逐项独立复核 | finding 生命周期、validator、去重与证据链 |
| 模型过早结束长任务 | Stop Hook 阻止结束并重注入任务 | 外部 continuation controller |
| 长任务中角色和阶段混杂 | 探索、澄清、设计、实现、审查分阶段 | 持久状态机 + 阶段工具权限 |
| 子 Agent 摘要造成信息损失 | 子 Agent 返回关键文件，主 Agent 重读 | evidence index + primary-agent verification |
| AI 判断直接触发副作用 | 先公开候选，等待并接受人工否决 | propose/wait/revalidate/apply |
| 自动化使用过期事实 | 执行前重新检查评论、reaction、label 时间 | optimistic concurrency / precondition check |
| 控制器异常导致死循环 | 部分显式异常会清理；set -e 提前退出另有缺口 | 按控制目标选择 fail-open/fail-closed，并覆盖真实错误路径 |
| 策略与提示漂移 | 生命周期配置集中管理 | machine policy 与解释文案同源 |

## 7. 推荐的通用 Harness 骨架

综合这些实现，可以得到一个小而实用的架构：

```text
Intent
  │
  ▼
Scope Resolver ──► Evidence Index
  │                     │
  ▼                     ▼
Planner / Proposers ─► Candidate Artifacts
  │                     │
  │              Deterministic Checks
  │                     │
  └──────────────► Independent Validator
                            │
                   confirmed / rejected
                            │
                     Approval / Cooldown
                            │
                     Revalidate Preconditions
                            │
                          Executor
                            │
                    Checkpoint + Audit Log
                            │
                    Continue / Stop Controller
```

最低限度的数据对象建议包括：

- `RunState`：run ID、阶段、轮数、时间/token/费用预算、取消状态；
- `Artifact`：计划、finding、patch、测试报告及其来源；
- `EvidenceRef`：文件、行号、命令输出、版本；
- `Proposal`：待执行动作、理由、影响、过期时间、前置条件；
- `Validation`：validator 结论、检查过的证据、确定性检查结果；
- `EffectReceipt`：幂等键、执行结果、补偿信息。

## 8. 落地优先级

如果正在自研 coding agent/harness，建议按收益与复杂度依次实现：

1. **所有循环默认有界**：轮数、时间、token、费用、无进展次数至少选两种预算。
2. **把候选与已确认结果分开**：特别是代码审查、安全发现和删除建议。
3. **副作用延迟到最后**：先 plan/dry-run，再显式 apply，并在 apply 前重验世界状态。
4. **让子 Agent 返回证据索引**：主 Agent 对关键结论回读一手材料。
5. **把阶段和状态持久化**：不要只把工作流写进一大段 prompt。
6. **为每个副作用生成幂等键和 receipt**：支持重试、恢复和审计。
7. **模型完成声明后再跑外部 verifier**：测试、schema、静态分析或独立验收 Agent。

## 9. 事实边界与参考实现

### 9.1 本仓库可直接验证

- [code-review 编排命令](https://github.com/anthropics/claude-code/blob/d7dbd9a09f59775726ed14bbea8fc9dfdff62f7b/plugins/code-review/commands/code-review.md)
- [PR reviewer 的置信阈值](https://github.com/anthropics/claude-code/blob/d7dbd9a09f59775726ed14bbea8fc9dfdff62f7b/plugins/pr-review-toolkit/agents/code-reviewer.md)
- [Ralph Stop Hook](https://github.com/anthropics/claude-code/blob/d7dbd9a09f59775726ed14bbea8fc9dfdff62f7b/plugins/ralph-wiggum/hooks/stop-hook.sh)
- [Ralph 状态初始化](https://github.com/anthropics/claude-code/blob/d7dbd9a09f59775726ed14bbea8fc9dfdff62f7b/plugins/ralph-wiggum/scripts/setup-ralph-loop.sh)
- [feature-dev 分阶段工作流](https://github.com/anthropics/claude-code/blob/d7dbd9a09f59775726ed14bbea8fc9dfdff62f7b/plugins/feature-dev/commands/feature-dev.md)
- [duplicate 延迟关闭脚本](https://github.com/anthropics/claude-code/blob/d7dbd9a09f59775726ed14bbea8fc9dfdff62f7b/scripts/auto-close-duplicates.ts)
- [issue 生命周期清理脚本](https://github.com/anthropics/claude-code/blob/d7dbd9a09f59775726ed14bbea8fc9dfdff62f7b/scripts/sweep.ts)
- [生命周期单一配置源](https://github.com/anthropics/claude-code/blob/d7dbd9a09f59775726ed14bbea8fc9dfdff62f7b/scripts/issue-lifecycle.ts)

### 9.2 不能从本仓库推出

- 不能据 Ralph 插件断言 Claude Code 内核的 Agent Loop 就是 Stop Hook 状态机；
- 不能据 Markdown 命令断言阶段切换、并行数量和模型选择由宿主强制保证；
- 不能把 reviewer 自报的 0～100 置信分数当作概率校准值；
- 不能把这些示例的默认预算、安全性和并发处理视为生产级承诺；
- 第 7 节的类型、状态和通用架构是从仓库机制提炼出的**设计建议**，不是仓库现存内部 API。

## 10. 复习检查问题

1. 为什么增加 reviewer 数量可能同时提高召回率和误报数量？
2. proposer 与 validator 应如何隔离，才能减少锚定和相关错误？
3. Ralph Loop 中哪些状态在 prompt、文件系统和控制文件里？为什么要分开？
4. completion promise 为什么只能算软终止条件？
5. 哪些控制故障应 fail-open，哪些应 fail-closed？
6. 为什么子 Agent 返回“关键文件索引”比只返回长摘要更可靠？
7. 用户批准为什么可视为产生副作用之前的 commit point？
8. duplicate 自动关闭中的三天等待、后续评论检查和点踩否决分别防什么风险？
9. 为什么 `apply` 前必须重新验证 proposal 的前置条件？
10. 如何用结构化 finding、proposal 和 effect receipt 支持恢复、去重与审计？

## 11. 本次复核：已有控制器未改，安全插件另有一条审查链

与旧基线 `0fa8c19` 相比，本篇引用的 code-review、Ralph、feature-dev 和 issue 脚本没有代码差异，原先从这些实现提炼的学习内容继续保留。提交链接更新到本次核验版本，不能把原有能力误写成这次新增。

标题“有界自循环”描述应采用的设计；Ralph 初始化默认 `MAX_ITERATIONS=0` 仍然表示无限制。显式设上限才是有界使用，不应把标题理解成插件默认有界。

此外，security-guidance 的 Stop 与 commit/push 审查值得单独研究：前者做 diff 分析，后者可进入 SDK 调查和反证；它们都属于事后反馈，不会撤销已经完成的提交或推送。阅读新增安全审查篇。

## 12. 源码复核补充：提示词步骤与异常代码都可能自相矛盾

code-review 第 5 步明确针对第 3/4 个 reviewer 的候选启动复核，不能把流程图画成所有 reviewer 的候选无条件进入同一验证环节。其第 6 步又要求过滤未验证问题，规则审查候选如何走过这两步存在提示词歧义；宿主没有强制状态机替它补齐。

Ralph 的错误处理也不能只读注释：[plugins/ralph-wiggum/hooks/stop-hook.sh](D:/codes/claude-code/plugins/ralph-wiggum/hooks/stop-hook.sh#L90) 的命令替换失败受 set -e 影响；[plugins/ralph-wiggum/hooks/stop-hook.sh](D:/codes/claude-code/plugins/ralph-wiggum/hooks/stop-hook.sh#L119) 的 Perl 替换未要求标签先存在。这些是静态代码发现，本次未运行完整 Bash Hook。
