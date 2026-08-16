# 08.08 Claude Code Skills：发现预算、调用控制与安全边界

> **源码审查更正（2026-08-15）**：当前 `anthropics/claude-code` GitHub 仓库公开的是插件、示例和维护脚本，不含 Claude Code CLI/harness 的完整实现。本篇只能把官方 Skills、Tools、Permissions 与 Hooks 文档列为当前产品行为的证据。`description + when_to_use` 的 **1,536 字符截断**、`disable-model-invocation`、`user-invocable` 和 `allowed-tools` 有公开文档依据；下文关于 `skillListingBudgetFraction`、`skillOverrides`、按调用频率移除描述、`/doctor` 的 listing 计费，以及 `SLASH_COMMAND_TOOL_CHAR_BUDGET` 的结论，没有在当前公开仓库或官方 Skills 文档中得到验证，不得作为当前配置接口或稳定运行机制使用。应改写为“特定构建的逆向线索，待以目标版本实测验证”。

## 1. 一句话定位

Claude Code 中的 Skill 有两个不同阶段：

```text
发现阶段
名称 + description/when_to_use 进入 Skill listing
        ↓ Claude 或用户决定调用
调用阶段
完整 SKILL.md 正文及所需资源进入当前任务上下文
```

默认情况下，Skill 正文不会因为文件存在就全部常驻上下文。模型先根据 listing 中的元数据发现 Skill，调用后才加载正文。

### 1.1 预算判断发生在请求组装之前

Skill listing 的长度判断属于 prompt/context assembly 的预处理，不是把原始列表发送给模型后再让模型压缩：

```text
扫描可用 Skills
    ↓
读取 frontmatter：name / description / when_to_use
    ↓
应用单项 description 上限
    ↓
构造候选 listing 并计算总字符数
    ├── 未超预算：直接采用
    └── 超预算：按使用频率降级 description，名称保留
    ↓
把最终 listing 组装进模型上下文
    ↓
发送 API 请求
```

因此模型从一开始看到的就是裁剪后 listing，并不知道某段 description 原本多长。`/context` 的 Skills 行显示预算应用后的实际大小，这也与该执行顺序一致。

这与会话进行一段时间后触发的 auto-compaction 是两套机制：前者压缩“待暴露的能力索引”，后者清理或摘要“已经进入历史的对话和工具结果”。压缩后 Skill 正文的重挂载规则详见 `04_Claude_Code_上下文压缩、Microcompact_与状态恢复.md`。

### 1.2 `Skill` tool 是按需加载器

Claude Code 使用现有的内置 `Skill` tool 运行 Skill，而不是为每个 Skill 新增一个独立工具 schema：

```text
最终 Skill listing 进入上下文
    ↓
LLM 根据 name + description 做语义路由
    ↓
tool call：Skill(code-review)
    ↓
Claude Code 找到 SKILL.md
    ↓
展开 $ARGUMENTS、命名参数和动态上下文
    ↓
渲染后的完整 Skill 作为一条消息进入会话
    ↓
LLM 按指令调用 Read / Grep / Bash / MCP 等真实工具
```

`Skill` tool 通常不直接执行 Skill 的业务逻辑。对于代码审查 Skill，它负责加载审查流程；真正的读取、搜索、测试和报告仍由模型调用普通工具完成。整个架构可概括为：

```text
轻量 Skill 索引
  + LLM 路由
  + Skill tool 按需加载
  + 普通工具执行
```

Skill 被调用后，渲染正文会留在会话上下文中，后续轮次不会每次重新读取磁盘文件。相同渲染内容被再次调用时，较新版本只添加“已加载”提示；参数或动态上下文变化导致渲染内容不同，才会追加新正文。auto-compaction 后则按“每项最多 5,000 tokens、合计 25,000 tokens、最近调用优先”重新挂载。

## 2. 单项上限与总 listing 预算是两层限制

当前官方配置把限制分成两层：

| 限制 | 默认值 | 当前配置 |
|---|---:|---|
| 单个 Skill 的 `description + when_to_use` 上限 | 1,536 字符 | `skillListingMaxDescChars` |
| 所有 Skill listing 的总预算 | 模型上下文窗口的 1% | `skillListingBudgetFraction` |

早期版本曾使用 250 字符上限，不能再把它写成当前默认值。还要特别纠正一个易混配置名：

