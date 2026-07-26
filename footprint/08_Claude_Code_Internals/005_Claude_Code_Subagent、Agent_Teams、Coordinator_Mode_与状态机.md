# Claude Code Subagent、Agent Teams、Coordinator Mode 与状态机

> 所属分类：Claude Code 源码与机制解读  
> 整理日期：2026-07-26；审查基线：Claude Code v2.1.220  
> 核心问题：Claude Code 的主 Agent、普通 Subagent、Agent Teams 和 Coordinator Mode 如何通信、隔离、恢复与判断状态？

## 1. 先给出结论

Claude Code 当前存在几种容易被混为一谈的多 Agent 机制：

| 机制 | 组织关系 | 主要通信方式 | 典型生命周期 |
|---|---|---|---|
| 普通 Subagent | 主 Agent 调用一个专用工作者 | `Agent` 调用结果、后台完成通知、`SendMessage` | 一次运行结束后可保留 transcript，并按 ID 恢复 |
| Fork Subagent | 从主会话完整分叉 | `/subtask` 或实验性自动 fork；继承主会话上下文 | 分叉后独立运行，只把最终结果返回主会话 |
| Agent View / 后台 session | 多个彼此独立的完整 Claude Code session | `claude agents` 界面、直接进入并回复各 session | 可分派、挂起、重连和恢复；默认没有共享 Team task list |
| Agent Teams | 固定 Team Lead + 多个 Teammate | mailbox、直接消息、共享任务列表 | Teammate 可多轮工作、空闲、被再次唤醒，最后关闭 |
| Coordinator Mode | 严格中心化 Coordinator + Worker | `Agent`、完成通知、`SendMessage` | Coordinator 只编排，Worker 异步执行 |

最关键的边界是：

```text
普通 Subagent 的一次执行
≠
Agent Teams 中一个长期存在的 Teammate
≠
内部 Coordinator Mode 的 Worker 编排策略
```

还要避免命令名造成的版本混淆：自 v2.1.212 起，`/subtask` 启动会话内 Fork Subagent；`/fork` 通常把整个会话复制成一个独立后台 session。v2.1.211 及更早版本曾用 `/fork` 表示会话内 fork。

### 1.1 当前并行机制的选择轴

当前官方 “Run agents in parallel” 文档把并行能力按两个问题区分：

```text
是否需要留在当前 session 的一个 Agent 工具调用中？
  ├─ 是：普通 Subagent / Fork Subagent
  └─ 否：独立后台 session / Agent View

多个独立 session 是否需要共享任务表和互相通信？
  ├─ 否：Agent View 中的独立 session
  └─ 是：Agent Teams
```

因此“后台 Subagent”和“后台 session”不是同义词。前者仍属于当前主 session 的 Agent 调用与任务注册表；后者是可独立恢复、独立计费和独立管理的完整会话。

同时还要区分三个不同层次：

```text
模型消息协议：assistant / user / tool_use / tool_result
运行时任务系统：task id / agent id / status / notification
协作组织模型：main-subagent / lead-teammate / coordinator-worker
```

只看到 XML、`user` role 或 `completed` 字段，不能脱离所在层次推断完整架构。

## 2. 普通 Subagent 的完整通信链路

普通 Subagent 由主 Agent 通过 `Agent` 工具启动。`Agent` 是当前名称，`Task` 仍作为旧别名被接受。

```text
主 Agent
  │
  ├─ assistant: Agent(tool_use)
  │                    │
  │                    ▼
  │             Claude Code 运行时
  │                    │
  │                    ├─ 创建独立 Agent context
  │                    ├─ 在该 context 中多轮调用模型和工具
  │                    └─ 保存独立 transcript
  │
  └─ 接收工具结果或稍后的完成通知
```

主 Agent 通常不会收到 Subagent 的完整逐步工具轨迹。官方文档把其用途描述为：大量检索结果、日志和文件内容留在 Subagent 自己的上下文中，只把最终报告返回主会话。

