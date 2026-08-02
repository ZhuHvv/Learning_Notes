# 01.10 词向量与文本 Embedding 演进：Word2Vec、GloVe、BERT、SBERT、SimCSE 与 BGE

## 1. 总体性概念

更准确的演进路线是：

```text
静态词级表示
  Word2Vec / GloVe
        ↓
上下文化 Token 表示
  BERT
        ↓
面向相似度与检索优化的文本级表示
  SBERT / SimCSE / BGE
```

最核心的变化不仅是表示对象从“词”扩展到“句子”，更是训练目标发生了变化：

- Word2Vec：能否根据局部上下文预测词？
- GloVe：词向量能否拟合全局共现统计？
- BERT：能否根据双向上下文理解并恢复 Token？
- SBERT、SimCSE、BGE：语义相关的完整文本能否在向量空间中靠近？

## 2. 静态词向量：Word2Vec 与 GloVe

### 2.1 固定词表中的一词一向量

静态词向量为词表中的每个词维护一个固定向量：

```text
bank → [0.12, -0.35, 0.87, ...]
```

无论 `bank` 出现在 `river bank` 还是 `bank account`，查到的都是同一个向量。

### 2.2 Word2Vec：通过局部预测学习表示

Word2Vec 的两种主要结构是：

- **CBOW**：根据窗口内的上下文词预测中心词；
- **Skip-gram**：根据中心词预测窗口内的上下文词。

Skip-gram 的目标可写为：

$$
\sum_{-c \le j \le c,\,j\ne0}\log P(w_{t+j}\mid w_t)
$$

完整 Softmax 需要遍历整个词表，训练中通常使用 Negative Sampling 或 Hierarchical Softmax 降低成本。负采样下，一个正样本词对 $(w,c)$ 的损失可以写为：

$$
-\log \sigma(v_w^\top v_c)
-\sum_{i=1}^{k}\log \sigma(-v_w^\top v_{n_i})
$$

目标是让真实共现词的向量靠近，让随机负样本远离。

### 2.3 GloVe：拟合全局共现统计

GloVe 先统计词—词共现矩阵：

$$
X_{ij}=\text{词 }i\text{ 与词 }j\text{ 在窗口中共同出现的次数}
$$

再优化加权最小二乘目标：

$$
J=\sum_{i,j}f(X_{ij})
\left(w_i^\top\tilde w_j+b_i+\tilde b_j-\log X_{ij}\right)^2
$$

它让两个词向量的点积近似共现次数的对数。Word2Vec 主要从滑动窗口预测任务学习，GloVe 则显式使用整个语料库的全局共现统计。

### 2.4 静态词向量的缺陷

1. **无法处理一词多义**：`苹果很好吃` 与 `苹果发布了新手机` 中的“苹果”仍是同一向量。
2. **不能天然表示句子**：简单平均词向量会丢失词序、语法和否定关系，`狗咬人` 与 `人咬狗` 甚至可能得到相同均值。
3. **固定词表带来 OOV**：训练词表外的词没有对应向量。FastText 的字符 n-gram 能部分缓解此问题，但这不是标准 Word2Vec 或 GloVe 本身的能力。

## 3. 上下文化表示：BERT

### 3.1 多层双向 Transformer Encoder

BERT 不是一张静态词向量表。其输入和输出可概括为：

```text
Token Embedding + Position Embedding + Segment Embedding
                         ↓
              多层 Transformer Encoder
                         ↓
        H = [h1, h2, ..., hn]  # 每个 Token 的上下文化表示
```

每个 $h_i$ 都综合了句中其他 Token 的信息，所以“苹果”在水果和公司语境中会得到不同的隐藏状态。

### 3.2 原始 BERT 的预训练任务

Masked Language Model（MLM）随机遮盖部分 Token，并利用左右上下文恢复它们：

$$
L_{\mathrm{MLM}}=-\sum_{i\in M}\log P(x_i\mid x_{\setminus M})
$$

原始 BERT 还包含 Next Sentence Prediction（NSP）：输入 `[CLS] sentence A [SEP] sentence B [SEP]`，判断 B 是否是 A 的后续句。RoBERTa 等后续研究表明 NSP 并非在所有场景都必要；它是原始 BERT 的训练设计，不是上下文化表示的必要条件。

### 3.3 BERT 的关键缺陷

- **不天然产生高质量句向量**：可以取 `[CLS]` 或对 Token 做 mean pooling，但 MLM 并未直接要求相似句靠近、无关句远离；未经针对性训练的 BERT 句向量在语义相似度任务中可能表现不佳，向量空间也可能存在各向异性。
- **Cross-Encoder 检索成本高**：把 `[CLS] query [SEP] document [SEP]` 一起编码可以获得细粒度交互，但面对 $N$ 个文档需要执行 $N$ 次模型推理，文档不能提前独立向量化，不适合作为大规模第一阶段召回。

