# DeepSeek Harness：快照回放、E2E、Invariant 与 Harness 评估

## 1. 一句话结论

dsh 的验证策略是一组互补证据：unit/coverage 检查局部契约，Loader composition 和 built smoke 检查真实装配，keyless snapshot 用 recorded Session JSONL 重放模型流并固定外部 transcript，real-API E2E 检查真实 provider 与外部世界结果，runtime invariant 监视跨事件关系；这些能证明特定路径与固定场景，不等于已经存在一个独立、通用的 Agent 质量 evaluator。

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

repository policy 明确：非平凡 model/protocol/human-visible change 必须在 runnable example 的 owning snapshot suite 中加入 keyless scenario。package mock test 不能替代 assembled transcript；反过来 snapshot 也不能替代 focused unit/race test。

### 2.2 LLM replay

```text
record 阶段（需要真实模型）
  → 运行真实 Agent composition
  → Session JSONL 保存 assistant/chunk、request/header、tool events...

replay 阶段（无 key）
  → dsh-llm-replay 读取 session.jsonl
  → 按 (turn, step) 聚合 assistant/chunk
  → 重建 StreamChunk sequence
  → 真 Agent Loop + 真 tools + 真 persistence 再运行
  → diff 新 Session log / JSON-RPC / stdout / UI snapshot
  → assertConsumed() 保证脚本没有少调用
```

普通成功调用必须以 finish chunk 结束。纯 pre-chunk throw、hang/cancel timing 不能从 JSONL chunks 推出，使用 `replay.override.json` replacement/patch 明确脚本。成功 compaction summarizer 只有在 `compaction/summary.llmStreamCall: true` 且有完整 `rawOutput` 时才可重建为本地 LLM call；外部/template summarizer 不能被误认。

嵌套 Agent 每个 Session 有独立 `session.N.jsonl`。live Session id 每次随机，replay 当前按首次调用顺序把 live session 绑定到 recorded script；并发 sibling 首次调用会造成非确定性，因此 README 明确把并发 subagent script binding 列为限制。

### 2.3 Snapshot surfaces

- ACP snapshot：启动真实 automation-server example，重放模型流，diff normalized JSON-RPC、stdout 与 repersisted log。
- Headless snapshot：explicit example composition + internal JSONL driver，固定 canonical backend events；产品 `dsh --profile headless` 由 CLI acceptance 另测。
- Web snapshot：真实 Host + replay LLM + Chromium，固定 Session、UI 语义输出和交互状态；CI replay 模式禁止写 expected files。
- JSON-RPC/SDK/CLI snapshot：各 front door 固定自己的 wire 与 presentation，而不是共享一份“万能快照”。

一个 `text-turn` 场景 pin 完整 system prompt/tool schemas；多数 fixture 把易变 header 内容 tokenized，避免一次 prompt 文案变化造成全库无意义 diff。record 与 refresh 是不同操作：模型 transcript 变化才 record；输入仍有效而仅派生输出变化可 refresh。两种 diff 都必须审查。

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

每个 workspace package 都发布 `./invariant` companion；有可观测关系时检查，纯 utility/薄 provider 若没有合理关系则用 package-specific “No runtime invariant” 解释，不造假检查 service/method 是否存在。

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
- 只检查权威关系：避免“服务存在”这类自证循环；没有关系时明确为空比伪 invariant 更诚实。
- world-state assertion：Agent 自述不是验证器，尤其是文件修改、安全和 goal completion。

## 4. 不能推出的结论

- 100% line coverage 不能推出分支语义、race、安全边界或产品 composition 正确。
- snapshot 通过不能推出真实模型今天仍会生成同样结果；replay 根本不调用 provider。
- real-API 单次 smoke 通过不能推出稳定成功率、泛化能力或无回归。
- invariant 未触发不能推出系统完全正确；它只覆盖已注册 owner 的指定关系和 observation window。
- telemetry/token projection 不能自动成为 eval score。
- Workflow structured child judge 是一个可编排 primitive，不自动成为独立、无偏的评估器。

## 5. 常见误区

- 修改 visible behavior 只补 unit test，不补 runnable example snapshot。
- 用 test-only fake tool 验证 bridge，却不启动 shipping tool/provider composition。
- 在 E2E 中搜索 assistant 输出的“完成”二字，而不检查文件、命令或外部状态。
- 遇到 snapshot diff 直接 refresh，不判断是期望行为改变、fixture 漂移还是 bug。
- 把 runtime invariant 写成检查注入 service 或 method 存在；这属于 load/type/unit gate。
- 把 Ralph/Goal 的 self-report 统计成“独立 evaluator 认证成功”。

## 6. 源码阅读任务

1. 选一个 ACP snapshot，从 scenario config、recorded `session.jsonl`、replay adapter 到 expected stdout/log 完整走一遍。
2. 构造 pre-chunk auth error 与 partial_disconnect，解释为什么前者需要 override，而后者能部分从 log 观察。
3. 比较同一行为的 package unit、Loader composition、built smoke、keyless snapshot 与 real-API E2E 各自防什么回归。
4. 阅读 Session、Tools、Compaction 三个 invariant companion，判断它们为何检查关系而非重复 input schema。
5. 为“Agent 修改一个文件并通过测试”设计 eval，明确外部 verifier、重复运行与不能使用的 self-report 指标。

## 7. 证据索引

- `docs/testing.md`
- `vitest.config.ts`
- `vitest.e2e.config.ts`
- `vitest.snapshot.config.ts`
- `packages/test-support/llm-replay/src/index.ts`
- `packages/test-support/llm-mock-server/src/index.ts`
- `packages/test-support/acp-snapshot/src/index.ts`
- `packages/runtime-diagnostics/invariants/src/index.ts`
- `packages/core/session/src/invariant.ts`
- `packages/core/agent-loop/src/invariant.ts`
- `packages/core/tools/src/invariant.ts`
- `packages/compaction/compaction/src/invariant.ts`
- `scripts/verify-package-invariants.ts`
- `examples/acp-agent/tests/acp.snapshot.ts`
- `examples/headless-agent/tests/`
- `apps/web/tests/`
- `packages/workflow/tool-ralph/README.md`
- `packages/goal/goal/README.md`

