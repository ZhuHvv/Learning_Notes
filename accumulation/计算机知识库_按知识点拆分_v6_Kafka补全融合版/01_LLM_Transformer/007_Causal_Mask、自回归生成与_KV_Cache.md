# Causal Mask、自回归生成与 KV Cache

> 所属分类：LLM / Transformer  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Causal Mask 禁止当前位置看到未来 token；自回归生成逐 token 追加；KV Cache 缓存历史 K/V 以减少重复计算。


## 2. 原理性解释

- 训练可并行计算所有位置，但 mask 保证因果约束。
- 推理必须一步步生成。
- KV Cache 只优化速度，不改变输出含义。
- 长上下文会让 KV Cache 占用显存。

### Causal Mask 与 KV Cache 解决的是两个不同问题

Causal Mask 解决“不能偷看未来”的训练/推理约束；KV Cache 解决“推理时不要重复计算历史 token 的 K/V”的效率问题。二者经常一起出现，但不是同一个概念。

在自回归生成中，第 t 步只需要为新 token 计算 Q/K/V。历史 token 的 K/V 不会因为新 token 到来而改变，因此可以缓存。新 token 的 Q 与缓存中的所有 K 做注意力，再汇总对应 V。

```python
# 第 t 步
q_new = x_new @ Wq
k_new = x_new @ Wk
v_new = x_new @ Wv
K_cache = concat(K_cache, k_new)
V_cache = concat(V_cache, v_new)
out = attention(q_new, K_cache, V_cache)
```

## 3. 机制流程

1. 输入 prompt。
2. 生成并缓存每层 K/V。
3. 采样 next token。
4. 追加 token。
5. 下一步复用历史 K/V。

### 生成阶段的流程

```text
prompt token ids
  ↓ 首轮 forward，构建每层 KV cache
采样得到 next token
  ↓
只输入新 token + 历史 KV cache
  ↓
计算新 token 对全部历史的注意力
  ↓
更新 KV cache
  ↓
直到遇到 EOS / 长度上限 / 停止词
```

没有 KV Cache 时，每生成一个 token 都要重新计算整个上下文，复杂度会急剧上升。使用 KV Cache 后，每步主要计算新 token 与历史缓存的注意力，延迟显著降低，但显存会随上下文长度增长。

## 4. 类比理解

写作文不能偷看未来句子，但可以保留前面做过的笔记。

## 5. 应用举例 / 代码或伪代码

```python
cache = {}
for _ in range(max_new_tokens):
    logits, cache = model.forward_one_step(last_token, kv_cache=cache)
    last_token = sample(logits)
```

## 6. 你在讨论中的理解推进

你问 decoder 如何预测下一个 token；这里对应 causal mask + 自回归循环 + KV Cache。

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

理解 **Causal Mask、自回归生成与 KV Cache** 时，不要只停留在“名词解释”，而要追踪张量和信息流：

1. **输入形态**：一段文本先变成 token id，再查 embedding table 得到向量。
2. **中间变换**：Transformer 层反复做注意力聚合、残差连接、归一化和 FFN 非线性变换。
3. **输出用途**：生成模型会把最后一层 hidden state 投影到词表 logits；Embedding/RAG 模型则会把向量用于相似度检索。
4. **调试方式**：看 shape 是否一致、mask 是否正确、logits 是否异常、相似度分布是否过于集中。

### 最小验证实验

```python
# 伪代码：用 shape 跟踪 Causal Mask、自回归生成与 KV Cache 是否真的理解到位
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

## 11. 针对 `Causal Mask、自回归生成与 KV Cache` 的专项排查

学习或实现 **Causal Mask、自回归生成与 KV Cache** 时，可以用下面的方式检查自己是否真正掌握：

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

当被问到 `Causal Mask、自回归生成与 KV Cache` 时，可以按“定义 → 数据流 → 为什么需要 → 工程影响”回答，避免只背名词。
