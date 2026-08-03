# 05.16 Milvus Segment、Compaction、持久化与内存加载

> 版本边界：本文整理自一组以 Milvus 2.5/2.6 文档与 PyMilvus 2.6.x 接口为主要依据的讨论。配置默认值和管理 API 可能随版本变化，部署时应以实际版本文档为准。

## 1. 总体性概念

Milvus 不是传统意义上的内存数据库。更准确地说，它是：

> 以对象存储或本地磁盘作为持久化层，以 Query Node 的内存、mmap 或磁盘型索引作为查询执行层的向量数据库。

理解其存储与查询机制需要抓住两个核心：

- **Segment** 是一批完整实体数据，是 Milvus 持久化、加载、建索引、搜索和合并的基本单元；
- **Compaction** 读取多个旧 Segment 的有效数据并重写成新 Segment，而不是直接拼接旧 HNSW 图或 IVF 索引文件。

“原始向量在磁盘，只把索引放在内存”只能描述部分量化索引、mmap 或冷热分层配置。对于 IVF_FLAT、普通 HNSW 等索引，加载的索引本身就可能包含原始向量或完整精度的向量表示。

## 2. Segment 是什么

### 2.1 数据层级

```text
Collection：documents
├── Partition：default
│   ├── Segment 1001
│   │   ├── Entity 1
│   │   ├── Entity 2
│   │   └── ...
│   ├── Segment 1002
│   └── Segment 1003
└── Partition：archive
    ├── Segment 2001
    └── Segment 2002
```

对应关系是：

```text
Collection
  └── Partition
        └── Segment
              └── Entity
```

- `Collection` 类似一张表；
- `Partition` 是用户可感知的数据分区；
- `Segment` 是 Milvus 自动创建和管理的数据块；
- `Entity` 类似表中的一行数据。

一个 Partition 可以包含多个 Segment，一个 Segment 可以保存许多 Entity。Segment 类似关系数据库中的数据页或数据分片，但并不完全等同。

### 2.2 Segment 保存完整实体，不只保存向量

假设 Collection Schema 是：

```python
{
    "id": "INT64",
    "text": "VARCHAR",
    "category": "VARCHAR",
    "embedding": "FLOAT_VECTOR",
}
```

某个 Segment 覆盖的是这一批实体的所有字段：

```text
Segment 1001
├── id
├── text
├── category
└── embedding
```

因此：

```text
一个 Segment ≠ 一个向量
一个 Segment = 一批数据行及这些行的所有字段
```

逻辑上可以把 Segment 类比成一个数据文件；实际持久化时，一个 Segment 可对应向量字段文件、标量字段 binlog、删除日志和索引文件等多个物理文件。

### 2.3 Growing Segment 与 Sealed Segment

新数据先进入 Growing Segment：

```text
insert
  ↓
Growing Segment
  ├── 持续接收新数据
  ├── 数据可参与实时搜索
  └── 通常还没有完整的持久化 ANN 索引
```

当容量、行数、时间等条件触发 seal/flush 后，它转为 Sealed Segment：

```text
Growing Segment
      ↓ seal / flush
Sealed Segment
      ├── 不再接收新数据
      ├── 持久化到对象存储或本地存储
      └── 构建 HNSW、IVF 等索引
```

随后新写入进入新的 Growing Segment。一次查询需要同时覆盖实时 Growing Segment 与历史 Sealed Segment。

## 3. Segment 与索引、查询的关系

Milvus 通常按 Segment 构建独立索引，而不是为整个 Collection 只维护一个全局 ANN 索引：

```text
Segment A → HNSW Index A
Segment B → HNSW Index B
Segment C → HNSW Index C
```

查询路径可简化为：

```text
查询向量
  ├── 搜索 Segment A
  ├── 搜索 Segment B
  ├── 搜索 Segment C
  └── 搜索 Growing Segment
              ↓
       合并各 Segment 的 Top-K
```

这解释了 Segment 过多的代价：

