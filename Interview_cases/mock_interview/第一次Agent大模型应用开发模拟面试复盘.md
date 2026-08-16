# 第一次 Agent / 大模型应用开发模拟面试复盘

> 目标岗位：中国国内互联网企业 Agent / 大模型应用开发工程师
> 
> 整理结构：**提问 → 我的回答 → 缺陷 → 参考答案（含具体优化方案）
> 
> **本文重点保留第一次模拟面试中暴露出的项目理解、工程设计与回答表达问题，并将后续讨论得到的优化方案回填到对应问题中。

> **代码复核说明（2026-08-12）
> 
> **本文已经依据 `industry_information_assistant` 当前仓库中的 DeepResearch V2 实际调用链修订。后文严格区分三类内容：
> 当前最重要的事实边界是：V2 虽保留了 LangGraph `StateGraph` 构图代码，但流式主链实际固定执行手写的 `_run_simplified()`；Checkpoint 能保存和加载状态，但恢复后尚未按 `phase` 跳转，而是重新进入完整手写流程；DeepResearch V2 的 Web 与 Milvus 候选没有接入普通聊天链路中的 DashScope Rerank。
> 
> **当前已实现**：能在当前默认运行路径中找到真实调用点；
> **当前边界**：代码已有结构或接口，但行为尚未闭环；
> **生产化方案**：面向并发、幂等、可靠事件和评测体系的后续设计，不能表述成项目现状。
> 
> 

---

## 1. 自我介绍

### 提问

请做一个 2～3 分钟的自我介绍，重点讲清楚：

1. 目前的工作经历，以及为什么希望转向 Agent / 大模型应用开发；
2. 在智能行业调研 Agent 系统中实际负责了哪些核心模块；
3. 相比普通后端开发，竞争这个岗位最大的优势是什么。

### 我的回答

目前从事游戏服务器开发。当前工作内容相对单调，并且和技术前沿脱离较远，因此希望改变工作方向，从事 AI 相关领域工作。

在 A要面向行业研gent 项目中主要负责后端。该项目主究业务，原本人工调研存在耗时长、格式不统一、内容质量依赖工作人员个人水平和经验等问题。项目通过六个不同功能的 Agent 协作，并结合共享状态编排、Checkpoint 状态快照、SSE 事件级细粒度推送等机制，使研究过程具备阶段可观测和来源引用能力。项目资料将目标耗时描述为约 30 分钟，但还需要准备真实运行样本、任务规模和统计口径，不能直接把它表述成已经系统验证的稳定指标。

相比普通后端开发，游戏服务器开发同样需要处理复杂状态、规则约束和异常场景，这些工程经验与 Agent 的规划、决策和执行过程存在一定共通性。

### 缺陷

1. **离职动机表达偏负面。
  
  **“当前工作内容单调且与技术前沿脱离较远”容易让面试官把注意力放在对现工作的负面评价上。

2. **Agent 项目亮点有，但缺少个人责任边界。
  
  **说了六 Agent、Checkpoint、SSE，但没有明确哪些模块是自己设计和实现的。

3. **“30 分钟”是一个容易被追问的量化指标。
  
  **需要准备：
  - 原人工流程大概耗时多久；
  - 30 分钟针对什么任务规模；
  - 是否做过多次统计；
  - 效率提升是否牺牲质量。
4. 当前仓库和学习资料中存在该目标描述，但没有足够的 benchmark 数据证明稳定达到，因此面试时应说“目标耗时”或“典型演示耗时”，除非已经补做多次统计。
5. **游戏 AI 到 Agent 的迁移逻辑还可以更完整。
  
  **除了“都是决策”，还可以补充状态建模、规则约束、异常场景处理、服务端工程能力等共通点。

### 参考答案

游戏服务器开发让我积累了两个方面的能力：一方面是服务端开发和复杂状态管理能力；另一方面是把业务目标拆解成“状态—条件—行动”的决策逻辑。我希望后续职业方向进一步聚焦到 LLM Agent 和大模型应用开发，因此自己重点做了一个智能行业调研 Agent 系统。

这个项目主要解决人工行业调研耗时长、报告格式和质量高度依赖个人经验的问题。我主要负责后端核心链路，包括 6-Agent 工作流拆分、ResearchState 共享状态管理、质量审核和回退流程、基于 asyncio.Queue 的步骤级 SSE 推送、PostgreSQL JSONB Checkpoint 原型，以及 Bocha Web Search + Milvus 的双通道检索。

架构上，仓库保留了 LangGraph `StateGraph` 构图版本，但当前为了获得 Agent 内部更细粒度的 SSE 事件，默认流式主链实际使用手写异步工作流 `_run_simplified()`。Checkpoint 已支持按 `session_id` 保存和加载状态，但当前恢复仍会重新进入完整流程，按阶段跳转、幂等和并发恢复还属于后续优化方向。

我认为自己的优势不是单纯“会调用大模型 API”，而是有传统后端和决策系统开发背景，比较关注 Agent 在真实运行中的状态、异常、恢复、可观测性和工程稳定性。我希望把这种工程能力继续迁移到 Agent 应用开发上。

---

## 2. 为什么拆成 6 个 Agent，而不是单 Agent + 多 Tool？

### 提问

这 6 个 Agent 分别负责什么？它们之间的数据和状态是怎么流转的？为什么要拆成 6 个 Agent，而不是一个 Agent 配多个 Tool？

### 我的回答

六个 Agent 分别是：

- 规划 Agent：负责整体计划，输出研究大纲，包括章节、关键实体、假设等；
- 搜索 Agent：根据规划结果从网页和知识库检索，提取事实、来源和实体关系；
- 数据分析 Agent：对数据做结构化提取，生成知识图谱和 ECharts 配置；
- 代码执行 Agent：生成、执行和修复 Python 分析代码，并生成图表；
- 写作 Agent：基于前面结果撰写和修订报告；
- 评审 Agent：审核和打分，决定是否补充搜索或修订报告。

每个 research session 都有单独的 session\_id，并维护一个 TypedDict 类型的 ResearchState，保存整体研究状态以及各 Agent 的输入输出。

拆成多个 Agent 的原因主要是职责明确、单一职责下质量更高，而且固定工作流程可以提升系统稳定性和可控性。

也尝试过单 Agent + 多 Tool 的 ReAct 模式，但长任务中所有输入输出都容易持续写入同一个上下文，更容易出现上下文膨胀甚至溢出。

### 缺陷

回答方向正确，但“为什么 Multi-Agent”还可以再系统一些。

当前主要讲了：

- 单一职责；
- 稳定性；
- 上下文问题。

还缺少两个非常重要的工程价值：


1. **故障隔离。
  
  **Search Agent 失败可以局部重试，不必重跑完整任务。

2. **上下文隔离不是 ResearchState 变小，而是 LLM 输入投影变小。
  
  **ResearchState 本身可以继续增长，但每个 Agent 只读取自己需要的字段，因此真正控制的是每次 LLM 调用的 context，而不是全局 state 大小。

### 参考答案

我们拆成 6 个 Agent 不是为了“Agent 数量更多”，而是为了把一个长研究任务拆成几个职责明确、输入输出边界稳定的阶段。

