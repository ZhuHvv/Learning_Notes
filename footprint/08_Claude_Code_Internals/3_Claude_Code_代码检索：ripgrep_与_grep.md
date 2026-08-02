# 08.03 Claude Code 代码检索：ripgrep 与 grep

## 1. 一句话定位

- `grep` 是 Unix/Linux 生态中的通用文本过滤器，尤其适合标准输入、Shell 管道和强调可移植性的脚本。
- `ripgrep` 的命令是 `rg`，它面向目录和代码仓库递归搜索，默认结合 ignore 规则过滤无关文件。

在代码仓库里，两者最重要的差异不只是速度，而是**默认搜索范围**：

```text
grep：尽可能忠实地搜索你指定的输入
rg：默认把当前目录当作代码项目，并主动减少噪声
```

## 2. 递归搜索与默认过滤

`grep` 搜索项目通常需要显式递归：

```bash
grep -R -n "HandleRequest" .
```

`rg` 默认递归搜索当前目录：

```bash
rg -n "HandleRequest"
```

在目录遍历中，`rg` 默认跳过：

- `.gitignore`、`.ignore`、`.rgignore` 排除的路径；
- 隐藏文件和隐藏目录；
- 检测为二进制的文件；
- 符号链接指向的目录。

这使搜索结果更接近“项目源码中有哪些匹配”，但也带来一个常见诊断点：

> `rg` 没搜到，不一定表示内容不存在，也可能表示文件被默认规则过滤了。

常用排查方式：

```bash
# 不遵循 ignore 文件
rg -u "password"

# 再包含隐藏文件
rg -uu "password"

# 连二进制文件也按文本尝试
rg -uuu "password"

# 查看某个路径为什么被过滤
rg --debug "password"
```

如果只是想包含隐藏文件，但仍遵循 ignore 规则，可使用：

```bash
rg --hidden "password"
```

## 3. 文件类型与 Glob 过滤

只搜索 Python 文件：

```bash
rg -tpy "class User"
```

近似的 `grep` 写法：

```bash
grep -R -n --include='*.py' "class User" .
```

更多 `rg` 示例：

```bash
# 只搜索 Go 文件
rg -tgo "func NewServer"

# 排除 JavaScript
rg -Tjs "createUser"

# 只搜索 YAML
rg "image:" -g '*.yaml' -g '*.yml'

# 排除 Go 测试文件
rg "NewServer" -g '!**/*_test.go'

# 查看内置文件类型映射
rg --type-list
```

文件类型不是简单的单一扩展名。例如 `-tc` 通常覆盖 C 源文件和相关头文件，比反复手写多个 `--include` 更适合代码检索。

## 4. 正则表达式差异

`grep` 默认使用 Basic Regular Expression；匹配 `foo` 或 `bar` 通常显式启用扩展正则：

```bash
grep -E 'foo|bar' file.txt
```

`rg` 默认即可写：

```bash
rg 'foo|bar' file.txt
```

但 `rg` 默认正则引擎不支持回溯引用和 look-around。它采用有限状态机路线，重点之一是避免回溯型正则的最坏情况性能风险。

需要前瞻、后顾或回溯引用时，使用 PCRE2：

```bash
rg -P '(?<=user=)\w+' app.log
```

因此不能简单记成“`rg` 的正则比 `grep` 更强”。更准确的是：

```text
rg 默认语法方便且性能边界稳定
复杂 PCRE 特性需要显式使用 -P/--pcre2
```

## 5. 为什么 `rg` 在代码仓库中通常更快

主要原因包括：

1. 默认忽略依赖、构建产物、隐藏目录和二进制文件，减少磁盘 I/O。
2. 默认并行搜索多个文件。
3. 正则引擎会利用字面量提取等优化，先缩小候选范围。
4. 工具本身针对递归目录遍历和大规模文本搜索进行了工程优化。

不能把性能优势简单归因于“它是 Rust 写的”，也不能由单个 benchmark 推导出“所有场景都必然更快”。

并行搜索意味着输出顺序可能变化。要求稳定路径顺序时可使用：

```bash
rg --sort path "TODO"
```

排序会关闭并行搜索，因此稳定性与吞吐量之间存在取舍。

## 6. 对 Claude Code 和代码 Agent 的意义

Claude Code 官方 Tools Reference 已明确说明：内置 `Grep` 工具构建在 **ripgrep** 之上，使用 ripgrep 正则语法，而不是 POSIX grep。工具还可以通过：