- 查询分发次数增加；
- 每个 Segment 都有索引搜索开销；
- 各 Segment Top-K 的全局合并开销增加；
- Segment 元数据、索引与生命周期管理更复杂。

## 4. Compaction 如何合并 Segment

### 4.1 合并的是有效数据，不是旧索引文件

假设旧数据为：

```text
Segment A：id=1, id=2, id=3（已删除）
Segment B：id=4, id=5
Segment C：id=6
```

Compaction 的抽象过程是：

```text
Segment A + Segment B + Segment C
                ↓
读取 insert binlog 与 delete log
                ↓
过滤逻辑删除、TTL 过期的数据
                ↓
生成 Segment D：id=1, id=2, id=4, id=5, id=6
                ↓
旧 Segment 标记为 Dropped
                ↓
后台 GC 最终清理旧文件
```

Milvus 的删除最初通常表现为逻辑删除，不会立刻释放旧 Segment 的磁盘空间。Compaction 将仍然有效的数据写入新 Segment，旧 Segment 进入 `Dropped` 状态后再由 GC 清理。

### 4.2 新 Segment 需要新索引

Compaction 不是：

```text
HNSW A + HNSW B → 直接拼成 HNSW D
```

而是：

```text
合并有效字段数据或量化编码
        ↓
生成新 Segment D
        ↓
为 Segment D 构建新索引 D
```

该原则适用于 HNSW、IVF_FLAT、IVF_SQ8、IVF_PQ 等索引。以 IVF_SQ8 为例，系统会读取仍有效的 SQ8 编码或对应字段数据，重新组织到新 Segment，再为新数据边界生成 IVF 索引；它不会直接把旧 IVF 文件拼接起来。

### 4.3 三类 Compaction

讨论所依据的 Milvus 2.6.x 配置与接口中，可把 Compaction 分成三类：

1. **Mix Compaction**：把多个较小的 sealed Segment 合并为较少、较大的 Segment，并清除已允许物理删除的数据。这是通常所说的后台 Segment 合并。
2. **L0 Compaction**：L0 Segment 主要承载删除记录；L0 Compaction 把这些删除操作应用到实际数据 Segment，减少查询阶段重复处理删除日志的成本。
3. **Clustering Compaction**：按某个标量聚类键重新组织实体，使带过滤条件的查询能够跳过无关 Segment。

Clustering Compaction 示例：

```text
原来：
Segment A：tenant=1、3、7 混合
Segment B：tenant=2、3、8 混合

聚类压缩后：
Segment C：tenant=1～3
Segment D：tenant=7～8
```

Milvus 可维护 `PartitionStats`，记录聚类键值与 Segment 的映射，以支持 Segment pruning。

### 4.4 手动触发与状态查询

PyMilvus 2.6.x 的最小示例：

```python
from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530",
    token="root:Milvus",
)

job_id = client.compact(collection_name="documents")
state = client.get_compaction_state(job_id=job_id)

print("compaction job:", job_id)
print("state:", state)
```

`compact()` 返回任务 ID，`get_compaction_state()` 可查询 `Executing`、`Completed` 等状态。普通 Collection 通常应主要依赖后台自动 Compaction，不应在不了解触发条件和资源开销时频繁手动调用。不同 PyMilvus 版本的参数和状态枚举需按对应 API 文档核对。

## 5. Milvus 为什么不是内存数据库

### 5.1 持久化层才是长期数据源

```text
WAL
└── 保存尚未完成持久化的写入操作

对象存储 / 本地持久化存储
├── Segment 字段数据与 binlog
├── 原始向量
├── 标量字段
└── 向量及标量索引文件
```

Query Node 被替换或服务重启后，数据依靠持久化存储恢复，而不是依靠旧进程内存：

```text
对象存储或本地磁盘：长期数据源
              ↓ load
Query Node 查询资源：运行时加速层
```

这与把内存作为主要数据状态的典型 Redis 使用模式不同。更接近 MySQL 的“磁盘数据页 + Buffer Pool”，只是 ANN 搜索对随机访问和内存带宽更敏感。

### 5.2 load/release 说明查询层高度依赖内存