具体包括 Planner、Search、Analysis、Code、Writer 和 Reviewer。它们共享同一个 ResearchState，但不是所有 Agent 每次都拿完整状态调用 LLM，而是根据节点职责只投影自己需要的字段。例如 Search 主要读取研究大纲和章节需求，Writer 主要读取事实证据、分析结果和已有报告，Reviewer 则读取报告及相关证据。

相比单 Agent + 多 Tool，我认为 Multi-Agent 在这个场景有四个主要优势：

1. **职责隔离**：不同 Agent 的 Prompt 和输出 Schema 可以针对单一任务优化；
2. **上下文隔离**：避免所有工具调用结果长期堆积在同一个 ReAct 上下文；
3. **故障隔离**：某个阶段失败可以单独重试、回退或者重新规划；
4. **流程可控**：行业研究业务流程本身相对固定，状态机比完全开放式的 ReAct 更适合做限制、审核和恢复。

因此这个项目采用的实际上是“受控 Workflow + 局部 Agent 自主决策”的架构，而不是完全开放式自治 Agent。

需要准确补充的是：当前默认流式运行时并不是编译后的 LangGraph 图，而是 `_run_simplified()` 手工编排。LangGraph 构图代码是仓库中保留的结构化版本；不能把“代码中定义了 StateGraph”直接说成“当前线上主链由 LangGraph 驱动”。

---

## 3. ResearchState 会不会随着流程持续膨胀？

### 提问

虽然拆成 6 个 Agent，但它们共享 ResearchState。如果 ResearchState 保存各个 Agent 输入输出，它本身不是仍然会越来越大吗？

进一步：

1. 每个 Agent 调用 LLM 时拿完整 ResearchState 还是部分字段？
2. 搜索结果、代码日志等长内容是否全部放入 state？
3. 多轮审核、补搜、修订如何避免上下文再次膨胀？

### 我的回答

ResearchState 的确会逐渐变大，但各 Agent 只读取自己需要的几个字段，并将这些字段拼接到调用 LLM 的 Prompt 中，因此实际进入上下文的增长量相对较小。

搜索结果不会直接全部放入 state。以 Search Agent 为例，搜索结果会先在 Agent 内部分析，再把提取后的结构化结果写入 state。

评审 Agent 设置最大迭代轮次，到达上限后强制结束流程。

### 缺陷

回答总体正确，但还不够“生产化”。

主要缺少：

1. **原始数据和上下文数据分层。
  
  **原始搜索网页、代码日志、完整文件等应该放外部存储；ResearchState 只保存结构化摘要、引用 ID 和必要 metadata。

2. **Token Budget 机制。
  
  **不应只依赖“每个 Agent 读取字段少”，还应该在 LLM 调用前进行 token 估算。

3. **摘要/压缩触发策略。
  
  **多轮 Reviewer 可能导致历史修订和证据继续积累，需要设计增量摘要或按阶段压缩。

4. **最大轮次只解决无限循环，不直接解决上下文膨胀。**

### 参考答案

ResearchState 可以增长，但要把“全局状态大小”和“单次 LLM Context 大小”分开看。

当前代码已经通过各 Agent 自己拼接 Prompt、限制 facts 数量和截断文本来控制单次输入。例如 DeepScout 最多把前 15 条候选结果交给搜索分析 LLM，DataAnalyst 主要读取前 20 条 facts，Critic 审核内容会做长度截断。但当前尚未实现统一 Token Budget、基于 token 的动态裁剪、阶段摘要或原文对象存储。

我的设计会分三层：

#### 1. 当前已实现：ResearchState 主要保存结构化中间结果

例如 Search Agent 不把整篇网页放进 state，而是保存：

```python
{
    "claim": "...",
    "evidence": "...",
    "source_id": "...",
    "url": "...",
    "credibility": 0.85
}
```

当前 V2 主要保存网页摘要经 LLM 提取后的 facts、data points 和 references；`raw_sources` 虽然在 ResearchState 中声明，但当前 V2 没有实际写入点。

把完整原文放入数据库或对象存储、state 只保存 `source_id` 和摘要，是生产化优化方案，不是当前已经落地的行为。

#### 2. 当前已实现：每个 Agent 自己选择所需字段构造 Prompt

例如：

```
Planner  → 用户 query、历史约束
Search   → outline、search requirements
Writer   → evidence、analysis、report draft
Reviewer → report、evidence、evaluation rubric
```

这样 ResearchState 即使整体较大，也不会全部进入每一次 LLM Context。

#### 3. 生产化方案：设置统一 Context Budget

每次调用模型前估算 token：

```
prompt_tokens < context_window × safety_ratio
```

接近阈值时：

- 压缩早期中间结果；
- 只保留关键事实和引用；
- 原始内容转为外部引用；
- 对多轮修订历史做增量摘要。

同时 Reviewer 设置最大迭代轮次，用于限制流程无限循环。需要注意，`create_initial_state()` 虽默认写入 3，但当前 Graph 会用 `llm_config.py` 的配置覆盖它，当前默认 `max_iterations=1`；V2 路由中的请求参数也没有传入 Graph，因此面试时不能把“默认最多 3 轮”当作当前运行事实。

---

## 4. Checkpoint 如何恢复任务？

### 提问

项目使用 PostgreSQL JSONB 保存关键阶段完整状态快照。假设 Search Agent 后已经保存 Checkpoint，Analysis Agent 执行过程中服务崩溃。

1. Checkpoint 保存什么？
2. 根据 session\_id 加载以后，如何知道从哪个 Agent 继续？
3. 如果崩溃发生在 Agent 执行一半，如何处理？

### 我的回答

Checkpoint 中包含 ResearchState 以及前端相关数据。

通过 session\_id 加载 Checkpoint 后，根据其中的研究状态字段判断当前流程处于哪个 Agent 阶段，恢复 ResearchState 后重新执行这个阶段。

断点保存以一个完整过程结束为节点。如果某个 Agent 执行一半，它的结果不会写入 Checkpoint，因此恢复后重新执行该 Agent。

### 缺陷

这部分与当前代码不一致。当前代码会根据 `session_id` 加载 state，但没有根据其中的 phase 跳转；加载后仍重新进入完整 `_run_simplified()`，从规划阶段开始执行。

因此当前准确语义是：

> 已实现 Checkpoint 保存、加载和 resume API 原型，但尚未实现节点级恢复。

节点级恢复完成后才可以进一步讨论 at-least-once execution：只要 Agent 没成功提交对应节点的 Checkpoint，恢复时就可能再次运行该 Agent。

因此必须继续考虑：

- 节点重复执行；
- 外部副作用；
- 并发恢复；
- Checkpoint 覆盖。

### 参考答案

当前项目在首次规划、检索、分析、写作四个阶段完成后尝试保存 Checkpoint，Checkpoint 模型中包含：

- ResearchState；
- phase；
- 研究任务状态；
- 前端恢复所需信息；
- 关键 Agent 输出。

当前加载流程是：