- `glob` 参数按路径模式限制文件；
- `type` 参数按语言类型限制文件；
- `multiline` 开启跨行匹配；
- 直接指定路径搜索通常会绕过“该路径被 `.gitignore` 忽略”的目录遍历问题。

还要区分 Claude Code 的 `Grep` 与 `Glob`，它们当前的 ignore 行为并不相同：

| 工具 | 目标 | 当前默认 ignore 行为 |
|---|---|---|
| `Grep` | 搜索文件内容 | 遵循 `.gitignore`；可直接传入被忽略文件的精确路径 |
| `Glob` | 按名称模式找文件 | 默认不遵循 `.gitignore`；可用 `CLAUDE_CODE_GLOB_NO_IGNORE=false` 改为遵循 |

因此“Claude Code 的搜索都会默认过滤 gitignored 文件”是错误的。先用 Glob 找文件时可能看到 ignored 路径，随后用 Grep 对目录搜索却看不到其中内容；这时应缩小到精确文件路径，而不是直接判断内容不存在。

当前 Grep 工具还有三个输出模式：

- `files_with_matches`：只返回路径，是默认模式；
- `content`：返回匹配行、文件和行号；
- `count`：返回每个文件及总匹配数。

这解释了为什么“工具只返回文件名”不等于搜索缺少行号能力，而可能只是选择了默认输出模式。

所以博客标题中的 “grep” 更适合作为“关键字/正则精确检索”这一类方法的统称；落实到当前 Claude Code 工具实现时，应写成：

```text
Claude Code Grep tool
        ↓
底层使用 ripgrep
        ↓
结合 Glob / Read / LSP 逐步扩大或缩小证据范围
```

代码 Agent 搜索函数时：

```bash
rg -n "func NewServer"
```

`rg` 通常不会把 `.git`、依赖目录、构建产物、二进制文件和 ignore 路径中的匹配返回给模型。这会同时降低：

- 工具执行时间；
- 输出长度；
- 上下文 token 消耗；
- 噪声结果对模型判断的干扰。

因此 `rg` 对 Agent 的价值可以概括为：

```text
更快找到候选位置
        +
少把无关文本送进模型上下文
```

在大型仓库中，推荐先用窄查询定位文件和行号，再按需读取局部内容：

```bash
rg --files
rg -n "NewServer" -tgo
rg -n "TODO|FIXME" src
```

这比先输出整个目录或大文件，再让模型从海量文本中筛选更节省上下文。

## 7. Language Server、LSP 与文本搜索的边界

### 7.1 LSP 是协议，Language Server 是实现

Language Server Protocol（LSP）规定编辑器或 Agent 与语言服务器之间怎样交换代码智能请求。两者关系类似：

```text
HTTP                         Web Server
协议                         Nginx / Apache

LSP                          Language Server
协议                         gopls / clangd / rust-analyzer / Pyright
```

典型结构：

```text
VS Code / Neovim / Agent
        LSP Client
            │
            │ JSON-RPC
            ▼
gopls / clangd / Pyright
     Language Server
            │
            ├── AST
            ├── 作用域与符号表
            ├── 类型检查结果
            ├── 导入/依赖关系
            └── 交叉引用索引
```

“服务器”不表示一定在远程机器上监听 HTTP 端口。最常见的语言服务器是由编辑器启动的本地常驻进程，通过标准输入输出或其它进程间通信方式传输 JSON-RPC 消息。

### 7.2 grep/rg 回答文本问题，LSP 回答语义问题

假设代码中有两个同名方法：

```go
type UserService struct{}

func (*UserService) Get(id int) {}

type OrderService struct{}

func (*OrderService) Get(id int) {}
```

文本搜索：

```bash
rg -n '\bGet\b' .
```

可以召回两个定义和所有包含 `Get` 的文本，但不能只凭字符判断：

```go
userService.Get(1)
```

绑定到哪个声明。

LSP 定义跳转请求会携带“文件 + 光标位置”。语言服务器结合 AST、变量类型、作用域和方法集合，把调用绑定到 `(*UserService).Get`。

因此两类工具的核心差异是：

```text
rg/grep：
哪些文本位置匹配这个模式？

LSP：
这个位置上的程序符号是什么，
它定义在哪里、有哪些真实引用、推导出的类型是什么？
```

### 7.3 常见 LSP 能力

- `textDocument/definition`：跳转定义；
- `textDocument/references`：查找语义引用；
- `textDocument/hover`：查看类型与文档；
- `textDocument/completion`：补全；
- `textDocument/rename`：生成跨文件重命名编辑；
- `textDocument/publishDiagnostics`：发布语法、类型等诊断。

