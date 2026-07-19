# JSON、XML 与正则提取

> 所属分类：Python / Async / FastAPI  
> 修订版本：v9 昨日今日增量版  
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