传统查询路径通常需要先加载 Collection：

```python
client.load_collection(collection_name="documents")
```

加载后，Query Node 获得搜索所需的资源：

```text
持久化存储
   ↓ load Collection / Segment
Query Node
├── ANN 索引
├── 搜索需要的向量数据
├── 过滤需要的标量字段
└── 主键及相关元数据
```

不再使用时可通过 `release_collection()` 释放查询资源。Milvus 的查询执行因此是内存密集型的，但“运行时依赖内存”不等于“持久数据只存在内存”。

### 5.3 “索引在内存、原始向量在磁盘”取决于索引类型

**IVF_FLAT** 的倒排列表内部保存未压缩的原始向量：

```text
IVF_FLAT Index
├── 聚类中心
├── 倒排列表
└── 列表内的原始 float32 向量
```

所以把 IVF_FLAT 索引加载到内存，已经包含大量原始向量数据。

**HNSW** 通常需要图结构和用于距离计算的向量表示：

```text
HNSW Index
├── 多层邻接图
└── 原始或完整精度的向量表示
```

普通 HNSW 更接近“图结构和向量都参与内存加载”，而不是“只有图在内存”。

**IVF_SQ8 / IVF_PQ** 的内存索引可以保存压缩表示：

```text
IVF_SQ8：倒排结构 + 8-bit 标量量化向量
IVF_PQ： 倒排结构 + PQ Code
```

原始高精度字段数据仍可保存在持久化层，在返回原始字段、重排或精确计算时再访问。因此简化说法对量化场景更接近事实，但仍必须结合具体配置。

### 5.4 mmap：映射不等于全部驻留 RAM

Milvus 支持把原始字段数据或支持的向量索引映射进进程虚拟地址空间：

```text
Query Node 虚拟地址空间
          ↓ mmap
本地磁盘上的 Segment / 索引文件
```

访问某一部分时，操作系统通过缺页机制把文件页载入 Page Cache：

```text
热点页 → 驻留 RAM
冷数据 → 保留在磁盘
```

需要区分：

- Collection 级 mmap 控制原始字段数据的映射；
- Index 级 mmap 控制支持 mmap 的向量索引；
- mmap 可以扩大可加载容量，但缺页与磁盘访问可能降低性能。

本文来源讨论记录了当时 Milvus 文档所述的“新建 Collection 默认启用 mmap”。这是版本相关默认值，不能脱离实际版本照搬。mmap 也不是绕过内存直接在磁盘上计算：被访问的文件页仍会进入操作系统页缓存。

### 5.5 DiskANN 是更典型的磁盘型 ANN 路径

```text
内存：
├── PQ 压缩编码
└── 热点缓存

SSD：
├── Vamana 图
└── 原始高精度向量
```

查询先利用内存中的压缩表示估算候选，再从 SSD 读取较少的原始向量完成更精确的距离计算。这与普通 HNSW、IVF_FLAT 的内存优先路径明显不同，适合数据量超出可用内存的场景。

## 6. 完整机制流程

```text
写入 Entity
   ↓
Growing Segment 实时可搜索
   ↓ seal / flush
Sealed Segment 持久化并构建独立索引
   ↓ load
Query Node 搜索各 Segment 并合并全局 Top-K
   ↓ 后台维护
Compaction 重写有效数据、清理删除/过期记录、构建新索引
```

存储与查询层可进一步概括为：

```text
持久化层：对象存储 / 本地磁盘
保存 Segment、字段数据、日志与索引文件
                     ↓
查询服务层：Query Node
使用 RAM、mmap 或 DiskANN 执行搜索
```

## 7. 理解推进、常见误区与排查

### 理解推进

- 从“Segment 是不是一个向量”推进到“Segment 是包含一批完整实体字段的数据组织单元”；
- 从“Collection 有一个全局索引”推进到“Sealed Segment 通常各自建索引，查询再合并各段 Top-K”；
- 从“Compaction 合并索引”修正为“重写有效数据形成新 Segment，再重建对应索引”；
- 从“Milvus 是内存数据库”修正为“持久化数据库的查询层高度依赖内存”；
- 最终明确“原始向量在磁盘、索引在内存”只适用于部分索引与加载策略。

