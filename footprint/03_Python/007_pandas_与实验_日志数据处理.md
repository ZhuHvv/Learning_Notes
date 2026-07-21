# pandas 与实验 日志数据处理

> 所属分类：Python / Async / FastAPI  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

pandas 可把实验结果、日志和指标整理成表格，用于聚合、排序、过滤和分析。


## 2. 原理性解释

- DataFrame 是二维表。
- JSONL 日志很适合 pandas 读取。
- groupby 可统计成功率、延迟、token。
- 平均值外还应关注 p95/p99。

### pandas 在实验中的价值是把日志变成可分析表格

当你做 Agent、RAG、模型实验时，原始日志通常是 JSONL 或散乱文本。pandas 的作用是把每次运行的 query、召回数量、耗时、token 数、是否成功等字段组织成 DataFrame，便于分组统计和定位异常。

```python
df = pd.read_json("runs.jsonl", lines=True)
df.groupby("strategy")["latency_ms"].mean()
```

## 3. 机制流程

1. 记录结构化日志。
2. 读入 DataFrame。
3. 清洗字段。
4. 聚合分析。
5. 优化系统。

### 实验分析流程

```text
运行实验 → 输出结构化 JSONL
  ↓
pandas 读取
  ↓
清洗字段 / 转换类型
  ↓
按策略、数据集、错误类型分组
  ↓
生成表格或图表
```

关键是日志阶段就要结构化，否则后续分析会花大量时间清洗字符串。

## 4. 类比理解

像把散落纸条整理成 Excel 再做透视表。

## 5. 应用举例 / 代码或伪代码

```python
df = pd.read_json("runs.jsonl", lines=True)
print(df.groupby("task").agg(success=("ok","mean"), latency=("latency","mean")))
```

## 6. 你在讨论中的理解推进

你在实验和日志场景中需要从运行记录走向可分析数据。

