# LangGraph 状态更新、invoke 与 stream

> 所属分类：Agent / RAG / Memory  
> 修订版本：v11  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

LangGraph 类框架把 Agent 表示为状态图；invoke 通常最终返回完整结果，stream 则逐步输出节点事件、状态增量或 token。


## 2. 原理性解释

- 节点读取 state，结束时返回 state update。
- 节点内部 LLM 可以流式吐 token，但图状态通常在节点返回后合并。
- 工具调用结果应结构化写回 state。
- 要区分 UI 流、LLM token 流、图状态更新。

### LangGraph 的状态更新与流式输出要分开理解

图式 Agent 的节点通常以 state 为输入，返回对 state 的增量更新。即使节点内部调用 LLM 可以 token-level stream，图状态也往往要等节点函数返回后才能提交。这就是你追问“节点内部多轮执行是否会整个节点结束后才更新状态”的关键。

`invoke()` 更像一次性运行直到终点并返回最终 state；`stream()` 则把节点执行过程中的事件、状态增量或消息分块暴露给调用方。但 stream 能看到什么，取决于框架是否在节点内部主动 yield 事件，而不是只看 LLM 是否支持流式。

## 3. 机制流程

1. 输入初始 state。
2. 执行节点。
3. 节点内部可 emit token。
4. 节点结束返回 update。
5. stream 产出事件给前端。

### invoke 与 stream 抽象流程

```python
# invoke
state = initial
while node := next_node(state):
    delta = node(state)
    state.update(delta)
return state

# stream
for event in graph.stream(initial):
    yield event  # 可能是节点开始、token、工具结果、state delta
```

工程上如果想让用户提前看到 LLM 输出，不需要自己在节点内部把 token 转发到 SSE/WebSocket：LangGraph（含 1.0）原生支持 `graph.stream(..., stream_mode=...)`，常用四种模式——`"values"`（每步之后的完整状态）、`"updates"`（每步的状态增量）、`"messages"`（自动流出节点内部 LLM 的 token）、`"custom"`（节点内用 `get_stream_writer()` 发送自定义事件）。服务端只需消费 `stream()` 产出的事件流，再转成 SSE/WebSocket 给前端即可。

## 4. 类比理解

invoke 像等会议纪要，stream 像实时听会议。

## 5. 应用举例 / 代码或伪代码

```python
from langgraph.config import get_stream_writer

def node(state):  # LangGraph 节点签名：def node(state) -> dict
    writer = get_stream_writer()  # 事件经 stream_mode="custom" 流出
    text = ""
    for chunk in llm.stream(state["prompt"]):
        text += chunk.content
        writer({"type": "token", "data": chunk.content})
    return {"answer": text}

# 调用方：stream_mode="messages" 可直接流出节点内 LLM token，无需手写 writer
for mode, event in graph.stream(inputs, stream_mode=["messages", "custom"]):
    handle(mode, event)
```

## 6. 你在讨论中的理解推进

你问节点内部多轮执行是否要等结束才更新状态；答案是流式输出可以提前，正式 state 合并取决于框架。

