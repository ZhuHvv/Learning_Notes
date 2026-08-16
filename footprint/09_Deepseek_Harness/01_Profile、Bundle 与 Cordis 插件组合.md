# DeepSeek Harness：Profile、Bundle 与 Cordis 插件组合

## 1. 一句话结论

dsh 的启动不是“CLI 读取一个大配置文件并创建若干单例”。CLI 先选择 Profile，再按顺序叠加 Bundle patch、profile patch、home patch 和 `--patch` overlay，最后用 Cordis Loader 装载所得插件树。产品差异因此优先表现为 composition，而不是大量 `if (mode === ...)`。

## 2. 从命令行到运行树

`apps/cli/src/bin.ts` 解析参数后分派三类模式：profile 启动、plugin 管理和配置导出。常规 `dsh web` 或 `dsh --profile headless <task>` 会进入 `runProfile()`。

`runProfile()` 的主要责任不是实现 Agent Loop，而是建立可靠启动边界：

```text
argv
  → parseDshArgs
  → loadLayeredEnv
  → composeProfile(profile, patches)
  → boot(Loader root, composed patch list)
  → 向 Context 提供 immutable command-line / environment facts
  → 监控用户 patch，处理 SIGINT/SIGTERM，最终 dispose 整棵树
```

环境读取有一个值得学习的安全细节：项目 `.env` 与 Harness home `.env` 会被解析和校验，但会拒绝改变 PATH、Node 启动选项、代理、模型 endpoint、`DSH_*` 等 bootstrap-only 变量。启动环境决定进程如何运行和到哪里联网，不能被后来发现的配置文件悄悄重写。

## 3. Patch 的顺序就是产品语义

`composeProfile()` 的有效层次从低到高是：

```text
1. profile package.json 中列出的 bundle（声明顺序）
2. profile 自己的 cordis.patch.yml
3. $DSH_HOME/cordis.patch.yml
4. 命令行 --patch 文件（argv 顺序）
5. 启动器附加的 overlay，例如 telemetry opt-out
```

后层可以按 row id 覆盖前层 row 的完整 `config`，也可以插入新 row。因此配置不是深层对象合并：修改一行时要知道该 row 的完整配置归谁拥有。项目在 bundle patch 注释中反复强调这一点，避免“漏写一个字段却意外保留底层旧值”的不透明行为。

这还解释了为何 `dsh --profile web --dump-config` 是重要调试命令：它显示的是**最终组合结果**，而不是某个 bundle 的局部片段。

## 4. Bundle 与 Profile 的分工

- **Bundle** 是可分发的一层 patch；包的 `package.json` 用 `dsh.bundle.patch` 指向其 patch 文件。
- **Profile** 是一个用户可选择的产品组合；它声明应叠加哪些 bundle，并可带自己的 patch。
- **Base bundle** 是每个产品的公共底座：LLM、Session、工具注册表、文件/shell 能力、安全策略、持久化等。
- **Headless bundle** 增加命令行 task 解析和一次性 runner，不启动 Host 或 HTTP 服务。
- **Web bundle** 增加 Host、webserver、API gateway、浏览器模块与 UI 插件，并将单 Agent 的能力移入 preset。

这是一种“产品装配”模型：Headless 与 Web 尽可能共用 Agent runtime，而不复制两个 Agent Loop。

## 5. Cordis 对运行时做了什么

Cordis Context 承载三种核心贡献：

| 机制 | 在 dsh 中的用途 |
| --- | --- |
| Service | 发布/消费能力，如 `ctx.llm`、`ctx.sessions`、`ctx.tools`、`ctx.agents` |
| Event | 观察或改变生命周期，如 `agent/pre-step`、`tools/execute`、`session/event` |
| Effect | 注册资源并在插件卸载时反向清理；注册不是永久全局副作用 |

因此一个插件应当通过 `ctx.effect()`、`ctx.on()` 或 `ctx.waterfall()` 安装贡献，并返回/持有对应 disposer。它避免了插件卸载、热更新或 agent scope 结束后残留旧工具和监听器。

Waterfall 事件尤其重要：监听器必须调用 `next()` 才会把处理交给下一层。它是有意的控制点，而非普通广播事件。例如工具执行前的策略插件可以在不调用 `next()` 时拒绝或要求审批。

## 6. Scope：为什么同一 Web 进程能有不同 Agent

Web 不能让所有 session 共用一份“当前 Agent 的工具集”。dsh 的回答是 `dsh-scope` 与 agent preset：

```text
host Context：共享持久化、sandbox、审批、registry、HTTP/API
  └─ standing preset scope：standard / minimal / code 等能力组合
       └─ agent scope：一个 session 绑定到一个 preset 的可见注册
```

`AgentPresets.mount(agentCtx, id)` 将新 Agent 的 scope parent 连接到选中的 standing preset。于是同一 `ctx.tools` registry 可以按 scope 暴露不同工具，prompt section 和 skill catalog 也可按 Agent 区分。已运行 Agent 保留其启动时的 preset generation；不能把已有工具调用历史随意切换到不兼容的能力集合。

## 7. 一个开发者扩展的决策路径

新需求先问“它属于哪一个层级”：

1. 所有产品都需要的 provider 或政策：考虑 base/deployment composition。
2. 仅某个产品表面需要的 Host/UI：放在相应 bundle。
3. 仅某种 Agent 才能看见的 prompt/tool：放到 preset 或 agent scope。
4. 仅一次临时实验需要：用 profile/home/`--patch` overlay，不要直接改 loop。

然后设计 Service Definition / Provider / Consumer 三个角色是否需要分包。若只是一个局部插件注册已有 service，不要人为制造新的 capability seam。

## 8. 常见误区

- YAML row 的书写顺序不等于 service 的激活顺序；服务可用性与注入依赖决定实际装载关系。
- Profile patch 不等于“用户唯一配置”；Harness home patch 和命令行 overlay 的优先级更高。
- `isolate` realm 不等于共享池；它用于隔离服务实例，必须结合 scope 关系理解。
- 把一个全局 Host 服务移动进 preset，可能导致 HTTP/API 在没有 Agent scope 时无法解析该服务。

## 9. 源码阅读任务

1. 跟读 `composeProfile()`，画出一个 `web` profile 的 patch 顺序。
2. 在 base 和 web patch 中找到 `system-prompt` row，确认为何 web 必须重述完整 config。
3. 阅读 `apps/cli/config/agent-presets/standard/agent.cordis.yml` 中的 `isolate` group，找出哪些 service 必须留在 host plane。

## 10. 证据索引

- `D:/codes/deepseek-harness/apps/cli/src/bin.ts`
- `D:/codes/deepseek-harness/apps/cli/src/profile-boot.ts`
- `D:/codes/deepseek-harness/packages/boot/app-boot/src/index.ts`
- `D:/codes/deepseek-harness/packages/bundle/base/cordis.patch.yml`
- `D:/codes/deepseek-harness/packages/bundle/headless/cordis.patch.yml`
- `D:/codes/deepseek-harness/packages/bundle/web-app/cordis.patch.yml`
- `D:/codes/deepseek-harness/packages/preset/agent-presets/src/index.ts`
