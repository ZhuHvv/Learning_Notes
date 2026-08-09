# 02.05 Agent Skills：模块化能力扩展

## 1. 总体性概念

Agent Skill 是一种模块化、可复用的能力扩展单元。它把完成某类任务所需的操作说明与配套资源放在一个目录中，使 Agent 能按统一入口发现并使用这项能力。

Skill 不是模型权重，也不等同于单个函数。它更像一个面向 Agent 的任务包：既可以描述工作流程，也可以提供确定性脚本、参考知识和可复用素材。

## 2. 典型目录结构

```text
skill-name/
├── SKILL.md       # 必需：用途、触发条件、工作流程与约束
├── scripts/       # 可选：可执行或可复用脚本
├── references/    # 可选：任务所需参考资料
└── assets/        # 可选：模板、图片等素材
```

- `SKILL.md` 是入口和任务指令集；
- `scripts/` 保存适合用程序稳定完成的步骤；
- `references/` 保存只在相关任务中按需读取的知识；
- `assets/` 保存生成结果时需要复用的模板或媒体资源。

## 3. 设计原则

1. 一个 Skill 聚焦一类边界明确的任务；
2. 明确何时使用、何时不要使用，避免与其他 Skill 重叠；
3. 把长篇背景资料与核心流程分离，减少无关上下文；
4. 能由脚本稳定完成的机械步骤优先复用脚本；
5. 在说明中写清输入、输出、失败处理和验证方法。

## 4. 与其他扩展机制的区别

- **Function Calling / Tool**：向模型暴露一个可调用动作，重点是函数 schema 和执行；
- **MCP**：规定应用如何发现和调用外部工具、资源、Prompt；
- **Agent Skill**：组织完成一类任务的方法和本地资源，可以在流程中调用 Tool 或 MCP 能力。

因此，Skill 处于任务方法层，Tool 处于动作层，MCP 处于外部能力接入协议层，三者可以组合使用。

## 5. 渐进式披露与按需加载

支持 Skill 的 Agent Runtime 通常不会在启动时把所有完整 `SKILL.md` 放进模型上下文，而是先暴露轻量的名称和描述，让模型或用户选中后再加载正文及相关资源：

```text
name + description → 发现与路由
完整 SKILL.md      → 调用后加载任务方法
references/assets  → 按任务需要继续读取
普通 Tool / MCP    → 执行真实动作
```

这能控制基础上下文成本，但具体 listing 预算、调用工具和压缩后恢复方式属于各宿主实现。Claude Code 的确定性规则和 `Skill` tool 机制统一维护在 `../08_Claude_Code_Internals/08_Claude_Code_Skills：发现预算、调用控制与安全边界.md`，本文件不重复产品细节。

## 6. 关联知识点

- `01_Prompt_工程：User_Prompt_与_System_Prompt.md`
- `03_Function_Calling_与_MCP_工具接入.md`
- `02_Agent_的端到端任务能力.md`
- `../08_Claude_Code_Internals/08_Claude_Code_Skills：发现预算、调用控制与安全边界.md`
