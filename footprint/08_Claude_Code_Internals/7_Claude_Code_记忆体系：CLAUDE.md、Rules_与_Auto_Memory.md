# 08.07 Claude Code 记忆体系：CLAUDE.md、Rules 与 Auto Memory

## 1. 先给结论

当前官方文档确认 Claude Code 有两类跨会话知识机制：

| 机制 | 主要作者 | 适合内容 | 主要加载方式 |
|---|---|---|---|
| `CLAUDE.md` / `CLAUDE.local.md` / `.claude/rules/` | 用户、团队或组织 | 明确规则、项目约定、工作流、架构说明 | 按作用域在启动时或读取匹配路径时加入上下文 |
| Auto memory | Claude | 在使用中发现的构建命令、调试经验、架构笔记、风格偏好和工作习惯 | `MEMORY.md` 索引常驻一部分，主题文件按需读取 |

两者都是**上下文**，不是硬约束：

```text
记忆/规则文件 → 作为模型输入影响决策
权限/Hook/沙箱 → 在执行层强制约束行为
```

若一条规则必须无条件阻止危险操作，应使用权限、Hook 或沙箱，不能只写进 `CLAUDE.md`。

## 2. “LLM 无状态”需要准确表述

一次普通模型 API 调用不会自动读取上一次调用的隐藏状态。跨轮连续性来自调用方再次提供：

- 历史消息；
- 已保存的会话；
- 文件内容与工具结果；
- 项目规则；
- Auto memory；
- 压缩摘要或服务端管理的会话状态。

所以“模型无状态”适合作为 API 心智模型，但不应夸张成“整个产品没有状态”。Claude Code 在模型外维护了会话 transcript、文件系统、任务状态、规则和记忆目录。

```text
模型调用本身：由本次输入决定
Claude Code 产品：持久化并重新组织多种状态
```

## 3. `CLAUDE.md` 的作用域与加载

### 3.1 启动目录及祖先目录

Claude Code 从当前工作目录向上查找 `CLAUDE.md` 和 `CLAUDE.local.md`。发现的内容不是互相覆盖，而是拼接进入上下文：

```text
较远祖先目录规则
    ↓
较近目录规则
    ↓
当前目录规则
    ↓
同层 CLAUDE.local.md
```

越接近启动目录的内容越晚出现，但“后出现”不等于程序化覆盖。冲突规则仍由模型解释，结果不具备配置系统那样的确定性。

### 3.2 子目录规则按需加载

当前工作目录以下的嵌套 `CLAUDE.md` 不会全部在启动时灌入。Claude 读取该子目录中的文件时，相应规则才进入消息历史。

这适合 monorepo：

```text
repo/CLAUDE.md                 # 全仓通用
repo/frontend/CLAUDE.md        # 读取前端文件时加载
repo/backend/CLAUDE.md         # 读取后端文件时加载
```

### 3.3 `.claude/rules/`

大型项目可以把规则拆成多个 Markdown 文件。带 `paths:` frontmatter 的规则只在匹配文件路径时加载：

```yaml
---
paths:
  - "src/**/*.tsx"
  - "src/**/*.jsx"
---

# React 规则

- Hooks 只能在组件或自定义 Hook 顶层调用。
```

这减少不相关规则占用上下文，但带来一个压缩边界：路径规则进入消息历史后可能在 compact 中被摘要掉，直到再次读取匹配文件才重新加载。

### 3.4 组织级、用户级、项目级和本地级

当前官方文档公开的主要来源包括：

| 作用域 | 典型位置或机制 | 用途 |
|---|---|---|
| Managed | 系统级 managed `CLAUDE.md` 或 managed settings 的 `claudeMd` | 组织统一行为指导 |
| User | `~/.claude/CLAUDE.md`、`~/.claude/rules/` | 跨项目个人偏好 |
| Project | 仓库中的 `CLAUDE.md`、`.claude/CLAUDE.md`、`.claude/rules/` | 团队共享规则 |
| Local | `CLAUDE.local.md`、本地 settings | 不提交的机器或个人约定 |