编辑器还会用 `didOpen`、`didChange` 等消息把当前缓冲区内容同步给语言服务器，所以它可以分析尚未保存到磁盘的代码。普通 `rg` 默认搜索磁盘文件，看不到编辑器里的未保存修改。

### 7.4 语言服务器为什么长期运行

语言服务器通常会缓存工作区状态，而不是每次查询都从头解析整个仓库：

```text
读取文件
  ↓
解析 AST
  ↓
建立包/模块依赖和类型信息
  ↓
建立符号引用索引
  ↓
文件修改后增量失效与重算
```

它常复用编译器前端的解析和类型检查能力，但目标不同：

| 维度 | 编译器 | 语言服务器 |
|---|---|---|
| 主要目标 | 构建目标程序并报告错误 | 为编辑过程提供低延迟代码智能 |
| 生命周期 | 一次构建或批处理 | 长期运行 |
| 输入 | 通常以磁盘工程为主 | 工作区、光标和未保存缓冲区 |
| 输出 | 二进制/字节码/构建诊断 | 定义、引用、补全、重命名、诊断 |
| 更新方式 | 重新构建或增量编译 | 缓存、快照与按需重算 |

### 7.5 LSP 也不是绝对真相

语言服务器依赖正确的工作区和构建环境。以下情况会导致结果缺失或错误：

- 依赖未安装或生成代码不存在；
- workspace 根目录、构建标签或条件编译配置错误；
- 代码存在严重语法错误；
- 反射、字符串调用、运行时插件、动态导入或宏展开超出静态分析能力；
- 语言服务器本身存在缺陷或索引尚未完成。

例如：

```go
reflect.ValueOf(service).MethodByName("GetUser")
```

`"GetUser"` 与真实方法的关联发生在运行时，LSP 很难把它可靠列为静态引用；这时文本搜索反而重要：

```bash
rg -n '"GetUser"' .
```

### 7.6 代码 Agent 中的组合顺序

```text
Glob/rg 广泛召回候选文件
            ↓
Read 读取局部证据
            ↓
LSP 确认定义、引用、实现和类型
            ↓
修改代码
            ↓
LSP diagnostics + 编译 + 测试验证
```

`rg` 适合搜索注释、配置、日志、错误码和动态字符串；LSP 适合做符号消歧和语义验证。两者不是替代关系。

## 8. 为什么 Claude Code 的本地代码检索不必默认依赖 RAG

博客把 Claude Code 的选择概括为“用 grep，而不用 RAG”。可保留的核心不是否定 RAG，而是：**本地代码库中的很多问题有精确、低成本、实时的权威信号。**

| 代码检索要求 | Grep / Glob / Read / LSP | 典型向量 RAG |
|---|---|---|
| 精确符号、字符串、错误码 | 强 | 可能近似召回 |
| 当前工作区未提交修改 | 立即可见 | 需要更新索引 |
| 目录、文件类型、ignore 过滤 | 原生 | 依赖索引元数据 |
| 调用定义、引用、类型关系 | LSP 可直接提供 | embedding 不保证结构关系 |
| 模糊自然语言主题 | 需多轮换关键词 | 语义召回通常更方便 |
| 超大规模跨仓库 | 每次现搜成本上升 | 预建索引更有优势 |
| 结果可解释性 | 路径、行号、匹配文本直接可查 | 需解释 chunk、分数和重排 |

Agent 可以在循环中迭代搜索：

```text
模糊目标
  ↓
Glob 找候选文件
  ↓
Grep 找符号/字符串
  ↓
Read 读取局部上下文
  ↓
LSP 查定义、引用、实现和类型（需要安装对应 code intelligence 插件与语言服务器）
  ↓
根据新证据改写下一次查询
```

这不是“一次 grep 代替所有检索”，而是让模型在多轮工具使用中控制搜索策略。

## 9. 博客“RAG 的问题”需要怎样修正

### 9.1 代码切片会破坏结构：有风险，但不是必然

固定字符切片确实可能把函数、类或调用链切断。生产代码 RAG 可以使用：

- AST / 符号级切片；
- 父子 chunk；
- 路径、语言、仓库、分支等元数据过滤；
- lexical + dense 混合召回；
- cross-encoder 或 LLM 重排；
- 最终回源读取完整文件。

所以问题应写成“朴素 chunking 会丢结构”，不能写成“所有 RAG 必然破坏代码结构”。