## 4. 文本级 Embedding 的共同结构

SBERT、SimCSE、BGE 通常仍使用 BERT、RoBERTa 等 Transformer 作为编码器，但会直接优化文本在向量空间中的位置：

```text
文本
  ↓ Tokenizer 与 Embedding Layer
初始 Token 向量
  ↓ Transformer
上下文化 Token 向量
  ↓ Pooling
固定长度文本向量
```

假设 Transformer 输出为：

$$
H=
\begin{bmatrix}
h_{\mathrm{CLS}}\\
h_1\\
\vdots\\
h_n
\end{bmatrix}
\in\mathbb{R}^{(n+1)\times d}
$$

句子向量是聚合函数 $g$ 的输出：

$$
z=g(H),\qquad z\in\mathbb{R}^{d}
$$

因此文本级 Embedding 并没有跳过 Token 表示，而是在一组上下文化 Token 向量之上增加可微分聚合，并用文本级目标端到端训练。

### 4.1 Mean Pooling

带 padding mask 的 mean pooling 为：

$$
e(s)=\frac{\sum_i m_i h_i}{\sum_i m_i}
$$

其中 $m_i$ 用于排除 padding Token。

Mean Pooling 并不是在平均 Word2Vec 式的孤立词向量。经过 Transformer 后，每个输出都已依赖整段上下文：

$$
h_i=f(x_i,x_1,x_2,\ldots,x_n)
$$

所以“苹果很好吃”和“苹果发布了新手机”中的“苹果”会携带不同的全句信息，平均后的结果也不同。

### 4.2 `[CLS]` Pooling

也可以直接取序列开头的特殊 Token：

$$
z=h_{\mathrm{CLS}}
$$

`[CLS]` 在每层 Self-Attention 中读取其他 Token 的信息，最终状态可聚合整段输入。原始 BERT 会将最终 `[CLS]` 用于句子级分类，但这不等于其余弦距离已经适合语义检索；是否可用于检索仍取决于后续训练目标。

### 4.3 可学习的 Attention Pooling

模型还可以学习每个 Token 的聚合权重：

$$
z=\sum_i\alpha_i h_i,\qquad \sum_i\alpha_i=1
$$

例如在“苹果公司发布了新手机”中，模型可能给“手机”“发布”等 Token 更高权重。SBERT、SimCSE、BGE 并不统一采用这一方式，具体模型可能使用 `[CLS]`、Mean Pooling 或其他专用 pooling，必须以模型卡和实现为准。

### 4.4 Pooling 为什么必须配合文本级训练

Pooling 只是把形状从 `[batch, seq_len, hidden_size]` 变为 `[batch, hidden_size]`，本身并不理解语义。以 Mean Pooling 为例：

$$
z=\frac{1}{n}\sum_i h_i
$$

若对 $z$ 计算文本级对比损失 $L$，梯度会经过 Pooling 回传到每个 Token 表示：

$$
\frac{\partial L}{\partial h_i}
=\frac{1}{n}\frac{\partial L}{\partial z}
$$

随后继续更新整个 Transformer。模型为了降低文本级损失，会逐渐学会生成“聚合后仍保留任务所需整段语义”的 Token 表示。因此第三阶段的能力可以概括为：

$$
\boxed{
\text{文本向量能力}
=\text{上下文化 Token 表示}
+\text{聚合函数}
+\text{文本级训练目标}
}
$$

直接对未经相似度训练的原始 BERT 做 Mean Pooling，数学上当然能得到固定长度向量，有时也比直接取 `[CLS]` 好，但并未解决向量空间与检索目标不匹配的问题。

## 5. SBERT：把 BERT 改造成可独立编码的 Bi-Encoder

SBERT 使用共享参数的 Siamese/Triplet 网络，也常称为 Bi-Encoder 或 Dual Encoder：

```text
sentence A → Encoder → Pooling → u
sentence B → Encoder → Pooling → v
```

对于查询 $q$ 和文档 $d$：

$$
e_q=f_\theta(q),\qquad e_d=f_\theta(d)
$$

$$
\operatorname{score}(q,d)=\cos(e_q,e_d)
$$

两个文本可分别编码并计算余弦相似度：

$$
\operatorname{sim}(u,v)=\frac{u^\top v}{\|u\|\|v\|}
$$

训练可使用分类、回归或 Triplet Loss：

$$
L=\max(\|e_a-e_p\|-\|e_a-e_n\|+\epsilon,0)
$$

$a$、$p$、$n$ 分别是锚点、语义相近文本和负样本。