博客将这些来源总结成“六层”有助于理解，但具体层数取决于把 managed、user、project、local、rules、auto memory 如何分组。当前官方文档更稳定的表达是“多作用域规则 + 独立 Auto memory”，不要把“恰好六层”当作永久架构契约。

## 4. `@` 导入与拆分边界

`CLAUDE.md` 可以导入其它文件，便于复用共享规范。导入主要解决组织问题：

```text
一个入口文件
  ├─ 导入安全规范
  ├─ 导入测试规范
  └─ 导入发布流程
```

但导入文件仍会进入上下文，并不会因为拆成多个文件自动减少 token。真正减少启动上下文应使用：

- 路径作用域规则；
- Skills 按需加载；
- 精简 `CLAUDE.md`；
- 将确定性检查移到 Hook、lint、测试或权限系统。

当前导入规则还有两个重要边界：

- 相对路径以包含 `@path` 引用的文件所在目录为基准，递归导入最多四层；
- 项目级规则首次导入工作目录之外的文件时会要求用户确认，避免仓库中的规则静默读取外部路径。

## 5. Auto memory 的当前公开存储模型

每个项目拥有独立记忆目录：

```text
~/.claude/projects/<project>/memory/
├── MEMORY.md
├── debugging.md
├── api-conventions.md
└── ...
```

在 Git 仓库中，项目标识基于仓库，因此同一仓库的子目录和 worktree 默认共享 Auto memory。它是本机状态，不会自动同步到其它机器或云环境。

`MEMORY.md` 是入口索引。当前官方规则是：

```text
启动时加载：
  MEMORY.md 前 200 行
  或前 25KB
  先达到哪个限制就以哪个为准

按需加载：
  debugging.md、api-conventions.md 等主题文件
```

Claude Code 会提示 Claude 保持索引简洁：每项尽量一行，把细节移入主题文件，合并或删除过时条目。超限写入可以成功，但超出加载限制的部分在下次启动不会进入上下文。

`200 行` 是 `MEMORY.md` 的启动加载硬边界，不应与官方对 `CLAUDE.md` 的“建议控制在 200 行以内”混淆：`CLAUDE.md` 会完整加载，200 行只是提高遵循度和减少 token 的写作建议。

Auto memory 目录可通过 `autoMemoryDirectory` 改写。当前文档允许从不同 settings scope 提供该值；若来自项目或本地 settings，则必须先通过 workspace trust，不能沿用旧版“项目级设置永远不接受”的结论。

### 5.1 Subagent 的记忆与主会话记忆

普通非 Fork Subagent 不会自动加载主会话 Auto memory。自定义 Subagent 可用 frontmatter 的 `memory: user | project | local` 获得自己的持久记忆；若全局关闭 Auto memory，该字段也不会生效。Fork Subagent 因继承完整主会话上下文而是例外。

## 6. “索引常驻 + 内容按需”是可靠的通用原则

博客最值得保留的抽象是：

```text
小索引：告诉模型有什么、去哪里找
大正文：只有真正需要时再读取
```

它解决：

- 全量加载会挤占上下文；
- 完全不加载又让模型不知道记忆存在；
- 纯语义检索不易审计；
- Markdown 可直接查看、修改、删除和版本管理。

但需要修正“索引始终在 system prompt 中”的表述。官方文档明确说明 `CLAUDE.md` 内容以 system prompt 之后的 user message 形式交付；Auto memory 的精确消息角色和内部包装不是稳定公共接口。对使用者而言，可靠结论只是“索引会加载进上下文”。

## 7. 当前官方文档没有承诺“四类记忆 + Sonnet top-5”

博客基于特定构建还原，描述了一套：

```text
user / feedback / project / reference 四种类型
每条记忆一个带 frontmatter 的文件
后台 extractMemories Agent
Sonnet 从候选中选择 top-5
两天后注入 stale 警告
```

截至本次整理，当前官方 Claude Code Memory 文档并未把这些内容列为公共契约。相反，官方当前明确说明：

