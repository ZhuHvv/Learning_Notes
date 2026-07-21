# Conda、pip、Python 路径与依赖隔离

> 所属分类：Python / Async / FastAPI  
> 修订版本：v9 昨日今日增量版  
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

