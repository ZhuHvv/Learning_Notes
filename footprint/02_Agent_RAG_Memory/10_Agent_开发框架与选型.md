# 02.10 Agent 开发框架与选型

## 1. 先按核心抽象分类

框架是否“热门”不是首要标准。更重要的是它把 Agent 系统中的哪一部分设为一等公民：

| 框架 | 核心抽象 | 更准确的定位 |
| --- | --- | --- |
| CrewAI | Agent + Task + Crew / Flow | 高层角色协作和任务编排 |
| AutoGen | Agent + Message + Runtime / Team | 多 Agent 对话与事件驱动运行时；新项目需留意维护状态 |
| MetaGPT | Role + SOP + Artifact | 软件研发等垂直 SOP 流水线 |
| LangGraph | State + Node + Edge | 有状态、可控制、可恢复的 Agent 工作流 |
| Agno | Agent Platform | 生产服务、存储、权限、调度和运营平台层 |
| OpenAI Agents SDK | Agent + Tools + Handoffs | OpenAI 生态内的轻量官方 Agent SDK |
| smolagents | CodeAgent | 用受控代码表达动作的轻量框架 |
| Mastra | Agent + Workflow + Tool | TypeScript / Node.js AI 应用框架 |
| Google ADK | Agent + Graph Workflow | Google / Gemini 生态的 code-first 开发套件 |
| Pydantic AI | Typed Agent / Workflow | Python 类型安全、结构化输出与可观测性 |
| Microsoft Agent Framework | Agent + Multi-agent Workflow | Python/.NET 的生产级 Microsoft Agent 框架 |

调研当时的生态信号如下。数字是带日期的快照，不代表当前值：

| 框架 | 2026-07-05 附近记录 | 适合场景 |
| --- | --- | --- |
| Agno | 约 41k stars；记录的最新 release 为 2026-07-03 | 公司级 Agent 平台 |
| OpenAI Agents SDK | 约 27.6k；2026-06-24 | OpenAI 工具、handoff、guardrail、session、tracing |
| smolagents | 约 28.2k；2026-05-29 | 研究、原型、代码执行型 Agent |
| Mastra | 约 25.8k；2026-07-01 | TypeScript / Next.js / Node.js |
| Google ADK | 约 20.5k；ADK 2.0 记录为 2026-06-18 | Gemini / Google Cloud 与图式 workflow |
| Pydantic AI | 约 18.2k；2026-07-04 | Python 后端、强 schema |
| Microsoft Agent Framework | 约 11.9k；2026-07-03 | Microsoft/Azure/.NET 或 AutoGen 迁移 |

## 2. CrewAI：角色协作与 Flow

CrewAI 把复杂任务拆成角色和任务，再由 Crew 或 Flow 编排：

- **Agent**：`role`、`goal`、`backstory`、tools、memory、delegation 等组成的执行单元；
- **Task**：带 description、expected output、负责 Agent 和上下文依赖的工作项；
- **Crew**：由多个 Agents 和 Tasks 构成的协作团队；
- **Flow**：管理状态、事件、分支和循环，并可调用 Crew 或普通函数。

```text
用户输入
  → Flow / Crew 接收任务
  → 按任务定义确定 Agent
  → Agent 带角色、目标、上下文和工具调用 LLM
  → LLM 回答或提出工具调用
  → 框架执行工具并写回 observation
  → 继续任务、委派或结束
```

### 2.1 “谁选择 Agent”取决于 Process

- `Process.sequential` 通常由开发者预先为 Task 指定 Agent，再按任务列表执行；不是模型运行时自由挑选角色；
- `Process.hierarchical` 由 manager agent 协调、委派并验证，更接近动态分工；
- delegation / planning 可以在执行中拆分或调整任务，但仍不等同于后端显式、可验证的状态机。

### 2.2 Crew 和确定性业务流程的边界

Crew 适合“调研 → 分析 → 写报告 → 审稿”这类目标导向协作。订单、风控、扣款、发券、记账等强事务流程应让 Flow 或后端状态机主导，只在适合的节点调用 Crew。