### 常见误区与排查

- **误区：Segment 等同于 Partition。** Partition 是用户层逻辑分区，Segment 是系统自动管理的数据块。
- **误区：一个 Segment 只保存向量。** 它覆盖一批实体的向量、标量、主键等完整字段。
- **误区：Compaction 可直接拼接 HNSW 图。** 新数据边界需要新索引生命周期。
- **误区：逻辑删除后磁盘立即释放。** 需要 Compaction 重写有效数据，旧文件再由 GC 清理。
- **误区：调用 load 就意味着全部数据复制进物理内存。** mmap 配置下可能只是建立地址映射，热点页按需进入 RAM。
- **排查 Segment 过多：** 观察 Segment 数、sealed/growing 状态、Compaction 任务、每段索引构建状态和全局 Top-K 合并开销。
- **排查内存占用：** 同时核对索引类型、加载字段、replica 数、mmap 开关、页缓存、量化方式和查询热点，不能只看原始向量文件大小。

## 8. 关联知识点与原始资料

- [数据库选型：SQL、MongoDB、Redis、向量库的分工](01_数据库选型：SQL、MongoDB、Redis、向量库的分工.md)
- [RAG 完整链路：召回、融合、重排、生成](../02_Agent_RAG_Memory/18_RAG_完整链路：召回、融合、重排、生成.md)
- [Milvus Glossary](https://blog.milvus.io/docs/glossary.md)
- [Milvus Data Processing](https://milvus.io/docs/data_processing.md)
- [Milvus Snapshots](https://milvus.io/docs/snapshots.md)
- [Milvus Architecture Overview](https://milvus.io/docs/architecture_overview.md)
- [Milvus DataCoord Compaction 配置](https://milvus.io/docs/id/configure_datacoord.md)
- [Milvus 2.5 Product FAQ：删除、Compaction 与磁盘空间](https://milvus.io/docs/v2.5.x/product_faq.md)
- [Milvus 维护者关于 Segment 索引与 Compaction 的说明](https://github.com/milvus-io/milvus/discussions/28565)
- [Milvus 默认配置 `milvus.yaml`](https://github.com/milvus-io/milvus/blob/master/configs/milvus.yaml)
- [PyMilvus 2.6.x `compact()`](https://milvus.io/api-reference/pymilvus/v2.6.x/MilvusClient/Management/compact.md)
- [PyMilvus 3.0.x `compact()`](https://milvus.io/api-reference/pymilvus/v3.0.x/MilvusClient/Management/compact.md)
- [Milvus Clustering Compaction](https://milvus.io/docs/clustering-compaction.md)
- [Milvus Load & Release Collection](https://milvus.io/docs/load-and-release.md)
- [Milvus IVF_FLAT](https://milvus.io/docs/zh/ivf-flat.md)
- [Milvus Index Explained](https://milvus.io/docs/index-explained.md)
- [Milvus mmap](https://milvus.io/docs/mmap.md)
- [Milvus Create Collection](https://milvus.io/docs/create-collection.md)
- [Milvus DiskANN](https://milvus.io/docs/diskann.md)

## 9. 复习检查问题

1. Collection、Partition、Segment 与 Entity 的层级关系是什么？
2. Growing Segment 与 Sealed Segment 的职责和索引状态有何不同？
3. 为什么一个 Collection 的查询结果需要合并多个 Segment 的 Top-K？
4. Compaction 为什么不能直接拼接旧 HNSW 或 IVF 索引？
5. Mix、L0 与 Clustering Compaction 分别解决什么问题？
6. 为什么说 Milvus 持久化在磁盘，但普通查询路径又高度依赖内存？
7. IVF_FLAT、HNSW、量化 IVF 与 DiskANN 对向量数据的加载方式有什么不同？
8. mmap 的虚拟地址映射、Page Cache 与物理 RAM 驻留是什么关系？
