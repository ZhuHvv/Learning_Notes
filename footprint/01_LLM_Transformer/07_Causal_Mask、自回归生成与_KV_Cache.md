# 01.07 Causal Mask、自回归生成与 KV Cache

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

```
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