当分支必须稳定可审计时，可在 Flow 层用 `@router()`、`@listen()`、`and_()`、`or_()` 等机制显式表达条件路由，而不是只让 Agent 通过自然语言自行决定下一步。

原因包括：

1. Crew 的高层抽象主要表达角色、任务和输出传递，不会自动把每个业务状态、事件和转移条件显式建模；
2. LLM 决策受提示词、上下文、模型版本、采样和工具结果影响，不能替代稳定的 `if/else` 与审批条件；
3. replay / checkpoint 能帮助从任务边界恢复，但不会自动理解工具副作用、业务幂等键、补偿动作或分布式事务；
4. 生产排障需要主动保存 prompt、Agent 决策、tool schema、参数、结果、Task 输出、request id、token 用量和异常；
5. memory、cache、上下文裁剪、manager 决策等不确定因素，会放大只看最终输出时的复现成本。

CrewAI 提供 tracing、replay、checkpointing、event listeners 等能力，但应在项目开始时就启用并定义恢复语义。Tracing 可记录 Agent 决策、任务时间线、工具使用、LLM 调用、性能和错误，并可结合 AMP 或 Langfuse、MLflow、OpenTelemetry 等观测系统。原始调研记录指出：replay 依赖已执行的 kickoff 且当时只支持 latest kickoff；checkpointing 当时属于早期能力，默认在 task 完成后保存。具体行为应以项目所用版本文档为准。

实践建议：

- 简单调研、写作、运营分析：Crew 可主导；
- 条件分支、审批、重试和恢复：Flow 管骨架，Crew 做智能步骤；
- 写库、支付、发消息等副作用：工具层负责幂等、超时、重试、补偿和审计；
- 长任务：明确 checkpoint 粒度和恢复后上下文；
- 高风险动作：在 Flow 加 human-in-the-loop。

## 3. AutoGen：消息驱动的多 Agent Runtime

AutoGen 把 Agent 看成能相互发消息、使用工具、执行代码或请求人工输入的实体：

- **AgentChat**：AssistantAgent、团队、终止条件和工具调用等高层 API；
- **Core**：异步消息、runtime、topic、subscription，更接近 Actor 模型；
- **Extensions**：模型客户端、代码执行器、MCP、gRPC、Docker 等集成。

```text
用户消息 → Team / Runtime → Agent 响应或 tool call
→ 工具结果成为新消息 → Team 选择下一发言者
→ 满足 termination condition 后结束
```

CrewAI 更像角色分工与任务编排，AutoGen 更像多 Agent 消息系统。Core 提供更细控制，也要求开发者处理消息类型、订阅关系、runtime 和生命周期。原始调研记录 AutoGen 官方仓库当时已标注 maintenance mode，并推荐新项目评估 Microsoft Agent Framework；因此它仍适合学习多 Agent 对话、协商、代码执行、人类介入与事件运行时，但生产新项目应按当前官方状态重新确认 Microsoft Agent Framework、Semantic Kernel 等推荐方向。

## 4. MetaGPT：用 SOP 约束多 Agent

SOP（Standard Operating Procedure）把重复工作固定为步骤、角色、输入输出和检查规则。在 Agent 系统中，它用于避免多个 Agent 只进行低效自由聊天。

MetaGPT 把软件公司式流程编码为多 Agent SOP，典型角色包括 Product Manager、Architect、Project Manager、Engineer、QA / Reviewer：

```text
需求 → PRD → 系统设计 → 任务拆解 → 代码 → 测试/审查 → 项目工件
```

每一步应明确输入、结构化产物、交接方式和审查规则。其优势是软件研发角色与产物链路清楚，适合原型项目、需求分析、架构和代码草案；局限是场景垂直，真实生产代码仍需人工审查，不适合无人值守合并或强实时、强事务流程。

## 5. LangGraph：有状态图工作流

LangGraph 的核心是 stateful graph：

