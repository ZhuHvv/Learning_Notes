# 04.13 Go 内存分配器：mcache、mcentral、mheap 与 mspan

> 所属主线：Go Runtime 与内存  
> 难度：深入  
> 前置知识：逃逸分析、栈与堆  
> 后续知识：GC 标记、写屏障与回收压力

## 1. 总体性概念

Go 内存分配使用 mcache、mcentral、mheap 和 span 分层，小对象优先从本地 mcache 分配。


## 2. 原理性解释

- `mspan` 描述一段连续页；用于小对象时会归属特定 span class，并切分为固定大小槽位。
- mcache 属于 P，本地无锁分配。
- mcentral 管理同类 span。
- mheap 向 OS 管理大块内存。
- 同样大小对象可复用同一个 span 槽位。

### mcache、mcentral、mheap 是为了减少小对象分配锁竞争

Go 内存分配把小对象按 size class 分类，同样大小级别的对象可以使用同一类 span 中的槽位。每个 P 有自己的 mcache，分配小对象时优先从本地缓存的 span 获取空闲槽位，减少共享锁竞争；本地 span 不可用时向对应的 mcentral 换取可用 span；再由 mheap 负责页级内存管理以及向操作系统申请或归还内存。

当 mcache 需要新的 span 时，通常不是从另一个 P 的 mcache 直接调取，而是从对应 span class 的 mcentral 获取可用 span。

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

理解这个流程有助于解释为什么大量短生命周期小对象会增加 GC 和分配压力，也解释了对象池 `sync.Pool` 的适用场景。`sync.Pool` 适合可临时复用、丢失后能重建的对象；池中元素可能在任意一次 GC 中被移除，因此不能把它当作普通缓存或资源所有权容器。

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

## 6. 边界与排查

- mcache、mcentral、mheap 是 runtime 内部实现，不是业务代码直接调用的 API。
- 优化前先用 benchmark、`pprof -alloc_space` 和 `-inuse_space` 找到真实热点。
- 减少分配通常比试图控制某个 mcache 更有效，例如预分配 slice、复用 buffer、减少临时字符串。
- 不要为了“少一次堆分配”牺牲所有权清晰度和代码正确性。