### 2.1 前台执行

前台 Subagent 会阻塞主会话，直到该次运行结束。Agent SDK 公布的工具输出类型可缩写为：

```ts
type AgentOutput =
  | {
      status: "completed";
      agentId: string;
      content: Array<{ type: "text"; text: string }>;
    }
  | {
      status: "async_launched";
      agentId: string;
      outputFile: string;
    }
  | {
      status: "sub_agent_entered";
      message: string;
    };
```

因此前台完成的稳定结构是：

```text
Agent 工具调用
  → status = completed
  → agentId
  → content
  → usage / duration 等统计信息
```

### 2.2 后台执行

后台启动时，`Agent` 工具先返回：

```text
status = async_launched
agentId = ...
outputFile = ...
```

这只表示“已启动”，不是最终任务结果。运行完成后，Claude Code 再产生后台任务通知。Agent SDK 当前公开的类型为：

```ts
type SDKTaskNotificationMessage = {
  type: "system";
  subtype: "task_notification";
  task_id: string;
  status: "completed" | "failed" | "stopped";
  output_file: string;
  summary: string;
};
```

SDK 还公开了来源标记：

```ts
type SDKMessageOrigin =
  | { kind: "human" }
  | { kind: "peer"; from: string; name?: string }
  | { kind: "task-notification" }
  | { kind: "coordinator" };
```

后台任务结束后触发的后续结果会带：

```json
{
  "origin": {
    "kind": "task-notification"
  }
}
```

这让宿主程序可以明确区分：

```text
用户真的输入了一条消息
vs
运行时为后台任务完成而注入了一个合成回合
```

当前版本边界还包括：

- 自 v2.1.186 起，后台 Subagent 需要权限时，提示会显示在主会话中，由用户批准或拒绝；旧版“后台一律自动拒绝需要确认的工具”已经过时。
- 自 v2.1.198 起，Subagent 默认后台运行；若主 Agent 必须立即依赖结果，仍可选择前台。
- 自 v2.1.199 起，Subagent 因 API 错误提前终止时会按失败回报，而不是把错误文本伪装成正常发现。
- 自 v2.1.210 起，Subagent 输出会扫描可能模仿 harness 指令的形态，但这不能替代权限和沙箱。

## 3. “XML 包装成用户消息”到底对不对

这个说法只对了一部分。

### 3.1 为什么工具结果出现在 `user` role

Claude Messages API 没有 OpenAI 风格的独立 `tool` role。客户端工具执行完后，调用方必须发送：

```json
{
  "role": "user",
  "content": [
    {
      "type": "tool_result",
      "tool_use_id": "toolu_123",
      "content": "..."
    }
  ]
}
```

所以：

```text
role = user
不等于
内容来自人类用户
```

它可能只是协议规定的工具结果承载位置。`tool_use_id` 才负责把结果与前一条 `assistant` 消息中的 `tool_use.id` 配对。

### 3.2 XML 出现在哪里

从特定版本 transcript 和实现还原中，可以观察到后台完成通知以合成用户消息注入，并使用类似结构：

```xml
<task-notification>
  <task-id>agent-id</task-id>
  <status>completed</status>
  <summary>...</summary>
  <result>...</result>
</task-notification>
```

因此更准确的表述是：

> 普通前台 Subagent 的返回值首先是 `Agent` 工具的 `tool_result`；后台 Subagent 会在稍后的合成回合中产生任务完成通知。特定 Claude Code 实现会在内部消息正文中使用 `<task-notification>` XML，但官方 Agent SDK 对外提供的是结构化 `SDKTaskNotificationMessage` 和 `origin.kind`，不应把 XML 文本当作永久公共协议。

换言之，不应该编写只依赖 XML 字符串的 SDK 集成：

```ts
// 脆弱：依赖内部文本格式
if (messageText.includes("<task-notification>")) {
  // ...
}
```

应优先按公开判别字段处理：

