# DeepSeek Harness：Skills 的发现、目录投影、按需加载与资源边界

## 1. 一句话结论

dsh 的 Skill 不是启动时把所有 Markdown 塞进 system prompt，而是三层协议：`ctx.skills` 合并 host/preset/agent scope 的 provider catalog，`skill-filesystem` 只发现并解析摘要，`tool-skill` 把可调用摘要作为 durable catalog 注入 Session；真正的正文在模型调用 `skill(name)` 或用户显式 `/name` 手势时才重新读取，并仅给出资源基址和按需加载指导。

## 源码阅读路线

按以下顺序打开源码；链接固定到本次核对时的实际行号。

1. [读取 scope 可见目录](<D:/codes/deepseek-harness/packages/skill/skill/src/index.ts#L473>)：packages/skill/skill/src/index.ts。
2. [本地来源与正文读取](<D:/codes/deepseek-harness/packages/skill/skill-filesystem/src/index.ts#L1>)：packages/skill/skill-filesystem/src/index.ts。
3. [模型目录与用户手势](<D:/codes/deepseek-harness/packages/skill/tool-skill/src/index.ts#L77>)：packages/skill/tool-skill/src/index.ts。
4. [冷会话的用户可调用列表](<D:/codes/deepseek-harness/packages/api/session-controller/src/skill-catalog.ts#L36>)：packages/api/session-controller/src/skill-catalog.ts。

## 2. 源码调用链与数据流

### 2.1 Provider registry

```text
filesystem / runtime / remote provider
  → ctx.skills.registerProvider(factory)
  → provider.list({ cwd, signal })
  → SkillCandidate{name, description, invocation, rank, locator, ...}
  → host + scope layers 合并
  → 同层按 rank / 注册顺序 / provider-local 顺序决定
  → 跨层由最近 scope 直接 shadow
```

`snapshot()` 返回 `{ skills, complete }`。provider reject、明确 incomplete 或连续 catalog revision race 会让 `complete = false`；当前候选仍可供本次 trusted caller 使用，但不会作为 authoritative catalog 缓存或发布。`get(name)` 重新走 winning provider 的 load，校验 definition，并在 discovery 与 load 之间发生 rename 时拒绝陈旧选择并 invalidates provider。

registry 区分两类 surface：`modelInvocable` 与 `userInvocable`。`get()` 本身是 trusted、policy-neutral primitive；每个 consumer 必须在自己的边界检查对应 predicate，不能把“能加载”自动等同于“能暴露给模型”。

### 2.2 本地发现顺序

`skill-filesystem` 默认扫描：

| Rank | 路径 | 来源 |
| --- | --- | --- |
| 100 | `<projectRoot>/.dsh/skills` | project-dsh |
| 200 | `<projectRoot>/.agents/skills` | project-agents |
| 300 | `customSkillDirs` | custom |
| 400 | `<dshHome>/skills` | user-dsh |
| 500 | `<agentsHome>/skills` | user-agents |
| 600 | `bundledSkillDir` 或 `$DSH_BUNDLED_SKILL_DIR` | bundled |

project root 是最近的 `.git` ancestor；找不到时使用传入 cwd。同一 scope layer 中 rank 数字更小者优先，随后才比较注册顺序和 provider-local 顺序。默认 bundled root 可由 config 或环境变量给出；`includeDefaultRoots: false` 会关闭 project/user 行和环境变量默认值，但保留显式 custom/bundled roots。user-dsh 根还会跳过 `.system` 子目录，避免把系统拥有的 Skill 当成普通用户 Skill。本地格式只认一层目录 bundle `<name>/SKILL.md` 或 flat `<name>.md`，不递归发现嵌套 `**/SKILL.md`。frontmatter 必须有 kebab-case `name` 与 `description`；可选 `whenToUse`、`metadata`、`disable-model-invocation`、`user-invocable`。invocation 字段类型错误会让整个 Skill fail closed 地从 discovery 消失，而不是默认为可调用。

若 `ctx.fs` 可用，provider 通过文件系统 seam 读取；否则最小本地 composition 可回退到 abortable Node FS。catalog membership 与 frontmatter 由 Chokidar/缺失路径 probe 观察；正文资源变化不会触发 catalog invalidation，因为正文每次 load 都重新读取。dsh 自己的 `write`/`edit` 还通过 `fs/observed` 同步触发可能影响 Skill catalog 的 invalidation，保证下一 step 能看到本次文件修改。

### 2.3 模型目录投影

```text
agent/pre-step
  → skills.snapshot({ cwd: session.header.cwd, scope: agent })
  → 过滤 modelInvocable
  → 确认本插件注册的 skill 工具在当前 tool view 可见且未被 shadow
  → 与 Session 中最新 visible skill-catalog digest 比较
  → 初次非空：注入完整 <available_skills>
  → 发生变化：追加完整 replacement catalog
  → incomplete：不发布，保留 last-good model view
```

catalog 只含排序后的 name 与最长 500 字符的规范化 description。path、provider、rank、body 与 `whenToUse` 都不进入目录。每条目录消息是 durable user-role `<system-reminder>`，source 记录精确 entries 和 update 标记；compaction 隐藏目录后，下一次 complete observation 会重新建立当前目录。空 replacement 明确退休旧名字。

### 2.4 按需正文加载

模型调用 `skill({ name })` 时：

```text
ToolRuntime
  → ctx.skills.get(name, { cwd, scope, signal })
  → 检查 modelInvocable
  → provider 重新读取当前 Skill definition
  → renderSkillContent()
  → tool/result 持久化 <skill_content>
```

工具不再额外 `agent.inject()` 一份正文，因为 tool result 已会进入下一 step。该结果像其他工具结果一样留在当前可见 surface，直到被后续 compaction replacement 隐藏；provider 不缓存 body，也不会在磁盘正文改变后追溯改写旧结果。用户直接输入 whitespace-bounded `/name` 时，pre-step gesture listener 检查 `userInvocable` 并把相同 `renderSkillContent()` 形态作为 instructions context 放在本 step 最后；这也是 `disable-model-invocation: true` Skill 的入口，模型既不会在 catalog 看见它，也不能自行用 tool 加载。

### 2.5 资源边界

loaded definition 可带 `resourceBase`：directory、URL 或 opaque guidance。渲染只告诉模型如何解析 Skill 正文中显式引用的资源，并要求按需读取；不会列举整个目录，也不会自动加载 `references/`、`scripts/`、`assets/`。因此 Skill 是 instructions + locator guidance，不是隐式附件打包协议。

Web 使用 Agent Preset 后，`ctx.skills` registry 留在 Host；每个 preset 的 Skill provider/tool registration 位于 preset scope layer。这样同一个 host 服务不同 agent composition，又不会把某 preset 的目录泄漏给兄弟 preset。

## 3. 设计取舍

- 摘要与正文渐进披露：常驻 token 与 Skill 数量/description 成正比，完整正文只在实际使用时付费。
- durable catalog 而非每轮重写 system prompt：变化以 append-only replacement 保留 KV 前缀，也能被 Session replay 理解。
- incomplete 保留 last-good：临时 I/O/provider 失败不应被模型误解为“所有 Skill 已删除”。
- body 不缓存：正文编辑立即影响下一次 load，代价是远程 provider 或大正文每次加载都要重新获取。
- 双 invocation policy：用户显式选择与模型自主路由是不同权限面，不能用一个 `enabled` 混合。
- 资源只给基址：避免目录枚举和无关文件膨胀，但 consumer 仍需借助 FS/Web 等工具取实际资源。

## 4. 不能推出的结论

- catalog 中有 Skill 不代表其正文已进入上下文；模型必须先调用工具，或用户通过手势显式注入。
- `whenToUse` 当前不进入模型 catalog，不能声称 dsh 依靠该字段自动路由。
- watcher 看到 frontmatter 变化不代表 body-only 变化会发布新 catalog；旧 tool result 也不会被追溯改写。
- `resourceBase` 不代表资源已读、已验证安全或自动附加到请求。
- project/user rank 只在同一 scope layer 内处理候选；更近 preset/agent layer 的同名 Skill 会直接 shadow 远层。
- 本地 provider 的目录规则不能推广到所有 provider；远程/embedded provider 可以使用 URL 或 opaque locator。

## 5. 常见误区

- 把 Skill 与 AGENTS.md workspace instructions 混为一谈：后者按路径作用域注入，Skill 通过 catalog 和显式 load 进入。
- 只检查 `modelInvocable`，忽略 Web slash 菜单应检查 `userInvocable`。
- 看到 catalog replacement 是完整列表就误以为 registry 每次缓存正文；digest 只覆盖 entries。
- 递归放置多层 `SKILL.md` 并期待自动发现；当前 filesystem provider 只扫描一层。
- 在 Skill 正文中提到“读取 references”就假设运行时会自动批量读取；必须显式引用并由 agent 按需加载。

## 6. 源码阅读任务

1. 从 `SkillRegistry.snapshot()` 追踪 provider failure、incomplete observation 和 revision race 如何影响 `complete` 与缓存。
2. 对照 filesystem root rank 与 scope shadowing，解释同名 Skill 在 project、user、preset 三处出现时谁胜出。
3. 阅读 `tool-skill` 的 pre-step listener，说明 digest、可见性与 compaction 后目录重建如何协作。
4. 比较模型调用 `skill` 与用户输入 `/name` 的 invocation predicate、Session source 和正文落点。
5. 修改一个 Skill 的 description 与 body，分别推演 watcher、catalog replacement 和下一次 load 的差异。

## 用户入口与 Web 冷会话读取

Web 的用户可调用 Skill 列表由 Session Controller 的 skill-catalog 路径提供。live Agent 存在时用其 scope；冷会话使用记录的 preset standing scope，因此列 Skill 不应启动 Agent 或模型请求。

`tool-skill` 的目录与手势 listener 保留 pre-step 决策中的 `startsRequestSeries`。完整 replacement catalog 指的是最新可见目录，不是删除原始 user/message 记录；正文变化也不会追溯重写先前 tool/result。阅读冷会话能力时，应同时检查 registry、preset 和 API consumer，而不只看 filesystem provider。

## 7. 证据索引

- [packages/skill/skill/src/index.ts](<D:/codes/deepseek-harness/packages/skill/skill/src/index.ts#L1>)
- [packages/skill/skill-filesystem/src/index.ts](<D:/codes/deepseek-harness/packages/skill/skill-filesystem/src/index.ts#L1>)
- [packages/skill/tool-skill/src/index.ts](<D:/codes/deepseek-harness/packages/skill/tool-skill/src/index.ts#L1>)
- [packages/skill/skill-badge/src/index.ts](<D:/codes/deepseek-harness/packages/skill/skill-badge/src/index.ts#L1>)
- [packages/core/scope/src/index.ts](<D:/codes/deepseek-harness/packages/core/scope/src/index.ts#L1>)
- [packages/core/tools/src/index.ts](<D:/codes/deepseek-harness/packages/core/tools/src/index.ts#L1>)
- [packages/fs/fs-observation-policy/src/index.ts](<D:/codes/deepseek-harness/packages/fs/fs-observation-policy/src/index.ts#L1>)
- [packages/bundle/base/cordis.patch.yml](<D:/codes/deepseek-harness/packages/bundle/base/cordis.patch.yml#L1>)
- [packages/bundle/web-app/cordis.patch.yml](<D:/codes/deepseek-harness/packages/bundle/web-app/cordis.patch.yml#L1>)
- [packages/preset/agent-presets/src/index.ts](<D:/codes/deepseek-harness/packages/preset/agent-presets/src/index.ts#L1>)
