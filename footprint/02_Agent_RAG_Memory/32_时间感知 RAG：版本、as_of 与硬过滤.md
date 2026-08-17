# 02.32 时间感知 RAG：版本、as_of 与硬过滤

## 1. 核心结论

用户问题中的“最新”“截至某日”“上一代有什么变化”不应只作为 Prompt 中的描述词。它们应被解析为结构化时间或版本约束，并在向量/BM25 检索之前通过 metadata 硬过滤执行。

```text
自然语言时间意图
      ↓
时间/版本解析
      ↓
Version Registry 决定有效版本
      ↓
metadata 硬过滤
      ↓
仅在合法候选范围内做语义检索、重排与生成
```

这样 LLM 只负责识别“用户要求最新”，不负责裁定“哪个版本最新”。

## 2. 入库时将时间与版本建模为一等公民

除正文和向量外，知识条目至少应有：

```json
{
  "product": "SU7",
  "version": "SU7_2026",
  "topic": "辅助驾驶",
  "published_at": "2026-04-10",
  "ingested_at": "2026-04-11",
  "effective_from": "2026-04-10",
  "effective_to": null,
  "source": "..."
}
```

三种时间不可混用：

| 字段 | 回答的问题 | 能否直接代表知识有效性 |
| --- | --- | --- |
| `published_at` | 文档何时发布 | 不一定 |
| `ingested_at` | 系统何时收录 | 不能 |
| `effective_from` / `effective_to` | 事实在哪段时间内有效 | 可以 |

例如，2024 款与 2026 款的不同配置可以都正确；把旧文档删掉会损失历史知识，混在“最新”检索中又会造成错误。版本和有效时间让两者兼得。

## 3. 从查询到硬过滤

用户问“最新一代 SU7 的辅助驾驶方案有什么变化？”时，解析器可以输出：

```json
{
  "entity": "SU7",
  "aspect": "辅助驾驶",
  "temporal_intent": "LATEST",
  "comparison": true
}
```

随后由程序而非 LLM 查询版本注册表：

```sql
SELECT version
FROM product_version
WHERE product = 'SU7'
  AND effective_from <= CURRENT_TIMESTAMP
ORDER BY effective_from DESC
LIMIT 1;
```

得到 `SU7_2026` 后，再将其加入向量数据库过滤条件：

```python
filter_expr = 'product == "SU7" && version == "SU7_2026"'
hits = vector_db.search(query_vector, filter=filter_expr, limit=20)
```

这与“先搜索所有 SU7 文档，再让 LLM 从混杂的新旧资料里猜最新”有本质区别：前者将时效性变成检索约束，后者只是生成阶段的脆弱判断。

## 4. `as_of`：统一处理最新与历史问题

内部可统一使用 `as_of` 表达“以哪个时点为准”：

```text
effective_from <= as_of
AND (effective_to IS NULL OR effective_to > as_of)
```

| 用户表达 | 可编译的约束 |
| --- | --- |
| “最新” | `as_of = now()`，解析当前有效版本 |
| “2025 年 6 月时” | `as_of = 2025-06-01` |
| “2025 年的方案” | 指定时间范围或版本 |
| “从上一代变了什么” | 同时解析 latest 与 previous 两个时间切片 |

“有什么变化”不能只检索最新版本：应分别检索 `latest` 与 `previous` 的同一主题材料，再做事实级差异比较，最后由 LLM 用带版本的证据生成结论。

## 5. 版本注册表与回退边界

建议将版本关系放在关系数据库或专门的 registry 中，而不是临时从向量库按最大日期推断：

```text
product_version
product | version  | effective_from | current
SU7     | SU7_2024 | 2024-03-28     | false
SU7     | SU7_2025 | 2025-02-01     | false
SU7     | SU7_2026 | 2026-04-10     | true
```

关系库负责版本关系与有效期；向量库负责在已确定版本范围内按语义检索。若当前版本已确定但知识库缺少该主题材料，系统应明确报告缺口，或在显式标注“降级到上一版本”的前提下回退；不能静默放宽过滤条件。

## 6. 与冲突检测的关系

不同时间、版本或适用范围下的不同数值，通常属于知识演化而不是真冲突。时间/版本字段既能防止旧资料污染“最新”检索，也能在冲突检测中避免将两个均正确的历史事实误判为矛盾。

## 7. 关联知识点

- [RAG 完整链路：召回、融合、重排、生成](18_RAG_%E5%AE%8C%E6%95%B4%E9%93%BE%E8%B7%AF%EF%BC%9A%E5%8F%AC%E5%9B%9E%E3%80%81%E8%9E%8D%E5%90%88%E3%80%81%E9%87%8D%E6%8E%92%E3%80%81%E7%94%9F%E6%88%90.md)
- [RAG 冲突证据：事实级检测、信源依赖与仲裁](33_RAG%20%E5%86%B2%E7%AA%81%E8%AF%81%E6%8D%AE%EF%BC%9A%E4%BA%8B%E5%AE%9E%E7%BA%A7%E6%A3%80%E6%B5%8B%E3%80%81%E4%BF%A1%E6%BA%90%E4%BE%9D%E8%B5%96%E4%B8%8E%E4%BB%B2%E8%A3%81.md)
