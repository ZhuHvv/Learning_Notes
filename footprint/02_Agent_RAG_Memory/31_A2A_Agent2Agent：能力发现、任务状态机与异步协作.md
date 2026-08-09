# 02.31 A2A（Agent2Agent）：能力发现、任务状态机与异步协作

## 1. 总体性概念

A2A（Agent2Agent Protocol）是一套让独立 AI Agent 发现彼此能力、委派目标级任务、持续交换消息并交付结果的开放协议。它解决的是不同框架、语言、厂商和部署环境中的 Agent 如何互操作，不负责实现 Agent 内部的模型、Prompt、Memory、工具或工作流。

```text
Client Agent / Coordinator
          │
          │ A2A：Message / Task / Artifact
          ▼
Remote Agent / A2A Server
          │
          └── 内部模型、工作流、MCP、数据库、搜索工具……
```

A2A 只约束远程 Agent 的外部通信契约。调用方无需知道对方使用 LangGraph、ADK、CrewAI 还是自研运行时，也不要求对方暴露系统提示、思考过程或内部工具清单。

## 2. A2A 不是额外的 HTTP 功能，也不一定是独立服务

A2A 位于应用协议层，HTTP、HTTP/2 等负责承载。A2A 1.0 提供三种标准绑定：

```text
Agent 业务逻辑
    ↓
A2A 数据模型与操作语义
    ↓
JSON-RPC over HTTP | HTTP+JSON/REST | gRPC
    ↓
HTTP(S) / HTTP/2
    ↓
TCP
```

因此，“A2A 是寄宿在 HTTP 上的额外服务”只描述了常见部署外观，不能当作协议定义。实现有三种常见形态：

1. 在现有 Agent 服务中增加 A2A 标准端点；
2. 在旧系统前增加 A2A Gateway / Adapter；
3. 独立部署 A2A Server，再连接内部任务队列和 Agent Runtime。

例如第一种形态只是同一进程多暴露几组接口：

```text
Research Agent Service
├── /internal/search
├── /api/report
├── /.well-known/agent-card.json
├── /message:send
├── /message:stream
└── /tasks/{id}
```

所以更准确的表述是：A2A 通常表现为 Agent 对外增加的一组标准协议接口，但规范不要求它成为独立微服务。

## 3. 核心角色与能力发现

### 3.1 Client 与 Server 是交互角色

- **A2A Client**：发起消息或任务的一方，常见为主控 Agent、Coordinator 或业务应用；
- **A2A Server / Remote Agent**：接收请求并自主完成任务的一方。

同一个 Agent 在不同调用链中可以切换角色：

```text
Agent A ──A2A──> Agent B：A 是 Client，B 是 Server
Agent B ──A2A──> Agent C：B 又是 Client，C 是 Server
```

### 3.2 Agent Card

Agent Card 是 Agent 对外发布的自描述清单，标准发现地址为：

```text
https://{domain}/.well-known/agent-card.json
```

它通常声明：

- Agent 名称、描述和技能 `skills`；
- 服务地址与协议绑定；
- 协议版本；
- 默认输入、输出媒体类型；
- 是否支持 streaming 和 push notification；
- 身份认证要求。

简化示例：

```json
{
  "name": "Research Agent",
  "description": "搜索资料并生成调研报告",
  "supportedInterfaces": [
    {
      "url": "https://research.example.com/a2a/v1",
      "protocolBinding": "HTTP+JSON",
      "protocolVersion": "1.0"
    }
  ],
  "capabilities": {
    "streaming": true,
    "pushNotifications": true
  },
  "defaultInputModes": ["text/plain", "application/json"],
  "defaultOutputModes": ["text/markdown", "application/json"],
  "skills": [
    {
      "id": "industry-research",
      "name": "行业调研",
      "description": "搜索、分析并生成行业调研报告",
      "tags": ["research", "report"]
    }
  ]
}
```

Agent Card 负责回答“你是谁、在哪里、会做什么、怎样通信”。它是能力发现入口，不代表调用方已经获得执行权限；真实调用仍要经过认证、授权和输入校验。

## 4. 核心数据对象

### 4.1 Message 与 Part

`Message` 表示 Agent 之间的一次沟通，例如提交目标、补充要求、请求认证或询问用户。`Part` 是消息或结果的内容单元，可承载文本、结构化数据、URL 或原始二进制内容。

