# JSON、XML 与正则提取

> 所属分类：Python / Async / FastAPI  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

JSON 用于结构化数据交换，XML/标签用于划分语义边界，正则适合提取简单、受控的文本模式。处理 LLM 输出时，要把 JSON 语法解析、顶层类型、业务 schema 和内容可信度分层验证。

## 2. 原理性解释

- `json.load` / `dump` 操作文件对象，`json.loads` / `dumps` 操作字符串；
- `default=str` 会丢失类型和结构，不适合作为可恢复协议；
- JSON mode 通常不保证业务字段满足 schema；
- 容错解析应先严格、再有限放宽，并记录采用了哪条路径；
- 合法 `{}` 与解析失败不能都折叠成同一个无信息结果；
- 正则修复不理解 JSON 字符串边界，可能破坏 URL、代码和转义；
- `ast.literal_eval` 不执行任意表达式，但仍要防资源消耗。

### JSON、XML、正则在 LLM 协议里各司其职

JSON 适合机器解析参数；XML 风格标签适合在 Prompt 中标记区域；正则可以提取简单标签内容：

```python
match = re.search(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL)
if match:
    payload = json.loads(match.group(1))
```

`.*?` 是非贪婪匹配，`re.DOTALL` 让点号跨行。若存在嵌套 XML、属性或严格安全要求，应使用 XML 解析器；工具调用优先使用模型 API 的原生 tool calling。

### `dumps` / `loads` 与显式编码

```text
Python object --json.dumps--> JSON text
JSON text     --json.loads--> Python object
```

datetime、UUID、Enum、set 等应定义稳定编码器。无条件 `default=str` 只适合日志兜底，因为调用方无法可靠恢复原类型；Queue、Task、Session 等更不应通过字符串化进入 checkpoint。

### 模型 JSON 输出的四层质量

1. 语法有效：能否 `json.loads`；
2. 顶层类型正确：是否为约定的 dict/list；
3. 结构有效：必填字段、枚举、嵌套类型和范围；
4. 语义可信：事实、引用和业务含义。

`response_format={"type":"json_object"}` 不能替代 Pydantic/JSON Schema 和事实核验。

### 从严格到宽松的容错边界

合理顺序通常是：整段标准 JSON → 明确的 `json` 代码块 → 受控对象提取 → 少量可审计修复 → schema 校验 → 重试、降级或终止。

删注释、补 key、删尾逗号等正则有明显风险：`//` 可能属于 URL，首尾花括号截取不是括号解析器，全局恢复 `\\n` / `\\t` 可能改变代码、路径和正则语义。修复应限制输入长度，记录前后文本，并在修复后继续做 schema 校验。

检查成功时应使用 `result is not None` 一类显式状态，而不是 `if result`；合法空 dict/list 也是假值。

### `ast.literal_eval` 与 `eval`

`ast.literal_eval` 只接受 Python 字符串、数字、容器、布尔和 None 等字面量，不允许一般变量、函数调用和属性访问，因此不会执行 `os.system(...)` 这类调用。它解析的是 Python 语法，不是 JSON；极深或巨大的输入仍可能耗尽内存、CPU 或栈，需限制长度和深度。不要用 `eval()` 解析用户或模型输入。

## 3. 机制流程

1. 优先接收原生 tool calling / structured output；
2. 对 JSON 文本先执行标准 `json.loads`；
3. 必要时提取明确标签或 fenced code block；
4. 记录有限修复路径；
5. 校验顶层类型和 Pydantic/schema；
6. 执行业务语义与权限检查；
7. 失败时按风险选择重试、领域默认对象、终止或人工审核。

### 解析流程

```text
LLM 输出
  ↓ 标准 JSON 解析
语法有效？——否→ 受控提取/修复并记录
  ↓
Pydantic / schema 校验
  ↓
事实、引用、权限校验
  ↓
进入业务逻辑或显式失败
```

## 4. 类比理解

XML 标签像包装盒，JSON 像盒中的标准表单，正则负责在简单场景中找到盒子；Pydantic 像检查表单字段，事实核验则检查表单内容是否真实。

## 5. 应用举例 / 代码或伪代码

```python
import json
import re
from dataclasses import dataclass
from typing import Any

JSON_BLOCK = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

@dataclass
class ParseResult:
    value: Any | None
    source: str | None
    error: str | None

def parse_json_output(text: str) -> ParseResult:
    candidates = [("full_text", text)]
    if match := JSON_BLOCK.search(text):
        candidates.append(("json_fence", match.group(1)))

    errors = []
    for source, candidate in candidates:
        try:
            return ParseResult(json.loads(candidate), source, None)
        except json.JSONDecodeError as exc:
            errors.append(f"{source}: {exc.msg}")
    return ParseResult(None, None, "; ".join(errors))
```

该返回结构能区分合法 `{}` 与全部解析失败。后续仍需单独执行业务模型校验。

## 6. 你在讨论中的理解推进

你从 `json.load(s)`、XML Prompt 和正则提取，推进到结构化输出的分层契约：解析容错只解决语法的一部分，结构、语义和安全必须继续验证，失败也要显式可观察。
