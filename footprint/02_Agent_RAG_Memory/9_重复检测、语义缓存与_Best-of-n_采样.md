# 重复检测、语义缓存与 Best-of-n 采样

## 1. 总体性概念

重复检测发现相似 query/action，语义缓存复用相似问题结果，Best-of-n 生成多个候选并用 verifier 选择最优。


## 2. 原理性解释

- 字符串缓存只能命中完全相同表达。
- 语义缓存用 embedding 判断相似，但要有阈值和过期。
- Best-of-n 成本约为 n 倍，需要评估器。
- 重复检测还应看工具参数和 observation。

### 重复检测要从“字符串相等”升级到“语义等价”

你指出过一个关键问题：如果只用历史 query 的字符串完全匹配，用户换一种问法就会失效。工程上通常要结合标准化、embedding 相似度、意图分类和参数抽取。比如“介绍 Best-of-n 采样”和“什么是 best of n sampling”本质相近，应该能命中语义缓存。

Best-of-n 则是另一类优化：不是缓存已有结果，而是一次生成多个候选答案/行动路径，再用评分器选择更优结果。它提升质量，但会增加成本。

## 3. 机制流程

1. 计算 query embedding。
2. 查相似历史。
3. 命中则复用或改写。
4. 复杂任务并行生成候选。
5. 用 verifier 选最优。

### 语义缓存与 Best-of-n 流程

```python
def semantic_cache_lookup(query):
    q = normalize(query)
    qv = embed(q)
    hit = cache.search(qv, top_k=1)
    if hit and cosine(qv, hit.vector) > 0.88 and same_intent(query, hit.query):
        return hit.answer
    return None

def best_of_n(prompt, n=5):
    candidates = [llm(prompt, temperature=0.7) for _ in range(n)]
    scored = [(judge(prompt, c), c) for c in candidates]
    return max(scored)[1]
```

语义缓存适合稳定问答；Best-of-n 适合开放生成、推理或方案设计。二者可以组合：先查缓存，未命中再采样多个候选。

## 4. 类比理解

语义缓存像记得问过类似问题；Best-of-n 像多个人做题后选最优答案。

## 5. 应用举例 / 代码或伪代码

```python
hit = cache.search(embed(query), threshold=0.92)
if hit and not hit.expired:
    return adapt(hit.answer, query)

answers = [llm(question, temperature=0.7) for _ in range(n)]
return max(answers, key=lambda a: verifier(question, a))
```

## 6. 你在讨论中的理解推进

你指出同一问题不同表达会让简单缓存失效；因此需要语义相似度而非纯字符串匹配。

