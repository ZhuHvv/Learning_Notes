# JSON、XML 与正则提取

> 学习层级：中级  
> 前置知识：[dataclass、TypedDict 与 Pydantic](004_dataclass、TypedDict_与_Pydantic.md)  
> 后续阅读：[pandas 与实验日志数据处理](006_pandas_与实验日志数据处理.md)

## 1. JSON 的对象、文本与文件 API

JSON 用于结构化数据交换。Python 标准库中：

- `json.dumps`：Python 对象 → JSON 字符串；
- `json.loads`：JSON 字符串 → Python 对象；
- `json.dump`：把 Python 对象写入文件对象；
- `json.load`：从文件对象读取 JSON。

常见的 `json.load(s)` 记忆法只是把 `load` 与 `loads` 合写，实际调用时必须根据输入是文件对象还是字符串选择正确函数。

```text
Python object --json.dumps--> JSON text
JSON text     --json.loads--> Python object
```

datetime、UUID、Enum、set 等对象需要稳定、明确的编码方式。无条件使用 `default=str` 会丢失原类型和结构，只适合作为日志兜底，不适合作为需要恢复的存储协议。Queue、Task、Session 和连接等运行时资源更不应通过字符串化进入 checkpoint。

使用 `.format()` 构造包含字面 JSON 的模板时，花括号要转义：

```python
template = '输出格式：{{"answer": "{answer}"}}'
print(template.format(answer="ok"))
```

## 2. JSON、XML 标签与正则各司其职

- JSON：适合机器解析的结构化参数；
- XML 或 XML 风格标签：适合划分语义区域；
- 正则：适合提取简单、受控、无嵌套的文本模式。

```python
import json
import re

match = re.search(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL)
if match:
    payload = json.loads(match.group(1))
```

`.*?` 是非贪婪匹配；`re.DOTALL` 让点号可以跨行。若数据存在嵌套 XML、属性、命名空间或严格安全要求，应使用合适的 XML 解析器，而不是用正则模拟完整 XML 语法。处理不可信 XML 时还要评估实体扩展等安全风险。

对于模型工具调用，应优先采用模型 API 原生的 tool calling 或 structured output，而不是自行从自然语言中猜测参数。

## 3. 模型 JSON 输出的四层质量

1. **语法有效**：能否通过 `json.loads`；
2. **顶层类型正确**：是否为协议约定的 dict、list 或标量；
3. **结构有效**：必填字段、枚举、嵌套类型和范围是否符合 schema；
4. **语义可信**：事实、引用、权限和业务含义是否正确。

例如，`response_format={"type":"json_object"}` 主要保证模型输出可解析的 JSON object，不能替代 Pydantic/JSON Schema 校验和事实核验。JSON Schema、数据库 schema 与 Agent 输出 schema 虽然都可能简称为 schema，却属于不同层。

## 4. 从严格到宽松的容错边界

合理的解析顺序通常是：

```text
原生 tool calling / structured output
  ↓
整段标准 JSON
  ↓
明确的 json 代码块或受控标签
  ↓
少量、可审计的修复
  ↓
Pydantic / schema 校验
  ↓
语义、事实与权限校验
```

删注释、补 key、删除尾逗号等正则修复存在明显风险：

- `//` 可能是 URL 的一部分；
- 截取首尾花括号不是括号解析器；
- 全局替换 `\\n`、`\\t` 可能改变代码、路径和正则含义；
- 修复出“合法 JSON”不代表业务结构正确。

修复流程应限制输入长度，记录采用的解析路径及修复前后文本，并在修复后继续做 schema 校验。成功状态应使用 `result is not None` 等显式判断，而不是 `if result`，因为合法的 `{}` 和 `[]` 也是假值。

## 5. `ast.literal_eval` 不等于 JSON 解析

`ast.literal_eval` 接受 Python 的字符串、数字、容器、布尔值和 `None` 等字面量，不允许一般变量、函数调用和属性访问，因此不会执行 `os.system(...)` 这类调用。

但它解析的是 Python 语法而不是 JSON。极深或巨大的输入仍可能消耗大量内存、CPU 或栈，所以仍需限制长度和复杂度。不要用 `eval()` 解析用户或模型输入。

## 6. 保留解析成功与失败信息

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

该返回结构能区分合法空对象与全部解析失败。后续仍需单独执行顶层类型、业务模型、事实和权限校验。

## 7. 常见误区

- 混淆 `load` / `loads` 和 `dump` / `dumps`；
- 认为 `default=str` 能得到可逆序列化；
- 认为 JSON mode 自动保证业务 schema；
- 使用正则完整解析嵌套 JSON 或 XML；
- 把解析失败与合法空对象都转成 `{}`；
- 使用 `eval()` 或不受限的宽松修复处理不可信输入。
