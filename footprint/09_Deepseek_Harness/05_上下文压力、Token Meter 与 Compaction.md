# DeepSeek Harness：上下文压力、Token Meter 与 Compaction

## 1. 一句话结论

dsh 把“计量当前请求压力”“决定何时压缩”“如何改写可见历史”拆成独立插件：`token-meter` 从 durable Session log 折叠出估算与 provider usage 锚点，`compaction-basic` 在 step 前或确认的上下文溢出后选择安全区间，必要时先无模型裁剪大工具结果，再用一次独立 `llm.stream()` 生成摘要并以 `surfaceOp: replace` 替换旧 surface。

## 2. 源码调用链与数据流

### 2.1 计量链

```text
Session event log
  ├─ request/header、request/context
  ├─ user/message、assistant/message、tool/result
  ├─ assistant/chunk / usage
  └─ surface replace
        ↓ replay fold
ctx.tokenMeter.measure(session, requestHeader?)
        ├─ totalTokens：本次请求与响应压力
        ├─ surfaceTokens / nodes：当前可见 surface 的启发式价格
        └─ provider usage anchor：仅在 canonical request envelope 匹配时复用
```

`token-meter` 的固定估算是“四字符约一 token + 消息、block、request envelope 结构开销”。它不是 provider tokenizer。若最新成功请求的 provider usage 与当前 canonical envelope 完全匹配，meter 以 provider 数字为锚点；system prompt、tools、provider、model、call config 或可见历史改变后，不能机械沿用旧 usage，而要重新估算或按 surface delta 推进。

可选的 projection 有三组：`tokenUsage` 汇总 durable usage；`contextPressure` 暴露上一请求的 `pressureTokens`、推进到下一请求的 `projectedTokens` 与 adapter 给出的 `contextWindow`；`contextBreakdown` 只估算 system/tools/messages 的构成。projection 面向 UI 和查询，不是 compaction 的判定输入；compaction 直接调用同一 revision 上的 `measure()`。

### 2.2 自动压缩链

```text
agent/pre-step（串行）
  → compactIfNeeded(agent, "pressure", signal)
  → 读取 durable route
  → adapter.resolveModelInfo(provider, model).context
  → threshold = floor(contextWindow × thresholdRatio)
  → tokenMeter.measure()
  → 未过阈值：next()
  → 已过阈值：可选 toolResultPruner.prune()
  → 重新 measure()
  → selectCompactableRange()
  → compactRegion()
```

默认策略是 `thresholdRatio = 0.8`、`retainRatio = 0.16`、`maxTokens = 8192`、`compactionRetries = 1`、`maxOverflowRetries = 1`、`auto = true`。这些是当前 `compaction-basic` provider 的默认配置，不是 compaction Service Definition 的永久语义，也不是任意模型都应采用的通用公式。`modelPolicies` 可按精确 provider/model 覆盖策略；容量由负责该 route 的 adapter 提供，缺失容量时常规压力压缩不能猜测窗口。手动 pressure 检查会抛出精确 route 的配置错误；自动 listener 对同一 target 只警告一次并让 turn 携完整历史继续，而 provider 已明确报告的 canonical overflow 仍可绕过容量元数据尝试恢复。

### 2.3 canonical overflow 恢复链

```text
LLM adapter 抛出 CONTEXT_WINDOW_EXCEEDED
  → agent/request-error
  → compactIfNeeded(agent, "context-overflow", signal)
  → 不依赖 contextWindow 元数据，绕过普通 threshold/retain 策略
  → 先尝试 pruner，再做最大可用的 balanced head reduction
  → surface.replaceGeneration 前进才允许重试原请求
```

未知 provider 错误、非 canonical overflow、没有产生任何 replacement、重试耗尽或取消，都不会被伪装成成功；原始 provider failure 保持权威。

### 2.4 事务与 surface 改写

一次成功压缩的 durable 顺序是：

```text
compaction/start              # 日志锁开始
llm.stream(purpose=compaction)
compaction/summary            # 原摘要、范围、usage、call envelope
user/message                  # <compacted-summary>，surfaceOp: replace
compaction/end                # 日志锁释放
```

旧事件仍留在 raw log；`deriveMessages()` 只在当前 surface 上看到一个 user-role checkpoint 加保留的近期尾部。范围按 surface 位置选择，不按 seq 数值区间选择；边缘必须经过 tool-call/result pairing 检查，不能把一个尚未回答的工具调用劈开。

摘要调用不走 Agent Loop 的普通 step，也不触发 `agent/request`；它直接走 `llm/stream`，重放原请求的 system prompt、tools 与被压缩消息前缀，再追加压缩指令，以争取复用 provider KV cache。只有返回文本进入 checkpoint；reasoning、工具调用或图片输出不被悄悄混入摘要。