- Auto memory 可以保存 build commands、debugging insights、architecture notes、code style preferences、workflow habits；
- `MEMORY.md` 是简洁索引，主题文件由 Claude 自行组织；
- Claude 在会话中直接读取和写入记忆文件；
- 带 frontmatter 的记忆文件在较新版本中可记录 `modified` 时间；
- 官方没有承诺固定四种 `type`；
- 官方没有承诺一定运行独立抽取 Agent；
- 官方没有承诺固定使用 Sonnet；
- 官方没有承诺每次只选 top-5；
- 官方没有承诺“两天即 stale”的固定阈值。

因此博客描述可能代表某个实验分支、旧版或未公开构建，不能直接用于判断当前发行版。

## 8. 博客中“不要保存代码与架构信息”的说法已不适合作为当前规则

博客的版本还原称 Auto memory 不应保存：

- 代码模式与架构；
- 文件路径与项目结构；
- 调试方案；
- Git 历史；
- 临时状态。

其中“动态事实应优先从权威源验证”仍然成立：

```text
当前代码 → 读文件 / Grep / LSP
当前提交 → git log / git blame
当前任务 → 任务注册表
```

但当前官方文档明确把 debugging insights、architecture notes 和 build commands 列为 Auto memory 的典型内容。因此不能再写成“Claude Code 明确禁止保存架构和调试信息”。

更稳妥的工程规则是：

> 可以记住稳定、难以重新发现、未来有用的知识；对于易变的路径、行号、分支状态和临时任务进度，应在使用前从代码、Git 或任务系统重新验证。

## 9. 记忆不是向量数据库的反面

Claude Code 当前公开的本地记忆体系以 Markdown 和按需文件读取为主，官方未公开声明使用向量数据库。这个设计适合：

- 单仓库或单项目；
- 记忆规模可控；
- 需要人类审计与手工编辑；
- 规则、命令、偏好等高精度信息；
- 可以通过索引和文件名找到主题。

但不能由此推出“向量数据库对 Agent memory 无用”。向量或混合检索仍适合：

- 数量远超人工索引能力的记忆；
- 跨仓库、跨团队、跨文档库；
- 用户使用模糊自然语言而不知道关键词；
- 需要语义召回后再重排；
- 已经有权限过滤、版本管理和评估体系。

选择关键不是“文件还是向量”二选一，而是：

```text
候选规模
检索精度
更新频率
审计需求
权限边界
维护成本
失败代价
```

常见组合是：

```text
小型权威索引 + 精确文件读取
              +
大规模语义召回 + 元数据过滤 + 重排
```

## 10. 写入质量比召回算法更先决定上限

无论是否使用 embedding，记忆系统都应先解决写入治理：

1. 这条信息未来是否仍有用？
2. 它是否能从代码、Git、配置或任务系统低成本重新获得？
3. 它的作用域是用户、仓库、子目录还是一次任务？
4. 谁可以读取和修改？
5. 什么时候过期，怎样验证？
6. 与已有记忆冲突时如何合并？
7. 是否包含 secret、个人信息或不应持久化的内容？

“垃圾进，垃圾出”不因换成向量数据库或 LLM 选择器而改变。

## 11. 时间感知与主动验证

当前官方文档从 v2.1.214 起，为带 YAML frontmatter 的 Auto memory 文件维护 `modified` 时间。Claude Code 只更新已经存在 frontmatter 的文件，不会为原本没有 frontmatter 的文件自动添加整个 frontmatter。这为时效判断提供信号，但“多旧算过期”仍取决于内容类型：

| 内容 | 典型半衰期 |
|---|---|
| 用户偏好的回复风格 | 较长 |
| 构建命令 | 中等，依赖工程变更 |
| 当前分支路径或发布日期 | 很短 |
| 架构决策及原因 | 较长，但应对照 ADR/代码 |
| 临时调试结论 | 短到中等 |

使用记忆前的可靠顺序：

```text
读取记忆
  ↓
识别内容类型和修改时间
  ↓
若涉及可变事实，查询当前权威源
  ↓
使用、更新或删除旧记忆
```