```ts
function isTaskNotification(message: {
  type?: string;
  subtype?: string;
}): boolean {
  return (
    message.type === "system" &&
    message.subtype === "task_notification"
  );
}
```

## 4. Subagent 与主 Agent 如何隔离

隔离不是一个总开关，而是多个维度。

| 隔离维度 | 普通非 Fork Subagent | Fork Subagent |
|---|---|---|
| 对话历史 | 不继承主对话 | 继承完整主对话 |
| System prompt | 使用自己的定义和环境信息 | 与主会话相同 |
| 已读文件内容 | 不继承 | 继承当时会话历史中的内容 |
| 已调用 Skills | 默认不继承；可预加载指定 Skill | 随完整上下文继承 |
| Auto memory | 不加载主会话 auto memory | 随主会话上下文 |
| 工具集合 | 从主会话能力中筛选，并受 Agent 定义限制 | 与主会话相同 |
| Prompt Cache | 独立 | 首次请求可复用主会话前缀 |

普通 Subagent 的初始上下文通常包含：

- 自己的 system prompt；
- 主 Agent 编写的委派任务消息；
- Claude Code 加入的环境信息；
- 通常加载的 `CLAUDE.md` 层级和项目规则；
- 会话开始时的 Git 状态快照；
- Agent 定义中明确预加载的 Skills。

内置 Explore 和 Plan Agent 对 `CLAUDE.md` 与 Git 状态有特殊跳过规则，不能把普通自定义 Agent 的加载行为机械套用到它们。

### 4.1 上下文隔离不等于文件隔离

普通 Subagent 默认从主会话的当前工作目录开始，所以通常共享同一个 checkout：

```text
主 Agent context       Subagent context
      │                      │
      └──────── 同一个工作目录 ────────┘
```

这意味着：

- 两边看不到彼此完整对话；
- 但一方写入磁盘后，另一方重新读取文件就能看到；
- 并发编辑同一文件可能互相覆盖。

若需要文件系统隔离，可在 Subagent 定义中使用：

```yaml
---
name: isolated-worker
description: 在隔离分支中修改代码
isolation: worktree
---
```

此时 Subagent 在临时 Git worktree 中运行。当前官方文档说明，该 worktree 默认从仓库的默认分支创建，而不是自动从父会话当前 `HEAD` 创建；设计任务时不能假定它天然包含父分支尚未合并的提交。它解决的是 checkout 隔离，也不会自动解决业务逻辑冲突、数据库冲突或外部服务副作用。

### 4.2 工具与权限隔离

自定义 Subagent 可以限制工具：

```yaml
---
name: code-reviewer
description: 只读代码审查
tools: Read, Grep, Glob
permissionMode: plan
---
```

Agent 消息不能替用户批准权限，也不能通过 `SendMessage` 修改另一个 Agent 的权限模式、`CLAUDE.md` 或配置。这是通信通道与权限通道的明确分离。

## 5. 前台和后台不是两种不同的 Subagent

以下描述不准确：

```text
普通 Subagent 执行较久后，自动变成后台 Subagent
```

官方文档没有公布“运行超过 N 秒就自动转后台”的阈值。当前行为更接近调度选择：

- 主 Agent 需要结果后才能继续时，使用前台执行；
- 任务可与主线并行时，使用后台执行；
- 用户可以明确要求前台或后台；
- 用户可以用 `Ctrl+B` 把正在运行的前台任务切到后台；
- 自 v2.1.198 起，Subagent 默认后台运行，但主 Agent 仍可在需要立即依赖结果时使用前台。

所以前台与后台描述的是：

```text
主会话是否等待这次运行
```

而不是：

```text
Subagent 的能力等级或任务难度
```

## 6. 为什么完成后还要恢复旧 Subagent

主 Agent 已拿到的通常只是最终报告；旧 Subagent 的独立 transcript 仍保存：

- 之前的任务说明；
- 完整工具调用与结果；
- 读过的文件和定位过程；
- 已排除的假设；
- 该 Agent 自己的多轮上下文。