### 2.5 无模型工具结果裁剪

`compaction-tool-result-pruner` 只处理过大的、含文本的 `tool/result`，默认 `thresholdChars = 8192`、保留头部 4096 与尾部 1024 Unicode code points。它追加 `compaction/prune` 价格事件并用受限 replacement 改写该结果，不调用模型。普通、低于 pressure 的 step 检查不会为了省一点上下文就主动裁剪；只有 pressure/overflow 已成立后才进入此阶段。

## 3. 设计取舍

- 计量独立于压缩：UI、其他 pressure consumer 与不同 compaction backend 可共享 `ctx.tokenMeter`，不会反向依赖 `CompactionEngine`。
- provider usage 与启发式估算并存：完全精确需要每个 provider tokenizer 和最终序列化器；当前实现选择“能复用精确锚点时复用，否则保守估算”。
- raw log 不删、surface 替换：恢复与审计仍保留原事实，但模型下一请求只付 checkpoint 与保留尾部的成本。
- 先裁剪再总结：大工具载荷可用确定性变换解决时，避免额外模型调用；剩余语义压缩才交给 summarizer。
- durable lock 而非内存互斥：崩溃留下 unmatched `compaction/start`，可区分当前生命周期的 busy 与 `session/end-seed` 之前的陈旧证据。
- 摘要复用会话请求前缀：降低 auxiliary call 成本，但换 provider/model 或压缩非 head 区间时不能承诺 cache 命中。

## 4. 不能推出的结论

- 不能把 `contextPressure` projection 当成计费记录、同一原子时刻的精确占用率或 compaction 门禁。
- 不能从四字符估算推出 DeepSeek tokenizer 的真实分词，CJK、JSON schema 与图片尤其可能偏差明显。
- 不能说达到 80% 必然压缩：阈值可配置、可按 route 覆盖，且需要 adapter 容量与可切割的 balanced range。
- 不能说压缩会删除 Session 原始历史；它替换的是 derived surface，raw events 仍在日志中。
- 不能说摘要无损。checkpoint 是模型生成的语义提炼，细节可能丢失；长期硬约束仍应存在于可重新加载的权威状态中。
- 不能从 `purpose: compaction` 推出 provider 必然计费不同或必然命中缓存；它只是 adapter 可使用的调用归因。

## 5. 常见误区

- 把 `pressureTokens` 与 `projectedTokens` 混用：前者是最近 provider sample，后者才把此后的 surface 增减估算进去。
- 认为 compaction 是“截掉最旧 N 条消息”：实现按 token 预算、surface 位置与工具配对边缘选择范围。
- 认为 overflow 恢复等于无限重试：`maxOverflowRetries` 有界，且必须有 durable surface progress。
- 认为 pruner 会为旧工具结果生成摘要：它是确定性的头尾裁剪，不调用 LLM。
- 认为 compaction summary 是 assistant 消息：当前 checkpoint 是带 `surfaceOp: replace` 的 `user/message`。

## 6. 源码阅读任务

1. 从 `BasicCompactionEngine` 的 `agent/pre-step` listener 跟到 `tokenMeter.measure()`，写出 threshold 未命中、prune 后安全、需要 summarize 三条分支。
2. 阅读 `surface-fold.ts` 与 token projection，解释为什么 `contextBreakdown` 不应与 `projectedTokens` 强求相加相等。
3. 在 `region.ts` 中跟踪一次成功事务，标出每个 durable event 与真正改变 surface 的唯一事件。
4. 用测试中的 tool-call/result 边界案例说明为什么 numeric seq 连续不等于 surface range 安全。
5. 对比 pressure 与 context-overflow 两种 trigger，列出它们对容量元数据、保留尾部和重试授权的差异。

## 7. 证据索引

- `packages/llm/token-meter/src/index.ts`
- `packages/llm/token-meter/src/surface-fold.ts`
- `packages/llm/token-meter/src/projection.ts`
- `packages/compaction/compaction/src/index.ts`
- `packages/compaction/compaction/src/tool-pairing.ts`
- `packages/compaction/compaction-basic/src/index.ts`
- `packages/compaction/compaction-basic/src/config.ts`
- `packages/compaction/compaction-basic/src/region.ts`
- `packages/compaction/compaction-basic/src/summarizer.ts`
- `packages/compaction/compaction-tool-result-pruner/src/index.ts`
- `packages/core/agent-loop/src/agent.ts`
- `packages/bundle/base/cordis.patch.yml`
- `examples/headless-agent/compaction.cordis.snapshot.yml`