### 9.2 向量是近似召回：正确，但可与精确检索组合

向量相似度不等于代码正确性，也不能替代：

- 精确符号搜索；
- 类型检查；
- 编译；
- 测试；
- Git 与文件系统。

但向量检索可以作为候选生成器，随后再用关键字、元数据、重排和回源校验。

### 9.3 索引会滞后：取决于更新机制

本地直接搜索天然看到当前磁盘。RAG 若只离线每日建索引会滞后；若有文件监控、增量索引、commit/branch 版本键，则可显著降低滞后。这里是工程成本与一致性策略的权衡，不是 RAG 的逻辑必然。

### 9.4 “模型越来越强，所以不需要 RAG”不是可靠结论

模型能力增强会提升：

- 查询改写；
- 多轮检索；
- 候选判断；
- 工具选择。

但不会消除：

- 信息不在上下文中；
- 跨仓库规模过大；
- 权限过滤；
- 数据更新；
- 精确证据与可追溯性。

更强的模型通常会**更好地使用检索工具**，而不是自动让检索消失。

## 10. 什么时候应增加 RAG 或代码索引

以下条件出现时，单纯实时 Grep 的收益会下降：

- 数十个仓库或千万行以上代码需要统一搜索；
- 查询以业务语义为主，用户不知道符号名和关键词；
- 代码、设计文档、Wiki、工单和 PR 需要联合检索；
- 需要跨版本、跨分支的历史知识；
- 允许承担索引、更新、权限过滤和评估成本。

推荐渐进式架构：

```text
第一层：Glob / Grep / Read / LSP，实时且精确
第二层：Git、构建、测试，验证动态事实
第三层：混合 RAG，扩大跨仓库和语义召回范围
第四层：重排与回源，避免直接把近似召回当答案
```

## 11. `grep` 仍然适合什么场景

`grep` 并没有被 `rg` 完全替代：

- 服务器、容器和精简 Unix 环境中通常预装 `grep`，`rg` 可能不存在；
- 编写跨机器执行的 Shell 脚本时，`grep` 的可用性通常更稳定；
- 标准输入和管道搜索不需要项目 ignore 语义。

例如：

```bash
docker logs my-service | grep ERROR
ps aux | grep nginx
curl -s http://localhost:8080/metrics | grep request_total
```

`rg` 同样可以读取标准输入，但在单一数据流中，其项目遍历和过滤优势不明显。

## 12. 选择速查

| 场景 | 优先选择 | 原因 |
|---|---|---|
| 大型代码仓库递归搜索 | `rg` | 默认递归、ignore 感知、类型过滤、输出噪声低 |
| 只列出仓库文件 | `rg --files` | 直接复用相同的过滤规则 |
| 日志/进程/HTTP 输出管道 | `grep` 或 `rg` | 两者都能处理标准输入，`grep` 更普遍 |
| 跨服务器的可移植脚本 | `grep` | 基础系统中可用性更高 |
| look-around、回溯引用 | `rg -P` 或 `grep -P` | 需要 PCRE 支持，并注意环境兼容性 |
| 怀疑文件被忽略 | `rg --debug`、`-u`、`--hidden` | 逐层检查默认过滤 |
| 需要稳定排序 | `rg --sort path` | 以关闭并行搜索为代价换取确定顺序 |
| 当前仓库精确代码定位 | Claude Code Grep / Glob / Read / LSP | 实时、可解释、无需索引 |
| 跨仓库模糊语义查询 | 混合 RAG + 重排 + 回源 | 扩大候选范围，同时保留精确验证 |

## 13. 你在讨论中的理解推进

- 起点：把 `grep` 和 `ripgrep` 都理解为“在文件里找字符串”。
- 推进：发现 `rg` 默认递归，并把 Git ignore、隐藏文件、二进制文件等项目语义纳入搜索。
- 工程化理解：Agent 搜索不仅关心命令耗时，也关心返回多少无关结果、消耗多少上下文。
- 产品连接：Claude Code 的 Grep 工具底层使用 ripgrep，并与 Glob、Read、LSP 和 Agent Loop 组合，不是只运行一次 Shell `grep`。
- 语义推进：进一步区分 LSP 协议与语言服务器实现，并明确文本召回与符号语义查询的边界。
- 最终连接：精确搜索与 RAG 不是信仰对立；单仓实时代码优先使用权威本地工具，跨仓语义场景再增加混合检索。

## 14. 常见误区

