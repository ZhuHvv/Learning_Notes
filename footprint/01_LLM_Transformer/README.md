# LLM / Transformer

本目录按“先建立全局地图，再理解张量与模块，随后进入架构、生成、训练和检索系统”的顺序组织。编号越大，知识从单个概念逐步走向完整工程链路。

知识点文件数：13

## 建议学习顺序

### 第一阶段：先看清输入、输出和总体结构

1. [Transformer 的作用：从 token 序列到上下文向量](001_Transformer_的作用：从_token_序列到上下文向量.md)
   先建立全局地图；这里出现的细节名词会在后续文件逐一展开。
2. [Token、Embedding、Seq Len 与 Hidden Size](002_Token、Embedding、Seq_Len_与_Hidden_Size.md)
   理解后续所有公式和代码共同使用的输入表示与张量形状。

### 第二阶段：拆开一个 Transformer Block

3. [Q K V 注意力机制](003_Q_K_V_注意力机制.md)
4. [Multi-Head Attention 与表达能力](004_Multi-Head_Attention_与表达能力.md)
5. [FFN 前馈神经网络](005_FFN_前馈神经网络.md)

这一阶段的依赖关系是：单头注意力 → 多头注意力 → Attention 与 FFN 共同组成 block。

### 第三阶段：从模块进入模型架构与生成

6. [Encoder、Decoder、Decoder-only 与 Cross Attention](006_Encoder、Decoder、Decoder-only_与_Cross_Attention.md)
7. [Causal Mask、自回归生成与 KV Cache](007_Causal_Mask、自回归生成与_KV_Cache.md)

先区分架构和可见范围，再理解 decoder-only 模型如何训练、逐 token 生成以及复用历史 K/V。

### 第四阶段：应用协议、训练与对齐

8. [Prompt、XML JSON 与工具调用格式](008_Prompt、XML_JSON_与工具调用格式.md)
9. [预训练、SFT、RLHF 与 LoRA](009_预训练、SFT、RLHF_与_LoRA.md)

008 先说明如何使用模型完成结构化交互；009 再深入模型能力如何通过预训练、后训练和参数高效微调形成。

### 第五阶段：从表示到完整检索链路

10. [稠密向量、稀疏向量与多向量表示及检索](010_稠密向量、稀疏向量与多向量表示及检索.md)
11. [倒排索引与稀疏检索](011_倒排索引与稀疏检索.md)
12. [Bi-encoder、Cross Encoder 与重排](012_Bi-encoder、Cross_Encoder_与重排.md)
13. [知识图谱、HyDE、RRF 与检索增强](013_知识图谱、HyDE、RRF_与检索增强.md)

这一阶段严格按依赖组织：先认识表示方式，再深入稀疏检索的数据结构，然后学习召回与重排，最后组合查询增强、多路召回和排名融合。

## 使用说明

- 第一次学习建议按编号阅读；复习时可直接进入某一阶段。
- 每篇先回答“输入、输出、解决什么问题”，再看公式和代码。
- 检索主题的完整 RAG 上下游位于 [Agent / RAG / Memory](../02_Agent_RAG_Memory/README.md)。

另有：[附_通用学习与排查模板](附_通用学习与排查模板.md)——v11 从本目录各文件抽取的共用模板段，正文中不再重复。
