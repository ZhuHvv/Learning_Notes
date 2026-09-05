# 08.11 Security Guidance：差异基线、异步审查与反证

> 核验：2026-09-05；源码 `d7dbd9a09f59775726ed14bbea8fc9dfdff62f7b`。这是现有插件的补充解读，不是本次 Git 增量新增模块。未调用外部模型服务，也未触发 commit/push。

## 1. 总体模型：快速提醒与较慢审查分工

这个插件不只做正则提醒。它将每次编辑后的便宜检查，与 Stop、commit、push 之后的差异审查分开，利用持久状态减少重复反馈。

| 事件 | 注册与处理 | 目的 |
|---|---|---|
| SessionStart | `ensure_agent_sdk.py` | 准备 SDK 依赖环境 |
| UserPromptSubmit | `handle_user_prompt_submit` | 获取本轮 Git 基线 |
| PostToolUse 编辑 | `main` 的编辑分支 | 记录路径、检查模式、提示新增风险 |
| PostToolUse Bash commit/push | 专门处理函数 | 审查已提交或推送范围 |
| Stop | `handle_stop_hook` | 审查本轮文件差异 |

首先读 [plugins/security-guidance/hooks/hooks.json](D:/codes/claude-code/plugins/security-guidance/hooks/hooks.json#L1)。Stop 与 Bash commit/push 设置了 `asyncRewake`：审查在后台运行，发现问题后按宿主机制唤醒反馈；它们不是提交前拦截器。

## 2. 真实调用链：Stop 不走 Agent 调查循环

```text
hooks.json
  → sg-python.sh → security_reminder_hook.main
  → handle_stop_hook
      → 检查 stop_hook_active，避免递归
      → consume_stop_state，取得基线与待处理状态
      → 检查开关、次数与凭据/连通性
      → compute_v2_review_set
      → get_git_diff → 文件筛选与载荷裁剪
      → analyze_code_security
      → 去重、更新状态、反馈或跳过
```

入口：[plugins/security-guidance/hooks/security_reminder_hook.py](D:/codes/claude-code/plugins/security-guidance/hooks/security_reminder_hook.py#L1700)；关键调用：[plugins/security-guidance/hooks/security_reminder_hook.py](D:/codes/claude-code/plugins/security-guidance/hooks/security_reminder_hook.py#L1854)。

文件顶部和函数说明仍有“两次 Haiku 分析”的旧说法，但当前执行分支只调用 `analyze_code_security`，`analyze_security_concerns` 没接入此处。`llm.py` 中 [plugins/security-guidance/hooks/llm.py](D:/codes/claude-code/plugins/security-guidance/hooks/llm.py#L64) 的默认模型字符串是 `claude-opus-4-7`。这是配置默认值，不代表本次进行了模型调用，也不代表模型在所有提供方可用。

“single-shot”在这里指未进入工具探索式 Agent Loop，不保证只发一个 HTTP 请求：下游还有 [plugins/security-guidance/hooks/llm.py](D:/codes/claude-code/plugins/security-guidance/hooks/llm.py#L521) 等封装。读调用链时不要把函数名当请求计数器。

## 3. 审查集合与内容基线必须分开

[plugins/security-guidance/hooks/diffstate.py](D:/codes/claude-code/plugins/security-guidance/hooks/diffstate.py#L163) 用 Git 快照作为本轮起点。[plugins/security-guidance/hooks/diffstate.py](D:/codes/claude-code/plugins/security-guidance/hooks/diffstate.py#L353) 从当前 Git 状态构造集合，可概括为：

```text
dirty_now = 当前已跟踪脏文件 + 本轮新增/变化的未跟踪文件
若 HEAD 从起点线性前进：再纳入本轮提交涉及的文件

有可用基线：review_set = dirty_now ∩ changed_since_baseline
基线缺失或 Git 查询失败：review_set 回退到 dirty_now
```

文件列表用来避免 checkout/pull 放大审查范围；diff 正文优先与轮初快照比较，以排除用户开始前的未提交改动。两者不是同一个基准。

未跟踪文件不在普通 stash create 快照内，代码另外记 `mtime_ns`，排除时间戳未变的原有文件。这是启发式而非内容哈希；保留时间戳的修改不能由该条件可靠识别。源码也明确提到：只有 Bash 写入、又在 Stop 前中断的回合仍有覆盖限制。

## 4. 状态竞争与 Windows 边界

按顺序读 [plugins/security-guidance/hooks/session_state.py](D:/codes/claude-code/plugins/security-guidance/hooks/session_state.py#L25) → [plugins/security-guidance/hooks/session_state.py](D:/codes/claude-code/plugins/security-guidance/hooks/session_state.py#L118) → [plugins/security-guidance/hooks/diffstate.py](D:/codes/claude-code/plugins/security-guidance/hooks/diffstate.py#L74)。

状态文件默认在 `~/.claude/security/`，按净化后的会话标识命名；可由 `SECURITY_WARNINGS_STATE_DIR` 修改。远程会话优先用稳定的远程会话标识。

Unix 可使用 `fcntl.flock` 包围读改写；导入不到 `fcntl` 时（典型为原生 Windows），代码直接无锁读改写。`save_state` 也是直接打开文件写 JSON，不能称为跨平台原子持久化或事务。

Stop 在慢速 I/O（输入输出）和模型请求之前消费一次状态快照。连通性等暂时失败路径可调用 [plugins/security-guidance/hooks/diffstate.py](D:/codes/claude-code/plugins/security-guidance/hooks/diffstate.py#L116) 恢复未审工作。这个设计减少竞争窗口，但没有锁的平台仍需单独验证并发正确性。

## 5. commit/push：调查候选，再试图反证

按 [plugins/security-guidance/hooks/security_reminder_hook.py](D:/codes/claude-code/plugins/security-guidance/hooks/security_reminder_hook.py#L901) → [plugins/security-guidance/hooks/security_reminder_hook.py](D:/codes/claude-code/plugins/security-guidance/hooks/security_reminder_hook.py#L832) → [plugins/security-guidance/hooks/llm.py](D:/codes/claude-code/plugins/security-guidance/hooks/llm.py#L1059) 阅读。push 另有 [plugins/security-guidance/hooks/security_reminder_hook.py](D:/codes/claude-code/plugins/security-guidance/hooks/security_reminder_hook.py#L1378)。

`agentic_review` 借助 Claude Agent SDK 的 `query` 让模型读周边代码，产生候选，再通过反证阶段尝试排除已有保护、非新增问题等误报。配置中有 `allowed_tools=[Read,Grep,Glob]`、`setting_sources=[]` 和轮数限制；不能把 `allowed_tools` 单独解释为从宿主彻底移除其它工具的白名单，应结合 SDK 权限语义理解。

这条路径包含回退与竞速，不应画成无条件串行单路。若 Agent SDK 不可用或调查失败，调用者可以回退到普通 diff 分析。源码参数可改变调查轮数、筛选模式和是否反证，因此“每次必定完成两阶段”也不是保证。

[plugins/security-guidance/hooks/review_api.py](D:/codes/claude-code/plugins/security-guidance/hooks/review_api.py#L291) 展示软过滤思想：把候选标为 `in_diff` 或 `off_diff` 并排序，而不直接丢掉后者。修改调用方或删除保护时，漏洞位置可能在未修改行；仅凭行号交集硬过滤会漏报。`llm.py` 当前仍内联了部分类似逻辑，不能仅凭 review_api 的模块说明宣称所有辅助函数都被入口复用。

## 6. 有限预算、去重与实际副作用

| 控制 | 代码中的值/行为 | 解释边界 |
|---|---|---|
| Stop 轮数 | `MAX_STOP_HOOK_FIRINGS` 默认 3，0 表示无限制 | 是插件反馈预算，不是主任务轮数 |
| Stop 文件数量 | `MAX_DIFF_FILES` 默认 30；超过十倍时跳过，中间范围挑选优先文件 | 有选择和遗漏，不是全量安全证明 |
| 载荷长度 | `DIFF_PER_FILE_BYTES`、`DIFF_TOTAL_BYTES` | 名称写 bytes，但当前部分函数对 Python 字符串用 len/切片，单位应实测 |
| 结果等级 | `analyze_code_security` 保留 critical/high/medium | 附近 high/critical 注释已不完全对应代码 |
| 重复反馈 | 状态记录与 late dedup（输出前去重） | 减少重复提醒，不等于全系统恰好一次 |

源码：[plugins/security-guidance/hooks/security_reminder_hook.py](D:/codes/claude-code/plugins/security-guidance/hooks/security_reminder_hook.py#L177)、[plugins/security-guidance/hooks/review_api.py](D:/codes/claude-code/plugins/security-guidance/hooks/review_api.py#L31)、[plugins/security-guidance/hooks/llm.py](D:/codes/claude-code/plugins/security-guidance/hooks/llm.py#L972)。

`git commit && git push` 可同时命中两个 Hook 配置。入口通过 `tool_use_id` 去重，并优先 commit 分支；该复合调用不会同时执行 push sweep，后续独立 push 才可能补审。见 [plugins/security-guidance/hooks/security_reminder_hook.py](D:/codes/claude-code/plugins/security-guidance/hooks/security_reminder_hook.py#L2082)。这是具体行为，不能用“所有 push 都完成范围补审”概括。

副作用包括读取工作区与 Git、写插件状态、在满足配置条件时向模型端发送审查内容、注入反馈。本次只静态检查并做纯函数实验，未启动该完整流程。

## 7. 从源码提炼出的设计建议

先保存基线，再发现变更；先产生候选，再要求证据；先区分暂时失败与永久跳过，再决定恢复待审工作。每个阶段都应记录覆盖范围，避免将“没有返回 findings”解释成“全仓安全”。

改进跨平台生产实现时，优先补状态锁与原子替换、载荷单位统一、跳过原因和覆盖率观测。这些是从当前代码限制推导的建议，不是已经提交的修复。

## 8. 复习问题

1. Stop 与 commit 审查为什么不能画成同一条模型调用链？
2. 为什么文件集合与 diff 正文需要不同基线？
3. Windows 无锁分支对“原子检查并标记”这个函数名有什么影响？
4. 为什么 off_diff 不能直接等同于误报？
