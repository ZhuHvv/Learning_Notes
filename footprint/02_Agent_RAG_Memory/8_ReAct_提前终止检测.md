# ReAct 提前终止检测

## 1. 总体性概念

ReAct 提前终止检测判断已有信息是否足够回答，或是否已经陷入重复、低收益、工具失败循环。


## 2. 原理性解释

- 终止条件包括信息覆盖度、一致性、重复行动、预算上限。
- 信息充分性适合确切问答。
- 重复检测适合防循环。
- 冲突证据未解决时不应过早结束。

### 提前终止检测要同时看“充分性”和“循环性”

你之前总结得很准确：提前终止主要有两个方向：一是当前信息是否足够回答用户问题，二是最近若干轮行动是否重复或没有增益。ReAct 如果只靠模型自己说“我完成了”，容易过早结束；如果完全不终止，又会无限查找。

充分性检测可以看：用户问题中的槽位是否都被填充、关键结论是否有证据、不同证据是否一致、是否存在未解决约束。循环性检测可以看：工具名重复、query 高相似、observation 无新信息、状态摘要变化很小。

## 3. 机制流程

1. 每轮 ReAct 后抽取 evidence。
2. 评估 query 所需槽位覆盖。
3. 检测最近 action/observation 相似度。
4. 满足条件则合成答案。

### 提前终止伪代码

```python
def should_stop(state):
    if has_final_answer(state) and evidence_covers_question(state):
        return True, "answer_sufficient"
    if contradiction_unresolved(state):
        return False, "need_disambiguation_or_more_evidence"
    if repeated_actions(state.trace[-3:]) and no_new_evidence(state):
        return True, "loop_detected"
    if state.steps >= MAX_STEPS:
        return True, "max_steps"
    return False, "continue"
```

最终回答中可以根据停止原因调整语气：充分停止就直接回答；循环停止要说明“已查到的信息有限”；最大步数停止要给出阶段性结论和不确定点。

## 4. 类比理解

查资料时资料够了就下笔；连续翻到同一页就该停止。

## 5. 应用举例 / 代码或伪代码

```python
def should_stop(state):
    if coverage(state.question, state.evidence) > 0.85 and not conflict(state.evidence):
        return True, "evidence enough"
    if repeated(state.steps[-3:]):
        return True, "loop detected"
    return len(state.steps) >= 8, "budget"
```

## 6. 你在讨论中的理解推进

你已经总结出两个角度：信息是否足够、最近若干轮是否重复；这里将其工程化。

