---
This is a note of Something about AI
---
# AI Notes

## Prompt 提示词

参考：

1. [万字说透提示词工程：User Prompt 与 Sys Prompt | 人人都是产品经理](https://www.woshipm.com/ai/6290455.html)
2. [LLM - User Prompt与System Prompt原理、方法与实战\_system prompt user prompt-CSDN博客](https://blog.csdn.net/yangshangwei/article/details/154863849)~

- 基本要素：
  1. What（问题）：AI完成什么任务；
  2. Why（背景）：任务的情境、目的、特殊偏好；
  3. How（要求）：需要的格式、风格、规则；
- 每次用户发送`User Prompt`时，系统会将`System Prompt`一起发给模型；

### User Prompt 用户提示词

#### 概念

- 用户或API实时下发的即时指令，用于指导AI完成当前任务，即用户在对话框中向AI输入的单次指令；
- 作用域：会话/临时；

#### 构造

##### RTF原则

1. Role 角色
   希望AI扮演的角色；
2. Task 任务
   希望AI完成的具体如任务；
3. Format 格式
   希望AI输出结果按照的格式；

##### 其他

1. 提供**few-shot 示例**；
2. 语言清晰、要求明确（如字数限制）；

##### 示例

```java
– 目标：让AI生成一篇关于“费曼学习法”的介绍文章

# 角色 (Role)

你是一位资深的教育专家和学习方法研究者，擅长将复杂的概念用通俗易懂的语言解释给大众。

# 任务 (Task)

请撰写一篇关于“费曼学习法”的科普文章，内容需要包含：

1. 费曼学习法的核心思想是什么？

2. 详细介绍费曼学习法的四个步骤。

3. 举一个具体的例子（比如学习“光合作用”），说明如何应用这四个步骤。

4. 分析费曼学习法为什么有效，并指出其适用场景和局限性。

# 格式 (Format)

– 全文使用Markdown格式。

– 文章总标题为：“费曼学习法：讲出来才算真正学会”。

– 每个要点使用二级标题（##）或三级标题（###）。

– 步骤介绍部分使用有序列表。

– 语言风格要求生动、有趣，多使用比喻，避免枯燥的学术术语。

– 总字数控制在1200字左右。
```

### System Prompt 系统提示词

#### 概念

- 由系统或开发者预设，决定AI的角色、能力边界、行为准则等；
- 作用域：全局/长期；

#### 使用场景

系统提示词效果取决于**底模的指令遵循能力、上下文处理能力**；

![](LA_images\SysPromptUsage.png)

#### 构造

##### 原则

1. 严格根据需求设定，仔细考虑语句必要性，避免冗余；
2. 以迭代的方式逐步改善，尝试设定$\rightarrow$得到结果$\rightarrow$修改设定$\rightarrow$得到结果$\rightarrow$……；
3. 保持备份，避免方向偏离无法回头；

##### 结构化构造方法

1. 角色定义（Role）
2. 能力边界（Scope）
3. 行为约束（Behavior Rules）
4. 输出规范（Output Format）

示例：

```javascript
你是一个通用的大模型应用助手。
你的目标是准确、清晰地帮助用户完成任务。

行为规则：
- 不确定时明确说明
- 不编造事实或接口
- 严格遵守安全与合规要求

你可以在不违反上述规则的前提下，根据用户要求采用不同的专业视角回答问题。

```

### 一些问题

#### 角色冲突

系统提示词和用户提示词得构造都提到对AI的角色设定，由于系统提示词中的角色优先级高于用户提示词，并且一般来说是代码中设定、几乎不可修改的，若两者不同不是出问题了？

> 大多数通用 LLM 应用都应让系统角色保持宽泛，像 ChatGPT、Gemini 这种面向大众的产品，设定为\*\*“高级顾问”**或**“全能助手”，此举能让用户提示词更容易“覆盖”或“扩展”它，而不会产生严重冲突；

## AI Agent 人工智能代理

参考：

1. [https://github.com/datawhalechina/hello-agents.git](https://github.com/datawhalechina/hello-agents.git)
2. [什么是AI Agent？AI Agent综述，看这一篇就够了！ - 知乎](https://zhuanlan.zhihu.com/p/1895877953453265781)

### 概念

- 通过**传感器（Sensors）**感知其所处**环境（Environment）**，并**自主**地通过**执行器（Actuators）**采取**行动（Action）**以达成特定目标的实体；
- 负责接收用户指令，不仅能回答问题，还能协调AI和**实际工具**完成复杂任务；

### 原理

#### 任务环境

- **P**erformance 性能度量——用来衡量 Agent 行为是否“好”的标准；

  > 常见的有：
  >
  > - 任务是否完成（success / fail）
  > - 输出是否正确
  > - 是否遵守约束
  > - 成本（token / money）
  > - 时间（延迟）
  > - 安全性（是否违规）
  >
- **E**nvironment 环境——Agent所处的外部世界或上下文，包括可以感知和影响的部分；

  > 对于LLM Agent来说，比如以下这些：
  >
  > - 工具集合（API、DB、Search）
  > - 外部系统（文件系统、Web、业务系统）
  > - 对话上下文
  > - 任务状态
  >
- **A**ctuators 执行器——Agent 对环境施加影响的方式，也就是能够做的；

  > 对于LLM Agent来说，比如以下这些：
  >
  > - 调用某个 API
  > - 写文件
  > - 发送 HTTP 请求
  > - 输出一段文本
  > - 调用另一个模型
  >
- **S**ensors 传感器——Agent感知环境的工具或输入通道，用于获取信息；

  > 对于LLM Agent来说，比如以下这些：
  >
  > - 用户输入
  > - 工具返回结果
  >

#### 运行机制

Agent Loop 智能体循环
![](LA_images\AgentLoop.png)

##### 感知 Perception

- Agent通过传感器（例如，API 的监听端口、用户输入接口）**接收来自环境的输入信息**（即**观察Observation**，例如，用户指令、环境状态变化反馈）；

##### 思考 Thought

Agent决策阶段，由LLM驱动的内部推理，即调用AI来思考；

###### 规划 Planning

- Agent基于当前观察、内部记忆，更新对任务、环境的理解，并**制定/调整行动计划**；

###### 工具选择 Tool Selection

- Agent根据当前计划，从工具库中**选择工具**，并确定调用所需参数；

##### 行动 Action

- Agent通过执行器进行具体行动，通常就是使用选定的工具对环境施加影响；
- **引起环境状态变化**，从而产生新的观察，用于下一轮的感知；

### 主流 Agent 开发框架：CrewAI、AutoGen、MetaGPT、LangGrap

| 框架 | 是否主流 | 更准确定位 |
| --- | --- | --- |
| CrewAI | 是 | 高层、角色协作式 multi-agent/workflow 框架，适合快速搭建业务型 Agent 团队 |
| AutoGen | 是，但偏历史主流 | 多 Agent 对话、事件驱动 Agent Runtime 的代表；当前新项目需注意 maintenance mode |
| MetaGPT | 是，但偏垂直场景 | 把软件公司角色和 SOP 固化为多 Agent 流程，适合代码生成、产品/研发流程模拟 |
| LangGraph | 是 | 偏底层、可控、生产化的状态图编排框架，适合复杂 Agent 工作流 |


#### 新出现且更流行的框架

截至 2026-07-05，Agent 框架生态里比较热门的新选择主要有以下几类。这里的“热门”同时参考官方背书、GitHub star、最近 release、生产化能力和社区讨论度，不只看 star。

| 框架 | 当前热度依据 | 核心定位 | 更适合的场景 |
| --- | --- | --- | --- |
| Agno | GitHub 约 41k stars，最新 release 为 2026-07-03 | Agent platform SDK，强调生产 API、存储、记忆、上下文、人工审批、可观测性、RBAC、多租户、调度、部署 | 想把 Agent 做成可运营平台，而不只是脚本 |
| OpenAI Agents SDK | GitHub 约 27.6k stars，最新 release 为 2026-06-24 | OpenAI 官方 Agent SDK，核心是 Agents、tools、handoffs、guardrails、sessions、tracing、MCP、hosted tools | OpenAI 生态内构建轻量但可追踪的 Agent 应用 |
| smolagents | GitHub 约 28.2k stars，最新 release 为 2026-05-29 | Hugging Face 出品，强调极简和 CodeAgent，让 Agent 用代码表达动作 | 研究、原型、代码执行型 Agent、小而透明的 Agent loop |
| Mastra | GitHub 约 25.8k stars，最新 release 为 2026-07-01 | TypeScript AI app / agent 框架，面向 Node.js、前后端一体、workflow、tools、evals、MCP | TypeScript 技术栈、Next.js/Node.js 团队构建 AI 应用 |
| Google ADK | GitHub 约 20.5k stars，ADK 2.0 最新 release 为 2026-06-18 | Google 官方 code-first Agent Development Kit，支持 Agent、Workflow、评估、部署；2.0 引入图式 workflow runtime、Task API、human-in-the-loop | Gemini / Google Cloud 生态，或需要官方支持的图式 Agent workflow |
| Pydantic AI | GitHub 约 18.2k stars，最新 release 为 2026-07-04 | Pydantic 团队出品，强调类型安全、结构化输出、模型无关、OpenTelemetry/Logfire 可观测性 | Python 后端、FastAPI/Pydantic 技术栈，需要强 schema 和类型约束 |
| Microsoft Agent Framework | GitHub 约 11.9k stars，最新 release 为 2026-07-03 | Microsoft 官方 AutoGen 后继框架，面向 Python 与 .NET 的生产级 Agent 和 multi-agent workflow | Microsoft/Azure/.NET 生态，或已有 AutoGen 项目迁移 |

##### Agno

Agno 不是单纯的“一个 Agent 类”，而是更偏 **Agent 平台层**。它的目标是让开发者 build、run、manage agent platforms，官方 README 强调：

- 可以使用任意 agent framework 构建 Agent；
- 以生产服务运行，支持 tracing、scheduling、RBAC；
- 提供统一 control plane；
- 支持 session、memory、knowledge、traces 持久化；
- 支持 human approval、OpenTelemetry tracing、audit logs、多租户隔离、Slack/Telegram/WhatsApp/Discord 等界面集成。

底层上，它解决的是 Agent 落地后的平台问题：

```text
Agent 逻辑
  -> Agno 生产 API / 运行服务
  -> 存储 session、memory、trace、knowledge
  -> 接入权限、审批、调度、审计、监控
  -> 暴露到 Slack / Web / API / 其他业务入口
```

如果只想写一个 Agent demo，Agno 可能偏重；如果要做公司内部的 Agent 平台，Agno 的定位更接近后端工程需求。

##### OpenAI Agents SDK

OpenAI Agents SDK 是 OpenAI 官方的 Agent SDK。它的核心抽象是：

- **Agent**：由 instructions、tools、guardrails、handoffs 等组成；
- **Tools**：可以是函数、MCP 工具、OpenAI hosted tools 等；
- **Handoffs**：让一个 Agent 把任务交给另一个更专门的 Agent；
- **Guardrails**：对输入/输出做安全或结构校验；
- **Sessions**：管理跨 run 的对话历史；
- **Tracing**：记录 Agent 执行链路，便于调试和优化。

底层流程可以理解为：

```text
Runner 启动一次 run
  -> Agent 携带 instructions 与上下文调用模型
  -> 模型选择直接回答、调用工具、或 handoff 给其他 Agent
  -> SDK 执行工具并把结果回填
  -> guardrails 做输入/输出检查
  -> sessions 保存对话历史
  -> tracing 记录完整执行轨迹
```

它适合 OpenAI 生态内的 Agent 应用，尤其是已经使用 Responses API、OpenAI hosted tools、MCP 或需要官方 tracing 的场景。它的控制力不一定比 LangGraph 这种状态图框架强，但上手和官方生态集成更直接。

##### smolagents

smolagents 是 Hugging Face 推出的轻量 Agent 框架，官方描述是“agents that think in code”。它强调极简抽象和 CodeAgent：

- 传统 tool-calling Agent 通常让模型输出 JSON 工具调用；
- CodeAgent 则让模型输出一段受控代码，用代码组合工具、变量、中间结果和控制流；
- 为了安全，支持 Docker、E2B、Modal、Blaxel 等 sandboxed environments。

这种设计的优点是：复杂动作可以直接用代码表达，例如循环、条件、组合多个工具、处理表格数据，而不必让模型多轮输出碎片化 JSON 调用。

风险也很明显：代码执行型 Agent 必须重视沙箱、权限、网络、文件系统、超时、资源限制和审计。它适合研究、原型和代码执行任务，但生产系统必须把安全边界设计好。

##### Mastra

Mastra 是面向 TypeScript 生态的 AI application / agent framework。它适合 Node.js、Next.js、全栈 TS 团队，因为它把 Agent、workflow、tool、eval、MCP 等能力放进现代 TypeScript 工程体系。

底层定位可以理解为：

```text
TypeScript 应用
  -> 定义 Agent / Tool / Workflow
  -> 接入 OpenAI、Anthropic、Google、Groq 等 provider
  -> 在 Node.js 服务或前后端工程中运行
  -> 结合 evals、workflow、MCP 做工程化迭代
```

如果团队主语言是 Python，LangGraph、Pydantic AI、OpenAI Agents SDK 可能更顺手；如果团队已经是 TypeScript / Next.js / Node.js，Mastra 的开发体验更贴近原有技术栈。

##### Google ADK

Google ADK 是 Google 官方 Agent Development Kit。它是 code-first Python 框架，目标是构建、评估和部署复杂 Agent。ADK 2.0 的 README 明确提到：

- Agent 定义 AI 的 instructions、tools 和 behavior；
- Workflow 用图式流程编排 agents 和 tasks；
- Workflow Runtime 支持 routing、fan-out/fan-in、loops、retry、state management、dynamic nodes、human-in-the-loop、nested workflows；
- Task API 支持结构化 agent-to-agent delegation。

它和 LangGraph 在“图式 workflow runtime”上有相似点，但更贴近 Google / Gemini / Google Cloud 生态。若业务主要使用 Vertex AI、Gemini、Google Cloud，ADK 值得重点评估。

##### Pydantic AI

Pydantic AI 的价值在于：把 Python 后端熟悉的 **类型约束、schema 校验、依赖注入、结构化输出** 带到 Agent 开发中。官方 README 将其定位为 production grade GenAI applications and workflows，并强调：

- 由 Pydantic 团队构建；
- model-agnostic，支持多模型和多 provider；
- 与 Pydantic Logfire / OpenTelemetry 集成，用于 tracing、成本跟踪、调试和评估；
- 适合需要强类型、结构化输出和后端工程可维护性的 Python 应用。

从后端视角看，Pydantic AI 的优势不是“多 Agent 花样最多”，而是让 LLM 调用结果更像正常后端接口：输入输出有类型、错误可校验、trace 可观测，适合和 FastAPI / Pydantic 项目结合。

##### Microsoft Agent Framework

Microsoft Agent Framework 是 AutoGen 的官方后继方向。它支持 Python 和 .NET，官方 README 明确面向 production-grade AI agents and multi-agent workflows，适合：

- 需要 Python / .NET 双栈；
- 需要 Azure OpenAI、Microsoft Foundry、GitHub Copilot SDK 等生态集成；
- 需要 graph-based patterns、durability、restartability、observability、governance、human-in-the-loop；
- 已有 AutoGen 项目准备迁移。

如果团队在 Microsoft / Azure / .NET 体系内，MAF 比 AutoGen 更值得作为新项目起点。

#### 新框架选型建议

1. **Python 后端、强类型和结构化输出**：优先看 Pydantic AI。
2. **OpenAI 生态、轻量官方 SDK、需要 tracing / handoff / guardrails**：优先看 OpenAI Agents SDK。
3. **生产级复杂状态图和可恢复流程**：继续优先看 LangGraph；Google 生态可对比 Google ADK。
4. **TypeScript / Next.js / Node.js 团队**：优先看 Mastra。
5. **要做公司级 Agent 平台，不只是单个 Agent**：优先看 Agno。
6. **想研究代码执行型 Agent**：看 smolagents，但生产必须先设计沙箱和权限。
7. **Microsoft / Azure / .NET 或 AutoGen 迁移**：优先看 Microsoft Agent Framework。

#### CrewAI

CrewAI 的核心思想是：把复杂任务拆成多个角色、多个任务，再通过一个 Crew 或 Flow 进行编排。

核心概念：

- **Agent**：具备 role、goal、backstory、tools、memory、delegation 等属性的执行单元。它不是“模型本身”，而是“模型 + 指令 + 工具 + 运行约束”的封装。
- **Task**：一个明确的工作项，通常包含 description、expected output、分配给哪个 Agent、依赖哪些上下文。
- **Crew**：由多个 Agents 和 Tasks 组成的协作团队，按照顺序、层级或其他 process 执行。
- **Flow**：比 Crew 更偏工程控制的流程抽象，用于事件驱动、条件分支、状态管理，把多个 Crew、普通函数、外部系统串起来。

底层流程可以理解为：

```text
用户输入
  -> Flow / Crew 接收任务
  -> 根据任务定义选择 Agent
  -> Agent 携带 role、goal、backstory、工具描述调用 LLM
  -> LLM 生成回答或工具调用意图
  -> 框架执行工具，拿到 observation
  -> 将 observation 写回上下文
  -> 继续下一个 Task 或结束
```

CrewAI 的优势是抽象直观，适合把现实组织结构映射成 Agent 团队，例如 researcher、writer、reviewer、planner。它的问题是：高层抽象越强，底层状态流、分支控制、错误恢复、可重放调试就越容易被隐藏；如果任务进入复杂生产流程，通常要结合 Flow、日志、人工审核、工具权限控制一起设计。

一个容易误解的点是：**CrewAI 并不总是“自行根据 task 选择 Agent”**。

- 在 `Process.sequential` 顺序流程中，通常是开发者先定义好 agents 和 tasks，并且每个 task 要明确指定 `agent` 参数，然后 Crew 按任务列表顺序执行。也就是说，这种模式下更像“开发者预先排好角色和任务”，不是运行时自动挑人。
- 在 `Process.hierarchical` 层级流程中，manager agent 会协调工作流、委派任务、验证结果；这时才更接近“由管理者根据任务和成员能力分配给不同 Agent”。
- 如果开启 delegation / planning，Agent 或 manager 也可能在执行中拆分、委派、调整任务，但这属于 Agent 自主协作能力，不等同于传统后端里显式、可验证、可审计的状态机流转。

所以更准确的理解是：**CrewAI 对“角色协作”和“任务完成”很友好，但如果业务要求严格遵循固定流程、固定状态转移、固定审批点和固定失败恢复语义，仅靠 Crew 抽象不够，应该用 Flow 或后端状态机承载主流程，把 Crew 当成某个步骤里的智能执行单元**。

例如：

```text
适合 Crew 主导：
收集资料 -> 分析资料 -> 写报告 -> 审稿

更适合 Flow / 后端状态机主导：
创建订单 -> 风控校验 -> 用户确认 -> 扣款 -> 发券 -> 记账 -> 通知
```

原因是第二类流程里，每一步通常都有强业务约束：状态只能按规定迁移，扣款不能重复执行，失败要有补偿，人工审批要阻塞流程，审计日志要可追溯。这些能力不是让某个 Agent “觉得下一步该做什么”就能替代的。

为什么会这样：

1. **Crew 把执行细节压缩成 Agent / Task / Process，降低了显式状态建模的程度**

   CrewAI 的 Crew 抽象关注“哪些 Agent 执行哪些 Task，以及用 sequential 还是 hierarchical process 协作”。这对原型很友好，但从后端工程角度看，很多运行时信息没有天然变成显式业务状态，例如：

   - 当前任务执行到第几步；
   - 这个 Agent 为什么选择某个工具；
   - 工具调用前后的参数、返回值、异常；
   - 上一个 Task 的输出如何进入下一个 Task 的上下文；
   - hierarchical process 中 manager agent 如何分配、审查、判定完成。

   官方 Processes 文档也体现了这一点：Crew 的 process 主要是 `sequential` 和 `hierarchical`。`sequential` 按任务列表顺序执行，并把一个任务的输出作为后续上下文；`hierarchical` 由 manager agent 规划、委派、审查任务。也就是说，在 Crew 层，状态流更多表现为“任务输出传递”和“manager 决策”，而不是像后端状态机那样每个状态、事件、转移条件都显式建模。

   对比之下，官方把 Flow 定位为管理 state、event-driven execution、conditional logic、loops、branching 的结构化工作流，并建议生产应用从 Flow 开始，再在 Flow 的某一步委托 Crew 做复杂任务。因此，**Crew 更像智能执行单元，Flow 才更像可控的业务流程骨架**。

2. **分支控制如果只放在 Agent 自主决策里，后端很难做确定性保证**

   在 Crew 中，Agent 可以根据 role、goal、backstory、tools 和上下文自主完成任务。问题是：LLM 的决策天然不是传统代码里的 `if/else`，它可能因为提示词、上下文顺序、模型版本、温度、工具返回内容不同而选择不同路径。

   例如一个 researcher Agent 可能自行决定：

   ```text
   是否搜索更多资料
   -> 用哪个搜索工具
   -> 搜索几次
   -> 什么时候停止
   -> 是否把结果交给 writer
   ```

   这些步骤在体验上像“一个聪明员工在完成任务”，但在工程上不是显式 DAG / 状态机。真正需要稳定分支时，应把分支上移到 Flow 层：用 `@router()`、`@listen()`、`and_()`、`or_()` 等机制表达条件路由，而不是完全依赖 Agent 在自然语言推理中自行决定。

3. **错误恢复不能只依赖“重新跑一次 Crew”**

   传统后端任务失败时，一般希望知道：

   - 哪一步失败；
   - 是否可以重试；
   - 重试是否幂等；
   - 上游已经产生的副作用是否要补偿；
   - 是否从失败节点继续，而不是全流程重跑。

   CrewAI 提供 replay 和 checkpointing 能力，但它们也说明了高层 Crew 默认不是完整的事务编排系统：

   - replay 文档说明，需要先执行过 `crew.kickoff()`，并且当前只支持 latest kickoff；
   - checkpointing 文档说明，该能力处于 early release，默认在 `task_completed` 后保存 checkpoint；
   - 从 checkpoint 恢复时，会跳过已完成任务，从第一个未完成任务继续。

   这些能力有用，但粒度通常是 task / flow method / event，而不是业务系统里任意细粒度的事务步骤。如果某个工具已经写库、发消息、调外部 API，框架本身无法自动知道业务幂等键、补偿动作、分布式事务边界，这些仍要后端自己设计。

4. **可重放调试依赖日志、trace、checkpoint 是否提前打开**

   Agent 出错时，只看最终回答通常不够，必须看到完整链路：

   ```text
   输入 prompt
   -> Agent 决策
   -> 工具 schema
   -> 工具参数
   -> 工具返回
   -> LLM 中间响应
   -> Task 输出
   -> 下一个 Task 接收的上下文
   ```

   CrewAI 有 tracing，官方文档说明可以观察 agent decisions、task execution timeline、tool usage、LLM calls、performance metrics、error tracking 等。但这些并不是“只定义 Crew 就自然具备完整本地审计”的东西，通常需要显式开启 `tracing=True`、配置环境变量、登录 AMP 平台，或接入 Langfuse、MLflow、OpenTelemetry 等观测系统。

   这就是“高层抽象隐藏调试细节”的来源：Crew 的使用者写的是 role、goal、task、expected output；而生产排障需要的是每次模型调用、每个工具参数、每段上下文、每次状态转移。二者关注层级不同。

5. **LLM Agent 的不确定性会放大高层抽象的排障成本**

   普通后端函数大多是确定性的：同样输入、同样数据库状态，通常能稳定复现。LLM Agent 不同，它还受这些因素影响：

   - 模型版本和采样参数；
   - prompt 拼接顺序；
   - 上下文窗口裁剪；
   - memory / cache / knowledge 检索结果；
   - 工具返回时延和错误；
   - manager agent 或 planner 的临时决策。

   高层框架把这些复杂性包装成“Agent 完成任务”，开发效率更高；但如果没有把状态、trace、checkpoint、工具幂等和错误处理显式设计出来，线上问题就会表现为“这次为什么走了另一条路”“为什么同样输入结果不同”“为什么从中间恢复后上下文不一致”。

更准确地说，**这不是 CrewAI 没有状态、分支、恢复、调试能力，而是 Crew 抽象默认更偏自主协作；生产级控制需要开发者主动把关键路径放到 Flow、checkpointing、tracing、event listeners 和后端业务状态机中**。

实践建议：

- 简单调研、写作、分析任务：可以只用 Crew；
- 有条件分支、审批、重试、失败恢复的任务：用 Flow 管整体流程，把 Crew 当作某个复杂步骤；
- 有数据库写入、支付、发券、发邮件、调用外部系统等副作用：工具层必须自己做幂等、超时、重试、补偿、审计；
- 要求线上排障：一开始就打开 tracing / 日志，并保存 task output、tool args、tool result、LLM request id、token usage、异常栈；
- 长任务：开启 checkpoint，并明确 checkpoint 粒度和恢复语义；
- 高风险任务：在 Flow 中加入 human-in-the-loop，而不是让 Agent 自行决定是否继续。

适合：

- 内容生成、资料调研、运营分析、报告编写；
- 业务流程中天然存在多个角色分工的任务；
- 快速验证 multi-agent 协作原型。

不太适合：

- 对状态机、分支、回滚、审计要求非常强的核心交易流程；
- 需要精细控制每一步 Agent 状态转移的复杂系统。

#### AutoGen

AutoGen 是 Microsoft 推出的多 Agent 框架。它的代表性价值在于：把 Agent 看成可以互相发消息、接收消息、调用工具、请求人工输入的实体。

官方文档中 AutoGen 主要分三层：

- **AgentChat**：高层 API，用于快速创建 AssistantAgent、团队协作、终止条件、工具调用等；
- **Core**：底层事件驱动框架，支持异步消息传递、agent runtime、topic、subscription 等，更接近分布式 Actor 模型；
- **Extensions**：与模型客户端、代码执行器、MCP、gRPC、Docker 等外部能力集成。

底层流程可以理解为：

```text
用户消息
  -> Team / Runtime 接收
  -> 某个 Agent 根据消息和上下文生成回复
  -> 如果需要工具，生成 tool call
  -> 执行工具或请求人工输入
  -> 工具结果作为新消息进入对话
  -> GroupChat / Team 决定下一个发言 Agent
  -> 满足 termination condition 后结束
```

AutoGen 和 CrewAI 的区别在于：CrewAI 更像“任务编排和角色分工”，AutoGen 更像“多 Agent 消息系统”。如果使用 AutoGen Core，开发者需要更清楚地处理消息类型、runtime、订阅关系、Agent 生命周期，这给了更强的底层控制，也带来更高的工程复杂度。

需要特别注意：AutoGen 当前官方 GitHub README 已经标注 maintenance mode，并推荐新项目使用 Microsoft Agent Framework。因此：

- 学习多 Agent 对话、工具调用、人类介入、事件驱动 Agent Runtime，AutoGen 仍然有价值；
- 生产新项目如果已经在 Microsoft 生态内，应优先评估 Microsoft Agent Framework、Semantic Kernel 等官方推荐方向；
- 已有 AutoGen 项目需要关注版本维护、迁移成本和安全更新。

适合：

- 多 Agent 对话实验；
- 研究 Agent 协商、辩论、代码执行、human-in-the-loop；
- 需要事件驱动、消息驱动 Agent Runtime 的系统原型。

不太适合：

- 想用一个长期稳定、官方推荐的新项目默认框架；
- 只需要简单任务编排，不想处理消息系统复杂度的场景。

#### MetaGPT

**SOP（Standard Operating Procedure，标准作业流程 / 标准操作规程）**，指把一类重复出现的工作沉淀成固定步骤、角色分工、输入输出标准和检查规则。它的目标不是“让人自由发挥”，而是让不同执行者在相同条件下尽量产出稳定、可检查、可交接的结果。

在普通业务里，SOP 类似：

```text
接到客户退款申请
  -> 核对订单状态
  -> 判断是否符合退款规则
  -> 提交主管审批
  -> 原路退款
  -> 通知客户
  -> 记录审计日志
```

在 Agent 系统里，SOP 的作用是把“多个 Agent 自由聊天”约束成“按固定流程交付工件”。它通常会明确：

- 每个 Agent 扮演什么角色；
- 每一步需要读取什么输入；
- 每一步必须产出什么结构化结果；
- 上一步结果如何交给下一步；
- 哪些节点需要审查、测试、回滚或人工确认。

MetaGPT 的核心思想是：把一家软件公司的标准化流程编码进多 Agent 系统中。它不是简单地让几个 Agent 自由聊天，而是给 Agent 分配明确职业角色，并让它们按照 SOP 产出结构化工件。

典型角色包括：

- Product Manager：理解需求，输出 PRD；
- Architect：做架构设计；
- Project Manager：拆解任务；
- Engineer：编写代码；
- QA / Reviewer：测试、检查、反馈。

底层流程可以理解为：

```text
用户提出软件需求
  -> 产品经理 Agent 生成需求文档
  -> 架构师 Agent 基于需求生成系统设计
  -> 项目经理 Agent 拆任务
  -> 工程师 Agent 生成代码
  -> 测试 / 审查 Agent 检查结果
  -> 产出项目文件、文档或代码
```

MetaGPT 的关键不是“Agent 数量多”，而是 **SOP 约束**。没有 SOP 的多 Agent 很容易变成低效聊天；有 SOP 后，每个 Agent 的输入、输出、交接物、下一步动作都更明确，系统更接近流水线。

优势：

- 对“软件公司式协作”抽象清晰；
- 适合演示从需求到代码的端到端流程；
- 通过 SOP 降低多 Agent 自由对话的随机性。

局限：

- 垂直场景明显，最自然的场景是软件研发、文档、需求分析；
- 对真实生产代码质量、测试覆盖、架构合理性仍需要人工审查；
- 如果任务不是 SOP 型流程，MetaGPT 的角色体系可能反而显得重。

适合：

- 自动生成原型项目；
- 学习多 Agent 如何通过标准流程协作；
- 需求分析、架构草案、代码草案生成。

不太适合：

- 严肃生产系统的无人值守代码合并；
- 非软件工程类、强实时、强事务的业务流程。

#### LangGraph

LangGraph 是 LangChain 生态中面向 Agent 工作流的状态图框架。它的核心不是“帮你定义几个角色”，而是让开发者把 Agent 应用建模成一个 **有状态图（stateful graph）**。

核心概念：

- **State**：整个工作流共享和持续更新的状态，例如 messages、任务计划、工具结果、用户确认信息；
- **Node**：图中的执行节点，可以是 LLM 调用、工具调用、普通函数、子图、人工审核节点；
- **Edge / Conditional Edge**：节点之间的跳转规则，可以固定跳转，也可以根据状态条件选择下一步；
- **Checkpoint / Persistence**：把状态持久化，使长任务可以暂停、恢复、重放；
- **Human-in-the-loop**：在关键节点中断，等待人工确认、修改或拒绝后继续；
- **Streaming / Debugging**：支持流式观察中间状态，便于排查 Agent 为什么走到某一步。

底层流程可以理解为：

```text
初始输入写入 State
  -> 从入口 Node 开始执行
  -> Node 读取 State，调用 LLM / Tool / 函数
  -> Node 返回 State 更新
  -> Reducer 合并状态
  -> Edge 根据当前 State 决定下一个 Node
  -> 可在 checkpoint 暂停、恢复、人工介入
  -> 到 END 节点结束
```

LangGraph 的优势是控制力强。很多生产 Agent 的难点不是“让模型会回答”，而是：

- 如何保证流程可中断、可恢复；
- 如何知道当前执行到哪一步；
- 如何处理工具失败、重试、超时；
- 如何把人工审批插入关键路径；
- 如何让一次复杂 Agent 执行可观测、可调试、可回放。

LangGraph 正是围绕这些问题设计的。因此它更像“Agent 工作流运行时 / 状态机框架”，而不是简单的多 Agent 角色扮演框架。

适合：

- 生产级 Agent 工作流；
- 复杂分支、多步骤工具调用；
- 需要状态持久化、人工介入、流式追踪、可观测性的系统；
- 多 Agent 之间需要明确状态转移，而不是自由聊天的场景。

不太适合：

- 只想用极少代码快速演示几个角色协作；
- 不想设计状态、节点、边、条件跳转的简单任务。

#### 综合对比

| 维度 | CrewAI | AutoGen | MetaGPT | LangGraph |
| --- | --- | --- | --- | --- |
| 抽象层级 | 高层 | 中高层到低层都有 | 高层、垂直 SOP | 偏低层、强控制 |
| 核心模型 | Agent + Task + Crew / Flow | Agent + Message + Runtime / Team | Role + SOP + Artifact | State + Node + Edge |
| 协作方式 | 角色分工完成任务 | Agent 之间消息对话 | 软件公司角色流水线 | 状态图驱动执行 |
| 状态控制 | Flow 可管理状态，但 Crew 抽象较高 | Core 层可控，AgentChat 较高层 | 依赖 SOP 和中间产物 | 最强，状态是一等公民 |
| 工具调用 | 支持工具绑定到 Agent | 支持工具、代码执行、人类输入 | 支持角色行动和工程产物生成 | 节点中可调用任意工具 |
| 人工介入 | 可在流程层设计 | 支持 UserProxy / human-in-loop 模式 | 通常偏自动流水线 | 官方重点能力之一 |
| 可观测和调试 | 需要结合日志、Tracing 工具 | 取决于 API 层和运行时设计 | 关注产物链路 | 强，适合流式、checkpoint、回放 |
| 最适合 | 快速搭建业务型多 Agent 团队 | 多 Agent 对话和事件驱动实验 | 需求到代码的 SOP 型流程 | 复杂、可靠、可控的生产 Agent |
| 主要风险 | 高层抽象隐藏细节 | 当前 maintenance mode，选型需谨慎 | 场景较垂直，真实代码仍需审查 | 学习成本和设计成本较高 |

#### 选型建议

1. **想快速做一个多角色 Agent 原型**：优先 CrewAI。它的 Agent、Task、Crew 抽象最贴近日常理解，上手快。
2. **想研究多 Agent 对话、协商、消息驱动 Runtime**：可以学习 AutoGen，尤其是它的 AgentChat 和 Core 设计；但新生产项目要考虑其维护状态。
3. **目标是“输入需求，生成软件项目草案”**：MetaGPT 更合适，因为它天然围绕软件公司 SOP 设计。
4. **目标是生产级复杂 Agent 应用**：优先 LangGraph。因为它把状态、节点、分支、持久化、人工介入作为核心抽象，更容易做可靠性工程。

从后端和 Agent 工程角度看，真正的选型关键不是“哪个最火”，而是：

- 任务是否有固定流程；
- 是否需要多 Agent 角色协作；
- 是否需要精确状态控制；
- 是否需要人工审批；
- 是否需要失败重试、幂等、审计、可回放；
- 是否要长期维护在生产环境中。

如果是生产系统，通常建议把 Agent 框架看成“编排层”，而不是让它直接吞掉全部业务逻辑。业务权限、工具执行、数据库事务、审计日志、限流、重试、补偿、监控告警仍应放在后端工程体系中处理。

参考依据：

1. [CrewAI Documentation - Introduction](https://docs.crewai.com/introduction)
2. [CrewAI GitHub Repository](https://github.com/crewAIInc/crewAI)
3. [CrewAI Documentation - Processes](https://docs.crewai.com/en/learn/sequential-process)
4. [CrewAI Documentation - Flows](https://docs.crewai.com/en/concepts/flows)
5. [CrewAI Documentation - Hierarchical Process](https://docs.crewai.com/en/learn/hierarchical-process)
6. [CrewAI Documentation - Replay Tasks](https://docs.crewai.com/en/learn/replay-tasks-from-latest-crew-kickoff)
7. [CrewAI Documentation - Checkpointing](https://docs.crewai.com/en/concepts/checkpointing)
8. [CrewAI Documentation - Tracing](https://docs.crewai.com/en/observability/tracing)
9. [Microsoft AutoGen Documentation](https://microsoft.github.io/autogen/stable/)
10. [Microsoft AutoGen GitHub Repository](https://github.com/microsoft/autogen)
11. [Microsoft Agent Framework Documentation](https://learn.microsoft.com/en-us/agent-framework/)
12. [MetaGPT GitHub Repository](https://github.com/geekan/MetaGPT)
13. [MetaGPT ICLR 2024 OpenReview](https://openreview.net/forum?id=VtmBAGCN7o)
14. [LangGraph Documentation - Overview](https://docs.langchain.com/oss/python/langgraph/overview)
15. [LangGraph GitHub Repository](https://github.com/langchain-ai/langgraph)
16. [Agno GitHub Repository](https://github.com/agno-agi/agno)
17. [OpenAI Agents SDK Documentation](https://openai.github.io/openai-agents-python/)
18. [OpenAI Agents SDK GitHub Repository](https://github.com/openai/openai-agents-python)
19. [Hugging Face smolagents GitHub Repository](https://github.com/huggingface/smolagents)
20. [Mastra Documentation](https://mastra.ai/docs)
21. [Mastra GitHub Repository](https://github.com/mastra-ai/mastra)
22. [Google ADK Python GitHub Repository](https://github.com/google/adk-python)
23. [Pydantic AI Documentation](https://ai.pydantic.dev/)
24. [Pydantic AI GitHub Repository](https://github.com/pydantic/pydantic-ai)
25. [Microsoft Agent Framework Documentation](https://learn.microsoft.com/en-us/agent-framework/)
26. [Microsoft Agent Framework GitHub Repository](https://github.com/microsoft/agent-framework)

## Function Calling 函数调用

### 概念

- AI大模型在处理任务时，能够**识别特定的指令或提示**，进而**生成结构化的工具调用意图**，让应用层**调用预先定义好的外部函数（工具）**来完成特定功能；

### 流程

1. 使用**JSON**格式定义`Tool Schema(函数描述)`，并且System Prompt允许LLM使用工具；
   工具描述示例：

   ```json
    {
     //工具名称
     "name": "get_weather",
     //工具功能说明
     "description": "当用户询问某个城市的天气情况时使用",
     //参数列表
     "parameters": {
       "type": "object",
       "properties": {
         "city": { "type": "string" },
         "data": { "type": "string" }
       },
       //必须传递的参数
       "required": ["city"]
     }
   }
   ```
2. 用户输入User Prompt，LLM对输入进行推理，进行**语义识别**，如果判断用户需求不能由模型本身完成，即需要使用工具。LLM会根据工具描述中的信息，决定 使用哪个工具、传入什么参数，生成**结构化JSON**作为调用请求；
   调用的结构化JSON示例如下：

   ```json
   {
     "function_call":{//固定字段，表示这是一个工具调用请求
      "name": "get_weather",
      "parameters": {
        "city": "上海",
        "unit": "celsius",
        "date": "2026-2-1"
      }
    }
   }
   ```
3. 系统（应用层）得到调用请求，做必要的安全性检查之后对工具进行实际调用；
   得到结果示例如下：

   ```json
   weather_data = {
       "city": "上海",
       "time": "2026-2-1",
       "weather_condition": "晴",
       "temperature": "25℃"
   }
   ```
4. 将得到的结果作为输入回传给LLM，LLM对结果格式和内容做一定的修改、补充;

## MCP（Model Context Protocol）模型上下文协议

参考：
[MCP (Model Context Protocol)，一篇就够了。 - 知乎](https://zhuanlan.zhihu.com/p/29001189476)

[MCP | 一文详解什么是 MCP以及 MCP 可以做什么-CSDN博客](https://blog.csdn.net/m0_56255097/article/details/148785847)

[Model Context Protocol 官方文档](https://modelcontextprotocol.io/docs/getting-started/intro)

### 概念

- MCP 本质上是一个**开放的应用层协议 / 标准**，用于规范 MCP Client 与 MCP Server 之间如何交换工具、资源、提示词模板等上下文能力；
- MCP 不是模型本身，也不是 Function Calling 的替代品，而是解决 **AI 应用接入外部工具时的统一适配问题**；
- Function Calling 关注的是：LLM 如何生成结构化的工具调用意图；
- MCP 关注的是：Host / Client 如何发现外部工具、获取工具参数描述、发送调用请求、接收工具结果；
- 因此二者常常配合使用：MCP 负责把外部能力以标准协议暴露出来，Host 再把这些能力转换为 LLM 可理解的工具定义；
- MCP 的底层消息采用 `JSON-RPC 2.0` 风格，常见传输方式包括：
  1. `stdio`：本地进程之间通过标准输入 / 标准输出传递 JSON-RPC 消息；
  2. `Streamable HTTP`：远程服务通过 HTTP 传递 JSON-RPC 消息；

  ![](LA_images\mcp.png)

### 结构

![](LA_images\mcpArchitectrue.png)

#### Host

- 能够通过 MCP 集成外部能力的 AI 应用主体，比如 `Claude Desktop`、IDE、Agent 框架等；
- 通常负责与用户、LLM交互，并管理安全策略、用户授权、工具注册表等；
- 是 Client 运行的环境，一个 Host 可以创建并管理多个 Client；
- Host 决定如何把 MCP Server 暴露出的工具信息交给 LLM：
  1. 如果模型 API 支持原生 `tools` / `function calling`，Host 通常会把 MCP 工具的 `name`、`description`、`inputSchema` 转换成模型接口所需的工具定义；
  2. 如果模型或框架不支持原生工具调用，Host 也可能把工具说明序列化进 System Prompt、隐藏上下文或其他约定格式中；
- 所以“LLM 知道有哪些工具”并不是 MCP Server 直接告诉 LLM，而是 **Host 先通过 MCP 发现工具，再把工具信息暴露给 LLM**；

#### Client

- MCP Host内部的**组件**，负责与MCP Server交互；
- 由Host创建，并与MCP Server建立**一对一连接**；
- 负责协议层面的连接初始化、能力协商、工具 / 资源 / Prompt 发现、发送调用请求、获取结果；
- Client 获取到的信息一般会先交给 Host，由 Host 再决定如何注册为 LLM 可用的工具或上下文；

#### Server

- 轻量级服务程序，负责对接具体数据源或工具（如数据库、`API`等），并按照MCP规范提供标准化的功能接口；
- 封装了特定的能力，如文件检索、数据库查询等（可能是它自身实现的，也可能是外部的API），并将结果返回给Client；
- Server 不需要直接理解完整对话历史，也不直接面对 LLM；它只按照 MCP 协议接收请求、执行能力、返回结果；
- 对外提供的三种**原语**：
  1. Tool工具

     > 实现特殊功能的函数、API；
     >
  2. Resource资源

     > 一些只读数据，比如日志、文件内容等；
     >
  3. Prompt提示词模板

     > 可复用的 LLM 提示模板；
     >
     > - 针对特定用途 / 场景的、可复用、可参数化、具有明确语义边界的提示词模板；
     > - 比如本来的LLM的系统提示词是作为一个通用助手，某个MCP Server提供的Prompt可以临时注入，让它**在系统提示词保持通用助手身份不变的前提下**，作为一个养猪高手来回答问题，那么每次需要询问这个领域的问题时，可以使用这个提供的Prompt；
     >

### 流程

以 Tool 调用为例：

1. Host 根据配置连接一个或多个 MCP Server，并为每个 Server 创建一个独立的 Client；
2. Client 向 Server 发送 `initialize` 请求，进行协议版本和能力协商；
3. Server 声明自己支持的能力，例如 `tools`、`resources`、`prompts`；
4. Client 发送 `tools/list`，向 Server 获取可用工具列表；
5. Server 返回工具元数据，通常包括：
   - `name`：工具唯一名称；
   - `description`：工具用途说明；
   - `inputSchema`：工具参数的 JSON Schema；
   - `outputSchema`：可选，描述结构化输出；
6. Host 将多个 MCP Server 返回的工具汇总成统一工具注册表，并转换成 LLM 可理解的形式；
7. LLM 在对话中判断需要调用工具时，生成结构化工具调用意图；
8. Host 拦截该工具调用，并根据工具所属 Server，将其路由为 MCP 的 `tools/call` 请求；
9. Server 执行工具，将结果返回给 Client；
10. Host 再把工具结果作为上下文交回 LLM，由 LLM 生成面向用户的最终回答；

#### 消息示例

Client 向 Server 发现工具：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}
```

Server 返回工具定义：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "get_weather",
        "description": "查询指定城市的天气",
        "inputSchema": {
          "type": "object",
          "properties": {
            "city": {
              "type": "string"
            }
          },
          "required": ["city"]
        }
      }
    ]
  }
}
```

Client 向 Server 调用工具：

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "get_weather",
    "arguments": {
      "city": "上海"
    }
  }
}
```

#### 与 Function Calling 的区别

- Function Calling 是**模型接口层 / 推理输出层**能力：让 LLM 以结构化格式表达“我要调用哪个工具、传什么参数”；
- MCP 是**应用协议层 / 工具接入层**能力：让 AI 应用用统一协议发现工具、调用工具、拿到结果；
- 传统 Function Calling 往往需要开发者在应用中手动写死工具 schema 和调用逻辑；
- MCP 可以让工具提供方通过 Server 自描述工具能力，Host 通过协议动态发现并接入这些工具；
- 所以更准确的关系是：**MCP 提供工具接入标准，Function Calling 提供模型调用工具的表达机制**；

## Context Window 上下文窗口

### 概念

- LLM在生成或理解文本时所能参考的**Token数量范围**；
- 简单说就是LLM能够`记住`的文本量；
- 在任何时候，**输入和输出的token总数**不能超过上下文窗口的**最大长度限制**

### 作用

1. 理解长文本
   > 可以一次性理解更长的文章、报告或代码；
   >
2. 记住上下文
   > 可以记住多轮对话的上下文，从而更好地理解用户的需求；
   >
3. 复杂任务处理
   > 对于复杂的任务，如代码生成、论文写作、长篇问答等，较大的上下文窗口能让模型处理更多的信息，从而提高完成任务的质量和准确性;
   >

- 但也不是窗口越大越好，窗口越大，上下文信息越多，处理的时间就更长，消耗的`Token`也越多；

## RAG（Retrieval-Augmented Generation）检索增强生成

### 概念

- 一种AI框架，将**信息检索**与**LLM**结合；

### 针对问题

1. 大模型知识局限性

   > - 大模型自身的知识完全源于训练数据，而现有的主流大模型的训练集基本都是构建于网络公开的数据，缺乏一些实时性的、非公开的或私域的数据；
   >
2. 幻觉问题

   > - 大模型生成的内容与事实不符，存在虚构或误导信息，尤其在大模型自身不具备某一方面知识或不擅长的场景下，
   >

### 工作流程

**检索 + 生成**

#### 数据准备

1. 从网页、PDF、数据库等来源**采集与问答系统相关的原始数据（文本）**；
2. 对收集到的数据进行**清洗**，去除噪声、重复项、无关信息；
3. 将文本**切割**成长短适配的片段（chunks）

   > 切割策略：
   >
   > - 固定大小（如 512 token）：简单易操作，但会损失很多语义信息，一般通过在头尾增加一定冗余量来缓解；
   > - 语义边界（段落、章节）：保留内容逻辑，适配结构化文档；
   > - 递归分割（n-gram 切割）：灵活处理复杂文本，平衡颗粒度；
   >

#### 知识库构建

1. 用**Embedding 模型**将文本块**转化为向量矩阵**，该过程会直接影响到后续检索的效果；
2. 将向量**存入向量数据库**，作为知识库；

#### 数据检索

1. 同样使用Embedding模型将**用户输入**转换为向量；
2. 在向量数据库中检索与输入向量**相似度最高的知识库片段**；

   > 检索方式：
   >
   > * 相似性检索：通过**余弦相似性、欧氏距离、曼哈顿距离**等计算查询向量与所有存储向量的相似性得分，返回得分高的记录；
   > * 全文检索：在数据存入时，通过关键词构建倒排索引；在检索时，通过关键词进行全文检索，找到对应的记录；
   >

#### 注入Prompt、输出

1. 将**检索到的相关片段与用户的原始输入合并**，增强上下文信息；
2. LLM据此生成回答；

## Agent Skills

未完待续

### 概念

- 模块化、可复用的能力扩展插件；
- 每个`skill`是一个**文件夹**，包含**任务指令集 SKILL.md**、**可执行脚本 scripts**、**参考文档 references**、**素材资源 assets**，除了指令集必选，其他三项可选；
