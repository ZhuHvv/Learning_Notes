# 知识图谱、HyDE、RRF 与检索增强

> 所属分类：LLM / Transformer  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

知识图谱表达实体关系，HyDE 生成假想答案辅助检索，RRF 用倒数排名融合多路召回结果。


## 2. 原理性解释

- 知识图谱适合结构化关系。
- HyDE 不是事实来源，只用于改善 query 表达。
- RRF 不依赖不同检索器分数尺度。
- 多路召回后仍需 rerank 和权限过滤。

### 知识图谱、HyDE、RRF 分别补检索的不同短板

知识图谱擅长显式实体关系，例如“公司—创始人—产品”；HyDE 通过让模型先生成一个假想答案/文档，再用这个假想文档做向量检索，缓解 query 太短或措辞不匹配；RRF 则把多个检索器的排名融合，降低单一路径失败的风险。

```python
# RRF 思想：排名越靠前贡献越大
score[doc] += 1 / (k + rank(doc))
```

三者不是互斥关系：复杂问答可以先用 HyDE 改写查询，再同时走 BM25、向量检索和图谱邻居扩展，最后用 RRF 融合候选。

## 3. 机制流程

1. 关键词/向量/图谱多路召回。
2. 必要时 HyDE 扩展。
3. RRF 融合排名。
4. 去重过滤重排。

### 混合检索的机制流程

```text
用户问题
 ├─ 原始 query → BM25
 ├─ embedding(query) → 向量检索
 ├─ HyDE 生成假想文档 → 向量检索
 └─ 实体识别 → 知识图谱邻居扩展
        ↓
候选文档集合
        ↓
RRF / 加权融合 / Cross-Encoder 重排
        ↓
送入生成模型
```

工程上要记录每个候选来自哪条检索路径，否则很难判断是 BM25、向量库、HyDE 还是图谱扩展出了问题。

## 4. 类比理解

RRF 像综合多个同学推荐名单，越多人靠前推荐越优先。

## 5. 应用举例 / 代码或伪代码

```python
def rrf(lists, k=60):
    s = {}
    for xs in lists:
        for rank, doc_id in enumerate(xs, 1):
            s[doc_id] = s.get(doc_id, 0) + 1/(k+rank)
    return sorted(s, key=s.get, reverse=True)
```

## 6. 你在讨论中的理解推进

你问过知识图谱和 RRF；重点是它们增强检索，不替代 LLM。

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

理解 **知识图谱、HyDE、RRF 与检索增强** 时，不要只停留在“名词解释”，而要追踪张量和信息流：

1. **输入形态**：一段文本先变成 token id，再查 embedding table 得到向量。
2. **中间变换**：Transformer 层反复做注意力聚合、残差连接、归一化和 FFN 非线性变换。
3. **输出用途**：生成模型会把最后一层 hidden state 投影到词表 logits；Embedding/RAG 模型则会把向量用于相似度检索。
4. **调试方式**：看 shape 是否一致、mask 是否正确、logits 是否异常、相似度分布是否过于集中。

### 最小验证实验

```python
# 伪代码：用 shape 跟踪 知识图谱、HyDE、RRF 与检索增强 是否真的理解到位
tokens = tokenizer("hello agent")
x = embedding(tokens)                 # [seq_len, hidden_size]
for layer in transformer_layers:
    x = layer.self_attention(x)        # token 之间交换上下文信息
    x = layer.ffn(x)                   # 每个 token 内部做非线性特征变换
logits = lm_head(x[-1])                # 只用最后一个位置预测下一个 token
next_token = argmax(logits)
```

### 常见落地场景

- 做 RAG 时，Encoder-only 或 Embedding 模型用于“把问题和文档变成可比较向量”。
- 做工具调用时，Decoder-only 模型根据 prompt 中的 schema 预测结构化 JSON/XML。
- 做性能优化时，KV Cache、batching、量化、LoRA 会影响推理成本和部署策略。

## 11. 针对 `知识图谱、HyDE、RRF 与检索增强` 的专项排查

学习或实现 **知识图谱、HyDE、RRF 与检索增强** 时，可以用下面的方式检查自己是否真正掌握：

- **形状检查**：是否能说清输入和输出的 shape，例如 `[batch, seq_len, hidden_size]`、`[seq_len, vocab_size]`。
- **信息流检查**：是否能说明一个 token 的信息如何影响另一个 token，哪些位置因为 mask 看不到未来。
- **训练/推理差异检查**：训练时通常并行计算整段序列，推理时则逐 token 生成，并通过 KV Cache 复用历史键值。
- **和 RAG 的连接**：如果本主题产出的是 embedding，要关注相似度；如果产出的是 logits，要关注下一个 token 概率。

### 小型练习

```python
# 练习：给一个 Transformer 相关概念写 shape 注释
batch = 2
seq_len = 5
hidden = 768

x = Tensor(shape=[batch, seq_len, hidden])
# 问题：经过 self-attention 后 shape 是否改变？
# 答案：通常仍是 [batch, seq_len, hidden]，但每个位置的向量已经融合了上下文。
```

### 面试表达模板

当被问到 `知识图谱、HyDE、RRF 与检索增强` 时，可以按“定义 → 数据流 → 为什么需要 → 工程影响”回答，避免只背名词。
