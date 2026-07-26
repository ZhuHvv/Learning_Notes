# Claude Code Prompt 前缀缓存与三级上下文

> 所属分类：Claude Code 源码与机制解读  
> 整理日期：2026-07-21；审查更新：2026-07-26
> 核心问题：Claude Code 所谓的“三级缓存”是什么，为什么追加后续内容时旧前缀仍然可以复用？

## 1. 总体性概念

Claude Code 会在每次模型调用时重新提交当前请求所需的上下文，但模型服务端可以复用与旧请求完全相同的前缀计算结果。为了提高命中率，Claude Code 按“由稳定到易变”的顺序组织请求：

| 层级 | 典型内容 | 变化频率 |
|---|---|---|
| System prompt | 核心指令、工具定义、输出风格、部分运行环境信息 | 很低 |
| Project context | `CLAUDE.md`、自动记忆、项目规则 | 通常在会话边界变化 |
| Conversation | 用户消息、模型回复、工具调用与结果 | 每轮追加 |

因此，“三级缓存”更准确的说法是**三级上下文布局**：它们不是三个彼此独立、可以任意命中的缓存池，而是共同组成一条需要从开头精确匹配的请求前缀。

```text
[System prompt] → [Project context] → [Conversation] → [本轮新增内容]
      最稳定                                               最易变化
```

## 2. Prompt Cache 的前缀匹配

假设上一轮请求为：

```text
P = [系统提示词][项目上下文][对话 A][对话 B]
```

下一轮只在末尾追加内容：

```text
P' = [系统提示词][项目上下文][对话 A][对话 B][新消息 C]
```

`P` 是 `P'` 的完整前缀。服务端可以复用 `P` 已完成的预填充计算，只处理新增的 `C`。如果前缀中间发生变化：

```text
[系统提示词][修改后的项目上下文][对话 A][对话 B][新消息 C]
```

从修改位置开始，后续 token 的计算结果都可能不同，因此修改点之后不能继续命中旧缓存。

在 Claude API 的实际请求结构中，前缀顺序是：

```text
tools → system → messages
```

缓存断点标记的是“从请求开头到当前 block 为止的完整前缀”，不是只缓存被标记的那个 block。例如断点位于第一条用户消息之后，逻辑缓存对象是：

```text
全部 tools + 全部 system + 第一条 user message
```

Claude Code 与 Claude API 官方文档都强调：缓存采用请求开头的精确前缀匹配，不是按文件或任意片段独立缓存，也不是语义相似度命中。

### 2.1 自动缓存与显式断点

Claude API 支持两种方式：

- 自动缓存：在请求顶层设置 `cache_control`，断点自动移动到最后一个可缓存 block；
- 显式断点：在具体 content block 上设置 `cache_control`，精确控制稳定前缀边界。

增长式对话中的自动缓存大致表现为：

```text
第一轮写入：tools + system + U1
第二轮读取：tools + system + U1
第二轮写入：tools + system + U1 + A1 + U2
第三轮读取：tools + system + U1 + A1 + U2
```

缓存项要等到第一次响应开始后才可用。两个完全相同的首次请求若同时并发发出，后一个请求不一定能命中尚未建立完成的缓存。

### 2.2 20-block 回溯窗口

当最终断点自身没有对应缓存项时，服务端会向前查找以前真正写入过的缓存位置：

```text
当前断点 → 前一个 block → ... → 最多检查 20 个位置
```

这里的 20 指 **content block**，不是 20 个 token、20K token、20 条 message 或 20 轮对话。一个 message 可以包含多个 text、image、tool use 或 tool result block。

三个关键规则：

1. 缓存只在断点处写入，不会为前面的每个 block 自动生成缓存项；
2. 读取时寻找的是旧请求真正写入过的前缀，不是临时发现一段稳定内容就现场缓存；
3. 每个断点最多回溯 20 个 block，可使用多个显式断点覆盖不同稳定区域；当前 API 最多允许 4 个断点槽位。

例如：

```text
Turn 1：Block 1 ... 10 [写入]
Turn 2：Block 1 ... 15 [断点] → 回溯到 10，命中
Turn 3：Block 1 ... 35 [断点] → 只检查 35...16，找不到 15
```

因此，在一轮中一次追加大量 content block 时，即使旧缓存仍在 TTL 内，也可能因为超出回溯窗口而无法被找到。

## 3. 为什么未来内容不会改变旧前缀

根本原因是 Decoder-only 模型使用 **Causal Mask（因果掩码）**。第 `i` 个 token 只能注意到位置 `1...i`，不能看到未来位置。

```text
旧请求：[A B C]
新请求：[A B C D E]

A 只能看 A
B 只能看 A、B
C 只能看 A、B、C
D 可以看 A、B、C、D
E 可以看 A、B、C、D、E
```

追加 `D、E` 后，`A、B、C` 可见的输入没有变化，所以它们在各层产生的隐藏状态以及 Key/Value 结果也不会变化。新 token 只需生成新的 Query，并读取旧前缀已经计算好的 Key/Value。