```text
正确：skillListingMaxDescChars
错误：maxSkillDescriptionChars
```

示例：

```json
{
  "skillListingBudgetFraction": 0.02,
  "skillListingMaxDescChars": 1024
}
```

两层限制彼此独立。即使每个描述都没有达到单项上限，Skill 数量足够多时，总 listing 仍可能超过预算。

## 3. 总预算溢出时怎样降级

当 listing 超过总预算时，Claude Code 不会随机删除整个 Skill，也不会把完整 `SKILL.md` 都提前塞进上下文。当前官方行为是：

1. 所有 Skill 名称仍保留；
2. 从调用最少的 Skill 开始移除描述；
3. 被降级的条目只剩名称；
4. 直到 listing 回到预算以内。

```text
高频 Skill：name + description
低频 Skill：name only
```

只剩名称时，Claude 仍可能调用该 Skill，但自动匹配能力会下降。名称如果过于模糊，例如 `db-helper`，模型很难判断它究竟用于死锁、迁移还是查询优化。

可以用 `/doctor` 估算 listing 成本和主要贡献者；超预算时也会写入 debug 日志。`/context` 中的 Skills 行显示预算应用后模型实际收到的 listing 大小。

固定字符预算还可以通过环境变量覆盖：

```bash
export SLASH_COMMAND_TOOL_CHAR_BUDGET=16000
```

PowerShell：

```powershell
$env:SLASH_COMMAND_TOOL_CHAR_BUDGET = "16000"
```

## 4. 主动控制可见性

不希望完全交给使用频率决定时，可以在设置中使用 `skillOverrides`：

```json
{
  "skillOverrides": {
    "legacy-context": "name-only",
    "production-deploy": "user-invocable-only",
    "obsolete-helper": "off"
  }
}
```

| 状态 | Claude listing | `/` 菜单 |
|---|---|---|
| `on` | 名称和描述 | 显示 |
| `name-only` | 仅名称 | 显示 |
| `user-invocable-only` | 隐藏 | 显示 |
| `off` | 隐藏 | 隐藏 |

`skillOverrides` 不适用于插件 Skill；插件应通过插件管理入口控制。

## 5. `disable-model-invocation` 与 `user-invocable`

这两个字段写在 `SKILL.md` 顶部的 YAML frontmatter 中：

```yaml
---
name: production-deploy
description: Deploy the service to production
disable-model-invocation: true
user-invocable: true
---

按照部署清单执行，并在每个外部副作用前检查权限。
```

| 配置 | 用户可调用 | Claude 可自动调用 | listing 行为 |
|---|---:|---:|---|
| 默认 | 是 | 是 | 名称和描述常驻 |
| `disable-model-invocation: true` | 是 | 否 | 对 Claude 隐藏 |
| `user-invocable: false` | 否 | 是 | 对 Claude 可见 |

`user-invocable: false` 只控制用户侧命令入口，不会阻止 Skill 工具访问。阻止模型程序化调用应使用 `disable-model-invocation: true`，或在权限中拒绝对应 Skill：

```text
Skill(deploy)
Skill(deploy *)
```

前者精确匹配无参数调用，后者匹配带参数调用。

## 6. 为什么这些字段不是“依赖模型自觉”的软提示

需要区分三类约束：

| 约束 | 执行者 | 确定性 |
|---|---|---|
| frontmatter 可见性与调用控制 | Claude Code 宿主程序 | 结构化、确定性 |
| `description` 的相关性匹配 | 模型 | 软判断 |
| `SKILL.md` 正文中的操作说明 | 模型 | 软指令 |

Claude Code 会先解析 frontmatter，再构造 listing、`/` 菜单和 Skill 工具可用范围。`disable-model-invocation: true` 的含义不是：

```text
把 deploy 展示给模型，再请求模型不要调用
```

而是：

```text
不把 deploy 暴露给模型的自动调用路径
```

真正依赖模型理解的是“什么时候相关”和“加载后如何执行”，不是宿主是否展示该 Skill。

## 7. 调用控制不等于完整安全边界

即使模型不能调用部署 Skill，只要它仍有 Bash、MCP 或云平台工具权限，就可能绕过 Skill，直接执行等价操作：

```text
Skill(deploy) 被禁止
        │
        └── Bash("kubectl apply ...") 仍可能可用
```

因此高风险操作应分层控制：