“两天统一警告”是易懂的实现示例，不是适合所有记忆类型的通用过期策略。

## 12. 压缩之后什么会回来

当前官方 Context Window 文档说明：

| 内容 | Compact 之后 |
|---|---|
| System prompt / output style | 不属于消息历史，保持 |
| 项目根 `CLAUDE.md`、无作用域 rules | 从磁盘重新注入 |
| Auto memory | 从磁盘重新注入 |
| `paths:` 规则 | 直到再次读取匹配文件才重载 |
| 子目录嵌套 `CLAUDE.md` | 直到再次读取该目录文件才重载 |
| 已调用 Skill 正文 | 在预算内重新注入 |
| 只在早期对话中口头说过的规则 | 可能只剩摘要，可能丢失细节 |

所以长期规则应落到可重新加载的文件，而不是只依赖聊天早期的一句话。

Hook 本身不是一段要在消息历史中保留的上下文，但压缩完成后会触发 `SessionStart(source=compact)`；较新版本还提供 `PostCompact`。要调试规则究竟何时加载，可使用 `InstructionsLoaded` Hook 或 `/context`。

## 13. 安全与可审计性

Auto memory 是会被模型读取的持久化输入，需要按“项目数据”管理：

- 不写入 API key、token、密码和私钥；
- 不把外部不可信文本原样保存为高优先级规则；
- 定期通过 `/memory` 或文件系统审计；
- 对多人机器和敏感仓库检查目录权限；
- 不把“记忆写过”当成事实已验证；
- 对异常行为检查 `MEMORY.md`、主题文件和各层 `CLAUDE.md` 是否冲突。

Markdown 的优势是可见、可编辑，并不自动消除 prompt injection、过时信息或权限泄漏风险。

## 14. 一套可迁移的记忆架构

```text
权威规则层
  ├─ 组织策略
  ├─ 项目 CLAUDE.md
  └─ 路径作用域 rules

学习记忆层
  ├─ 小型 MEMORY.md 索引
  └─ 按主题拆分的详细文件

当前事实层
  ├─ 文件系统 / Grep / LSP
  ├─ Git
  ├─ 数据库 / 工单 / CI
  └─ 运行时任务注册表

执行约束层
  ├─ permissions
  ├─ hooks
  └─ sandbox
```

各层不能互相替代：

- 记忆告诉 Agent 过去学到了什么；
- 当前事实源告诉 Agent 现在是什么；
- 执行约束决定 Agent 实际能做什么。

## 15. 参考资料与事实边界

### 官方资料

- [Claude Code Memory](https://code.claude.com/docs/en/memory)
- [Claude Code Context Window](https://code.claude.com/docs/en/context-window)
- [Claude Code 工作机制](https://code.claude.com/docs/en/how-claude-code-works)
- [Claude Code Hooks](https://code.claude.com/docs/en/hooks)
- [Claude Code Permissions](https://code.claude.com/docs/en/permissions)

### 本次梳理的博客

- 记忆机制：`https://xiaolinnote.com/claudecode/source/cc_memory.html`

当前官方文档可以确认 `CLAUDE.md`、rules、Auto memory、`MEMORY.md` 的 200 行/25KB 加载限制、主题文件按需读取、项目级存储和 compact 后重注入。四种固定类型、独立抽取 Agent、Sonnet top-5、两天 stale 阈值来自博客所依据的特定实现还原，不能当作当前稳定事实。

## 16. 复习检查问题

1. `CLAUDE.md` 与 Auto memory 的作者、作用和加载方式有什么区别？
2. 为什么记忆文件不能替代权限、Hook 和沙箱？
3. `MEMORY.md` 为什么适合做索引而不是堆放全部正文？
4. 博客中的“四类记忆 + Sonnet top-5”为什么不能写成当前公共契约？
5. 为什么“当前代码在哪里”应优先从文件和 Git 验证？
6. Markdown 记忆与向量检索分别适合什么规模和场景？