- **误区：`rg` 搜不到就是文件中没有。** 文件可能被 ignore、隐藏文件或二进制规则过滤。
- **误区：`rg -uuu` 适合日常默认使用。** 它会逐层关闭保护性过滤，结果可能非常大，应只用于定向排查。
- **误区：并行搜索仍保证固定输出顺序。** 默认顺序可能随运行变化，需要稳定顺序时显式排序。
- **误区：`rg` 支持所有 PCRE 正则。** 默认引擎不支持 look-around 和回溯引用，需要 `-P`。
- **误区：Agent 搜索越宽越保险。** 过宽查询会放大工具输出和上下文噪声，通常应先窄后宽。
- **误区：Claude Code 的 Grep 工具底层就是 POSIX `grep`。** 官方文档明确说明它基于 ripgrep。
- **误区：语言服务器就是远程 HTTP 服务。** 它通常是编辑器启动的本地常驻进程；“服务器”表示提供语言能力的一方。
- **误区：LSP 是一个具体的代码分析程序。** LSP 是通信协议，`gopls`、`clangd`、Pyright 等才是语言服务器。
- **误区：LSP 是更快的 grep。** LSP 查询 AST、作用域、类型和符号索引，解决的是语义问题。
- **误区：LSP 的引用结果永远完整。** 反射、生成代码缺失、错误构建配置和动态加载都可能突破静态分析边界。
- **误区：不用向量库就等于没有检索系统。** Glob、Grep、Read、LSP 与多轮查询改写共同构成检索闭环。
- **误区：代码 RAG 一定无用。** 跨仓库、模糊语义和混合知识库仍是它的合适场景。
- **误区：模型变强会消除外部检索。** 模型仍需要获取未进入上下文的最新外部事实。

## 15. 关联知识点

- `001_Claude_Code_Prompt_前缀缓存与三级上下文.md`
- `004_Claude_Code_上下文压缩、Microcompact_与状态恢复.md`
- `006_Claude_Code_Agent_Loop、Query_生命周期与工具编排.md`
- `007_Claude_Code_记忆体系：CLAUDE.md、Rules_与_Auto_Memory.md`
- `../01_LLM_Transformer/11_倒排索引与稀疏检索.md`
- `../01_LLM_Transformer/10_稠密向量、稀疏向量与多向量表示及检索.md`
- `../02_Agent_RAG_Memory/18_RAG_完整链路：召回、融合、重排、生成.md`
- `../07_Backend_Deploy_Network/8_沙箱、权限与工具执行安全.md`

## 16. 参考资料与事实边界

- [Claude Code Tools Reference](https://code.claude.com/docs/en/tools-reference)
- [Language Server Protocol 官方概览](https://microsoft.github.io/language-server-protocol/)
- [Language Server Protocol 当前规范](https://microsoft.github.io/language-server-protocol/specifications/specification-current)
- [Go 官方 gopls 文档](https://go.dev/gopls/)
- [ripgrep User Guide](https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md)
- [ripgrep FAQ](https://github.com/BurntSushi/ripgrep/blob/master/FAQ.md)
- 本次梳理的博客：`https://xiaolinnote.com/claudecode/source/cc_grep.html`
- 本次整理来源之一：`https://chatgpt.com/share/6a6456db-7640-83ec-9c0d-5833820420cc`

Claude Code 的 Grep 工具基于 ripgrep、支持 glob/type/multiline 并遵循 `.gitignore`，可由当前官方工具文档确认。默认过滤、并行搜索、排序影响和正则引擎边界可由 ripgrep 官方仓库确认。博客关于“不使用 RAG 的产品哲学”属于架构解读，不是 Anthropic 对内部索引实现的长期承诺；具体性能数字也高度依赖仓库、磁盘缓存、表达式和输出量。

## 17. 复习检查问题

1. 为什么 `rg` 在代码仓库中的优势不仅是运行速度？
2. `rg` 默认会跳过哪些路径或文件？
3. `rg -u`、`rg -uu`、`rg -uuu` 分别逐步放开什么限制？
4. 为什么 `rg --sort path` 可能降低搜索速度？
5. 哪些场景下 `grep` 比 `rg` 更适合作为默认选择？
6. 为什么 Claude Code 的代码检索不能简化为“一次 grep”？
7. 哪些条件出现时，应在精确本地搜索之外增加混合 RAG？
8. LSP 与语言服务器分别是什么？为什么不能把它们当作同一个具体程序？
9. 哪些动态代码关系可能无法被 LSP 可靠解析，反而需要文本搜索补充？
