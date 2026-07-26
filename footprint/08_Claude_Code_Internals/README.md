# Claude Code 源码与机制解读

本专题从 Agent Harness 工程视角理解 Claude Code，重点关注 Agent Loop、上下文组织、Prompt Cache、代码检索、流式协议、输出上限、上下文压缩、状态恢复、项目记忆、Subagent 通信与 Agent Teams。

知识点文件数：7

> 审查基线：2026-07-26；Claude Code 最新公开发行版为 v2.1.220。
> 版本事实优先依据 Anthropic 官方文档、官方 GitHub release feed 与官方 Agent SDK 类型；第三方 source map / 反编译仅用于解释特定构建。

## 文件列表

- [Claude Code Prompt 前缀缓存与三级上下文](001_Claude_Code_Prompt_前缀缓存与三级上下文.md)
- [Claude Code 流式输出、max_tokens 与恢复机制](002_Claude_Code_流式输出、max_tokens_与恢复机制.md)
- [Claude Code 代码检索：ripgrep 与 grep](003_Claude_Code_代码检索：ripgrep_与_grep.md)
- [Claude Code 上下文压缩、Microcompact 与状态恢复](004_Claude_Code_上下文压缩、Microcompact_与状态恢复.md)
- [Claude Code Subagent、Agent Teams、Coordinator Mode 与状态机](005_Claude_Code_Subagent、Agent_Teams、Coordinator_Mode_与状态机.md)
- [Claude Code Agent Loop、Query 生命周期与工具编排](006_Claude_Code_Agent_Loop、Query_生命周期与工具编排.md)
- [Claude Code 记忆体系：CLAUDE.md、Rules 与 Auto Memory](007_Claude_Code_记忆体系：CLAUDE.md、Rules_与_Auto_Memory.md)

## 建议阅读顺序

```text
006 Agent Loop：先建立整个 Harness 骨架
  ├─ 001 Prompt Cache：理解多轮请求为什么要保持稳定前缀
  ├─ 003 代码检索：理解 Agent 怎样获得代码证据
  ├─ 002 流式与恢复：理解单次模型响应怎样收尾
  ├─ 004 上下文压缩：理解长循环怎样控制上下文
  ├─ 007 Memory：理解跨会话知识怎样加载和校验
  └─ 005 Multi-Agent：理解一个循环怎样委派给其它循环
```

## 阅读边界

- Anthropic 官方文档明确说明的 API 协议和 Claude Code 行为，作为稳定结论记录。
- Anthropic 官方 SDK 仓库、类型定义与 changelog 可验证宿主可观察的消息、事件和配置，但仍不等于公开了 Claude Code CLI 的全部内部实现。
- 官方 release feed 用于确认“某版本新增、修改或修复了什么”。当功能页尚未同步最新版本时，以更新日期更晚且表述明确的 release note 为当前版本基线，并在正文保留版本条件。
- 从特定版本源码、source map 或第三方源码解读得到的实现细节，会明确标注“版本相关”，不把常量、重试次数等当作永久契约。
- Claude Code 当前核心发行物并非完整开源。博客中的 `query.ts`、内部类名、feature gate、行数和常量来自特定构建/source map 还原，不能冠以“当前官方源码保证”。
- 本专题中的 Prompt Cache 指模型服务端的前缀计算缓存，不等同于 Claude Code 本地会话文件、Memory 或语义缓存。
- Claude Code CLI 内部压缩机制与 Claude API 公开的 Compaction / Context Editing 是相关但不同的层次，不根据相似字段名推断二者实现完全相同。
- Agent Teams 是官方公开的实验功能；内部 `COORDINATOR_MODE` 的 feature gate、专用 prompt 与工具白名单属于版本相关实现，不将二者混写为同一个稳定功能。
- 博客中的“四种 Auto memory 类型、Sonnet top-5、两天 stale 警告”没有出现在当前官方 Memory 契约中；专题按当前 `MEMORY.md` 索引与主题文件机制记录，并保留博客方案作为版本相关线索。

## 证据等级

| 等级 | 可写成什么 | 典型来源 |
|---|---|---|
| A：公开契约 | 当前稳定或带明确版本条件的行为 | Anthropic 官方文档、Messages API |
| B：公开可观察实现 | SDK 类型、事件、配置、changelog 中可验证行为 | Anthropic 官方 SDK 仓库 |
| C：版本相关实现 | 只能说明某一构建的函数、常量、内部 prompt | source map、反编译或第三方还原 |
| D：设计推断 | 有解释力但不能当产品事实 | 博客类比、架构哲学、作者猜测 |

出现冲突时按 A → B → C → D 排序，并记录访问日期与版本条件。

## 阅读时先问三个问题

1. 这是 Claude API 的公共协议、Claude Code 的产品行为，还是某一构建的内部实现？
2. 结论是否带版本条件，官方功能页与更新更晚的 release note 是否一致？
3. 这是模型可遵循的上下文，还是权限、Hook、沙箱等宿主强制约束？

这三个问题贯穿全部文档，可避免把相似概念混为一层：

```text
Claude API 协议
    ↓ 被 Claude Code / Agent SDK 使用
Claude Code Harness 行为
    ↓ 某个发行版的具体实现
内部函数、常量与持久化格式
```

## 六篇博客映射与主要修正

| 博客 | 主要归档位置 | 核验后的关键边界 |
|---|---|---|
| 源码架构 | 006、001、004、005 | “四层架构”“不使用 ReAct”等是解释模型；公共事实是 harness + tools + context + execution |
| Query Loop | 006、002 | 工具循环与流式协议可由官方验证；四层函数调用链、类名和代码行数是版本相关 |
| Compact | 004 | 先清理工具输出再摘要可确认；20K/13K/5 文件等固定值不是长期契约 |
| grep vs RAG | 003 | Claude Code Grep 当前明确基于 ripgrep；“不用 RAG”是场景选择，不是 RAG 普遍失效 |
| Memory | 007 | 当前官方机制是多作用域规则 + `MEMORY.md` 索引/主题文件；四类型、Sonnet top-5 等未成公共契约 |
| Multi-Agent | 005 | 区分 Subagent、Agent View 后台 session、Agent Teams 与内部 Coordinator Mode；Lead/Teammate/task list/mailbox 可确认，XML 与内部模式属于版本相关 |

## 核心权威入口

- [Claude Code 官方文档索引](https://code.claude.com/docs/llms.txt)
- [Claude Code 官方发行记录](https://github.com/anthropics/claude-code/blob/main/feed.xml)
- [Claude Agent SDK TypeScript 参考](https://code.claude.com/docs/en/agent-sdk/typescript)
- [Claude Messages API 文档](https://platform.claude.com/docs/en/api/messages)
