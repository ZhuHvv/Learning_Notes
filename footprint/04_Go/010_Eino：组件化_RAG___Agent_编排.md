# Eino：组件化 RAG   Agent 编排

> 所属分类：Go / Gin / Runtime  
> 修订版本：v11 审查修订版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Eino 是 Go 生态 LLM 应用编排框架，可组合 prompt、model、retriever、indexer、graph/runnable 构建 RAG/Agent。


## 2. 原理性解释

- 组件有明确输入输出。
- RAG pipeline 包括 loader、splitter、embedding、indexer、retriever、generator。
- Go 项目要处理 context、错误和类型。
- 可结合 SSE 输出流式结果。

### Eino 的价值在于把 LLM 应用拆成可编排组件

CloudWeGo Eino 把 prompt、model、retriever、tool、graph、runnable 等抽象为组件，使 RAG/Agent 可以像数据流一样组合。你项目中 knowledge_index_pipeline、ChatTemplate、StreamReader，本质上都是围绕“输入 → 组件处理 → 输出”的链路组织。

这比把所有逻辑写在一个 handler 里更利于测试、替换模型、接入流式输出和监控。

> 现状（2026）：Eino 由 CloudWeGo 持续活跃维护；自 v0.5 起发布了 ADK（Agent Development Kit），提供多 Agent 编排、interrupt/resume、human-in-the-loop 等能力，已成为该框架的主线方向，构建 Agent 应用时应优先了解 ADK。

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

## 6. 你在讨论中的理解推进

你接触 Eino、Milvus、jieba、embeddings；关键是把 RAG/Agent 放进 Go 后端工程。