因此恢复旧 Agent 的价值是复用高成本上下文：

```text
第一次：检查认证模块并找出风险
第二次：基于刚才的风险，继续检查授权边界
```

若新建 Agent，主 Agent 需要重新传递背景，新 Agent 也可能重新读取同一批文件。若恢复旧 Agent，则用原 `agentId` 继续：

```json
{
  "to": "agent-id",
  "message": "继续检查授权逻辑，并验证刚才第 2 条风险"
}
```

当前官方文档明确说明：完成的普通 Subagent 收到 `SendMessage` 后，会在后台自动恢复，不需要再次调用 `Agent`。Explore 和 Plan 是一次性 Agent，不返回可恢复的 Agent ID。

### 6.1 什么时候应该新建

以下情况更适合新建 Subagent：

- 新任务与旧上下文重合很少；
- 需要独立复核，避免继承旧结论的锚定偏差；
- 旧 Agent 的方向已明显混乱或上下文陈旧；
- 要使用不同工具、模型、权限或专业角色；
- 旧 Agent 已被用户主动取消，当前版本会拒绝自动恢复。

可用一个简单决策函数表达：

```js
function chooseAgent({ contextOverlap, needIndependentReview, cancelled }) {
  if (cancelled || needIndependentReview) return "spawn-new";
  if (contextOverlap >= 0.6) return "resume-existing";
  return "spawn-new";
}
```

`0.6` 只是业务策略示例，不是 Claude Code 内部阈值。

## 7. 主 Agent 如何判断 Subagent 状态

主 Agent 不应通过自然语言猜测状态。Claude Code 运行时维护任务记录，并向模型或 SDK发送结构化事件。

Agent SDK 当前公开了任务更新事件：

```ts
type TaskStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "killed";

type SDKTaskUpdatedMessage = {
  type: "system";
  subtype: "task_updated";
  task_id: string;
  patch: {
    status?: TaskStatus;
    end_time?: number;
    error?: string;
  };
};
```

主 Agent 可获得的信号包括：

- `AgentOutput.status = "completed"`：前台运行完成；
- `AgentOutput.status = "async_launched"`：后台运行已启动；
- `SDKTaskUpdatedMessage`：后台任务状态发生变化；
- `SDKTaskNotificationMessage`：后台任务完成、失败或停止；
- `/tasks` 和 Agent 面板：面向交互用户的运行时视图；
- `agentId`：后续查询、停止或恢复的稳定标识。

因此可靠判断链路是：

```text
运行时状态变化
  → 结构化 task event / notification
  → 主 Agent 获得当前状态
  → 决定等待、汇总、停止或发送后续消息
```

而不是：

```text
扫描历史对话
  → 看到“我开始处理了”
  → 猜测任务仍在运行
```

## 8. Agent Teams 不是完全平级

Agent Teams 中确实有多个独立 Claude Code session，但官方架构明确包含：

| 角色 | 职责 |
|---|---|
| Team Lead | 主会话；创建团队、生成 Teammate、协调与综合结果 |
| Teammate | 独立 Claude Code 实例；执行分配任务或自领任务 |
| Task list | 全体可见的共享任务列表 |
| Mailbox | Agent 之间的消息系统 |

因此正确表述是：

> Teammate 在执行能力和独立上下文上接近同伴关系，但治理权不对称。Lead 是固定角色，只有 Lead 能管理团队，且不能把 Lead 身份转让给 Teammate。

官方限制还包括：

- 一个 session 只有一个 team；
- 不支持嵌套 team；
- Teammate 不能生成新的 Teammate；
- Lead 在团队生命周期内固定；
- Teammate 启动时继承 Lead 的权限模式。

所以“同等若干 Agent 自组织、没有主从”并不符合当前 Claude Code Agent Teams。

## 9. Team mailbox 与普通 Subagent 恢复要分开

部分构建的 transcript / source map 还原显示 mailbox 可能使用类似路径：

```text
~/.claude/teams/{team-name}/inboxes/{agent-name}.json
```

