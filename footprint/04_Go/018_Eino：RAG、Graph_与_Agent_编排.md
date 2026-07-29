# Eino：RAG、Graph 与 Agent 编排

> 所属主线：Go AI 应用  
> 难度：深入  
> 前置知识：Context、SSE、接口与组件编排  
> 学习目标：理解 RAG 数据链路、Graph/Workflow 与 ADK Agent

## 1. 总体性概念

Eino 是 Go 生态 LLM 应用编排框架，可组合 prompt、model、retriever、indexer、graph/runnable 构建 RAG/Agent。


## 2. 原理性解释

- 组件有明确输入输出。
- RAG pipeline 包括 loader、splitter、embedding、indexer、retriever、generator。
- Go 项目要处理 context、错误和类型。
- 可结合 SSE 输出流式结果。

### Eino 的价值在于把 LLM 应用拆成可编排组件

CloudWeGo Eino 把 prompt、model、retriever、tool、graph、runnable 等抽象为组件，使 RAG/Agent 可以像数据流一样组合。`knowledge_index_pipeline`、`ChatTemplate`、`StreamReader` 等对象，本质上都围绕“输入 → 组件处理 → 输出”组织链路。

这比把所有逻辑写在一个 handler 里更利于测试、替换模型、接入流式输出和监控。

Eino 同时提供 ADK（Agent Development Kit），用于 Agent 接口、事件流、Runner、顺序/并行/循环等协作模式、interrupt/resume 和 human-in-the-loop。Graph/Workflow 更适合确定性数据流，ADK 更适合由 Agent 决策工具调用和协作方式；二者可以组合，而不是互相替代。

## 3. 机制流程

1. 文件进入 loader。
2. 切分 embedding 入库。
3. 问题经 retriever 召回。
4. prompt + model 生成。
5. stream 返回。

### Eino 风格 RAG 流程

```text
User Query
  ↓ Prompt Template
Retriever / Knowledge Index
  ↓
Documents + History
  ↓ ChatModel Stream
  ↓
SSE 输出 token / message
```

工程排查时要分别看：pipeline 是否成功建立索引、metadata 过滤表达式是否正确、retriever 是否返回文档、stream reader 是否被持续消费。

## 4. 类比理解

像 Go 版 AI 应用流水线搭建工具。

## 5. 应用举例 / 代码或伪代码

```go
rag := Chain(
    Retriever(vectorDB),
    Prompt("基于资料回答: {context}\n问题:{question}"),
    Model(llm),
    Parser(),
)
```

## 6. 工程边界

- 索引链路和在线问答链路应分开观察：前者关注切分、embedding 和写入，后者关注检索、提示词、模型与流式输出。
- Context 应贯穿模型、Retriever、Tool 和输出消费者，避免客户端断开后后台任务继续运行。
- 流式 Reader 必须被持续消费并正确关闭；SSE 只是传输层，不负责保存 Agent 状态。
- Agent 的 interrupt/resume 需要可持久化的检查点或会话状态，不能只依赖进程内变量。
- 示例中的 `Chain(...)` 是帮助理解的伪代码，实际 API 应以当前 Eino 官方文档和所用版本为准。
