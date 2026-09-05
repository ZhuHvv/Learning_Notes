# DeepSeek Harness：文件检索、FS、Shell、Terminal 与 LSP

## 1. 一句话结论

dsh 没有把“操作工作区”做成一个万能工具：FS seam 提供可替换的存储原语，FS tools 负责窗口化读取与受观察写入，Search 独立用打包的 ripgrep + subprocess，Shell 处理一次性命令，Terminal 处理持久 PTY，LSP 只暴露四个只读语义操作；这些能力能否出现由 composition 决定，而非目录存在即默认启用。

## 源码阅读路线

按以下顺序打开源码；链接固定到本次核对时的实际行号。

1. [注册文件工具](<D:/codes/deepseek-harness/packages/fs/tool-fs/src/index.ts#L54>)：packages/fs/tool-fs/src/index.ts。
2. [选择搜索二进制](<D:/codes/deepseek-harness/packages/fs/tool-fs-search/src/search-core.ts#L171>)：packages/fs/tool-fs-search/src/search-core.ts。
3. [持久终端 ownership](<D:/codes/deepseek-harness/packages/terminal/terminal/src/index.ts#L66>)：packages/terminal/terminal/src/index.ts。
4. [语义工具 consumer](<D:/codes/deepseek-harness/packages/lsp/tool-lsp/src/index.ts#L97>)：packages/lsp/tool-lsp/src/index.ts。

## 2. 源码调用链与数据流

### 2.1 FS 四层

```text
模型 read/write/edit/read_image
  → dsh-tool-fs（schema、参数、窗口、render）
  → fs/write-intent 或 fs/edit-intent waterfall（可选 policy）
  → ctx.fs（resolve/stat/read/write/edit 等 provider contract）
  → fs-local / fs-sandbox / fs-e2b
  → fs/observed（成功后的同步记录）
```

`ctx.fs` 定义 12 个 primitive：路径解析、process path、file URL、containment、stat/lstat、text/stream/bytes read、listDir、atomic write、atomic literal edit。target key 与 version 是 opaque branded id，consumer 不应解析。write/edit 的 version guard 在 Service Definition 上是可选的；默认产品同时挂载 `fs-observation-policy`，所以 overwrite/edit 要求先 read 且版本未变。

`read` 默认最多 2000 行、每行 2000 字符、整次 51200 bytes；大于等于 10 MiB 的文件走 stream。`read_image` 只有在 durable attachment store 已挂载时才注册，执行时还会在文件 I/O 前解析当前精确 provider/model route，并要求 adapter 明确声明 image input。成功读取的 PNG/JPEG/WebP/GIF 会先写入内容寻址 attachment store，再让 `tool/result` 以 attachment reference 携带 image block；图片字节不进入 Session JSONL，但该引用会像其他可见历史一样在每次后续请求中占用模型输入，直到 surface replacement 将其隐藏。`write`/`edit` mutation 发生在 provider 的 per-target atomic region，policy 返回 `createIfAbsent`、`replaceIfVersion` 或 `{ version }`，并用 `FS_NOT_OBSERVED`/`FS_STALE_VERSION` 指导模型先重读。

### 2.2 Search 不在 FS seam 上

```text
glob / grep
  → dsh-tool-fs-search
  → 固定 argv + --no-config
  → ctx.subprocess.spawn(@vscode/ripgrep binary)
  → parse raw rg output
  → capped inline result + optional spill artifact
```

Search 不依赖 `ctx.fs`，也不从 PATH 任意选 `rg`；`resolveRgPath()` 在单文件 runtime 优先选可执行文件旁的 `-rg` helper，Node 模式使用 `@vscode/ripgrep` 平台包，再通过 subprocess seam 执行，模型参数是 argv element 而非 shell string。`globMaxResults` 默认 100，`grepMaxMatches` 250，超出部分只有在完整 raw stdout 已捕获、解析成功且 formatted spill 保存成功时才可完整取回。raw `rg` stdout 默认最多 20,000,000 bytes；超过预算或 subprocess 仍报告 lossy 时整个调用以 `SEARCH_RAW_OUTPUT_OVERFLOW` 失败，不会拿不完整 tail 冒充搜索全集。Search workdir 与 FS provider 是否指向同一 execution world 没有运行时证明；远程/虚拟 FS 若不共置，搜索出的路径可能无法被 `read` 读取。

### 2.3 Shell 一次性命令

```text
bash / pwsh tool
  → ctx.shell.resolve request → spec
  → shell provider run() / start()
  → local 或 sandbox executor
  → subprocess capture / process group
  → foreground result 或 ctx.jobs background producer
```

`run()` 只有基础设施失败才 reject；非零 exit、timeout kill、abort kill 都返回带事实的 `ShellRunResult`，由工具 renderer 添加 `[exit code: N]`、signal、timeout、sandbox 等 marker。`start()` 无 executor timeout，由 generic jobs runtime 管理 output cursor、kill、settlement 与 notice。Shell 不提供交互式 stdin channel；一次性 stdin 由 trusted plugin 在 spawn 时写入并关闭。

### 2.4 Terminal 持久 PTY

Terminal family 分三层：`ctx.terminals` registry 负责 branded id 与 exact-Agent ownership；`terminal-bash` 通过 subprocess terminal backend 管理 PTY、readiness 和 bounded state；`tool-terminal` 暴露 `terminal_open/send/read/signal/close/list`。每个操作都要求最初创建它的 exact Agent，知道 id 不足以越权访问别的 agent session。

`terminal_send(run_in_background: true)` 复用 `ctx.jobs`，preflight 与每个 PTY session 的 exclusive send reservation 在返回 job id 前完成。foreground send/read 不把“inferred idle”误作进程已退出；Terminal 适合需要 cwd/env/shell state 或交互 stdin 的场景，普通一次性工作仍优先 Shell/FS。

### 2.5 LSP 精确导航

```text
lsp tool
  → session.header.cwd（无 fallback）
  → ctx.lsp 按 extension/provider 选择
  → lsp-stdio：ctx.fs + ctx.subprocess，临时 open/query/close
  → goToDefinition | findReferences | goToImplementation | hover
```

模型只看一个只读 `lsp` tool，坐标是 one-based UTF-16；Service Definition 内部使用 zero-based position。没有 generic JSON-RPC escape hatch，也没有 rename/codeAction 等 mutation。结果先规范化成 complete canonical locations/hover，再按 `maxLocations = 100`、`maxResultChars = 16000` 截断模型展示。

### 2.6 默认挂载边界

`dsh-base` 默认挂载 sandboxed Shell/Pwsh、generic jobs controller、`tool-fs` 与 `tool-fs-search`。Terminal 与 LSP packages 存在且有显式测试组合，但不在 base 默认工具面；只有 preset 或 overlay 明确挂载 service、provider、consumer 的完整角色后，模型才能使用。

## 3. 设计取舍

- FS provider 与 observation policy 分离：远程/沙箱 backend 复用同一读写工具，而 read-before-edit 是部署可选策略。
- Search 选择 ripgrep subprocess：删除自建递归搜索代码，但接受“Search 与 FS 共置”由 composition 负责的限制。
- Shell 与 Terminal 分工：一次性命令更易约束、捕获和终止；PTY 为状态和交互付出更复杂生命周期成本。
- LSP 只暴露四个语义动作：provider 可替换，模型无需理解 JSON-RPC，也不能借协议逃逸做任意 mutation。
- 结果有明确 cap 与 spill：控制模型上下文，但 capped inline output 不能冒充 complete result。
- exact-Agent ownership：可预测或泄漏的 terminal/job id 不是访问凭证。

## 4. 不能推出的结论

- `ctx.fs` 有 `listDir` 不代表模型默认有目录列表工具；模型侧目录发现主要是 glob/grep。
- Search 使用 packaged rg 不代表适用于任意 remote FS；它搜索 subprocess 所在 workdir。
- Shell nonzero exit 不等于 harness infrastructure error，也不必然触发 tool `isError`。
- Terminal “idle”或 send timeout 不能证明 foreground process 已退出。
- LSP 空结果不能证明符号不存在；server indexing、extension mapping、cursor 位置都可能造成 incomplete/empty。
- packages 中存在 Terminal/LSP 不能推出 shipped base 已启用；要看 profile/preset/overlay 的有效 composition。

## 5. 常见误区

- 用 shell `cat` 代替 `read` 并丢失窗口、版本观察与 read-card metadata。
- write/edit 遇到 stale 后直接重试，而不是重新 read 获取新 version。
- 把 `glob`/`grep` 的 capped 页面当成完整集合，忽略 omission/spill notice。
- 为保持 `cd` 状态滥用多次独立 bash；需要跨调用状态时才开 Terminal，并在结束后 close。
- 用文本 grep 代替所有 LSP，或反过来把 LSP 当全文搜索器；LSP 是歧义符号和影响分析的精确补充。

## 6. 源码阅读任务

1. 从 `tool-fs/read.ts` 跟到 provider 与 `fs/observed`，再说明 write/edit 如何消费同一 observation。
2. 查看 `tool-fs-search` 的 argv 构造，验证 `--no-config`、无 shell 层和 packaged binary 三个事实。
3. 对比 `ShellExecutor.run/start` 与 `TerminalRegistry`，列出 lifecycle、timeout、stdin、state 和 cleanup 的差异。
4. 从 `tool-lsp` 的 one-based 参数跟到 `lsp-stdio` 的 JSON-RPC position，核对 UTF-16 转换。
5. 在 base、ACP 与 headless compositions 中分别查找 Terminal/LSP rows，判断哪些是产品默认、测试示例或显式 overlay。

## 持久 Shell、图片引用与检索的组合限制

`minimal` preset 在 POSIX 挂持久 bash，在 Windows 挂持久 pwsh，两者都借 Terminal 保存状态；另一个模型工具是 str_replace_editor。终端 backend 仍消费 host sandbox policy，bare fs-local 编辑器则要单独审视，不能由“极简”推断更严格权限。

图片结果的 attachment reference 与临时路径不同。一次请求要由当前路由确认图片输入能力，后续回放、fork 和导出还需要对象存储中的真实字节；只有 JSONL 引用并不构成可携带的完整图片备份。

全文搜索、LSP、Web search 各解决不同问题：glob/grep 找工作区文本，LSP 解析符号语义，Web provider 获取外部信息。Web search/fetch 的 Service Definition、provider、consumer 可在 [packages/web/](<D:/codes/deepseek-harness/packages/web/>) 独立追踪；某 provider 包存在不代表当前会话挂载或拥有其凭据。

## 7. 证据索引

- [packages/fs/fs/src/index.ts](<D:/codes/deepseek-harness/packages/fs/fs/src/index.ts#L1>)
- [packages/fs/fs-local/src/index.ts](<D:/codes/deepseek-harness/packages/fs/fs-local/src/index.ts#L1>)
- [packages/fs/fs-sandbox/src/index.ts](<D:/codes/deepseek-harness/packages/fs/fs-sandbox/src/index.ts#L1>)
- [packages/fs/fs-observation-policy/src/index.ts](<D:/codes/deepseek-harness/packages/fs/fs-observation-policy/src/index.ts#L1>)
- [packages/fs/tool-fs/src/index.ts](<D:/codes/deepseek-harness/packages/fs/tool-fs/src/index.ts#L1>)
- [packages/fs/tool-fs-search/src/index.ts](<D:/codes/deepseek-harness/packages/fs/tool-fs-search/src/index.ts#L1>)
- [packages/fs/tool-fs-search/src/search-core.ts](<D:/codes/deepseek-harness/packages/fs/tool-fs-search/src/search-core.ts#L1>)
- [packages/attachment/attachment/README.md](<D:/codes/deepseek-harness/packages/attachment/attachment/README.md#L1>)
- [packages/attachment/attachment-local/README.md](<D:/codes/deepseek-harness/packages/attachment/attachment-local/README.md#L1>)
- [packages/shell/shell/src/index.ts](<D:/codes/deepseek-harness/packages/shell/shell/src/index.ts#L1>)
- [packages/shell/tool-bash/src/index.ts](<D:/codes/deepseek-harness/packages/shell/tool-bash/src/index.ts#L1>)
- [packages/terminal/terminal/src/index.ts](<D:/codes/deepseek-harness/packages/terminal/terminal/src/index.ts#L1>)
- [packages/terminal/tool-terminal/src/index.ts](<D:/codes/deepseek-harness/packages/terminal/tool-terminal/src/index.ts#L1>)
- [packages/lsp/lsp/src/index.ts](<D:/codes/deepseek-harness/packages/lsp/lsp/src/index.ts#L1>)
- [packages/lsp/lsp-stdio/src/index.ts](<D:/codes/deepseek-harness/packages/lsp/lsp-stdio/src/index.ts#L1>)
- [packages/lsp/tool-lsp/src/index.ts](<D:/codes/deepseek-harness/packages/lsp/tool-lsp/src/index.ts#L1>)
- [packages/bundle/base/cordis.patch.yml](<D:/codes/deepseek-harness/packages/bundle/base/cordis.patch.yml#L1>)
- [packages/preset/agent-presets/presets/minimal/agent.cordis.yml](<D:/codes/deepseek-harness/packages/preset/agent-presets/presets/minimal/agent.cordis.yml#L1>)
- [packages/lsp/tool-lsp/src/index.ts](<D:/codes/deepseek-harness/packages/lsp/tool-lsp/src/index.ts#L1>)