```
session_id
    ↓
PostgreSQL 查询最新 checkpoint
    ↓
恢复 ResearchState
    ↓
读取 state_json 中的 phase
    ↓
重新进入 _run_simplified()
    ↓
从规划阶段开始重跑完整手写流程
```

因此当前代码还不能表述为“从对应 Agent 节点继续”。它实现的是状态快照保存、加载和 resume API 原型，但恢复执行器尚未根据 `phase` 映射到下一节点。已有 facts、data points 和 references 在重跑时还可能继续累积。

此外还有两个实现边界：

1. `_message_queue` 是运行时 `asyncio.Queue`，保存时仍位于 state；当前清理函数用 `json.dumps(..., default=str)` 测试后却保留原对象，在标准 PostgreSQL JSONB 序列化下存在保存失败风险；
2. 审核、补搜、修订和最终完成后没有重新保存完整 state，完成时只更新 status，因此数据库里的最终 state/report 可能仍是首次写作版本。

正确修复方向是：保存时显式排除运行时字段；为 checkpoint 增加明确的 `next_stage`；恢复时根据该字段跳转；每次审核、补搜、修订和最终完成后原子保存最新状态。

完成这些改造后，节点级恢复模型会天然属于 at-least-once execution，因此还必须配合：

1. 幂等设计；
2. 外部副作用管理；
3. execution version；
4. 并发恢复控制。

---

## 5. Agent 重试时，怎么解决外部副作用？

### 提问

假设 Code Agent 已经生成文件、上传对象存储或调用外部 API，但在保存 Checkpoint 前崩溃。恢复以后重新运行该 Agent，会产生重复操作。

怎么防止脏数据、孤儿文件或重复副作用？

### 我的回答

第一反应是确定“以最新 Agent 执行结果为准”。

给每次 Agent 执行增加标识，例如计数器，并将计数保存到 state、checkpoint 和数据库中。之后根据计数删除早期执行产生的旧结果，只保留最新结果。

### 缺陷

思路已经接近 execution version，但存在关键问题：

如果：

```
checkpoint version = 3
第 4 次执行已经生成文件
↓
还没保存 version=4
↓
进程崩溃
```

数据库根本不知道 version=4 曾经存在，因此无法准确判断该文件是不是孤儿。

此外，“重新执行以后删旧结果”属于补偿思路，但很多副作用不能简单删除，例如：

- 邮件已经发出；
- API 已经扣费；
- 外部订单已经创建。

### 参考答案

以下属于生产化方案，当前项目尚未实现。这里要区分两个概念：

#### 1. execution\_version：区分“这是第几次执行”

例如：

```
attempt 8 → execution_version = 8
attempt 9 → execution_version = 9
```

它用于防止旧执行结果覆盖新执行结果。

#### 2. Idempotency Key：标识“这两次执行其实是在做同一件业务操作”

例如：

```
session=S123
chapter=3
operation=generate_chart

idempotency_key =
S123:chapter3:generate_chart
```

第一次执行和恢复后的第二次执行：


```
execution_version = 8 / 9    # 不同
idempotency_key   = same     # 相同
```

外部系统如果支持 Idempotency Key：

```
第一次：
key 不存在 → 真正执行 → 保存 result

第二次：
key 已存在 → 不再执行 → 返回第一次 result
```

这样：

> Agent 可以重试，但业务副作用只发生一次。

#### 如果外部系统不支持 Idempotency Key

可以采用以下方案：

##### A. 固定资源键

例如图表路径固定为：

```
/{session_id}/{chapter_id}/market_share.png
```

重试时覆盖同一个逻辑资源，而不是创建随机文件。

##### B. UNIQUE + UPSERT

数据库操作以业务 key 做唯一约束：

```sql
UNIQUE(session_id, chapter_id, operation)
```

重复执行时使用 UPSERT。

##### C. staging + commit

执行过程中先写：

```
/session_123/staging/execution_8/
```

只有 Checkpoint 成功后才标记为 committed。

失败执行留下的 staging 资源通过 GC 任务清理。

##### D. 补偿事务

对于无法幂等的外部系统，记录外部操作日志，如果流程失败则执行补偿操作，例如删除临时文件、撤销中间记录。

---

## 6. 同一个 session 被两个实例同时恢复怎么办？

### 提问

假设用户连续点击两次恢复，或两个 Worker 同时尝试恢复同一个 session：

1. 怎么保证两个实例不会同时认为自己是最新执行者？
2. 怎么防止互相覆盖 Checkpoint？
3. 最终如何保证只有一个实例能够提交？

### 我的回答

第一次模拟时暂时没有明确方案。

后续讨论中提出了两个优化方向：

1. Lease 时间覆盖单个 Agent 执行时间，每个 Agent 结束并保存 Checkpoint 时刷新 Lease；
2. 更好的方式是使用较短 Lease，并通过 Heartbeat 周期性续租。

### 缺陷

仅使用 Lease 仍然存在 split-brain：

```
A 获得 lease
↓
A 与数据库网络异常
↓
lease 过期
↓
B 接管
↓
A 实际还活着
```

此时 A 和 B 可能同时工作。

因此 Lease 只能解决：

> “当前谁应该拥有执行权？”

还必须使用 fencing token / execution version 解决：

> “旧 Worker 恢复后还能不能提交？”

### 参考答案

以下属于生产化方案，当前项目目前没有 Lease、Heartbeat、execution version、fencing token 或 CAS 提交。推荐使用：

> **短 Lease + Heartbeat + execution\_version/fencing token + CAS Checkpoint**

数据库字段：

```
session_id
owner_id
lease_until
execution_version
checkpoint
current_stage
status
```

### 1. Worker 获取执行权

通过原子 UPDATE：

```sql
UPDATE research_session
SET
    owner_id = :worker_id,
    execution_version = execution_version + 1,
    lease_until = NOW() + INTERVAL '60 seconds'
WHERE session_id = :session_id
  AND (
      owner_id IS NULL
      OR lease_until < NOW()
  )
RETURNING execution_version;
```

只有一个 Worker 能成功获取 Lease。

### 2. Heartbeat 周期续租

例如：

```
Lease TTL = 60 秒
Heartbeat = 每 20 秒
```

续租必须校验：

```sql
UPDATE research_session
SET lease_until = NOW() + INTERVAL '60 seconds'
WHERE session_id = :session_id
  AND owner_id = :worker_id
  AND execution_version = :version;
```

如果 affected\_rows = 0，说明自己已经失去 ownership，应主动停止。

### 3. Checkpoint 提交同样校验 version

```sql
UPDATE research_session
SET
    checkpoint = :checkpoint,
    current_stage = :next_stage
WHERE session_id = :session_id
  AND owner_id = :worker_id
  AND execution_version = :version;
```

假设：

```
A version = 8
B 接管后 version = 9
```

即使 A 后来恢复，也无法提交 version=8 的旧结果。

### 4. Checkpoint 与 Lease 刷新放同一个事务

每个 Agent 成功结束时：

```
保存 checkpoint
+
更新 current_stage
+
刷新 lease
```

放在同一个数据库事务中，避免两者状态不一致。

### 5. Heartbeat 失败采用 Fail Closed