与把 `[CLS] query [SEP] document [SEP]` 联合输入的 Cross-Encoder 不同，Bi-Encoder 的文档向量可提前计算并建立索引。面对 $N$ 个文档，Cross-Encoder 每次查询需要执行约 $N$ 次联合编码；Bi-Encoder 只需编码一次查询，再执行向量内积或近似最近邻搜索。

缺陷包括：

- 效果依赖 NLI、STS 等训练数据及其领域覆盖；
- 单一向量会压缩掉词级细节；
- 双塔的 query 与 document 不直接交互，精度通常低于 Cross-Encoder；
- 对训练领域外的语义关系可能泛化不足。

## 6. SimCSE：用对比学习改善句向量空间

### 6.1 无监督 SimCSE

同一句子在训练模式下输入模型两次，不同 Dropout mask 产生略有差异的向量，二者构成正样本；同一批次的其他句子充当负样本：

```text
sentence → Encoder(dropout mask 1) → z
sentence → Encoder(dropout mask 2) → z+
```

常用 InfoNCE 损失：

$$
L_i=-\log
\frac{e^{\operatorname{sim}(z_i,z_i^+)/\tau}}
{\sum_{j=1}^{N}e^{\operatorname{sim}(z_i,z_j^+)/\tau}}
$$

在一个 batch 中，第 $i$ 个句子的第一种 Dropout 表示与其第二种表示互为正样本，其他句子的表示充当 In-batch Negatives。这样无需为每个句子单独构造大量随机负样本，但也会带来“批内语义相似句被误当成负样本”的风险。

这一目标不仅拉近同句的两种表示，也会改善表示的 alignment 和 uniformity，从而缓解原始 BERT 句向量集中在狭窄方向、各向异性明显的问题。

### 6.2 有监督 SimCSE

有监督版本使用自然语言推理数据：entailment 作为正样本，contradiction 作为困难负样本。

主要缺陷是：

- 无监督版本可能把批内语义相似句误当负样本；
- 对 batch size 和温度 $\tau$ 较敏感；
- Dropout 形成的正样本变化较弱；
- 主要针对句子语义相似度优化，不一定直接适合“短查询检索长文档”。

## 7. BGE：面向通用文本表示与检索优化

BGE 不是完全不同的基础网络，而是一套面向检索的模型与多阶段训练方案。典型双塔仍是：

```text
query   → Transformer → Pooling → q
passage → Transformer → Pooling → p
```

向量归一化后以内积打分：

$$
\operatorname{score}(q,p)=q^\top p
$$

此时内积等价于余弦相似度。BGE 更强调大规模 query-document 数据、多任务与跨领域数据，并结合弱监督文本对训练、有监督对比学习和困难负样本训练。部分模型会在查询侧加入检索任务指令，例如“为这个句子生成表示以用于检索相关文章：人工智能是什么？”，文档侧通常不加同一指令；实际使用必须遵循具体模型卡。

困难负样本不是与查询毫无关系的随机文本，而是“主题接近但答案不匹配”的文本。例如：

```text
查询：Python 如何读取文件？
正样本：使用 open() 打开并读取文件。
简单负样本：今天北京天气如何？
困难负样本：Python 如何创建并写入文件？
```

简单负样本很容易区分；困难负样本会迫使模型学习“读取”与“写入”这种更细的语义边界。

主要缺陷与边界：

- 对查询指令、训练任务和数据分布敏感；
- 困难负样本质量直接影响训练效果；
- 单向量可能丢失长文档中的局部信息；
- 精确关键词、编号、代码和专有名词可能不如 BM25；
- 相似度绝对值通常不能脱离具体数据集直接解释，需要校准阈值；
- Bi-Encoder 召回精度通常低于 Cross-Encoder，工程中常采用 `BGE Embedding 召回 Top-K → BGE Reranker 精排`。

## 8. 总体对比

| 类型 | 基本表示 | 如何得到文本向量 | 是否专门优化文本相似度 | 适合场景 | 核心缺陷 |
|---|---|---|---:|---|---|
| Word2Vec / GloVe | 每个词一个固定向量 | 对词向量求和或平均 | 否 | 词相似度、轻量特征 | 一词多义、OOV、词序丢失 |
| BERT | 每个 Token 一个上下文化向量 | 取 `[CLS]` 或平均 Token | 原始预训练通常否 | 阅读理解、分类、抽取 | 不天然产生高质量句向量 |
| SBERT | 一个文本一个向量 | Pooling 后用 NLI、STS、Triplet 等训练 | 是 | 语义搜索、聚类 | 依赖监督数据，双塔交互不足 |
| SimCSE | 一个文本一个向量 | Pooling 后进行对比学习 | 是 | 句子相似度 | 假负样本，对批次和温度敏感 |
| BGE | 面向检索的文本向量 | Pooling 后进行多阶段检索训练 | 是 | RAG、文本检索 | 长文本压缩、领域偏差，常需精排 |

## 9. 最小机制示例

