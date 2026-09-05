# DeepSeek Harness：快照回放、E2E、Invariant 与 Harness 评估

## 1. 一句话结论

dsh 的验证策略是一组互补证据：unit/coverage 检查局部契约，Loader composition 和 built smoke 检查真实装配，keyless snapshot 用 recorded Session JSONL 重放模型流并固定外部 transcript，real-API E2E 检查真实 provider 与外部世界结果，runtime invariant 监视跨事件关系；这些能证明特定路径与固定场景，不等于已经存在一个独立、通用的 Agent 质量 evaluator。

## 源码阅读路线

按以下顺序打开源码；链接固定到本次核对时的实际行号。

1. [Session 驱动场景与独立工作区证据](<D:/codes/deepseek-harness/snapshots/AGENTS.md#L1>)：snapshots/AGENTS.md。
2. [内嵌流回放](<D:/codes/deepseek-harness/packages/test-support/llm-replay/src/index.ts#L34>)：packages/test-support/llm-replay/src/index.ts。
3. [实际选择的场景范围](<D:/codes/deepseek-harness/vitest.snapshot.config.ts#L47>)：vitest.snapshot.config.ts。
4. [有关系才发布 invariant](<D:/codes/deepseek-harness/scripts/verify-package-invariants.ts#L1>)：scripts/verify-package-invariants.ts。

## 2. 源码调用链与数据流

### 2.1 测试层级

| 层级 | 主要证据 | 不能替代什么 |
| --- | --- | --- |
| Unit | 函数、service、事件、race、error path | shipped composition 是否可启动 |
| `test:coverage` | `packages/*/*/src` per-file 100% | 语义正确与产品可用性 |
| Loader/composition test | 真 `cordis.yml`、真实 plugin rows | built artifact 与真实 provider API |
| Built smoke | plain Node 运行 `lib/` bin/worker | 模型任务质量 |
| Keyless snapshot | 固定模型流下的 Session/协议/UI 输出 | provider 当前行为与真实推理 |
| Real-API E2E | 真 key、真 adapter、真实模型/搜索 provider | 所有 nondeterministic 场景可重复性 |
| Browser snapshot | Chromium 中 replayed Host/Client/UI | 非浏览器 front door |
| Runtime invariant | 运行时跨事件/可变关系 | 纯函数、配置结构和外部世界真值 |

repository policy 明确：非平凡 model/protocol/human-visible change 必须在对应 Session snapshot owner 中加入 keyless scenario。package mock test 不能替代 assembled transcript；反过来 snapshot 也不能替代 focused unit/race test。

### 2.2 LLM replay

`llm-replay` 根据选择的 Session generation，经格式 catalog 读取当前逻辑事件，再从 v2 的 assistant/message、assistant/attempt 内嵌 stream 展开 StreamChunk。一个 step 内多个重试尝试各自保留，不能按 turn/step 把它们合成一条成功流。

```text
选最高规范 generation → sessionFormatCatalog → 当前逻辑事件
 → expandAssistantStream(message/attempt.stream) → 每次调用的 replay entry
 → shipped dsh profile + scenario patch → 真 Loop / tools / persistence
 → 比对日志、协议、UI 与独立工作区结果
```

throw-before-chunk、hang/cancel timing 等无法只靠 durable stream 恢复的行为，需要 replay.override.json。成功 compaction 调用只有在明确 llmStreamCall 标记和 rawOutput 足够时才可恢复，不能把模板摘要当作真实模型调用。

每个嵌套 Session 独立成 role；当前 replay 仍按首次调用顺序绑定 live Session 与 recorded script，并发 sibling 的首次调用顺序是已知限制。assertConsumed() 防止只运行了脚本前半段却判成功。

### 2.3 Snapshot surfaces

顶层 `snapshots/` 只放以 Session JSONL 为输入与预期持久输出的场景。被测进程统一经 `dsh` + shipped profile + 可选 scenario patch 启动；不要按旧 examples 的内部 driver 另建产品入口。

| 落点 | 关注内容 |
| --- | --- |
| snapshots/session/headless.snapshot.ts | headless 的 Session 与工作区场景 |
| snapshots/acp/acp.snapshot.ts | ACP（Agent Client Protocol，代理客户端协议）协议与持久结果 |
| snapshots/sdk/sdk.snapshot.ts | SDK 的 wire/event/run 投影 |
| apps/web/tests/ | 浏览器 assembled UI 场景，按构建模式选择 |

父文件名为 session[.vN].jsonl，子文件名为 session.<ordinal>[.vN].jsonl。record/refresh 选择最高规范版本，发布版本命名结果并保留已提交旧代；固定历史格式的 owner 在 snapshot.yml 声明版本和迁移覆盖。

修改工作区的场景声明 workspace.final: true 并提交 workspace.expected/，record/refresh 不改写这份独立结果证据。模型说完成、工具输出声称完成，都不能替代真实文件比对。非 Session 驱动的 CLI、ARIA（可访问性语义）、几何或生成器 expected 输出留在各自 owner。

record 使用真实模型，refresh 用既有 replay 输入更新派生输出，普通 replay 不写 expected。它们的用途和证据成本不同；本轮未执行 record/refresh。

### 2.4 Real-API E2E 与 mock server

`test:e2e` 在没有 key 时 self-skip；有 key 时运行 DeepSeek 和 provider-specific smoke。原则是只 mock 昂贵或非确定性边界，工具、executor、Agent Loop、persistence 保持真实。断言应重新读取文件、重跑命令或检查外部世界，而不是在 assistant 自述中找关键词。

`llm-mock-server` 提供 OpenAI-compatible HTTP/SSE fault script：connection reset、pre/post-chunk disconnect、stall、429/5xx、auth、context overflow、malformed event、max_tokens、tool call 等。它用于检验真实 adapter/loop recovery policy；random 模式只表示测试压力分布，不是生产事故概率。

### 2.5 Runtime invariants

```text
dsh-invariants service
  → ctx.invariants.register(packageName, installer)
  → package ./invariant companion
  → child fiber 中订阅 authoritative event / mutable state
  → fail(message) 抛 InvariantError{ code: INVARIANT, packageName }
```

只有存在独立观察可能分歧的运行时关系，包才发布 `./invariant` companion；纯 utility/薄 provider 无此关系时应省略源码、导出与挂载，并在 README 说明。空 installer 或检查 service/method 是否存在不构成有效 invariant。

典型检查：Session seq/turn/step/tool pairing、Agent status/inbox、LLM stream grammar、request reconstruction、tool pipeline/frozen result、compaction bracket/metadata、subagent/workflow child pairing、Goal revision/round、approval asked/decided、Jobs lifecycle。Session 自身始终执行 candidate JSON/surface 基础验证；可选 companion 负责跨记录关系。

service 支持 enabled、package allowlist/blocklist。register 即使被 filter 禁用也预留包名，防止两个 companion 静默争用。companion reload 会丢弃 live trace 并从 durable events 重建能重建的 baseline；只观察 live operation 的 invariant 无法反推 reload 前未记录的瞬态。

### 2.6 Harness“评估”的证据边界

当前仓库可直接证明的是测试、回放、runtime invariant、telemetry/projection 与 structured output/workflow primitives。它们适合建立一个未来 eval harness，但没有证据表明当前产品已有统一 benchmark runner、独立 judge、任务成功评分数据库或跨模型质量报告。

Goal/Tool-Ralph README 反而明确写出：complete/blocker 是 worker/model self-report，不是 independent evaluation；Goal 只机械验证 authority、revision 和 round threshold。要构建真正质量评估，应额外定义：任务 corpus、外部 world verifier、grader isolation、重复采样、成本/延迟统计、版本固定和 failure taxonomy，不能把绿 snapshot 或 self-reported complete 直接当成功率。

## 3. 设计取舍

- recorded Session 是 replay 输入：最接近真实 assembled behavior，且自然覆盖 stream、tools 与持久化；代价是某些纯 throw/timing 需 sidecar。
- keyless replay 与 with-key E2E 并存：前者确定、便宜、可 CI；后者检验真实 provider compatibility 与模型能力。
- one pinned prompt fixture + 其余 tokenized：在 detecting request-shape drift 与控制 snapshot churn 之间取平衡。
- invariant 归包所有：失败能指向 owner，避免一个中央 checker 导入所有 product package 并复制知识。
- 只检查权威关系：避免“服务存在”这类自证循环；没有关系时省略 companion 并说明原因。
- world-state assertion：Agent 自述不是验证器，尤其是文件修改、安全和 goal completion。

## 4. 不能推出的结论

- 100% line coverage 不能推出分支语义、race、安全边界或产品 composition 正确。
- snapshot 通过不能推出真实模型今天仍会生成同样结果；replay 根本不调用 provider。
- real-API 单次 smoke 通过不能推出稳定成功率、泛化能力或无回归。
- invariant 未触发不能推出系统完全正确；它只覆盖已注册 owner 的指定关系和 observation window。
- telemetry/token projection 不能自动成为 eval score。
- Workflow structured child judge 是一个可编排 primitive，不自动成为独立、无偏的评估器。

## 5. 常见误区

- 修改 visible behavior 只补 unit test，不补对应 shipped-profile Session snapshot。
- 用 test-only fake tool 验证 bridge，却不启动 shipping tool/provider composition。
- 在 E2E 中搜索 assistant 输出的“完成”二字，而不检查文件、命令或外部状态。
- 遇到 snapshot diff 直接 refresh，不判断是期望行为改变、fixture 漂移还是 bug。
- 把 runtime invariant 写成检查注入 service 或 method 存在；这属于 load/type/unit gate。
- 把 Ralph/Goal 的 self-report 统计成“独立 evaluator 认证成功”。

## 6. 源码阅读任务

1. 选一个 ACP snapshot，从 scenario config、选中的版本化 Session JSONL、replay adapter 到 expected stdout/log 完整走一遍。
2. 构造 pre-chunk auth error 与 partial_disconnect，解释为什么前者需要 override，而后者能部分从 log 观察。
3. 比较同一行为的 package unit、Loader composition、built smoke、keyless snapshot 与 real-API E2E 各自防什么回归。
4. 阅读 Session、Tools、Compaction 三个 invariant companion，判断它们为何检查关系而非重复 input schema。
5. 为“Agent 修改一个文件并通过测试”设计 eval，明确外部 verifier、重复运行与不能使用的 self-report 指标。

## 本次修订的验证边界

本次修改学习笔记，不修改业务源码、快照或产品文案。执行的文档验证覆盖：目标文件保存与差异、引用文件存在、源码行号范围、专题导航链接、旧失效路径和过时关键结论扫描。

源码测试与快照仅作为核对依据阅读；没有执行真实模型 E2E、整库覆盖率、浏览器运行或跨平台恢复实验。因而本文不宣称当前工作树全部测试通过，也不把 Windows 源码分支当作本机运行结果。项目内 doc-sync 等门禁不扫描本目录，不能冒充对项目外学习笔记的验证。

## 7. 证据索引

- [docs/testing.md](<D:/codes/deepseek-harness/docs/testing.md#L1>)
- [vitest.config.ts](<D:/codes/deepseek-harness/vitest.config.ts#L1>)
- [vitest.e2e.config.ts](<D:/codes/deepseek-harness/vitest.e2e.config.ts#L1>)
- [vitest.snapshot.config.ts](<D:/codes/deepseek-harness/vitest.snapshot.config.ts#L1>)
- [packages/test-support/llm-replay/src/index.ts](<D:/codes/deepseek-harness/packages/test-support/llm-replay/src/index.ts#L1>)
- [packages/test-support/llm-mock-server/src/index.ts](<D:/codes/deepseek-harness/packages/test-support/llm-mock-server/src/index.ts#L1>)
- [snapshots/acp/acp.snapshot.ts](<D:/codes/deepseek-harness/snapshots/acp/acp.snapshot.ts#L1>)
- [packages/runtime-diagnostics/invariants/src/index.ts](<D:/codes/deepseek-harness/packages/runtime-diagnostics/invariants/src/index.ts#L1>)
- [packages/core/session/src/invariant.ts](<D:/codes/deepseek-harness/packages/core/session/src/invariant.ts#L1>)
- [packages/core/agent-loop/src/invariant.ts](<D:/codes/deepseek-harness/packages/core/agent-loop/src/invariant.ts#L1>)
- [packages/core/tools/src/invariant.ts](<D:/codes/deepseek-harness/packages/core/tools/src/invariant.ts#L1>)
- [packages/compaction/compaction/src/invariant.ts](<D:/codes/deepseek-harness/packages/compaction/compaction/src/invariant.ts#L1>)
- [scripts/verify-package-invariants.ts](<D:/codes/deepseek-harness/scripts/verify-package-invariants.ts#L1>)
- [snapshots/sdk/sdk.snapshot.ts](<D:/codes/deepseek-harness/snapshots/sdk/sdk.snapshot.ts#L1>)
- [snapshots/session/](<D:/codes/deepseek-harness/snapshots/session/>)
- [apps/web/tests/](<D:/codes/deepseek-harness/apps/web/tests/>)
- [packages/workflow/tool-ralph/README.md](<D:/codes/deepseek-harness/packages/workflow/tool-ralph/README.md#L1>)
- [packages/goal/goal/README.md](<D:/codes/deepseek-harness/packages/goal/goal/README.md#L1>)