如果 Worker 无法确认自己仍拥有 Lease：

```
heartbeat 连续失败
↓
lost_lease = true
↓
在最近安全点停止 Agent
↓
禁止提交 checkpoint
```

不能默认“数据库暂时不可用，但我应该还是 owner”。

---

## 7. 为什么使用 asyncio.Queue + SSE？

### 提问

为什么使用 asyncio.Queue + SSE？

1. Agent 执行和 SSE 响应如何解耦？
2. Queue 具体承担什么作用？
3. 前端断开连接后 Agent 怎么处理？
4. 如果 Producer 远快于 Consumer，如何处理 Backpressure？

### 我的回答

长任务中单个 Agent 输出耗时较长，需要让用户感知任务进度。

Agent 执行过程中把事件写入异步队列，外层循环读取队列后包装成 SSE 消息返回客户端。

如果直接在 Agent 中 yield，这些中间进度消息会与 Agent 自身执行结果耦合。

当前 Queue 没有 maxsize，确实存在积压风险。最初考虑可以设置最大长度，满时丢弃最早消息，因为后面的消息通常价值更高。

### 缺陷

1. “为什么 Queue”还应该明确说出：

> Queue 的本质价值是 **解耦 Producer 与 Consumer 的执行速度和控制流**。

1. 不能简单认为“后面的事件价值更高”。

例如：

- progress 可以丢；
- final / error / chart / review result 不能随意丢。
1. Queue 没有 maxsize 时可能导致内存增长。
2. 如果 SSE consumer 退出，而 Producer 仍持有 Queue 引用，Queue 不会因为 handler 结束就立刻被 GC。

### 参考答案

当前真实结构：

```
Agent Producer
      ↓
asyncio.Queue
      ↓
SSE Consumer
      ↓
Frontend
```

`asyncio.Queue` 在当前代码中有两个核心作用：

1. **控制流解耦**：Agent 不需要直接操作 HTTP Response；
2. **速度解耦**：Agent 产生事件和客户端发送事件可以异步进行。

如果直接让 Agent `yield`，Agent 的业务执行逻辑和传输协议会强耦合。当前每个 Agent 通过 `add_message()` 同时把事件追加到 `state["messages"]` 并用 `put_nowait()` 写入 queue；Graph 为单个 Agent 创建 task，并以 0.5 秒超时轮询 queue。

需要注意：当前 queue 没有 `maxsize`，也没有可靠事件存储、事件优先级或多订阅者机制；`messages` 会在每个 Agent 完成后清空。因此现阶段它是请求内的低延迟传输通道，不是可靠消息队列。

### Backpressure 改造（当前未实现）

首先设置：

```python
asyncio.Queue(maxsize=N)
```

但不能统一 drop old。

建议给事件分类：

#### 可丢事件

```
heartbeat
progress
token_delta
“正在搜索”
```

可以：

- drop oldest；
- 合并；
- 只保留最新状态。

例如连续：

```
progress 51%
progress 52%
progress 53%
```

慢客户端只保留 `53%` 即可。

#### 不可丢业务事件

```
search_result
chart_generated
review_completed
chapter_completed
```

应可靠保存。

#### 终态事件

```
completed
failed
cancelled
```

必须持久化，不能依赖内存 Queue。


---

## 8. SSE 断开后，Agent 为什么还能继续？

### 提问

如果 SSE HTTP 请求协程因为客户端断开被取消，而 Agent 是在请求处理中启动的，为什么 Agent 不会跟着取消？

### 我的回答

实际项目中通过 `asyncio.create_task()` 把**当前单个 Agent 调用**包装成 task，同时由 SSE generator 消费 queue。

因此 SSE 断开时，已经创建的 Agent task 可能继续运行一段时间；但整个 Research Workflow 仍由当前 SSE async generator 驱动，项目没有独立 Job Worker、后台任务注册表或持久化调度器，不能保证断线后完整工作流继续，更不能保证一定保存 Checkpoint。

generator 进入 `finally` 后会把 `_message_queue` 设为 `None`。这只能停止后续事件入队，不等于 Job 生命周期已经和 HTTP 连接分离。

### 缺陷

这一回答说明了当前代码行为，但暴露出架构问题：

> Research Job 生命周期仍然依赖 SSE 请求生命周期。

如果用户：

- 刷新网页；
- Wi-Fi 闪断；
- 浏览器暂时后台；

都会影响业务任务是否完整执行。

需要明确区分：

1. **SSE disconnect**
2. **reconnect**
3. **主动 cancel**

### 参考答案

更成熟的架构是把：

```
Research Job
```

和：

```
SSE Subscription
```

彻底拆开。

#### Research Job

独立后台执行：

```
Planner
↓
Search
↓
Analysis
↓
Writer
↓
Reviewer
```

不依赖当前 HTTP Connection。

#### SSE

只负责订阅该 Job 的事件。

因此：

```
SSE disconnect
→ unsubscribe
→ Job 继续

reconnect
→ 重新订阅
→ 补发遗漏事件

cancel
→ 修改 Job 状态
→ Agent 在安全点停止
```

---

## 9. SSE 临时断线如何恢复事件？

### 提问

如果要求用户临时掉线不影响任务，但用户主动点击停止时必须真正停止 Agent，如何设计？

### 我的回答

第一次模拟中暂时没有完整设计。

当前项目已经支持用户主动停止：`POST /research/cancel/{session_id}` 在 Redis 写入一个有效期 5 分钟的 cancel flag，Graph 在 Agent 启动前和运行期间轮询；运行期间发现标记时会 `task.cancel()`。

但 `_run_simplified()` 每次开始时会先清除旧 cancel flag；取消状态也没有进入持久化 Job 模型。当前没有 SSE 重连、事件序号、可靠事件存储或断线补发。

### 缺陷

缺少：

- SSE 重新订阅；
- 事件序号；
- 可靠事件存储；
- 断线期间事件补发。

### 参考答案

事件统一增加递增 ID：

```yaml
id: 101
event: search_result
data: ...
```

可靠事件同时写入 Event Store，例如：

```
PostgreSQL event table
或
Redis Stream
```

客户端断线重连时携带最后收到的 event id。

服务端：

```
Last Event ID = 101
↓
查询 event_id > 101
↓
补发 102、103、104...
↓
切换到实时订阅
```

推荐模型：

```
Agent
  ↓
Event Store  ← 可靠事件
  ↓
SSE Subscriber

asyncio.Queue
  ↓
仅承担低延迟实时传输
```

因此 Queue 不再是唯一消息来源。

---

## 10. Web Search + Milvus RAG 链路

### 提问

规划 Agent 给出章节研究任务后：

1. Web Search 和 Milvus 怎么召回？
2. 两路结果怎么合并？
3. Rerank 怎么做？
4. 结果如何进入 ResearchState？

### 我的回答

Query 先进入 Planner，由 Planner 输出研究大纲和每章的 `search_queries`，DeepScout 再按章节执行检索。

Search Agent 中：

