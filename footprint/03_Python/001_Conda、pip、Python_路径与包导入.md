# Conda、pip、Python 路径与包导入

> 学习层级：入门  
> 前置知识：能够在终端运行命令  
> 后续阅读：[Python 标准输入、split、map 与 range](002_Python_标准输入、split、map_与_range.md)

## 1. 先区分解释器、环境与包管理器

一台机器可以同时安装多个 Python。Conda 和 `venv` 用来隔离解释器及其依赖，pip 则把包装进某个具体的 Python 环境。

因此，`pip install` 显示成功并不等于当前脚本一定能够导入该包。最常见的原因是：

```text
执行脚本的 Python ≠ pip 安装包时对应的 Python
```

优先使用下面的形式安装和查询包：

```bash
python -m pip --version
python -m pip show openai
python -m pip install -r requirements.txt
```

`python -m pip` 会让当前这个 `python` 解释器执行 pip，比直接运行来源不明的 `pip` 更可靠。

## 2. 确认当前使用的 Python

先查看脚本实际使用的解释器：

```bash
python -c "import sys; print(sys.executable)"
python -m pip --version
```

再在程序中确认模块究竟从哪里导入：

```python
import sys
import pydantic

print(sys.executable)
print(pydantic.__file__)
print(sys.path)
```

- `sys.executable`：当前解释器路径；
- `module.__file__`：模块实际来源；
- `sys.path`：Python 查找模块的目录顺序。

IDE、终端和测试工具必须尽量指向同一解释器。切换环境后，通常还要重启 IDE 的语言服务器或终端会话。

## 3. Conda、venv 与项目依赖

两种常见隔离方式：

```bash
conda create -n demo python=3.12
conda activate demo
```

```bash
python -m venv .venv
```

项目应通过 `requirements.txt`、`pyproject.toml` 或锁文件固定依赖，而不是依赖全局环境。安装后可执行：

```bash
python -m pip check
```

检查已安装包之间是否存在已知的版本冲突。

不要同时混用系统 Python、全局 pip、Conda 环境和项目 venv。重建环境应是确认解释器、安装位置和版本约束之后的手段，而不是第一步。

## 4. 包导入、`__init__.py` 与 `__all__`

`__init__.py` 可以初始化普通包、重新导出名字，并通过 `__all__` 声明星号导入时的公共名称：

```python
# mypkg/__init__.py
from .client import Client

__all__ = ["Client"]
```

现代 Python 也支持 namespace package，所以“目录没有 `__init__.py` 就绝对不能导入”并不成立。导入是否成功还取决于：

- 项目是否以包的方式安装；
- 启动命令所在目录；
- `sys.path` 与 `PYTHONPATH`；
- IDE、测试器和应用服务器使用的解释器及工作目录。

不要为解决导入错误而随意追加大量路径。先确认包结构和启动方式，再决定是否需要 editable install：

```bash
python -m pip install -e .
```

## 5. 依赖与导入排查流程

```text
确认 IDE 使用的解释器
  ↓
打印 sys.executable
  ↓
执行 python -m pip --version / show
  ↓
打印目标模块的 __file__ 与 sys.path
  ↓
检查依赖约束和 python -m pip check
  ↓
必要时重新创建环境并重启 IDE
```

可以把环境隔离理解成多个彼此独立的厨房：买到调料不等于把它放进了当前正在做菜的那间厨房。

## 6. 常见误区

- `pip install` 成功，所以所有 Python 都能导入这个包；
- 终端环境正确，IDE 就一定使用同一解释器；
- 所有 `ImportError` 都是“没有安装”，而忽略版本不兼容、同名文件遮蔽和循环导入；
- 直接修改 `PYTHONPATH`，却没有先确认项目安装方式；
- 一遇到问题就删除并重建环境，因而掩盖真正的解释器或依赖约束错误。