共享任务列表存储为：

```text
~/.claude/tasks/{team-name}/
```

该 inbox 文件路径不是官方稳定接口。官方当前只公开 team config 与 task list 的本地存储位置，不建议应用直接编辑内部 mailbox 文件。Teammate 消息会自动投递，Lead 不需要轮询；Teammate 也能按名字直接互发消息，并共同查看、领取任务。

普通 Subagent 的恢复则依赖其 Agent ID、独立 transcript 和 `SendMessage` 路由。它不等于“把一封邮件写入 Team mailbox”。当前 transcript 路径为：

```text
~/.claude/projects/{project}/{sessionId}/subagents/agent-{agentId}.jsonl
```

两种“消息唤醒”要分别理解：

```text
普通 Subagent：
completed / stopped
  → SendMessage(agentId)
  → 同 ID 新一轮后台运行

Team Teammate：
idle
  → mailbox / direct message
  → 同一 Teammate session 开始下一轮
```

这里的 `completed` 和 `idle` 也不是同义词：

- `completed` 可以描述某次 Subagent 运行或某个任务已经完成；
- `idle` 表示 Teammate 当前没有执行 turn，但 session 仍存在且可寻址；
- 完成一个 Team task 不代表 Teammate 已关闭。

Agent Teams 的共享任务只有三个正式状态：

```text
pending → in progress → completed
```

任务领取时的文件锁只保护“谁领取该任务”这次竞争，不保护源代码文件。官方明确提醒：两个 Teammate 修改同一文件仍会发生覆盖。

## 10. 普通 Subagent 现在也能 `SendMessage`

把 `SendMessage` 只理解为 Agent Teams 专属能力已经过时。

当前 Subagent 专题文档明确说明：

- 主 Agent 可以按 Agent ID 或名字恢复普通 Subagent；
- 完成或被 `TaskStop` 停止的 Subagent 可自动恢复；
- 运行中的 Subagent 可接收主 Agent 的中途方向修正；
- 自 v2.1.206 起，若命名 Subagent 的工具中包含 `SendMessage`，启动时还会获得 `main` 与已有命名 Agent 的 sibling roster，这些名字都可作为消息目标；
- 普通恢复不要求启用 Agent Teams；
- Team 专用的 `shutdown_request`、`plan_approval_response` 等结构化协议仍属于 Agent Teams。

这说明“普通 Subagent 永远只能向主 Agent 回报”也不再是所有当前构建的完整描述。普通命名 Agent 可以具备点对点消息能力，但仍没有 Agent Teams 的共享任务列表、基于 Team mailbox 的会话级投递、Teammate 生命周期和 Team 协议。

Claude Code 文档在快速演进，旧版工具表、旧文章和新版专题页可能暂时存在表述差异。遇到冲突时，应记录：

```text
Claude Code 版本
文档抓取或访问日期
具体功能页
实际 SDK 类型或 transcript
```

不能把某一旧版的“Subagent 只能最终回报”永远写死。

### 10.1 Subagent 嵌套生成必须按版本说明

“Subagent 永远不能生成 Subagent”与“默认总是禁止”都已不准确。公开版本历史显示：

- v2.1.172～v2.1.216 曾默认允许最多五层，且不能配置；
- v2.1.217～v2.1.218 引入可配置深度后默认值为 1；
- 自 v2.1.219 起，默认最大深度改为 3；设置 `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` 可禁用嵌套；
- 子 Agent 的工具池还必须包含 `Agent`；省略或禁用该工具会阻止该 Agent 继续生成；
- 当前还存在每会话总数与并发数限制，它们和嵌套深度是三套不同预算。

因此稳定原则是“有限深度、受工具白名单和运行时预算共同约束”，具体默认值必须带版本。Agent Teams 的 Teammate 不能生成新的 Teammate，属于另一条团队治理限制，不能与普通 Subagent 嵌套混写。

## 11. Agent Teams 与内置 Coordinator Mode 的区别