### 9.1 训练：让文本距离具备任务语义

假设 batch 中第 $i$ 个 query 与第 $i$ 个 document 是正样本，其他 document 是 In-batch Negatives。归一化后，矩阵乘法就是两两余弦相似度：

```python
import torch
import torch.nn.functional as F


def contrastive_loss(
    query_embeddings: torch.Tensor,
    document_embeddings: torch.Tensor,
    temperature: float = 0.05,
) -> torch.Tensor:
    queries = F.normalize(query_embeddings, p=2, dim=-1)
    documents = F.normalize(document_embeddings, p=2, dim=-1)
    scores = queries @ documents.T / temperature
    labels = torch.arange(scores.size(0), device=scores.device)
    return F.cross_entropy(scores, labels)
```

对应的 InfoNCE 目标为：

$$
L_i=-\log
\frac{\exp(\operatorname{sim}(q_i,p_i^+)/\tau)}
{\exp(\operatorname{sim}(q_i,p_i^+)/\tau)
+\sum_j\exp(\operatorname{sim}(q_i,p_j^-)/\tau)}
$$

完整反向链路是：

```text
Token ID → 初始 Token Embedding → Transformer
         → 上下文化 Token 向量 → Pooling → 文本向量
         → 对比损失 → 反向更新 Pooling 与 Transformer
```

### 9.2 推理：提前建库并进行向量召回

```python
def masked_mean_pool(last_hidden_state, attention_mask):
    # last_hidden_state: [batch, seq_len, hidden_size]
    # attention_mask:    [batch, seq_len]
    mask = attention_mask.unsqueeze(-1).to(last_hidden_state.dtype)
    summed = (last_hidden_state * mask).sum(dim=1)
    counts = mask.sum(dim=1).clamp_min(1e-9)
    return summed / counts


query_vectors = normalize(encoder(query_texts))
document_vectors = normalize(encoder(document_texts))  # 可离线预计算
scores = query_vectors @ document_vectors.T
```

这段代码表达的是文本级 Bi-Encoder 的共同数据流；不同模型的 pooling、指令模板、归一化要求和最大长度必须以各自模型卡为准。

由于每篇文档都有与当前查询无关的固定向量，可以使用 HNSW、IVF、Product Quantization 等 ANN 方案，并通过 FAISS、Milvus 等系统建立向量索引。Cross-Encoder 的文档表示依赖 query，不能直接建立这种可复用的单文档向量索引。

## 10. 你在讨论中的理解推进

- 起点：以“静态词向量 → BERT → 句子级 Embedding”三代模型理解演进。
- 概念修正：这不是正式分代，更准确的是表示粒度和训练目标的连续变化。
- 使用方式修正：BERT 并非只能把两段文本一起输入；它也能独立输出单段文本的 `[CLS]` 或 Token 均值，真正的问题是原始训练并未保证这些向量的距离等于语义相关性。
- 关键连接：句子向量来自“上下文化 Token 表示 + Pooling + 句子级目标”；损失虽然计算在聚合向量上，梯度仍会回到每个 Token 和整个 Transformer。
- 训练目标修正：MLM 目标不等于检索目标；SBERT、SimCSE、BGE 的价值在于直接塑造文本向量空间。
- 最终理解：召回模型的单向量压缩换取可预计算和高吞吐，Cross-Encoder 则用更高成本换取 query-document 细粒度交互，因此两者常组成召回与精排链路。

## 11. 关联知识点

- [Token、Embedding、Seq Len 与 Hidden Size](02_Token、Embedding、Seq_Len_与_Hidden_Size.md)
- [稠密向量、稀疏向量与多向量表示及检索](11_稠密向量、稀疏向量与多向量表示及检索.md)
- [Bi-encoder、Cross Encoder 与重排](13_Bi-encoder、Cross_Encoder_与重排.md)
- [RAG 完整链路：召回、融合、重排、生成](../02_Agent_RAG_Memory/18_RAG_完整链路：召回、融合、重排、生成.md)

## 12. 参考资料

- [Efficient Estimation of Word Representations in Vector Space（Word2Vec）](https://arxiv.org/abs/1301.3781)
- [GloVe: Global Vectors for Word Representation](https://nlp.stanford.edu/projects/glove/)
- [BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding](https://aclanthology.org/N19-1423/)
- [On the Sentence Embeddings from Pre-trained Language Models](https://aclanthology.org/2020.emnlp-main.733/)
- [Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks](https://aclanthology.org/D19-1410/)
- [SimCSE: Simple Contrastive Learning of Sentence Embeddings](https://aclanthology.org/2021.emnlp-main.552/)
- [C-Pack / BGE 技术报告](https://arxiv.org/abs/2309.07597)
- [FlagEmbedding 官方实现](https://github.com/FlagOpen/FlagEmbedding)