- Web 通过 Bocha API；
- 搜索 Query 做 MD5，用于缓存；
- 缓存未命中时对多个章节并发 Web Search；
- 本地知识库保存用户上传文件；
- 文件通过 DocMind 解析、分块；
- 使用 text-embedding 模型向量化后写 Milvus；
- 查询文本同样向量化并在 Milvus 召回；
- 初次最多并发处理 3 个章节，但单个章节内部会按 query 依次执行 Web Search 和本地检索；
- 两路结果按执行顺序追加到同一个候选列表；
- DeepResearch V2 没有调用 DashScope Rerank，而是截取候选列表前 15 条交给 LLM；
- 最后结合大纲交给 LLM 提取事实、证据和引用。

其中 MD5 缓存只是 `DeepScout` 实例上的进程内字典，没有 TTL，也不是 Redis 分布式缓存。路由每次请求会新建 V2 Service，因此缓存主要只在单次研究任务内生效。

### 缺陷

原回答把普通 Chat/RAG 链路和 DeepResearch V2 链路混在了一起。普通聊天链路确实接入了 DashScope Rerank，但 V2 DeepScout 没有调用该实现。

当前还存在以下边界：

1. 由于先执行 Web、再追加本地结果，最终又只取前 15 条，候选顺序可能让本地知识库结果被截掉；
2. 没有显式 relevance rerank，事实选择和可信度评分都依赖同一次搜索分析 LLM；
3. `kb_name` 虽进入 Service 参数，但 DeepScout 实际固定检索 `knowledge_base` collection，没有按指定知识库过滤；
4. Planner 通常生成 5～8 章，但 Scout 初次只处理 `pending_sections[:3]`，主链不会继续调度剩余章节；
5. 本地链路只有 Dense Retrieval，没有 BM25、RRF 或 source quota。

### 参考答案

### 当前真实链路

```
Planner Outline
     ↓
Search Requirements
     ↓
每章 search_queries
        ↓
逐个 query 执行
        ↓
Bocha Web Search
        ↓
Milvus Dense Search（启用本地检索时）
        ↓
按执行顺序追加到 all_results
        ↓
截取前 15 条
                   ↓
       LLM Evidence Extraction
       + Credibility Scoring
                   ↓
    facts / data_points / references
```

当前 V2 使用的本地检索是“查询向量化 → Milvus Top K”，文件上传侧的解析、分块和入库属于知识库模块；不能把普通 Chat 链路的 Rerank 自动归到 DeepResearch V2。

### 更好的 RAG 融合方案（当前未实现）

本地知识库不要只有 Dense Retrieval，可以改成：

```
Dense Retrieval ─┐
                 ├→ RRF → Top N KB
BM25 ────────────┘

Web Search ─────────→ Top N Web

        ↓
Candidate Pool
        ↓
Rerank
        ↓
Top K
```

#### 为什么用 RRF？

BM25 和向量检索 score 的量纲不同，不适合直接线性相加。

RRF 只看每一路的排名：

```
RRF(d) = Σ 1 / (k + rank_i(d))
```

可以融合：

- Dense 语义匹配；
- BM25 精确关键词匹配。

#### 如何防止本地知识库完全被 Web 挤掉？

可以增加 source quota：

```
KB 至少保留 Top N1
Web 至少保留 Top N2
```

然后再统一 Rerank。

这样可以避免候选阶段因为某一路召回规模大而完全淹没另一条链路。

---

## 11. 如果两条来源事实冲突怎么办？

### 提问

例如：

- 来源 A：市场份额 18.2%
- 来源 B：市场份额 20.1%

Search Agent 应该选择一个，还是保留冲突？

### 我的回答

当前项目没有专门兜底。

发送给 LLM 时会带上标题、出处等信息，之后主要依赖 LLM 自己判断。

### 缺陷


如果简历强调“事实可靠性、信源可信度、引用溯源”，仅依赖 LLM 自由判断会比较薄弱。

主要风险：

- LLM 可能因为文本表达更像 query 而偏向低质量来源；
- 不同来源可能采用不同统计口径，并不一定存在绝对“正确值”；
- 如果 Search 阶段直接丢掉冲突，后续 Writer 无法解释数据差异。

### 参考答案

建议 Search Agent 不直接“选一个答案”，而是把 Claim 和来源结构化：

```json
{
  "claim": "2025 年 A 公司市场份额",
  "candidates": [
    {
      "value": "18.2%",
      "source": "官方统计",
      "authority": 0.95
    },
    {
      "value": "20.1%",
      "source": "行业媒体",
      "authority": 0.70
    }
  ],
  "conflict": true,
  "resolution": "unresolved"
}
```

之后根据规则处理：

```
官方一手来源
    ↓
优先

没有一手来源
    ↓
多个独立来源交叉验证

仍然冲突
    ↓
保留 conflict
    ↓
Writer 明确说明统计口径或来源差异
```

原则：

> 不要让 LLM 在不可确认的事实冲突中偷偷猜一个结果。

---

## 12. 信源可信度评分是怎么实现的？

### 提问

简历中写了“信源可信度评分”。

新华社、国家统计局、公司官网、券商研报、自媒体如何评分？

该分数是在 Rerank 前、Rerank 后，还是作为 metadata 给 LLM？

### 我的回答

可信度评分也是通过 LLM 完成。

### 缺陷

“让 LLM 打一个分”还不足以形成稳定的工程方案。

需要进一步回答：

1. 输入哪些字段；
2. 评分 Rubric 是什么；
3. 输出格式是什么；
4. 如何降低模型评分波动；
5. 相关性与权威性如何协同；
6. 是否有人工评测集验证评分有效性。

### 参考答案

当前版本可以准确描述为：

> DeepScout 的搜索分析 LLM 在提取事实时，同时按 Prompt 中的来源类型 Rubric 生成 `source_type` 和 `credibility_score`。

它不是独立部署的 Credibility Judge，也没有单独的二阶段评分服务。代码只是把该分数作为 fact metadata，Writer 和 Critic 会在 Prompt 中看到它；当前没有硬编码 authority gating、冲突检测或人工标注集校准。

当前实际输入更接近：

```json
{
  "query": "...",
  "section_title": "...",
  "title": "...",
  "source": "...",
  "date": "...",
  "summary": "..."
}
```

Prompt 中提供明确 Rubric，例如：

```
5 - 政府、监管机构、公司官方公告、原始论文
4 - 权威研究机构、主流财经媒体
3 - 一般专业媒体
2 - 聚合站、二次转载
1 - 自媒体、来源不明
```

模型在 `extracted_facts` 中输出：

```json
{
  "content": "...",
  "source_name": "...",
  "source_url": "...",
  "source_type": "official",
  "credibility_score": 0.95
}
```

### 相关性和可信度不要混为一个分数

Reranker 主要解决：

```
这篇内容和 Query 有多相关？
```

Credibility Score 解决：

```
这个来源值得多大程度相信？
```

生产化后可以做两阶段处理：

```
Retrieval
↓
Rerank relevance
↓
Authority/Freshness filter
↓
Final candidate set
```

关键数字事实可以进一步设计 gating：

```
高相关 + 低可信
→ 不能直接作为关键事实

中相关 + 官方来源
→ 应保留

来源冲突
→ 进入 conflict resolution
```

