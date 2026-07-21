# Agent Memory 四类：短期、情景、语义、程序性

> 所属分类：Agent / RAG / Memory  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Agent Memory 可分短期、情景、语义、程序性：短期是当前上下文，情景记录经历，语义保存事实，程序性保存做事方法。


## 2. 原理性解释

- 短期记忆容量有限但可直接被模型看到。
- 情景记忆记录具体事件。
- 语义记忆记录抽象事实。
- 程序性记忆记录 SOP、规则、工具使用策略。
- 长期记忆要有写入、检索、更新、遗忘机制。

### 四类记忆解决的不是同一类问题

短期记忆通常是当前上下文窗口里的消息和中间状态；情景记忆记录发生过的具体事件；语义记忆保存稳定事实、概念和用户偏好；程序性记忆保存“如何做事”的流程或技能。Agent 记忆设计如果不区分这些类型，就会把聊天记录、知识库、工具使用经验混在一起，检索时噪声很大。

例如“用户喜欢 C++”偏语义记忆；“上次调 Kafka 时把 localhost 拼成 locolhost”偏情景记忆；“排查 Docker volume 要先看挂载路径是否绝对路径”偏程序性记忆。

## 3. 机制流程

1. 判断是否值得记忆。
2. 分类存储。
3. 生成 embedding 和 metadata。
4. 任务时检索相关记忆。
5. 注入上下文或状态。

### 记忆写入与检索流程

```python
def classify_memory(event):
    if event.is_current_task_state:
        return "short_term"
    if event.is_specific_episode:
        return "episodic"
    if event.is_stable_fact:
        return "semantic"
    if event.is_how_to:
        return "procedural"
```

检索时也应按用途选择：回答用户偏好优先语义记忆；复盘问题优先情景记忆；执行任务优先程序性记忆；当前多轮对话则依赖短期状态。

## 4. 类比理解

短期像桌面纸，情景像日记，语义像百科卡，程序性像操作手册。

## 5. 应用举例 / 代码或伪代码

```python
memory = {
  "short": messages[-12:],
  "episodic": event_logs,
  "semantic": facts,
  "procedural": rules,
}
```

## 6. 你在讨论中的理解推进

你问短期记忆是否等同 context window；工程上可近似如此，但长期记忆需要外部系统。

