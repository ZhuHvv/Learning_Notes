# JSON、XML 与正则提取

> 所属分类：Python / Async / FastAPI  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

JSON 是结构化数据格式，XML 是标签式边界，正则可提取模式文本；LLM 工具调用常用 XML 包 JSON。


## 2. 原理性解释

- json.load 读文件对象，json.loads 读字符串。
- XML 标签适合标记区域。
- `.*?` 是非贪婪匹配。
- re.DOTALL 让点号匹配换行。

### JSON、XML、正则在 LLM 工具协议里各司其职

JSON 适合机器解析结构化参数；XML/标签适合在 prompt 中划分语义区域；正则适合从模型输出中提取被标签包住的片段。你看到的 `re.search(r"<tool_call>(.*?)</tool_call>", content, re.DOTALL)` 中，`.*?` 是非贪婪匹配，`re.DOTALL` 让点号能跨行匹配。

```python
m = re.search(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL)
if m:
    payload = json.loads(m.group(1))
```

## 3. 机制流程

1. 输出 XML 包裹 JSON。
2. 正则提取。
3. json.loads 解析。
4. 校验字段。

### 解析流程

```text
LLM 输出文本
  ↓ 正则定位 tool_call 标签内部内容
JSON 反序列化
  ↓
校验 name / arguments
  ↓
调用对应工具函数
```

如果模型可能输出多个 tool_call，用 `re.findall` 或更严格的解析器；如果安全要求高，不要只靠正则，应尽量使用模型 API 原生 tool calling。

## 4. 类比理解

XML 是包装盒，JSON 是表单，正则负责取出表单。

## 5. 应用举例 / 代码或伪代码

```python
m = re.search(r"<tool_call>(.*?)</tool_call>", content, re.DOTALL)
call = json.loads(m.group(1))
```

## 6. 你在讨论中的理解推进

你从 json.load 问到 XML prompt 和正则提取，最终理解结构化边界和参数解析。

## 7. 常见误区与排查思路

- 只背名词，不知道它在完整链路中的输入、输出和失败模式。
- 只看正常路径，忽略异常、超时、权限、重复和可观测性。
- 把相邻概念混用，导致设计或排查时定位错误。

## 8. 关联知识点

- 回到 00_总体索引.md 查看上下游知识点。
- 结合 00_总体知识网络图.md 理解跨模块关系。

## 9. 复习检查问题

- 它解决的核心问题是什么？
- 它的输入、输出和中间状态分别是什么？
- 它在真实项目中最容易出错的边界条件是什么？
- 它和上游、下游知识点如何连接？

## 10. 更细的工程拆解

**JSON、XML 与正则提取** 在 Python 工程中通常关系到“运行时行为”而不是语法表面：

1. **生命周期**：对象、协程、文件流、上下文管理器分别什么时候创建、挂起、恢复、释放。
2. **阻塞点**：网络 IO、文件 IO、数据库查询、模型调用是异步服务最常见的等待来源。
3. **错误传播**：异常是直接抛出、被 task 包装，还是在日志中被吞掉，会决定排障难度。
4. **可观测性**：日志、trace id、结构化 JSON 输出能把一次请求的执行路径串起来。

### 最小调试骨架

```python
import asyncio
import logging

logging.basicConfig(filename="app.log", level=logging.INFO)

async def run_step(name, coro):
    logging.info("start step=%s", name)
    try:
        result = await coro
        logging.info("done step=%s result=%r", name, result)
        return result
    except Exception:
        logging.exception("failed step=%s", name)
        raise

# 用法：await run_step("retrieve", retriever(query))
```

### 工程落地要点

- 写 FastAPI/RAG/Agent 服务时，先明确哪些函数必须是 async，哪些只是普通 CPU 计算。
- 不要把大文件一次性读入内存，能流式就流式；不要在事件循环里跑长时间 CPU 任务。
- 对生成器、上下文管理器和 task，都要明确“谁负责消费、谁负责关闭、异常从哪里冒出”。

## 11. 针对 `JSON、XML 与正则提取` 的专项排查

Python 服务中很多问题不是语法错，而是运行时行为与预期不一致。排查 **JSON、XML 与正则提取** 时建议看：

- **是否真的被执行**：生成器、协程、上下文管理器经常只有在被消费/await/进入时才执行。
- **是否阻塞事件循环**：异步函数内部如果跑 CPU 密集循环，仍然会卡住其他请求。
- **异常是否被吞掉**：后台 task、日志函数、try/except 都可能让错误不再显式暴露。
- **资源是否关闭**：文件、数据库连接、上传流和 session 都需要明确生命周期。

### 小型练习

```python
async def safe_call(name, func, *args, **kwargs):
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        print(f"[{name}] failed:", repr(e))
        raise

# 练习：把涉及 JSON、XML 与正则提取 的函数包一层 safe_call，观察错误到底在哪里发生。
```

### 面试表达模板

回答 `JSON、XML 与正则提取` 时，可以按“它改变了什么运行时行为 → 什么时候执行 → 和同步写法有什么差异 → 项目中如何排错”来组织。