```json
{
  "messageId": "msg-001",
  "role": "ROLE_USER",
  "parts": [
    {
      "text": "分析 2026 年 Agentic RAG 的发展趋势",
      "mediaType": "text/plain"
    }
  ]
}
```

### 4.2 Task 与 Context

`Task` 是需要持续执行和追踪状态的工作单元。`id` 标识具体任务，`contextId` 把多个相关任务或消息关联到同一交互上下文。

```json
{
  "id": "task-123",
  "contextId": "ctx-456",
  "status": {
    "state": "TASK_STATE_WORKING"
  }
}
```

Task ID 通常由服务端产生。继续一个未终止任务时，后续 Message 携带原 `taskId` 与 `contextId`，而不是把每次补充都当成互不相关的新任务。

### 4.3 Artifact

`Artifact` 是远程 Agent 生成的正式任务产物，可以是 Markdown、PDF、图片、表格或结构化 JSON：

```json
{
  "artifactId": "report-001",
  "name": "agentic-rag-report.md",
  "parts": [
    {
      "text": "# Agentic RAG 调研报告\n...",
      "mediaType": "text/markdown"
    }
  ]
}
```

需要明确区分：

```text
Message  = 协作过程中的沟通
Artifact = 任务产生的正式结果
```

任务可以增量产生 Artifact；流式更新中 `TaskArtifactUpdateEvent` 还可表达追加片段与最后一块。

## 5. HTTP 消息体与 A2A 协议的关系

在 HTTP+JSON 和 JSON-RPC 绑定中，Message、Task、Artifact 等核心对象主要位于 HTTP Body，但整个 A2A 不能简化为“一个 Body 格式”。

### 5.1 HTTP+JSON / REST 绑定

```http
POST /message:send HTTP/1.1
Host: agent.example.com
Content-Type: application/a2a+json
A2A-Version: 1.0
Authorization: Bearer <token>

{
  "message": {
    "messageId": "msg-001",
    "role": "ROLE_USER",
    "parts": [
      {
        "text": "分析这份财务报告",
        "mediaType": "text/plain"
      }
    ]
  },
  "configuration": {
    "acceptedOutputModes": ["application/json"]
  }
}
```

其中：

```text
HTTP Method / Path  → 选择 A2A 操作
Headers             → 版本、扩展、认证、媒体类型
Body                → A2A 请求对象
状态码与响应体       → 传输结果和协议结果
```

标准 REST 操作包括发送消息、流式发送、查询任务、列出任务、取消任务和订阅任务等。`GET /tasks/{id}` 可以没有请求体，却仍然是 A2A 操作，这正说明 A2A 不只存在于 Body。

### 5.2 JSON-RPC 绑定

JSON-RPC 绑定会在 HTTP Body 中再包一层远程方法调用结构：

```json
{
  "jsonrpc": "2.0",
  "id": "request-001",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "msg-001",
      "role": "ROLE_USER",
      "parts": [{"text": "分析这份财务报告"}]
    }
  }
}
```

```text
HTTP：传输
  └── JSON-RPC：方法、参数、请求 ID 与错误包装
        └── A2A：Agent 消息、任务、状态和产物语义
```

### 5.3 gRPC 绑定

gRPC 绑定使用同一套核心操作语义，但对象通过 Protobuf 编码进 gRPC 消息帧：

```text
A2A Object
    ↓ Protobuf
gRPC Message
    ↓
HTTP/2
```

它不是普通 REST JSON Body，因此“所有 A2A 都是 HTTP Body 中的 JSON”也不成立。

## 6. 一次完整 A2A 工作流

以“调研 Agentic RAG 并生成 Markdown 报告”为例：

1. Coordinator 获取远程 Agent 的 Agent Card；
2. 检查所需 skill、输入输出模式、协议版本、streaming 能力和认证方式；
3. 选择 HTTP+JSON、JSON-RPC 或 gRPC 接口并完成认证；
4. 发送 `Message` 与可接受的输出模式；
5. 简单问题可直接得到 `Message`，复杂工作则得到 `Task`；
6. Remote Agent 在内部自主拆解任务并调用模型、MCP 或其它服务；
7. Client 通过轮询、流式订阅或 Webhook 获取状态和增量 Artifact；
8. 若状态进入 `INPUT_REQUIRED` 或 `AUTH_REQUIRED`，调用方继续向原 Task 补充信息；
9. Task 进入终止状态后，Client 获取 Artifact 并继续整合或委派给下一个 Agent。