如果没有人工标注数据做过验证，需要在面试中明确：

> 当前版本仍然属于启发式 LLM Judge，没有经过系统性校准，这是项目后续可以继续优化的点。

---

# 13. 第一次模拟面试暴露出的核心知识缺口

## 13.0 先修正“项目事实”和“设计方案”的表达层次

后续回答统一采用三段式：

```
当前代码怎么做
    ↓
当前实现有什么边界
    ↓
如果生产化，我会怎么改
```

不能把第三段直接表述成第一段。例如：

- 当前有 JSONB Checkpoint 表和 resume API，但没有按 `phase` 跳转；
- 当前有请求内 asyncio.Queue，但没有独立 Research Job 和 Event Store；
- 当前有 LLM 生成的 credibility score，但没有经过校准的权威性评分系统；
- 当前没有 Lease、Heartbeat、Fencing Token、Idempotency Key、RRF 或系统化 Evaluation。

主动说明真实边界并不会削弱项目，反而能证明自己真正读过调用链，并具备从原型走向生产的工程判断。

## 13.1 Checkpoint 不是“保存状态”这么简单

需要继续掌握：

- At-least-once execution
- Idempotency
- Idempotency Key
- execution version
- CAS
- Lease
- Heartbeat
- Fencing Token
- staging / commit
- Saga / Compensation
- 分布式任务 ownership

---

## 13.2 SSE 不只是 Streaming

需要继续掌握：

- Producer / Consumer
- asyncio.Queue 生命周期
- Backpressure
- Queue maxsize
- 事件优先级
- Job 与 Connection 生命周期分离
- SSE reconnect
- Event ID
- Event Store
- 主动 Cancel 与网络 Disconnect 的区别

---

## 13.3 RAG 要从“链路会搭”提升到“效果怎么保证”

需要继续掌握：

- Dense Retrieval
- BM25
- Hybrid Retrieval
- RRF
- Cross-Encoder Rerank
- Source Quota
- Recall@K / MRR / nDCG
- Authority Score
- Conflict Resolution
- Retrieval Evaluation

---

## 13.4 Agent 项目需要 Evaluation 闭环

虽然第一次模拟没有正式进入 Evaluation 题，但这是后续必须准备的重点。

推荐建立四层评价体系：

### L1：Final Outcome

- 报告事实准确率；
- 引用正确率；
- 章节覆盖率；
- 完成率。

### L2：Agent Node

Planner：

- 章节覆盖率；
- 重复任务率。

Search：

- Recall@K；
- MRR；
- 引用准确率。

Reviewer：

- 错误报告拦截率；
- 正确报告误杀率。


### L3：Trajectory

评估：

- Agent 调用顺序；
- 无效循环；
- 是否需要补搜；
- 是否正确停止；
- 工具调用和参数是否合理。

### L4：System Metrics

- Total Latency；
- Token Usage；
- LLM Calls；
- Tool Calls；
- Retry Count；
- Reviewer Rounds；
- Failure Rate；
- Resume Success Rate；
- Cost per Report。

最终形成：

```
线上失败 Case
    ↓
加入离线 Benchmark
    ↓
修改 Prompt / Workflow / Retrieval
    ↓
Regression
    ↓
重新上线
```

---

# 14. 第一次模拟后的项目回答主线

之后再介绍这个项目，可以把核心架构压缩成下面这条主线：

```
用户研究请求
    ↓
Planner
    ↓
分章节 Research Plan
    ↓
Search
├── Web Search
└── Milvus RAG
    ↓
Evidence / Citation
    ↓
Analysis + Code
    ↓
Writer
    ↓
Reviewer
    ├── Pass
    ├── Re-search
    └── Rewrite
    ↓
Final Report
```

横向基础设施：

```
ResearchState
    +
Checkpoint
    +
SSE Event Stream
    +
Retry / Structured Output Repair
```

需要按当前代码补充两点：

1. 以上运行主线由 `_run_simplified()` 手工编排，LangGraph 构图版本当前不是默认流式主路径；
2. Checkpoint 当前属于保存/加载原型，尚未实现根据阶段精确恢复。

进一步的生产化优化：

```
Checkpoint
→ Lease + Heartbeat + Fencing Token

Node Retry
→ Idempotency Key + staging/commit

SSE
→ Job / Subscription 分离 + Event Store

RAG
→ Dense + BM25 + RRF + Rerank + Authority

Evaluation
→ Outcome + Node + Trajectory + System Metrics
```

这一组属于“如果重新设计”的回答，不能说成当前已经落地。

---

# 15. 代码复核后新增的真实实现风险

## 15.1 初次检索没有覆盖完整大纲

DeepScout 初次只取：

```python
pending_sections[:3]
```

并发处理三个章节，单章内部的多个查询仍然串行。主链初次只调用一次 Scout，因此 Planner 生成超过三章时，后续章节没有专属检索。

面试中可回答：

> 当前为了控制外部搜索调用量，一次最多处理三个章节，但调度层尚未循环拉取剩余 pending 章节。这是当前实现缺口；应改为带并发上限的任务池，直到所有章节进入 researched 状态。

## 15.2 Agent 异常可能被吞掉

`run_agent_with_streaming()` 获取 Agent task 异常后只记录日志，没有重新抛出。Graph 可能继续进入后续阶段，并基于不完整状态生成报告。

生产化修复应包括：

- 区分可重试异常与不可重试异常；
- Agent 失败后写入结构化 error event；
- 阻止依赖节点继续执行；
- 保存 failed checkpoint 和失败节点；
- 达到重试上限后明确结束，而不是发送伪 completed。

## 15.3 审核—补搜—修订存在契约断点

当前存在三个相互关联的问题：

1. 补搜会追加 facts，但再次写作时已经 drafted 的章节可能被跳过；
2. Writer 修订主要覆盖 `final_report`，Critic 有 drafts 时却优先审核旧 `draft_sections`；
3. 最后一次未通过审核后的修订可能不再接受下一轮 Critic 审核，Graph 随后无条件标记 completed。

因此更稳妥的项目表述是：

> 项目已经实现 Reviewer 驱动的 pass、re-search、revise 路由原型，但补搜证据到章节重写、修订稿到再次审核以及超限完成语义还需要继续闭环。

## 15.4 Checkpoint 的 P0 修复项

优先顺序：

1. 保存时显式删除 `_message_queue`、`_user_id` 等运行时字段；
2. 为 checkpoint 增加 `next_stage` 或明确约定保存状态对应的下一节点；
3. resume 根据 `next_stage` 跳转，而不是重跑完整流程；
4. 审核、补搜、修订和最终完成后保存最新完整状态；
5. 为 `session_id` 增加唯一约束，并用原子 UPSERT 避免并发创建重复行；
6. 再引入 lease、heartbeat、fencing token 和幂等副作用控制。

---

---

# 16. PostgreSQL 基础补充：和本次 Agent 项目直接相关的部分

> 这一部分用于补足前文 Checkpoint、Lease、CAS、幂等设计中涉及的 PostgreSQL 基础。重点不是完整学习 PostgreSQL，而是先理解这些机制为什么能够支撑 Agent 的状态持久化、并发恢复和一致性控制。

