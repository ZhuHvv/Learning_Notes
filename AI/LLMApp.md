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