```text
发现 Agent Card
  → 选择接口与认证
  → SendMessage
  → Message 或 Task
  → 状态更新 / 多轮补充 / 增量 Artifact
  → COMPLETED
  → 获取正式 Artifact
```

Remote Agent 内部怎样规划、是否使用 MCP、选什么模型以及是否进行反思审核，均不属于 A2A 的管辖范围。

## 7. Task 状态机与异步长任务

### 7.1 生命周期独立于单次连接

A2A 的关键能力不是“HTTP 请求用了 async”，而是 Task 可以脱离创建它的那一次连接继续存在：

在 A2A 1.0 中，`SendMessageConfiguration.returnImmediately` 用于选择调用是否在创建 Task 后立即返回：默认阻塞模式等待 Task 到达终止或中断状态；设为 `true` 时立即返回当前 Task，由调用方后续轮询、订阅或等待推送。无论初始调用采用哪种等待方式，Task 都不应依赖某一条流连接才能存在。

```text
Client                         A2A Server
  │── SendMessage ───────────────>│
  │<── Task: SUBMITTED ───────────│
  │         请求结束               │ 后台继续执行
  │                                │
  │── GetTask(task-123) ─────────>│
  │<── Task: WORKING ─────────────│
  │                                │
  │── GetTask(task-123) ─────────>│
  │<── COMPLETED + Artifact ──────│
```

流连接断开不应取消 Task 本身；客户端可重新查询或重新订阅。规范把任务生命周期与任意单个 stream 的生命周期分离。

### 7.2 状态与暂停点

典型状态包括：

| 状态 | 含义 | 是否终止 |
|---|---|---:|
| `TASK_STATE_SUBMITTED` | 已提交并确认 | 否 |
| `TASK_STATE_WORKING` | 正在执行 | 否 |
| `TASK_STATE_INPUT_REQUIRED` | 等待补充输入 | 否 |
| `TASK_STATE_AUTH_REQUIRED` | 等待认证或授权 | 否 |
| `TASK_STATE_COMPLETED` | 成功完成 | 是 |
| `TASK_STATE_FAILED` | 执行失败 | 是 |
| `TASK_STATE_CANCELED` | 已取消 | 是 |
| `TASK_STATE_REJECTED` | Agent 拒绝执行 | 是 |

```text
SUBMITTED → WORKING → INPUT_REQUIRED → WORKING
                    → AUTH_REQUIRED  → WORKING
                    → COMPLETED | FAILED | CANCELED | REJECTED
```

未终止 Task 可以继续接收 Message，因而能支持 human-in-the-loop 和 Agent 间多轮协作。终止状态不能再按原 Task 继续追加工作。

### 7.3 三种进度交付方式

| 方式 | 连接特征 | 适用场景 | 代价 |
|---|---|---|---|
| `GetTask` 轮询 | 每次独立请求 | 简单集成、低频更新 | 有延迟和空查询 |
| Streaming / Subscribe | 持续流连接；HTTP 绑定常用 SSE，gRPC 用服务端流 | 实时进度和增量产物 | 要处理重连、断开和背压 |
| Push Notification / Webhook | Server 主动 HTTP POST | 分钟或小时级任务、客户端不宜保持长连接 | 要验证回调身份并处理重试去重 |

流式事件可按如下顺序出现：

```text
Task
→ TaskStatusUpdateEvent(WORKING)
→ TaskArtifactUpdateEvent(partial)
→ TaskStatusUpdateEvent(COMPLETED)
```

## 8. A2A 只规定异步语义，不提供可靠任务执行器

生产系统仍需自己实现持久化和调度：

```text
POST /message:send
    ↓
A2A Handler：生成 task_id
    ↓
Task Repository：保存 SUBMITTED
    ↓
Kafka / RabbitMQ / Redis Queue
    ↓
Agent Worker：更新 WORKING
    ↓
保存 Artifact / Checkpoint
    ↓
更新 COMPLETED 或 FAILED
```

最小伪代码：

```python
async def send_message(request):
    task_id = generate_task_id()
    await task_repository.save(task_id, "SUBMITTED", request.message)
    await task_queue.publish(task_id)
    return {"id": task_id, "status": {"state": "SUBMITTED"}}

async def task_worker(task_id):
    await task_repository.update_state(task_id, "WORKING")
    try:
        artifact = await run_agent_workflow(task_id)
        await task_repository.save_artifact(task_id, artifact)
        await task_repository.update_state(task_id, "COMPLETED")
    except Exception as error:
        await task_repository.update_state(task_id, "FAILED", str(error))
```

