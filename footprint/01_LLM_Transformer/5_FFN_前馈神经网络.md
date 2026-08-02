# FFN 前馈神经网络

## 1. 总体性概念

FFN 是 Transformer block 中对每个 token 独立执行的非线性变换；attention 负责信息交互，FFN 负责信息加工。


## 2. 原理性解释

- FFN 通常是 hidden -> intermediate -> hidden。
- 激活函数引入非线性。
- 它不直接做 token 间通信。
- 很多模型参数大量集中在 FFN。

### FFN 为什么放在 Attention 后面

Attention 解决的是 token 之间的信息交换，但它主要是加权求和，表达上偏线性组合。FFN 则对每个 token 的 hidden 向量单独做非线性变换，相当于把刚刚从上下文收集来的信息进一步加工、筛选和重编码。

典型 FFN 是两层线性层加激活函数，中间维度通常比 hidden size 大，例如 `4 * hidden_size`。这相当于先把特征投影到更高维空间里展开，再压回原维度。

```python
def ffn(x):
    return W2 @ gelu(W1 @ x + b1) + b2
```

所以 FFN 的作用不是“让 token 之间再交流一次”，而是“每个 token 对自己已经融合的上下文信息做深加工”。

## 3. 机制流程

1. attention 输出上下文向量。
2. LayerNorm。
3. FFN 升维、激活、降维。
4. 残差相加。

### 一层 Transformer Block 的完整顺序

现代模型常用 Pre-LN 结构：

```text
x
 ├─ LayerNorm → Self-Attention → Residual Add
 ↓
x'
 ├─ LayerNorm → FFN → Residual Add
 ↓
out
```

其中 residual connection 让模型可以保留原信息，LayerNorm 稳定训练，FFN 提供非线性表达能力。排查模型结构时，要区分：Attention 的复杂度主要与 `seq_len²` 有关；FFN 的计算量主要与 `hidden_size * intermediate_size` 有关。

## 4. 类比理解

attention 像收资料，FFN 像个人整理资料并形成新表达。

## 5. 应用举例 / 代码或伪代码

```python
class FFN(nn.Module):
    def __init__(self, h=768, mid=3072):
        self.w1 = nn.Linear(h, mid)
        self.w2 = nn.Linear(mid, h)
    def forward(self, x):
        return self.w2(F.gelu(self.w1(x)))
```

## 6. 你在讨论中的理解推进

你先关注 attention，随后追问 FFN 的作用；关键结论是二者分别负责交互和加工。