- **State**：messages、计划、工具结果、用户确认等共享状态；
- **Node**：LLM、工具、普通函数、子图或人工审核；
- **Edge / Conditional Edge**：固定或按状态跳转；
- **Checkpoint / Persistence**：暂停、恢复和重放；
- **Human-in-the-loop**：在关键节点中断并等待确认；
- **Streaming / Debugging**：观察中间状态和输出。

```text
初始输入写入 State → Node 读取并返回更新 → Reducer 合并
→ Edge 选择下一 Node → 可 checkpoint / 人工介入 → END
```

它适合复杂分支、多步骤工具调用、长任务、可恢复流程和明确状态转移。代价是必须设计 state、node、edge、reducer 和错误路径。具体的状态更新与流式调用见 `11_LangGraph_状态更新、invoke_与_stream.md`。

## 6. 新一代与生态型框架

### 6.1 Agno

Agno 更偏 Agent 平台层，而不只是 Agent 类：可把 Agent 逻辑作为生产 API 运行，持久化 session、memory、knowledge 和 traces，并接入 scheduling、RBAC、人工审批、OpenTelemetry、审计、多租户与 Slack/Telegram/WhatsApp/Discord 等界面。它允许底层使用不同 Agent framework。单个 demo 可能显得偏重，公司内部 Agent 平台更匹配。

### 6.2 OpenAI Agents SDK

核心抽象包括：

- Agent：instructions、tools、guardrails、handoffs；
- Tools：函数、MCP 工具、hosted tools；
- Handoffs：转交给更专门的 Agent；
- Guardrails：输入/输出检查；
- Sessions：跨 run 历史；
- Tracing：执行链路。

Runner 启动后，模型可直接回答、调用工具或 handoff，SDK 回填结果并记录 trace。它与 OpenAI 生态集成直接；若需要显式图状态与精细恢复，则应和 LangGraph 等图式框架对比。

### 6.3 smolagents

smolagents 强调“agents that think in code”。CodeAgent 用受控代码组合工具、变量、循环和条件，而传统 tool-calling Agent 通常输出离散 JSON 调用。复杂数据处理表达更紧凑，但代码执行必须配套 Docker、E2B、Modal、Blaxel 等隔离环境，以及文件、网络、权限、超时、资源和审计限制。

### 6.4 Mastra

Mastra 面向 TypeScript AI 应用，把 Agent、workflow、tool、eval 和 MCP 放进 Node.js / Next.js 工程，并可连接多种模型 provider。主技术栈是 TS 时更顺手；Python 团队可对比 LangGraph、Pydantic AI 或 OpenAI Agents SDK。

### 6.5 Google ADK

Google ADK 是 Google 的 code-first Agent Development Kit，用于构建、评估和部署 Agent。原始调研中的 ADK 2.0 包括图式 Workflow Runtime、routing、fan-out/fan-in、loop、retry、state、dynamic node、human-in-the-loop、nested workflow，以及用于结构化 agent-to-agent delegation 的 Task API。适合 Gemini、Vertex AI 和 Google Cloud 生态。

### 6.6 Pydantic AI

Pydantic AI 把类型约束、schema 校验、依赖注入和结构化输出带入 Python Agent / workflow，支持多模型与 provider，并通过 Pydantic Logfire / OpenTelemetry 做 tracing、成本跟踪、调试和评估。优势不是多 Agent 角色最多，而是让 LLM 输入输出更像可维护的后端接口，适合 FastAPI / Pydantic 项目。

### 6.7 Microsoft Agent Framework

Microsoft Agent Framework 是 AutoGen 的官方后继方向，面向 Python 和 .NET 的生产级 Agent 与 multi-agent workflow。适合 Azure OpenAI、Microsoft Foundry、GitHub Copilot SDK 集成，以及需要 graph pattern、durability、restartability、observability、governance 和 human-in-the-loop 的系统。

## 7. 综合比较