简化表示为：

```text
旧前缀：保存 K_A/V_A、K_B/V_B、K_C/V_C

生成 D：Q_D 注意旧 K/V，并生成 K_D/V_D
生成 E：Q_E 注意 A...D 的 K/V，并生成 K_E/V_E
```

所以“注意力不会变化”需要更精确地表达：

- 旧 token 对其可见历史的注意力结果不变；
- 新 token 对旧前缀的注意力需要重新计算；
- 最终输出当然会受新增内容影响，因为输出位置能够看到新增内容。

如果使用 BERT 一类双向注意力模型，旧 token 可以看后续 token，追加内容可能改变旧 token 的表示，就不能直接采用相同的追加式复用逻辑。

## 4. KV Cache 与 Prompt Cache 的关系

两者相关，但所处范围不同：

| 概念 | 主要作用范围 | 作用 |
|---|---|---|
| KV Cache | 一次生成过程，或服务端可复用的前缀状态 | 避免生成每个新 token 时重复计算旧 token 的 K/V |
| Prompt Cache | 多次 API 请求之间 | 识别相同请求前缀，复用其服务端预填充结果 |
| Claude Code 本地会话 | 客户端持久化 | 保存消息与状态，供恢复会话；不等于模型计算缓存 |
| Memory / `CLAUDE.md` | 提供长期或项目知识 | 属于模型输入内容，本身不是 KV 计算缓存 |

可以把 Prompt Cache 理解为：把“已经为某段请求前缀建立好的模型计算状态”跨请求保留一段时间。

## 5. 哪些变化容易破坏缓存

- 修改 system prompt 或工具定义：位置靠前，通常导致其后的项目上下文和对话全部失配。
- 切换模型：不同模型不能复用同一套模型计算结果。
- 改变影响缓存键的推理配置：具体字段取决于 Claude Code 和模型版本。
- 执行 `/compact`：历史对话被摘要替换，对话层需要重建；稳定的前两层仍可能命中。
- 在会话中连接、断开 MCP 或改变实际发送的工具集合：可能改变 system/tool 前缀。
- 缓存超过 TTL：即使请求文本相同，也可能需要重新创建缓存。

普通文件编辑通常不会倒改已经存在的历史消息。若 Claude Code 之后重新读取文件，新内容会作为后续消息追加，因此旧前缀仍然成立。

按 `tools → system → messages` 的层级，可进一步整理为：

| 修改内容 | Tools 前缀 | System 前缀 | Messages 前缀 |
|---|---|---|---|
| 工具名称、描述或参数 Schema | 失效 | 失效 | 失效 |
| System 内容 | 保留 | 失效 | 失效 |
| 历史消息 | 保留 | 保留 | 从修改位置起失效 |
| `tool_choice` | 保留 | 保留 | 失效 |
| 添加、删除或改变图片 | 保留 | 保留 | 失效 |
| 改变 Claude API 的 thinking 参数 | 保留 | 保留 | 失效 |

例如 Claude Code 在会话中增加一个 MCP 工具，若实际发送的 `tools` 数组从：

```text
Read + Write + Bash
```

变成：

```text
Read + Write + Bash + PostgreSQL MCP
```

由于变化发生在最前面的 tools 层，后续 system 和 messages 前缀也不能继续按原键命中。

这里要区分 Claude Code 的 **effort level** 与 Claude API 请求中的 **thinking 参数**：

- 当前 Claude Code 官方 Prompt Caching 文档说明，effort level 不属于 prompt，也不进入 Claude Code 的 cache key，中途调整不会导致缓存失效；
- Claude API 的工具缓存文档说明，改变实际发送的 thinking 参数会使 messages 层缓存失效；
- 因此不能把“调整 Claude Code effort”和“改变 API thinking 配置”写成同一个动作。

### 5.1 如何确认是否真的命中

不能只凭响应速度判断，应检查 API usage：

```json
{
  "cache_creation_input_tokens": 0,
  "cache_read_input_tokens": 100000,
  "input_tokens": 50
}
```

含义分别是：

```text
cache_read_input_tokens      = 从已有缓存读取的输入 token
cache_creation_input_tokens  = 本次新写入缓存的输入 token
input_tokens                 = 最后缓存断点之后按普通输入处理的 token
```

总输入量可按三者相加理解。首次请求通常以创建为主，后续增长请求通常同时包含缓存读取和新增缓存写入。

若创建与读取字段都是 0，常见原因是没有启用缓存，或可缓存前缀没有达到当前模型的最小 token 门槛。门槛、TTL、价格和模型支持范围会变化，应以当前官方文档为准。

### 5.2 TTL 与 Claude Code 的实际共享范围

当前 Claude API 提供 5 分钟与 1 小时两种 TTL。Claude Code 会按认证方式选择默认值：

- Claude 订阅通常使用 1 小时 TTL；若超出套餐额度并转为 usage credits，会降为 5 分钟；
- API key、Bedrock、Vertex、Foundry 等按 token 计费的路径默认使用 5 分钟；
- `ENABLE_PROMPT_CACHING_1H=1` 可为后者请求 1 小时 TTL，`FORCE_PROMPT_CACHING_5M=1` 可强制 5 分钟。

