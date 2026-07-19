# 预训练、SFT、RLHF 与 LoRA

> 所属分类：LLM / Transformer  
> 修订版本：v11 审查修订版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

预训练学习语言分布，SFT 学会指令跟随，RLHF/DPO 对齐人类偏好，RLVR/GRPO 用可验证奖励强化推理能力，LoRA 用低秩增量做参数高效微调。


## 2. 原理性解释

- 预训练常用 next-token prediction。
- SFT 使用指令-回答样本。
- RLHF/DPO 优化偏好而非补实时知识。
- RLVR（可验证奖励强化学习，常用 GRPO 等算法）用数学/代码等可自动判定对错的任务做强化学习，延长思维链、提升推理能力；自 2025 年（DeepSeek-R1、o 系列）起已是推理模型后训练的标准环节。
- LoRA 冻结主权重，只训练低秩矩阵。

### 预训练、SFT、RLHF、LoRA 分别改变模型的哪一部分能力

预训练让模型学语言统计规律和世界知识；SFT 让模型学会按指令格式回答；RLHF/DPO 等偏好优化让模型更符合人类偏好；LoRA 则是一种低成本微调方式，通过给部分线性层增加低秩增量矩阵，让模型在少量参数上适配新任务。

可以把基础模型看成“读了大量书但不一定听话的人”，SFT 是“教它按问答格式办事”，RLHF 是“告诉它哪些回答更好”，LoRA 是“不给整个人重训，只给关键神经通路加小插件”。

```python
# LoRA 思想：原权重 W 冻结，只训练低秩矩阵 A/B（缩放因子为 alpha/r）
W_eff = W + (alpha / r) * (A @ B)
output = x @ W_eff
```

## 3. 机制流程

1. 预训练。
2. SFT。
3. 偏好对齐。
4. 部署时结合 prompt/RAG/tool。
5. 必要时 LoRA 微调。

### 模型训练/适配的流程选择

```text
大规模无监督语料 → 预训练 base model
  ↓
人工指令数据 → SFT instruct model
  ↓
偏好数据 / reward model / DPO → 对齐模型
  ↓
可验证奖励任务（数学/代码）+ RL（GRPO 等） → 推理增强模型（推理模型必经）
  ↓
领域数据 + LoRA/QLoRA → 垂直任务适配
```

工程上不要把所有问题都归结为“微调”。如果知识频繁变化，优先 RAG；如果输出格式不稳定，优先 prompt/schema/SFT；如果领域风格和任务策略长期稳定，才考虑 LoRA 或全参微调。

## 4. 类比理解

预训练像读书，SFT 像学答题格式，RLHF 像老师按偏好打分，LoRA 像加一个小适配器。

## 5. 应用举例 / 代码或伪代码

```python
# y = x @ (W + (alpha/r) * A @ B)
W.requires_grad_(False)
A = Parameter(randn(in_dim, r))    # 下投影：随机初始化
B = Parameter(zeros(r, out_dim))   # 上投影：零初始化，保证训练起点 ΔW=0，不破坏预训练行为
y = x @ W + (alpha / r) * (x @ A @ B)
```

## 6. 你在讨论中的理解推进

对 AI 应用开发而言，优先判断问题该用 prompt、RAG、工具还是微调解决。