这里的 Coordinator Mode 特指特定 Claude Code 构建中由下面条件控制的内部模式：

```ts
export function isCoordinatorMode(): boolean {
  return (
    feature("COORDINATOR_MODE") &&
    isEnvTruthy(process.env.CLAUDE_CODE_COORDINATOR_MODE)
  );
}
```

这段实现说明它同时受：

- 构建或服务端 feature gate；
- `CLAUDE_CODE_COORDINATOR_MODE` 环境变量；

控制。因此只设置环境变量不保证当前发行构建一定启用。Anthropic 当前公开的 Claude Code 功能文档没有把它作为与 Agent Teams 同等级的稳定用户功能说明，以下细节应视为版本相关实现分析。

### 11.1 Coordinator Mode

第三方 source map / 源码还原显示，该模式倾向严格的中心化管理：

```text
用户
  ↓
Coordinator
  ├─ Research Worker
  ├─ Implementation Worker
  └─ Verification Worker
```

Coordinator 使用替换后的专用 system prompt，并按：

```text
Research → Synthesis → Implementation → Verification
```

组织工作。它自身的工具面被压缩为主要编排工具：

```text
Agent
SendMessage
TaskStop
```

Worker 被强制异步执行，通过任务完成通知返回结果；Coordinator 负责综合和继续派发。Worker 不通过 Agent Teams 的共享任务列表和 peer mailbox 自主协作。

### 11.2 Agent Teams

Agent Teams 是官方文档公开的实验功能：

- Lead 保持一个正常 Claude Code 主会话；
- Teammate 是独立 Claude Code session；
- Teammate 可直接互发消息；
- 全体共享 task list；
- Teammate 可以自领未阻塞任务；
- Lead 负责协调，但不是唯一的信息中转点。

### 11.3 对比

| 维度 | Coordinator Mode | Agent Teams |
|---|---|---|
| 公开稳定性 | 内部、feature-gated、版本相关 | 官方公开的实验功能（v2.1.32+） |
| 拓扑 | 严格中心化 Coordinator → Worker | Lead + 可直接通信的 Teammate |
| 主角色是否直接编码 | 设计上主要负责编排 | Lead 保持正常会话能力 |
| Worker/Teammate 是否长期存在 | 可按 ID 恢复，但以任务 Worker 为中心 | Teammate session 可跨多个任务持续工作 |
| 同伴直接通信 | Worker 通常向 Coordinator 回报 | Teammate 可直接互发消息 |
| 共享任务列表 | 不使用 Agent Teams 的共享 team task list | 有 |
| mailbox | 不使用 Team peer mailbox | 有 |
| 自主领取任务 | 无 Team 式自领任务 | 支持 |
| 综合责任 | Coordinator 强制集中综合 | Lead 综合，但 Teammate 可先互相协调 |

不要把 Claude Platform 文档中的“Build an orchestration mode”与 Claude Code 内部 `COORDINATOR_MODE` 自动画等号。前者是 API 上下文管理能力，后者是 Claude Code 某些构建中的 harness 模式。

## 12. 状态机到底是什么

状态机不是“保存一个 status 字符串”，而是对系统行为的完整约束：

```text
状态集合
+ 事件集合
+ 合法迁移规则
+ 迁移产生的副作用
```

以后台 Subagent 为例：

```text
created
  │ launch
  ▼
running
  ├─ finish ─────────→ completed
  ├─ error ──────────→ failed
  ├─ TaskStop ───────→ stopped
  └─ user cancel ────→ cancelled

completed / stopped
  │ SendMessage
  └──────────────────→ running

cancelled
  │ SendMessage
  └──────────────────→ rejected
```

这是概念模型。公开 SDK 的事件字段可能使用 `killed`，UI 和内部实现也可能区分 `stopped` 与 `cancelled`，不能把上图的名称当作所有版本的序列化枚举。

### 12.1 一个可运行的 JavaScript 状态机