## 16.1 JSONB：为什么适合保存 ResearchState / Checkpoint

PostgreSQL 支持 `json` 和 `jsonb` 两种 JSON 类型。

可以先这样理解：

```
json
→ 更接近“原始 JSON 文本”

jsonb
→ PostgreSQL 解析后的二进制结构化 JSON
```

对于 Agent 项目的 Checkpoint，通常更适合使用 `jsonb`，因为 ResearchState 本身就是嵌套结构，例如：

```json
{
  "session_id": "S123",
  "current_stage": "search",
  "outline": {...},
  "evidence": [...],
  "review_count": 1
}
```

可以直接保存为：

```sql
CREATE TABLE research_session (
    session_id TEXT PRIMARY KEY,
    state JSONB
);
```

写入：

```sql
UPDATE research_session
SET state = :research_state
WHERE session_id = :session_id;
```

相比把整个状态序列化成普通字符串，`jsonb` 的优势在于：

- PostgreSQL 能理解其中的字段结构；
- 可以按 JSON 字段查询；
- 可以对 JSONB 建索引；
- 更适合后续做状态分析、调试和管理。

例如：

```sql
SELECT state->>'current_stage'
FROM research_session
WHERE session_id = 'S123';
```

可以直接从 JSONB 中读取：

```
search
```

因此在本项目中：

```
ResearchState
    ↓
序列化
    ↓
PostgreSQL JSONB
```

是一个比较自然的 Checkpoint 持久化方案。

---

## 16.2 Transaction：为什么 Checkpoint 更新要放在事务里

事务可以先理解成：

> 一组数据库操作要么全部成功，要么全部失败。

最基本形式：

```sql
BEGIN;

-- 多条 SQL

COMMIT;
```

如果中间发生错误：

```sql
ROLLBACK;
```

事务中的修改不会只完成一半。

### 为什么 Agent Checkpoint 需要事务？

假设一个 Agent 执行完成以后要同时更新：

```
ResearchState
current_stage
lease_until
```

如果分别执行三条 SQL：

```
1. ResearchState 更新成功
2. current_stage 更新成功
3. lease_until 更新失败
```

数据库就可能进入不一致状态。

因此更好的做法是：

```sql
BEGIN;

UPDATE research_session
SET
    research_state = :new_state,
    current_stage = :next_stage,
    lease_until = NOW() + INTERVAL '60 seconds'
WHERE session_id = :session_id;

COMMIT;
```

这样从业务角度看：

```
Checkpoint
+
流程阶段
+
Lease
```

是一次整体状态切换。

如果失败：

```
全部回滚
```

而不是留下“半个 Checkpoint”。

---

## 16.3 MVCC：PostgreSQL 如何处理并发读写

MVCC 全称：

```
Multi-Version Concurrency Control
多版本并发控制
```

先不要陷入 PostgreSQL 内部实现，可以先记住它解决的问题：

> 多个事务同时读写数据库时，尽量不要因为一次写操作就把所有读取都阻塞。

例如：

```
事务 A
正在读取 session S123

事务 B
正在更新 session S123
```

PostgreSQL 不一定要求：


```
A 等 B
或者
B 等 A
```

而是通过不同的数据版本和事务可见性规则，让不同事务看到符合自己快照的数据。

直觉上可以理解成：

```
旧版本 row
新版本 row
```

不同事务根据自己的事务快照判断：

```
我应该看到哪个版本？
```

因此 PostgreSQL 中很多普通 `SELECT` 与 `UPDATE` 可以较高并发地运行。

对于 Agent 项目，MVCC 是 PostgreSQL 能够支持：

```
多个 session
多个 worker
多个并发请求
```

的重要基础。

但是 MVCC 本身并不能解决：

> “两个 Worker 能不能同时恢复同一个 session？”

这个问题仍然需要额外的：

- 条件 UPDATE；
- Lease；
- version；
- 行锁；

等机制。

---

## 16.4 行锁：SELECT ... FOR UPDATE 是什么

普通查询：

```sql
SELECT *
FROM research_session
WHERE session_id = 'S123';
```

只是读取数据。

如果使用：

```sql
SELECT *
FROM research_session
WHERE session_id = 'S123'
FOR UPDATE;
```

意思可以先理解为：

> 我要读取这条记录，并且在当前事务结束前锁住这条记录，防止其他事务同时修改它。

例如：

```
事务 A
BEGIN
↓
SELECT ... FOR UPDATE
↓
锁住 S123 这一行
```

这时候事务 B 如果也想修改 `S123`：

```
事务 B
UPDATE S123
```

通常需要等待 A 释放对应的行级锁。

### 为什么不建议用行锁锁住整个 Agent 执行过程？

因为 Agent 可能执行：

```
5 分钟
10 分钟
20 分钟
```

如果：

```sql
BEGIN;
SELECT ... FOR UPDATE;
```

然后持有数据库事务直到 Agent 跑完，会导致：

- 数据库连接长期占用；
- 行锁长期占用；
- 其他请求长时间等待；
- 故障后事务处理更复杂。

因此：

> 行锁适合短事务，不适合直接锁住一个几十分钟的 Agent Workflow。

这也是为什么前文更推荐：

```
短事务获取 Lease
+
后台 Heartbeat
+
execution_version
```

而不是直接：

```
FOR UPDATE 锁 30 分钟
```

---

## 16.5 Conditional UPDATE：为什么它可以实现 CAS 思想

前文多次提到了 CAS。

CAS 全称：

```
Compare And Set
```

核心思想：

> 只有当前值仍然等于我预期的值时，我才允许修改。

PostgreSQL 没有要求必须调用一个名叫 `CAS()` 的函数。

可以直接通过：

```sql
UPDATE ... WHERE ...
```

实现这个思想。

例如当前数据库：

```
session_id = S123
execution_version = 9
```

旧 Worker A 认为：

```
version = 8
```

A 执行：

```sql
UPDATE research_session
SET checkpoint = :checkpoint
WHERE session_id = 'S123'
  AND execution_version = 8;
```

数据库会先检查：

```
execution_version == 8 ?
```

实际：

```
9 != 8
```

因此：

```
affected rows = 0
```

A 就知道：

> 自己已经失去当前 session 的执行权。

Worker B 手里：

```
version = 9
```

执行：

```sql
UPDATE research_session
SET checkpoint = :checkpoint
WHERE session_id = 'S123'
  AND execution_version = 9;
```

可以成功：

```
affected rows = 1
```

因此：

```
WHERE execution_version = expected_version
```

就是 Compare。

```
SET checkpoint = ...
```

就是 Set。

这就是数据库中常见的乐观并发控制方式。

---

## 16.6 Lease + Heartbeat 在 PostgreSQL 中怎么落地

可以给 session 表增加：

```sql
CREATE TABLE research_session (
    session_id TEXT PRIMARY KEY,
    owner_id TEXT,
    execution_version BIGINT NOT NULL DEFAULT 0,
    lease_until TIMESTAMPTZ,
    current_stage TEXT,
    research_state JSONB
);
```

