# 可变默认参数与 default factory

> 所属分类：Python / Async / FastAPI  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

可变默认参数会被所有调用/实例共享；default_factory 每次创建实例时生成新对象。


## 2. 原理性解释

- 默认参数在定义时求值。
- list/dict/set 是可变对象。
- dataclass 字段应使用 field(default_factory=list)。
- 函数默认参数也有同样问题。

### 可变默认参数的问题来自“默认值只在函数定义时创建一次”

`embedding: List[float] = []` 的危险在于这个空列表不是每次实例化都新建，而是被所有默认使用者共享。dataclass 的 `field(default_factory=list)` 则是在每次创建实例时调用工厂函数，生成独立列表。

```python
@dataclass
class Doc:
    embedding: list[float] = field(default_factory=list)
```

这类问题不只出现在 dataclass，也出现在普通函数参数中。

## 3. 机制流程

1. 定义默认列表。
2. 多个实例共享它。
3. 一个实例修改。
4. 其他实例受到影响。

### 错误与正确流程对比

```python
def bad_append(x, arr=[]):
    arr.append(x)
    return arr

bad_append(1)  # [1]
bad_append(2)  # [1, 2]，不是你期望的新列表

def good_append(x, arr=None):
    if arr is None:
        arr = []
    arr.append(x)
    return arr
```

规则：默认参数适合不可变值，如 `None`、数字、字符串；可变容器用 `None` 或 `default_factory`。

## 4. 类比理解

像所有人共用一个草稿本；default_factory 是每人一本新本子。

## 5. 应用举例 / 代码或伪代码

```python
@dataclass
class Chunk:
    text: str
    embedding: list[float] = field(default_factory=list)
```

## 6. 你在讨论中的理解推进

你看到 `embedding=[]` 与 `default_factory=list` 后理解了共享列表陷阱。

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

**可变默认参数与 default factory** 在 Python 工程中通常关系到“运行时行为”而不是语法表面：

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

## 11. 针对 `可变默认参数与 default factory` 的专项排查

Python 服务中很多问题不是语法错，而是运行时行为与预期不一致。排查 **可变默认参数与 default factory** 时建议看：

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

# 练习：把涉及 可变默认参数与 default factory 的函数包一层 safe_call，观察错误到底在哪里发生。
```

### 面试表达模板

回答 `可变默认参数与 default factory` 时，可以按“它改变了什么运行时行为 → 什么时候执行 → 和同步写法有什么差异 → 项目中如何排错”来组织。
