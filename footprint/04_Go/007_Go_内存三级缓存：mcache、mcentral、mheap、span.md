# Go 内存三级缓存：mcache、mcentral、mheap、span

> 所属分类：Go / Gin / Runtime  
> 修订版本：v9 昨日今日增量版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Go 内存分配使用 mcache、mcentral、mheap 和 span 分层，小对象优先从本地 mcache 分配。


## 2. 原理性解释

- span 是按 size class 切分的内存块。
- mcache 属于 P，本地无锁分配。
- mcentral 管理同类 span。
- mheap 向 OS 管理大块内存。
- 同样大小对象可复用同一个 span 槽位。

### mcache、mcentral、mheap 是为了减少小对象分配锁竞争

Go 内存分配把对象按 size class 分类，同样大小级别的对象可以复用同一类 span。每个 P 有自己的 mcache，分配小对象时优先从本地 mcache 拿，避免全局锁；mcache 不够时向 mcentral 要；mcentral 不够再向 mheap 要。

你问“mcache 向 mcentral 申请 span，是从别的空闲 mcache 中调吗？”通常不是从别的 mcache 调，而是从对应 size class 的 mcentral 获取可用 span。

## 3. 机制流程

1. 请求分配。
2. 查 mcache。
3. 不足向 mcentral 取 span。
4. 再不足向 mheap 取。

### 小对象分配流程

```text
new object
  ↓ 判断 size class
mcache 对应 span 有空位？
  ├─ 有：直接分配
  └─ 无：向 mcentral 申请 span
          ↓ mcentral 无可用 span
          向 mheap 申请/切分更大内存
```

理解这个流程有助于解释为什么大量短生命周期小对象会增加 GC 和分配压力，也解释了对象池 `sync.Pool` 的适用场景。

## 4. 类比理解

像工位小盒、楼层仓库、总仓三级补货。

## 5. 应用举例 / 代码或伪代码

```go
obj := p.mcache[sizeClass].nextFree()
if obj == nil {
    span := mcentral[sizeClass].get()
    p.mcache[sizeClass] = span
}
```

## 6. 你在讨论中的理解推进

你问 mcache 是否从其他 mcache 调 span；通常是向 mcentral 申请。