### 获取 Lease

Worker A 尝试获取执行权：

```sql
UPDATE research_session
SET
    owner_id = 'worker_A',
    execution_version = execution_version + 1,
    lease_until = NOW() + INTERVAL '60 seconds'
WHERE session_id = 'S123'
  AND (
      owner_id IS NULL
      OR lease_until < NOW()
  )
RETURNING execution_version;
```

如果返回：

```
execution_version = 8
```

说明 A 成功获取执行权。

如果没有返回任何行：

```
说明当前 session 已经被其他有效 Worker 占用
```

### Heartbeat 续租

A 每隔 20 秒：

```sql
UPDATE research_session
SET lease_until = NOW() + INTERVAL '60 seconds'
WHERE session_id = 'S123'
  AND owner_id = 'worker_A'
  AND execution_version = 8;
```

如果：

```
affected rows = 1
```

继续运行。

如果：

```
affected rows = 0
```

说明：

```
ownership 已经发生变化
```

A 应停止后续执行。

### 为什么 Heartbeat 还必须带 version？

因为：

```
A version=8
↓
Lease 过期
↓
B 接管
↓
version=9
```

A 后来恢复。

如果只检查：

```
owner_id
```

可能出现错误续租。

因此：

```
owner_id + execution_version
```

一起构成当前执行者身份。

---

## 16.7 UNIQUE：数据库如何帮助防止重复业务数据


假设一个章节只允许存在一张正式图表：

```
session_id
chapter_id
chart_type
```

可以建立唯一约束：

```sql
CREATE TABLE chart (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT,
    chapter_id TEXT,
    chart_type TEXT,
    url TEXT,

    UNIQUE(session_id, chapter_id, chart_type)
);
```

那么：

```
S123 + chapter3 + market_share
```

最多只能存在一条。

第一次插入：

```sql
INSERT INTO chart(...)
VALUES (...);
```

成功。

第二次重复：

```sql
INSERT INTO chart(...)
VALUES (...);
```

会发生唯一键冲突。

这个机制可以直接帮助实现：

```
幂等
去重
防重复写入
```

---

## 16.8 ON CONFLICT：UPSERT 是什么

有些时候我们不希望重复插入直接报错，而是：

> 如果不存在就 INSERT；如果已经存在就 UPDATE。

这就是 UPSERT。

PostgreSQL 可以写：

```sql
INSERT INTO chart (
    session_id,
    chapter_id,
    chart_type,
    url
)
VALUES (
    'S123',
    'chapter3',
    'market_share',
    'new_url'
)
ON CONFLICT (
    session_id,
    chapter_id,
    chart_type
)
DO UPDATE SET
    url = EXCLUDED.url;
```

意思是：

```
不存在
→ INSERT

已经存在
→ UPDATE
```

对于 Agent 重试非常有用。

例如 Code Agent 第一次：

```
写 chart
```

恢复以后第二次：

```
仍然写同一个业务 chart
```

数据库不会创建第二条重复记录，而是更新原来的逻辑资源。

---

## 16.9 PostgreSQL 中 Idempotency Key 怎么实现

可以建立：

```sql
CREATE TABLE idempotent_operation (
    idempotency_key TEXT PRIMARY KEY,
    status TEXT,
    result JSONB
);
```

例如业务操作：

```yaml
S123:chapter3:generate_chart
```

第一次：

```sql
INSERT INTO idempotent_operation (
    idempotency_key,
    status
)
VALUES (
    'S123:chapter3:generate_chart',
    'running'
);
```

因为 `idempotency_key` 是主键，所以同一个 key 不能重复创建。

完成以后：

```sql
UPDATE idempotent_operation
SET
    status = 'completed',
    result = '{"url":"..."}'
WHERE idempotency_key =
      'S123:chapter3:generate_chart';
```

恢复后的 Worker 再执行前：

```sql
SELECT *
FROM idempotent_operation
WHERE idempotency_key =
      'S123:chapter3:generate_chart';
```

如果已经：

```
completed
```

可以直接使用已有结果。

需要注意：

> 仅仅建立一张 Idempotency 表并不能自动解决所有外部副作用。

如果：

```
OSS 上传成功
↓
数据库 idempotency result 写入前崩溃
```

仍然可能出现孤儿资源。

因此如果外部系统本身不支持 Idempotency Key，还要结合：

- 固定资源 key；
- staging / commit；
- 外部操作日志；
- 补偿删除；

一起使用。

---

## 16.10 Isolation Level：先知道它解决什么

事务隔离级别解决：

> 多个事务并发执行时，一个事务能够看到其他事务的哪些变化。

现阶段先记住 PostgreSQL 常见的几个名字：

```
Read Committed
Repeatable Read
Serializable
```

在大多数普通 PostgreSQL 应用中，默认使用：

```
Read Committed
```

当前 Agent 项目不需要一开始就依赖 Serializable 来解决所有并发问题。

对于 session 恢复更推荐：

```
明确的业务并发控制
=
Lease
+
execution_version
+
conditional UPDATE
```

而不是简单把事务隔离级别拉到最高。

---

## 16.11 把 PostgreSQL 机制映射回 Agent 项目

最终可以建立下面这张对应关系：

```
ResearchState
    ↓
JSONB
    ↓
保存复杂 Agent 状态


Agent 完成一次阶段
    ↓
Transaction
    ↓
Checkpoint + stage + lease 原子更新


多个请求同时操作数据库
    ↓
MVCC


短时间需要独占某一行
    ↓
SELECT ... FOR UPDATE


两个 Worker 竞争同一个 session
    ↓
Conditional UPDATE
+
Lease


防止旧 Worker 覆盖新 Worker
    ↓
execution_version
+
WHERE version = expected_version
+
affected rows


同一业务副作用可能被重试
    ↓
Idempotency Key
+
UNIQUE


重复写同一个逻辑资源
    ↓
ON CONFLICT / UPSERT
```

### 当前阶段最需要真正掌握的 PostgreSQL 知识

优先级建议：

```
第一优先：
Transaction
Conditional UPDATE
UNIQUE / ON CONFLICT
JSONB

第二优先：
MVCC
Row Lock
Isolation Level

第三优先：
索引
执行计划
连接池
WAL
Replication
```

对于当前 Agent 应用开发面试，第一、第二优先级已经足够支撑大部分 Checkpoint、幂等、恢复和并发相关问题。

# 17. 一句话总结第一次模拟

第一次模拟说明：

> 当前已经具备比较完整的 Agent 概念和系统设计知识，但第一次回答把部分生产化方案当成了项目现状，并混淆了 DeepResearch V2 与普通 Chat/RAG 的部分实现。下一阶段最重要的是先准确掌握默认运行链，再补足并发一致性、任务生命周期、幂等恢复、RAG 质量评估和 Agent Evaluation。

后续模拟应逐步减少“项目流程是什么”的基础问题，增加：

- 并发场景；
- 异常场景；
- 架构取舍；
- 性能与成本；
- Evaluation；
- 真实代码实现；
- “如果重新设计会怎么做”的系统设计题。
