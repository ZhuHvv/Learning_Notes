# 04.13 Go 内存分配器：mcache、mcentral、mheap 与 mspan

> 所属主线：Go Runtime 与内存  
> 难度：深入  
> 前置知识：逃逸分析、栈与堆  
> 后续知识：[GC、混合写屏障与回收](14_Go_GC：三色标记、混合写屏障与_Green_Tea.md)

## 1. 分配器的整体思路

Go 堆分配器最初基于 TCMalloc，之后已有大量独立演进。核心是**按大小分级、在 P 上缓存可用 span，并按页管理底层空间**，以减少共享访问和向操作系统申请内存的次数。

`new`、`make` 不保证产生堆分配，存储位置参见[逃逸分析](12_Go_逃逸分析、闭包与内存泄漏.md)。下面讨论需要在堆上分配的对象：分配器负责提供空间，GC 负责判断哪些对象可回收。具体阈值与字段以 **Go 1.26.0** 为参考，属于运行时实现，不是语言规范。[分配器总览](https://github.com/golang/go/blob/go1.26.0/src/runtime/malloc.go)

## 2. 页、span、槽位与三级管理

### 2.1 空间如何划分

**一个 span 管理一个或多个虚拟地址连续的 Go 内存页；用于小对象时，span 再划分成同规格的槽位。** span 不是页的一部分，也不要求背后的物理页连续。

```text
mheap 按页提供空间：Go 页为 8 KiB，不等同于操作系统页
        ↓
span：一个或多个连续页
        ↓ 小对象 span 按规格划分
[槽位][槽位][槽位]……
        ↓
普通小对象占一个槽位；tiny 对象还可共享一个 16 B 槽位
```

严格说，`mspan` 是管理这段空间的元数据结构，记录起始地址、页数、槽位大小、分配状态等。**“分配单位”需要说明层次：页分配层按页，普通小对象按槽位，tiny 对象按块内满足对齐要求的子区域。**

不能一律把“页数 × 8192 ÷ 槽位大小”当作真实槽位数：除尾部余量外，部分 span 还会预留位图等元数据空间，Go 1.26 的 Green Tea 路径也有相关处理。实际数量以 `mspan.nelems` 为准。[span 初始化](https://github.com/golang/go/blob/go1.26.0/src/runtime/mheap.go)

### 2.2 各层负责什么

| 结构 | 职责 | 补充或分配的内容 |
|---|---|---|
| `mcache` | 每个 P 的本地缓存，保存各 span class 的当前可用 span | 从 span 分配对象槽位；用完后补充 span |
| `mcentral` | 按 span class 管理共享 span 集合 | 向 mcache 提供可用 span |
| `mheap` | 管理堆页与底层内存 | 提供连续页并建立 span；必要时扩展堆 |

`size class` 表示槽位大小等级；`span class` 还区分是否需要扫描指针，即 scan / noscan。同样大小但指针扫描属性不同的对象，通常使用不同类别的 span。

`mcache` 属于 **P，而不是 goroutine 或固定的操作系统线程**。本地常见分配路径无须加锁；缓存耗尽后的补充路径可能访问共享结构。它通常从 `mcentral` 补充，而非直接从另一个 P 的 `mcache` 取 span。这些过程主要改变管理状态，不会把对象数据逐层复制。[mcache 实现](https://github.com/golang/go/blob/go1.26.0/src/runtime/mcache.go)、[mcentral 实现](https://github.com/golang/go/blob/go1.26.0/src/runtime/mcentral.go)

## 3. 普通小对象如何分配

### 3.1 先选择规格，再找空槽

请求大小向上取整到合适的 size class。例如，一个 **25 B、无指针**的对象可使用 32 B 槽位，剩余 7 B 是内部碎片，不能分配给另一个普通对象。已释放槽位可以在之后被同类分配复用，并非多个存活的普通对象共享槽位。

```text
请求分配 → 确定大小等级及 scan / noscan
    ↓
mcache 中对应 span 有空槽？
    ├─ 有：通过分配位图等信息找到空槽，分配给对象
    └─ 无：从对应 mcentral 获取可用 span
               ↓ 无可用 span，必要的清扫也无法提供空间
           从 mheap 获取连续页，建立对应规格的 span
               ↓ 无足够连续空闲页
           扩展堆，向操作系统申请更多空间
```

**mheap 从空间粒度上按页供给，但交给上层管理的是 span；mcentral 向 mcache 补充的也是 span。** 一次补充 span 后，可在本地完成多次槽位分配。[小对象分配路径](https://github.com/golang/go/blob/go1.26.0/src/runtime/malloc.go)

### 3.2 小对象与大对象的边界

常说的“小对象不超过 32 KiB”是概括。Go 1.26.0 的 `mallocgc` 普通分派条件是 `size <= maxSmallSize - gc.MallocHeaderSize`；这两个常量分别为 32768 和 8，因此该条件的请求大小上限为 **32760 B**，超过则进入大对象路径。分配头、专用快速路径和构建选项应以对应版本源码为准，不能把 32 KiB 当作语言保证。

含指针对象的某些分配还需要计入对象头，再选择 size class；不能对所有对象都直接拿业务数据大小查规格。[mallocgc 分派](https://github.com/golang/go/blob/go1.26.0/src/runtime/malloc.go)、[分配头常量](https://github.com/golang/go/blob/go1.26.0/src/internal/runtime/gc/malloc.go)

## 4. tiny 对象与 16 B 块由谁管理

常规情况下，**小于 16 B 且不含指针**的对象可以走 tiny allocator。多个微小对象共享一个 16 B 块，按各自大小和对齐要求分配子区域。

这个块本身来自 **16 B、noscan span 的一个槽位**，不是独立于 span 的另一套内存。当前 P 的 `mcache` 用 `tiny` 指向当前块，用 `tinyoffset` 记录分配偏移：

```text
mcache 中对应的 span：[16 B 槽][16 B 槽][16 B 槽]……
                                   ↑ tiny
一个块的示例：              [A 4 B][B 4 B][C 4 B][空闲 4 B]
                           tinyoffset = 12
```

当前已使用 12 B，后续分配还需满足对齐要求。块内放得下就调整偏移；放不下则从对应 span 获取新的 16 B 槽位，span 无空槽时复用上一节的补充路径。运行时有当前块的择优保留策略，不保证每次获取新块都简单替换旧块，也不保证每个块都填满。

整个 tiny 块要等其中所有对象都不可达后才能回收；其中一个对象存活，可能延长其他子对象所占空间的保留时间。`noscan` 表示不用扫描块内的指针，**不表示该块不参与 GC**。[tiny allocator](https://github.com/golang/go/blob/go1.26.0/src/runtime/malloc.go)、[tiny 状态字段](https://github.com/golang/go/blob/go1.26.0/src/runtime/mcache.go)

## 5. 大对象如何分配

### 5.1 按页取整，一个 span 只容纳一个对象

大对象不使用小对象的规格槽位缓存，而是向 `mheap` 获取一个专用 span。

```text
请求 33 KiB
    ↓ 页数 = ceil(33 / 8) = 5
mheap 提供 5 个虚拟地址连续的页
    ↓
一个 40 KiB 的 span，nelems = 1
[对象使用 33 KiB][尾部余量 7 KiB]
```

页数只需是整数，不必是 2 的幂。尾部 7 KiB 不会再分给其他对象，程序也不能越过对象的合法边界访问它。运行时完成必要的清零和 GC 元数据设置后返回对象地址。[页数取整](https://github.com/golang/go/blob/go1.26.0/src/runtime/mcache.go)、[大对象 span 初始化](https://github.com/golang/go/blob/go1.26.0/src/runtime/mheap.go)

### 5.2 “绕过 mcache 和 mcentral”的准确含义

源码调用路径包含 `mallocgcLarge → mcache.allocLarge → mheap.alloc`。虽然方法属于 `mcache`，它并不从小对象缓存中找槽位，而是直接申请页级 span。分配后还会把大对象 span 放入 `mcentral` 对应的已清扫、已满集合，使后台清扫器能够发现它。

因此，“绕过”指**不走小对象的缓存补充机制**，不能推断成“大对象代码完全不接触 mcache 或 mcentral”。[allocLarge 实现](https://github.com/golang/go/blob/go1.26.0/src/runtime/mcache.go)

### 5.3 mheap 如何找到页

页分配器使用位图记录页的使用状态，用基数树形式的多级摘要加速查找。摘要记录区域开头、结尾和区域内最大连续空闲页数，使其可以跳过不能满足请求的区域；底层策略是按地址顺序的首次适配（first-fit）。

mheap 优先利用已有空闲页，必要时回收可清扫的 span 或扩展堆，**不是每次大对象分配都调用操作系统申请新内存**。[页分配器](https://github.com/golang/go/blob/go1.26.0/src/runtime/mpagealloc.go)

## 6. 回收、边界与排查

- 普通小对象死亡后，槽位可复用；span 全部空闲后，页可归还 mheap。大对象死亡后，清扫阶段可以归还整个专用 span。[清扫实现](https://github.com/golang/go/blob/go1.26.0/src/runtime/mgcsweep.go)
- **对象回收、页归还 mheap、物理内存归还操作系统是不同步骤。** scavenger 等机制负责后者，因此 GC 后进程内存占用不一定立即下降。[内存归还机制](https://github.com/golang/go/blob/go1.26.0/src/runtime/mgcscavenge.go)
- 零大小分配有特殊处理，可能返回共享地址，不应套用“每个对象必占一个普通槽位”的说法。
- 这些结构是 runtime 内部实现，业务代码不直接操作。优化前先用 benchmark、`pprof -alloc_space` 和 `-inuse_space` 区分分配热点与长期存活内存。
- 预分配 slice、复用 buffer、减少临时对象要以实测为依据。`sync.Pool` 适合可临时复用、丢失后能重建的对象；元素可被自动移除，不能当作可靠缓存或资源所有权容器。不要为减少分配牺牲正确性和所有权清晰度。[sync.Pool 文档](https://pkg.go.dev/sync#Pool)