“同一账号的任何会话都能互相命中”也不准确。Claude Code 的 system prompt 会包含工作目录、平台、Shell、系统版本、Auto memory 路径和启动时 Git 状态等信息，因此：

- 同一机器、同一目录、相同启动状态的并行 session 更可能共享前缀；
- 不同目录或不同 worktree 通常会因工作目录不同而失配；
- 即使目录相同，启动时分支或 Git 状态快照不同也可能使前缀不同。

底层 API 缓存的组织隔离范围更宽，但 Claude Code 注入的环境内容使产品层的有效共享范围通常更窄。

## 6. Claude Code 的工程设计取向

Prompt Cache 要求前缀稳定，因此 Claude Code 的多项公开行为都采用追加或延迟生效：

- Plan Mode 和 Skills 的指令作为后续 conversation message 注入，因此不需要改写已有前缀；
- MCP Tool Search 可延迟加载完整工具 schema，但工具名称集合仍需稳定；工具集合改变仍会使前缀失配；
- `/compact` 的摘要请求复用主会话的 system、tools 与历史，并在末尾追加摘要指令，因此摘要生成本身可以读取已有前缀缓存；
- 修改已加载的 `CLAUDE.md` 或 output style 不会中途改写请求：它们通常到 `/clear`、`/compact` 或重启后才重新加载。

这反映了一个通用 Agent Harness 原则：**稳定内容靠前，动态内容靠后，状态尽量追加而不是回写前缀。**

## 7. 你在讨论中的理解推进

- 起点：把 Claude Code 的缓存理解为 System prompt、Project context、Conversation 三个独立缓存层。
- 修正：三层首先是请求布局；底层依赖的是从请求开头开始的精确前缀匹配。
- 追问：后续内容是否会改变旧 token 的注意力，从而使旧结果不可复用。
- 关键理解：因果注意力禁止旧 token 看到未来内容，所以追加新 token 不会改变旧 token 的隐藏状态和 K/V；变化发生在新 token 如何注意旧前缀。
- 最终连接：Claude Code 通过稳定前缀布局获得跨请求 Prompt Cache，模型则通过因果注意力和 KV 状态使这种计算复用成立。

## 8. 常见误区

- **误区：三层可以分别按任意片段命中。** 实际核心是从请求开头开始的连续前缀匹配。
- **误区：命中缓存后客户端不用再提交上下文。** API 请求仍需表达完整上下文，只是服务端避免重复模型计算。
- **误区：新增内容不会影响任何注意力。** 新 token 的注意力会变化，旧 token 的历史表示不变。
- **误区：Prompt Cache 等同于本地聊天记录。** 一个是服务端模型计算复用，一个是客户端消息持久化。
- **误区：缓存命中等于免费。** 缓存读取通常仍计费，只是价格与延迟低于重新处理普通输入；具体费率和 TTL 以当前官方说明为准。

## 9. 关联知识点

- `../01_LLM_Transformer/003_Q_K_V_注意力机制.md`
- `../01_LLM_Transformer/007_Causal_Mask、自回归生成与_KV_Cache.md`
- `../02_Agent_RAG_Memory/001_Prompt_工程：User_Prompt_与_System_Prompt.md`
- `../02_Agent_RAG_Memory/004_Agent_Skills_模块化能力扩展.md`
- `002_Claude_Code_流式输出、max_tokens_与恢复机制.md`
- `003_Claude_Code_代码检索：ripgrep_与_grep.md`
- `004_Claude_Code_上下文压缩、Microcompact_与状态恢复.md`

## 10. 参考资料与事实边界

- [Claude Code Prompt Caching](https://code.claude.com/docs/en/prompt-caching)
- [Claude API Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Claude API Tool Use with Prompt Caching](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching)
- [Anthropic 工程文章：Prompt caching is everything](https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything)
- 本次梳理的源码架构博客：`https://xiaolinnote.com/claudecode/source/cc_source.html`
- 本次补充讨论记录：`https://chatgpt.com/share/6a6456db-7640-83ec-9c0d-5833820420cc`

官方公开的是完整前缀顺序、断点、20-block 回溯、常见失效条件和 usage 字段；底层缓存的物理存储、分片、序列化方式、哈希算法和缓存内容的具体张量格式没有全部公开，不应凭推测补全。

## 11. 复习检查问题

1. 为什么“三层上下文”不等于三个独立缓存池？
2. 为什么把新 token 追加到末尾不会改变旧 token 的 K/V？
3. Prompt Cache 与单次生成中的 KV Cache 有什么联系和区别？
4. 为什么修改 system prompt 的代价通常高于追加一条用户消息？
5. `/compact` 为什么主要使对话层失配，而稳定前缀仍可能复用？
6. 20-block 回溯查找的是稳定文本，还是此前真正写入过的缓存项？
7. 应通过哪些 usage 字段确认缓存创建和读取？
