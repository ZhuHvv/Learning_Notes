# 03.06 pandas 与实验日志数据处理

> 学习层级：中级  
> 前置知识：[JSON、XML 与正则提取](5_JSON、XML_与正则提取.md)  
> 后续阅读：[async、await 与协程调度](7_async、await_与协程调度.md)

## 1. 从结构化日志到 DataFrame

pandas 可以把实验结果、日志和指标整理成二维表格，用于过滤、排序、分组、聚合和异常分析。Agent、RAG 或模型实验通常可以把每次运行记录成 JSONL：

```json
{"task":"qa","strategy":"baseline","ok":true,"latency_ms":120,"tokens":300}
{"task":"qa","strategy":"rerank","ok":false,"latency_ms":260,"tokens":510}
```

JSONL 每行是一个完整 JSON 对象，适合持续追加，也便于 pandas 读取：

```python
import pandas as pd

df = pd.read_json("runs.jsonl", lines=True)
```

日志阶段就应尽量结构化，否则后续分析会把大量时间花在从自然语言日志中提取字段。

## 2. 读取后先检查数据质量

```python
print(df.head())
print(df.dtypes)
print(df.isna().sum())
```

常见清洗包括：

- 把字符串时间戳转换为 datetime；
- 把数字文本转换为数值类型；
- 统一策略名、错误类型和数据集名称；
- 决定缺失值是删除、填充还是单独标记；
- 去除或标记重复运行记录。

类型转换示例：

```python
df["latency_ms"] = pd.to_numeric(df["latency_ms"], errors="coerce")
df["ok"] = df["ok"].astype("boolean")
```

`errors="coerce"` 会把无法转换的值变为缺失值，不能在没有检查缺失数量的情况下静默使用。

## 3. 分组统计成功率、延迟和 token

布尔列的平均值可以作为成功率：

```python
summary = (
    df.groupby("strategy")
      .agg(
          runs=("ok", "size"),
          success_rate=("ok", "mean"),
          avg_latency_ms=("latency_ms", "mean"),
          avg_tokens=("tokens", "mean"),
      )
      .sort_values("success_rate", ascending=False)
)

print(summary)
```

平均延迟会掩盖尾部慢请求，还应关注 p95/p99：

```python
latency_tail = (
    df.groupby("strategy")["latency_ms"]
      .quantile([0.95, 0.99])
      .unstack()
      .rename(columns={0.95: "p95_ms", 0.99: "p99_ms"})
)
```

还可以按数据集、任务、模型版本和错误类型分组，避免总体平均值掩盖局部退化。

## 4. 实验分析流程

```text
运行实验并输出结构化 JSONL
  ↓
读取 DataFrame
  ↓
检查缺失、类型、重复值和异常值
  ↓
按策略、数据集、错误类型分组
  ↓
比较成功率、平均值和 p95/p99
  ↓
定位样本并优化系统
```

pandas 像把散落的实验纸条整理成 Excel 再做透视表，但统计结果是否可信仍取决于日志字段、样本设计和指标定义。

## 5. 常见误区

- 只记录自由文本，不记录稳定字段；
- 只比较平均延迟，不看尾部延迟；
- 成功率分母不同，却直接比较百分比；
- 类型转换后不检查新产生的缺失值；
- 聚合后不回看原始失败样本；
- 把相关性或一次实验波动直接解释成因果关系。
