# Agent / RAG / Memory

Agent 行动、工具接入、框架编排、反思、记忆、RAG 检索增强与评估，并收录相关的 Prompt 工程和机器学习基础。

主线知识点文件数：23；基础附录：1。

阅读顺序按主题分块组织，每个主题块内部由基础概念逐步推进到实现、优化和评估。

## 1. 基础入口

- [Prompt 工程：User Prompt 与 System Prompt](001_Prompt_工程：User_Prompt_与_System_Prompt.md)

## 2. Agent 基本机制与工具能力

- [Agent 的端到端任务能力](002_Agent_的端到端任务能力.md)
- [Function Calling 与 MCP：模型决策和工具接入](003_Function_Calling_与_MCP_工具接入.md)
- [LangChain @tool 与 bind tools](004_LangChain_@tool_与_bind_tools.md)
- [Agent Skills：模块化能力扩展](005_Agent_Skills_模块化能力扩展.md)

## 3. Agent 推理、行动与运行控制

- [MRKL、ReAct、ToT 与 Plan-and-Execute](006_MRKL、ReAct、ToT_与_Plan-and-Execute.md)
- [Extended Thinking 与 ReAct 推理范式对比](007_Extended_Thinking_与_ReAct_推理范式对比.md)
- [ReAct 提前终止检测](008_ReAct_提前终止检测.md)
- [重复检测、语义缓存与 Best-of-n 采样](009_重复检测、语义缓存与_Best-of-n_采样.md)

## 4. Agent 框架与状态实现

- [Agent 开发框架与选型](010_Agent_开发框架与选型.md)
- [LangGraph 状态更新、invoke 与 stream](011_LangGraph_状态更新、invoke_与_stream.md)

## 5. Memory、反思与长上下文

- [Agent Memory 四类：短期、情景、语义、程序性](012_Agent_Memory_四类：短期、情景、语义、程序性.md)
- [Reflection、Insight 与执行后反思](013_Reflection、Insight_与执行后反思.md)
- [Generative Agents 的记忆与反思机制](014_Generative_Agents_的记忆与反思机制.md)
- [MemGPT：上下文窗口作为有限内存](015_MemGPT：上下文窗口作为有限内存.md)
- [IterResearch、Research Synthesis 与常量大小上下文](016_IterResearch、Research_Synthesis_与常量大小上下文.md)
- [Mem0 与 A-Mem：生产级长期记忆管理](017_Mem0_与_A-Mem：生产级长期记忆管理.md)

## 6. RAG 完整链路、查询增强与评估

- [RAG 完整链路：召回、融合、重排、生成](018_RAG_完整链路：召回、融合、重排、生成.md)
- [RAG Query Rewrite：查询改写](019_RAG_Query_Rewrite_查询改写.md)
- [RAG HyDE：假设文档嵌入](020_RAG_HyDE_假设文档嵌入.md)
- [RAG Multi-Query Expansion：多查询扩展](021_RAG_Multi-Query_Expansion_多查询扩展.md)
- [Query Rewrite、HyDE 与 Multi-Query 对比](022_Query_Rewrite、HyDE_与_Multi-Query_对比.md)
- [RAGAS 评估指标与 Ground Truth 来源](023_RAGAS_评估指标与_Ground_Truth_来源.md)

## 附录

- [深度学习基础：回归、梯度下降与评估指标](附_深度学习基础：回归、梯度下降与评估指标.md)：保留机器学习基础内容，但不参与 Agent / Memory / RAG 主线编号。
- [通用学习与排查模板](附_通用学习与排查模板.md)：v11 从本目录各文件抽取的共用模板段，正文中不再重复。

文档图片统一存放在 `assets/` 下，并按主题分目录管理。
