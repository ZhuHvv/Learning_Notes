# Transformer 的作用：从 token 序列到上下文向量

> 所属分类：LLM / Transformer  
> 修订版本：v12 学习顺序审查版
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。
> 阅读定位：本篇只建立全局地图；Token、Attention、FFN 等名词会在 002～005 中由浅入深展开。

## 1. 总体性概念

Transformer 的作用是把 token 序列变成带上下文语义的向量序列；训练和推理都使用同一套结构。它不是单独的“训练工具”，而是模型本身的计算骨架。


## 2. 原理性解释

- 输入 token id 经 embedding 变成矩阵 X。
- 每层 block 先通过 attention 做 token 间信息交互，再通过 FFN 做逐 token 非线性加工。
- 层与层串行堆叠，第 n 层输出是第 n+1 层输入。
- decoder-only 最后把隐藏向量映射到词表 logits。

### Transformer 到底“变换”了什么

Transformer 并不是把一句话整体当成一个黑盒字符串处理，而是把输入拆成 token 后，让每个 token 的向量在多层网络中不断吸收上下文信息。第 0 层的 token 向量主要表示“这个 token 自己是什么”；经过若干层 Attention 和 FFN 后，同一个 token 位置上的向量会逐渐包含“它在当前句子里是什么意思”。例如“苹果发布新品”和“我吃了苹果”里的“苹果”，初始 embedding 可以相同，但经过上下文交互后会变成不同的上下文向量。

可以把每一层看成一次“全班讨论 + 个人加工”：Attention 负责让每个 token 向其它 token 询问信息，FFN 负责对自己融合后的信息做非线性加工。层数越深，不代表简单地重复同一件事，而是让表示从局部词义逐步过渡到句法关系、语义关系、任务意图等更高层特征。

一个极简抽象：

```python
X = token_embedding(tokens)
X = inject_position_information(X)  # 如绝对位置向量；RoPE 则通常作用在注意力的 Q/K 上
for block in transformer_blocks:
    X = X + block.self_attention(norm(X))   # 跨 token 交换信息
    X = X + block.ffn(norm(X))              # 每个 token 独立做特征变换
return X  # [seq_len, hidden_size]，每一行都是上下文化后的 token 表示
```

## 3. 机制流程

1. 文本分词。
2. 查 embedding。
3. 经过多层 attention + FFN。
4. 输出 logits 或语义向量。
5. 生成、分类或检索使用输出。

### 从输入到输出的逐层机制

更细地看，Transformer 的主流程可以拆成 6 步：

1. 文本被 tokenizer 切成 token id。
2. token id 查表得到 embedding，并通过绝对位置向量、RoPE 等方式注入位置信息。
3. 每层先通过自注意力计算 token 之间的依赖关系。
4. 再通过 FFN 对每个位置的表示做非线性投影。
5. 多层堆叠后，每个位置都得到上下文化表示。
6. 对于 decoder-only 模型，最后一个位置的 hidden state 会接 LM Head，预测下一个 token 的概率分布。

```python
def transformer_forward(token_ids):
    x = embed[token_ids]
    for layer in layers:
        attn_out = layer.attention(layer.norm1(x), position_ids=range(len(token_ids)))
        x = x + attn_out
        ffn_out = layer.ffn(layer.norm2(x))
        x = x + ffn_out
    logits = x @ lm_head.T
    return logits
```

## 4. 类比理解

像多人会议纪要：每个词先带着自身含义入场，注意力听别人说什么，FFN 整理自己的理解。

## 5. 应用举例 / 代码或伪代码

```python
ids = tokenizer.encode(prompt)
for _ in range(max_new_tokens):
    x = embedding(ids)
    for block in blocks:
        x = block(x)
    next_id = sample(lm_head(x[-1]))
    ids.append(next_id)
```

## 6. 你在讨论中的理解推进

你从“Transformer 是否只是训练用”推进到：它是模型结构，训练时学习参数，推理时用参数逐步计算输出。