| 维度 | CrewAI | AutoGen | MetaGPT | LangGraph |
| --- | --- | --- | --- | --- |
| 抽象层级 | 高层 | 高层到低层 | 高层、垂直 SOP | 偏底层、强控制 |
| 协作方式 | 角色分工 | 消息对话 | 软件公司流水线 | 状态图执行 |
| 状态控制 | Flow 可控，Crew 较高层 | Core 层较强 | 依赖 SOP 与工件 | State 是一等公民 |
| 人工介入 | 流程层设计 | 支持 | 通常偏自动 | 核心能力之一 |
| 调试重点 | tracing + task/flow 状态 | 消息与 runtime | 产物链路 | state、checkpoint、stream |
| 最适合 | 业务型多角色原型 | 对话/事件驱动实验 | 需求到代码草案 | 生产级复杂流程 |

## 8. 选型决策

1. 快速做多角色业务原型：CrewAI；
2. 研究 Agent 协商、对话和消息运行时：AutoGen，但先确认维护状态；
3. 需求到软件项目草案：MetaGPT；
4. 生产级复杂状态图：LangGraph；Google 生态可对比 ADK；
5. Python 后端、强类型与 schema：Pydantic AI；
6. OpenAI 生态、轻量 SDK、tracing / handoff / guardrail：OpenAI Agents SDK；
7. TypeScript / Next.js / Node.js：Mastra；
8. 公司级 Agent 平台：Agno；
9. 代码执行研究与原型：smolagents，并先完成沙箱设计；
10. Microsoft / Azure / .NET 或 AutoGen 迁移：Microsoft Agent Framework。

最终还应检查：流程是否固定、是否多角色、状态控制精度、人工审批、失败恢复、幂等审计、技术栈、部署环境和维护周期。Agent 框架只是编排层；权限、事务、限流、重试、补偿、日志和监控仍属于后端工程体系。

## 9. 参考资料

1. [CrewAI Documentation](https://docs.crewai.com/introduction)
2. [CrewAI GitHub](https://github.com/crewAIInc/crewAI)
3. [CrewAI Sequential Process](https://docs.crewai.com/en/learn/sequential-process)
4. [CrewAI Flows](https://docs.crewai.com/en/concepts/flows)
5. [CrewAI Hierarchical Process](https://docs.crewai.com/en/learn/hierarchical-process)
6. [CrewAI Replay Tasks](https://docs.crewai.com/en/learn/replay-tasks-from-latest-crew-kickoff)
7. [CrewAI Checkpointing](https://docs.crewai.com/en/concepts/checkpointing)
8. [CrewAI Tracing](https://docs.crewai.com/en/observability/tracing)
9. [AutoGen Documentation](https://microsoft.github.io/autogen/stable/)
10. [AutoGen GitHub](https://github.com/microsoft/autogen)
11. [Microsoft Agent Framework Documentation](https://learn.microsoft.com/en-us/agent-framework/)
12. [Microsoft Agent Framework GitHub](https://github.com/microsoft/agent-framework)
13. [MetaGPT GitHub](https://github.com/geekan/MetaGPT)
14. [MetaGPT ICLR 2024 OpenReview](https://openreview.net/forum?id=VtmBAGCN7o)
15. [LangGraph Documentation](https://docs.langchain.com/oss/python/langgraph/overview)
16. [LangGraph GitHub](https://github.com/langchain-ai/langgraph)
17. [Agno GitHub](https://github.com/agno-agi/agno)
18. [OpenAI Agents SDK Documentation](https://openai.github.io/openai-agents-python/)
19. [OpenAI Agents SDK GitHub](https://github.com/openai/openai-agents-python)
20. [smolagents GitHub](https://github.com/huggingface/smolagents)
21. [Mastra Documentation](https://mastra.ai/docs)
22. [Mastra GitHub](https://github.com/mastra-ai/mastra)
23. [Google ADK Python GitHub](https://github.com/google/adk-python)
24. [Pydantic AI Documentation](https://ai.pydantic.dev/)
25. [Pydantic AI GitHub](https://github.com/pydantic/pydantic-ai)