```js
const transitions = {
  created: {
    launch: "running",
  },
  running: {
    finish: "completed",
    fail: "failed",
    stopByAgent: "stopped",
    cancelByUser: "cancelled",
  },
  completed: {
    sendMessage: "running",
  },
  stopped: {
    sendMessage: "running",
  },
  failed: {
    retry: "running",
  },
  cancelled: {},
};

function transition(currentState, event) {
  const nextState = transitions[currentState]?.[event];
  if (!nextState) {
    throw new Error(
      `Illegal transition: ${currentState} --${event}--> ?`
    );
  }
  return nextState;
}

let state = "created";
state = transition(state, "launch");
state = transition(state, "finish");
state = transition(state, "sendMessage");

console.log(state); // running
```

如果只写：

```js
task.status = input.status;
```

任何人都能把 `cancelled` 改成 `running`，它只是状态字段，不是可靠状态机。

### 12.2 状态与任务不是一回事

在 Agent Teams 中至少有两套状态：

```text
Task 状态：
pending → in_progress → completed

Teammate 生命周期：
working ⇄ idle → shutdown
```

例如：

```text
task-17 = completed
teammate-security = idle
```

表示安全审查任务已完成，但该 Teammate 仍可接收下一项工作。若把任务完成误解为进程退出，Lead 就会错误地新建重复 Teammate。

## 13. 一个更接近真实系统的状态存储示例

运行时应以 ID 为键保存权威状态，而不是从自然语言报告反推：

```js
class AgentRegistry {
  constructor() {
    this.agents = new Map();
  }

  register(agentId) {
    this.agents.set(agentId, {
      status: "running",
      lastResult: null,
    });
  }

  applyTaskEvent(event) {
    const agent = this.agents.get(event.taskId);
    if (!agent) throw new Error(`Unknown agent: ${event.taskId}`);

    agent.status = event.status;
    if (event.result !== undefined) {
      agent.lastResult = event.result;
    }
  }

  sendMessage(agentId, message) {
    const agent = this.agents.get(agentId);
    if (!agent) throw new Error(`Unknown agent: ${agentId}`);
    if (agent.status === "cancelled") {
      throw new Error("User-cancelled agents cannot auto-resume");
    }

    agent.status = "running";
    return {
      to: agentId,
      message,
    };
  }
}
```

真实 Claude Code 的内部数据结构更复杂，但设计原则相同：

```text
结构化运行时状态是权威来源
自然语言 result 是任务语义载荷
transcript 是可恢复上下文
```

三者不能互相替代。

## 14. 对本次讨论中原表述的逐条修正

### 表述一

> Subagent 执行时间较长则会变成后台 Subagent。

修正：

> 前台或后台是调度方式，不是按公开的耗时阈值升级。当前版本默认偏向后台；主 Agent 依赖结果时仍可前台执行，用户也能显式选择或用 `Ctrl+B` 切换。

### 表述二

> 只有 Team 模式启用信箱，主 Agent 才能实时指示 Subagent。

修正：

> Team mailbox 属于 Agent Teams；但当前普通 Subagent 也能通过 `SendMessage` 接收中途修正或在完成后恢复。二者的存储与组织模型不同。

### 表述三

> Subagent 的结果都用 XML 包装成用户消息。

修正：

> 前台结果是 `Agent` 工具的结构化 `tool_result`；后台完成会触发合成通知。内部 transcript 可使用 `<task-notification>` XML，但 SDK 暴露结构化事件，XML 不是应依赖的稳定公共协议。

### 表述四

> Agent Teams 没有主 Agent 和子 Agent，所有 Agent 完全平级。

修正：

> Agent Teams 有固定 Lead 和多个 Teammate。Teammate 能独立执行、直接通信和自领任务，但团队创建、管理、综合与关闭权仍集中在 Lead。

### 表述五

> 主 Agent 根据 Subagent 的文字回复判断它是否完成。

修正：

> 完成状态来自运行时任务注册表和结构化 task event；文字结果只承载任务内容，不是唯一状态依据。