```text
Skill 调用控制
      ↓
工具权限 deny/ask
      ↓
PreToolUse Hook 校验
      ↓
沙箱、云 IAM、数据库账号等底层权限
```

示例：

```json
{
  "permissions": {
    "deny": [
      "Skill(production-deploy)",
      "Skill(production-deploy *)",
      "Bash(kubectl apply *)",
      "Bash(terraform apply *)"
    ],
    "ask": [
      "Bash(git push *)"
    ]
  }
}
```

复杂业务规则可在 `PreToolUse` Hook 中读取工具名和参数，并返回 `permissionDecision: "deny"`。这种拒绝由宿主在工具执行前实施，不依赖模型同意。

还有两个容易误解的字段：

- `allowed-tools` 是 Skill 激活期间的临时预授权，不是“只允许这些工具”的白名单；
- 需要在 Skill 激活期间移除工具时，使用 `disallowed-tools`；需要跨 Skill、跨提示持续阻止时，使用全局或项目权限 deny 规则。

## 8. 设计建议

1. 名称要能独立表达用途，因为预算溢出后可能只剩名称；
2. 在描述开头放最关键的使用场景和触发词；
3. 只需人工调用的工作流使用 `disable-model-invocation: true`；
4. 背景知识型 Skill 可使用 `user-invocable: false`；
5. 低优先级条目主动设为 `name-only`，不要等预算自动降级；
6. 高风险副作用同时限制 Skill 入口和底层工具；
7. 用 `/doctor`、`/context`、debug 日志和真实触发样例验证配置，而不是只检查 YAML 是否能解析。

## 9. 常见误区

- **误区：每个描述未超过上限，总 listing 就一定不会溢出。** 单项上限和总预算是两层限制。
- **误区：当前默认描述上限仍是 250 字符。** 当前默认是 1,536 字符。
- **误区：`maxSkillDescriptionChars` 是当前配置名。** 当前设置文档使用 `skillListingMaxDescChars`。
- **误区：描述被移除后 Skill 就被删除。** 名称仍保留，主要损失是自动发现线索。
- **误区：`user-invocable: false` 会阻止 Claude 调用。** 它只控制用户入口。
- **误区：`allowed-tools` 会限制其它工具。** 它负责预授权，不负责移除。
- **误区：禁止自动调用 Skill 就能阻止底层副作用。** 模型可能通过其它工具走到同一能力，仍需权限、Hook 和基础设施权限。
- **误区：先把原始 Skill listing 发给模型，再由模型压缩。** 单项截断和总预算降级发生在请求上下文组装之前。
- **误区：每个 Skill 都会新增一个独立工具定义。** Claude Code 通过共同的内置 `Skill` tool 按名称加载 Skill。
- **误区：`Skill(name)` 会直接执行该任务的业务代码。** 它主要加载渲染后的指令包，随后仍由模型编排普通工具完成工作。
- **误区：调用后每一轮都会重新读取最新 `SKILL.md`。** 已渲染正文留在会话中；磁盘修改不会自动改写已加载的那一份。

## 10. 关联知识点

- `../02_Agent_RAG_Memory/05_Agent_Skills_模块化能力扩展.md`
- `01_Claude_Code_Prompt_前缀缓存与三级上下文.md`
- `04_Claude_Code_上下文压缩、Microcompact_与状态恢复.md`
- `06_Claude_Code_Agent_Loop、Query_生命周期与工具编排.md`
- `../07_Backend_Deploy_Network/08_沙箱、权限与工具执行安全.md`

## 11. 参考资料与事实边界

- [Claude Code Skills 官方文档](https://code.claude.com/docs/en/slash-commands)
- [Claude Code Settings 官方文档](https://code.claude.com/docs/en/settings)
- [Claude Code Permissions 官方文档](https://code.claude.com/docs/en/permissions)
- [Claude Code Hooks 官方文档](https://code.claude.com/docs/en/hooks)
- [Claude Code Tools Reference](https://code.claude.com/docs/en/tools-reference)
- 本次整理来源：[技术问题解答准则分享对话](https://chatgpt.com/share/6a69fbe0-2524-83ec-b330-b1326ce3d368)

具体默认值、字段名和版本条件属于产品行为，后续升级时应以官方 Settings 与 Skills 页面为准；文中的调用链是对公开行为的机制化表达，不等于 Anthropic 公开了完整内部源码。
