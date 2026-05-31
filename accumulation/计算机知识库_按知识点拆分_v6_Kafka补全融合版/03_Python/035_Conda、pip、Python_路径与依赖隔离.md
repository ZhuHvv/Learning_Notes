# Conda、pip、Python 路径与依赖隔离

> 所属分类：Python / Async / FastAPI  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Conda/venv 隔离解释器和依赖；pip 必须安装到当前运行的 Python 环境。


## 2. 原理性解释

- 机器上可能有多个 Python。
- 用 `python -m pip` 确保 pip 对应当前解释器。
- ImportError 常由版本不兼容或装错环境引起。
- IDE 解释器要和终端一致。

### 环境隔离问题本质是“你运行的 Python”和“你安装包的 Python”不是同一个

Conda、venv、pip、IDE 解释器路径经常造成混乱。`pip install` 成功不代表当前脚本能 import，因为 pip 可能对应另一个 Python。排查时先打印 `sys.executable`，再用 `python -m pip show package` 确认包装到了同一个环境。

```bash
python -c "import sys; print(sys.executable)"
python -m pip show openai
```

## 3. 机制流程

1. 查看 sys.executable。
2. 查看 pip --version。
3. 检查包版本。
4. 重建环境。

### 依赖排查流程

```text
确认 IDE 使用的解释器路径
  ↓
确认终端 python 路径
  ↓
使用 python -m pip 安装
  ↓
检查 conda env / venv 是否激活
  ↓
重启语言服务器或 IDE
```

不要混用全局 pip、conda pip、系统 Python 和项目 venv；项目根目录最好固定 `requirements.txt` 或 `pyproject.toml`。

## 4. 类比理解

买的调料必须放到正在做菜的厨房。

## 5. 应用举例 / 代码或伪代码

```bash
python -c "import sys; print(sys.executable)"
python -m pip --version
python -m pip install -r requirements.txt
```

## 6. 你在讨论中的理解推进

你遇到 langsmith/langgraph、pip/openai 路径问题；排查主线是解释器路径。

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

**Conda、pip、Python 路径与依赖隔离** 在 Python 工程中通常关系到“运行时行为”而不是语法表面：

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

## 11. 针对 `Conda、pip、Python 路径与依赖隔离` 的专项排查

Python 服务中很多问题不是语法错，而是运行时行为与预期不一致。排查 **Conda、pip、Python 路径与依赖隔离** 时建议看：

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

# 练习：把涉及 Conda、pip、Python 路径与依赖隔离 的函数包一层 safe_call，观察错误到底在哪里发生。
```

### 面试表达模板

回答 `Conda、pip、Python 路径与依赖隔离` 时，可以按“它改变了什么运行时行为 → 什么时候执行 → 和同步写法有什么差异 → 项目中如何排错”来组织。