## 15. 选择建议

| 需求 | 更适合的机制 |
|---|---|
| 一次性检索、审查或验证，只关心摘要 | 普通 Subagent |
| 任务需要继承主会话的完整背景，但仍只回传最终结果 | `/subtask` Fork Subagent |
| 需要复制整个会话并在独立后台 session 中继续 | `/fork` |
| 对同一专家角色做高度相关的追问 | 恢复已有 Subagent |
| 需要独立复核，避免旧上下文影响 | 新建 Subagent |
| 多个长期并行任务，需要互相通信和共享任务表 | Agent Teams |
| 多个完整会话并行，但不需要共享任务表 | `claude agents` / Agent View |
| 需要严格“协调者不实现、工作者执行”的中心化编排 | Coordinator Mode；但必须先确认构建支持 |
| 多个 Agent 会修改同一文件 | 先拆分文件所有权，或使用独立 worktree |

## 16. 关联知识点

- `001_Claude_Code_Prompt_前缀缓存与三级上下文.md`
- `002_Claude_Code_流式输出、max_tokens_与恢复机制.md`
- `004_Claude_Code_上下文压缩、Microcompact_与状态恢复.md`
- `../02_Agent_RAG_Memory/002_Agent_开发框架与选型.md`
- `../02_Agent_RAG_Memory/006_Agent_的端到端任务能力.md`
- `../02_Agent_RAG_Memory/007_MRKL、ReAct、ToT_与_Plan-and-Execute.md`
- `../02_Agent_RAG_Memory/017_LangGraph_状态更新、invoke_与_stream.md`

## 17. 参考资料与事实边界

### 官方资料

- [Claude Code Subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams)
- [Claude Code Run Agents in Parallel](https://code.claude.com/docs/en/agents)
- [Claude Code Tools Reference](https://code.claude.com/docs/en/tools-reference)
- [Claude Code Agent SDK TypeScript Reference](https://code.claude.com/docs/en/agent-sdk/typescript)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Claude Code 官方发行记录](https://github.com/anthropics/claude-code/blob/main/feed.xml)
- [Claude Messages API Tool Results](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
- Anthropic Multi-agent Coordination Patterns：`https://claude.com/blog/multi-agent-coordination-patterns`
- Anthropic Building Multi-agent Systems：`https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them`

### Coordinator Mode 与 XML 的版本相关实现线索

- Claude Wiki Coordinator Mode：`https://claude-wiki.com/coordinator-mode.html`
- Claude Code from Source - Coordination：`https://claude-code-from-source.com/ch10-coordination/`
- 本次梳理的 Multi-Agent 博客：`https://xiaolinnote.com/claudecode/source/cc_multi_agent.html`

官方资料可以确认 Subagent 的前后台行为、上下文隔离、worktree、恢复、`SendMessage`、Agent SDK 事件类型，以及 Agent Teams 的 Lead、Teammate、task list 和 mailbox。`<task-notification>` 的精确 XML、`COORDINATOR_MODE` 的内部函数、工具白名单和四阶段 prompt 来自特定构建的实现还原，应标记为版本相关，不能承诺未来版本保持不变。

## 18. 复习检查问题

1. 为什么 `role: "user"` 不足以证明消息来自真实用户？
2. 前台 Subagent 的 `tool_result` 与后台 `task_notification` 有什么区别？
3. 为什么普通 Subagent 的上下文隔离不等于文件系统隔离？
4. 什么情况下恢复已有 Subagent 比新建更合理？
5. `completed`、`idle` 和 `shutdown` 分别描述什么？
6. Agent Teams 为什么不能称为完全平级的 Agent 集合？
7. Team mailbox 与普通 Subagent 的 `SendMessage` 恢复有何不同？
8. Coordinator Mode 与 Agent Teams 的核心拓扑差异是什么？
9. 为什么一个 `status` 字段本身还不构成状态机？
10. 主 Agent 应该依赖什么判断后台任务的真实状态？