A2A 负责统一 Task 的表示、查询、订阅、取消、消息和结果格式；业务系统仍负责：

- 任务持久化、消息队列和 Worker 调度；
- 幂等、重试、超时、断点恢复和分布式锁；
- Webhook 投递保证与去重；
- 权限、租户隔离、审计和故障转移。

它不是 Celery、Temporal、Kafka 或 LangGraph Checkpointer 的替代品。

## 9. A2A 与 MCP 的分工

| 对比项 | MCP | A2A |
|---|---|---|
| 通信对象 | Host / Agent ↔ 工具、资源、Prompt | Agent ↔ Agent |
| 调用粒度 | 具体操作 | 目标级任务 |
| 能力发现 | Tools / Resources / Prompts 列表 | Agent Card 与 Skills |
| 长任务 | 可由扩展或应用实现，不是传统核心抽象 | 原生 Task 生命周期 |
| 多轮协作 | 不是主要定位 | 原生支持消息续接和暂停状态 |
| 结果 | 工具结果、资源内容 | Message、状态和 Artifact |
| 控制权 | Host 通常控制调用链 | Remote Agent 自主规划内部执行 |

```text
MCP 调用：search(query="A2A protocol")

A2A 委派：调研 A2A 协议、比较 MCP，并生成一份技术报告
```

二者可以组合：

```text
Coordinator Agent
├── A2A → Search Agent    ── MCP → 搜索工具
├── A2A → Analysis Agent  ── MCP → Python / 数据库
└── A2A → Writer Agent    ── MCP → 文档工具
```

## 10. 常见误区

- **A2A 是 Agent 框架。** 它只规定跨 Agent 通信，不实现推理和编排。
- **A2A 必须独立部署。** 可以直接集成进现有 Agent 服务，也可以由适配层实现。
- **A2A 就是 HTTP Body 格式。** 它还规定操作、路径、Header、版本、状态语义和流式行为，并支持 gRPC。
- **Task 状态机自动保证可靠执行。** 状态是外部协议契约，可靠队列、持久化和恢复仍由服务端实现。
- **SSE 连接断开就意味着任务结束。** Task 生命周期应独立于某一条订阅流。
- **A2A 会暴露远程 Agent 的内部思考。** 规范只要求外部能力、消息、任务和结果契约。
- **A2A 与 MCP 二选一。** 常见架构是 A2A 负责 Agent 委派，MCP 负责 Agent 内部接入工具和数据。

## 11. 你在讨论中的理解推进

你的理解从“在 HTTP 上额外部署一个 Agent 服务”推进为三层分离：A2A 是 Agent 协作语义，JSON-RPC、HTTP+JSON 或 gRPC 是协议绑定，HTTP/2 是承载。进一步明确了 Task 是可脱离单次连接存在的异步协作资源，而后台可靠执行仍由数据库、队列和 Worker 系统保证。

## 12. 关联知识点

- `03_Function_Calling_与_MCP_工具接入.md`：模型工具决策与外部能力接入；
- `11_LangGraph_状态更新、invoke_与_stream.md`：Agent 工作流内部状态与流式执行；
- `../07_Backend_Deploy_Network/02_RPC_与_gRPC：服务间调用.md`：RPC、gRPC 和协议绑定；
- `../07_Backend_Deploy_Network/07_HTTP_Streaming、SSE、WebSocket_与_gRPC_Streaming.md`：轮询、SSE 与服务端流；
- `../06_MessageQueue/02_流量削峰、异步解耦与最终一致性.md`：可靠异步执行基础设施。

## 13. 参考资料与事实边界

- [A2A 1.0.0 官方规范](https://a2a-protocol.org/v1.0.0/specification/)
- [A2A 官方仓库](https://github.com/a2aproject/A2A)
- [A2A 1.0 变更说明](https://a2a-protocol.org/latest/whats-new-v1/)

本文按 2026 年 8 月可用的 A2A 1.0.0 正式规范整理。协议版本、操作名和字段可能继续演进，工程实现应按 Agent Card 声明的 `protocolVersion` 和具体绑定协商，不能只依据示例硬编码。
