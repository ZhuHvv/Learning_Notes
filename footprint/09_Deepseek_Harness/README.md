# DeepSeek Harness 学习笔记

本目录以当前本地工作树中的 DeepSeek Harness 源码、可执行 `cordis.yml` / `cordis.patch.yml` composition、测试与 snapshot fixture 为首要证据，面向 Agent 与 Harness 开发者。表达结构参考相邻 Claude Code 源码学习笔记，但不迁移 Claude Code 的私有实现结论。

本轮逐文件审查基于 2026-08-15 的源码提交 `47f943859bef60e4160492346772ded9b24f765a`。该提交号只固定本轮结论的证据基线；项目仍处于开发者预览阶段，后续阅读时应重新核对有效 composition、源码与测试，而不能把本文中的默认值当作长期兼容承诺。

## 已完成

1. `00_证据边界与项目地图.md`：证据等级、项目对象与目录地图。
2. `01_Profile、Bundle 与 Cordis 插件组合.md`：从 CLI 到有效插件树。
3. `02_Agent_Loop、流式输出与工具编排.md`：turn/step、stream、工具并发和结果回填。
4. `03_Prompt、运行时上下文与 Workspace Instructions.md`：prompt assembly 与规则注入。
5. `04_Session 日志、持久化与记忆模型.md`：durable log、projection、恢复边界。
6. `05_上下文压力、Token Meter 与 Compaction.md`：计量锚点、自动/溢出压缩、工具结果裁剪与 surface replacement。
7. `06_工具注册表、审批、沙箱与错误模型.md`：ToolRuntime 管线、一次性授权、per-call sandbox policy 与结构化错误。
8. `07_Skills：发现、目录投影、按需加载与资源边界.md`：provider catalog、filesystem roots、durable catalog 与正文渐进加载。
9. `08_文件检索、FS、Shell、Terminal 与 LSP.md`：执行世界、读写观察、ripgrep、一次性命令、PTY 与语义导航。
10. `09_Subagent、Jobs 与 Workflow.md`：one-shot/continuable child、后台工作注册表与 worker-thread orchestration。
11. `10_Plan、Goal、Todo 与用户交互.md`：协作模式、同 Session 目标续跑、任务清单、Questions 与 Commands。
12. `11_Web、Headless、Host、Client、API 与 Agent Preset.md`：产品表面、双 Cordis 世界、typed/legacy API 与 per-preset Agent plane。
13. `12_快照回放、E2E、Invariant 与 Harness 评估.md`：测试层级、LLM replay、runtime relationships 与评估证据边界。

## 阅读方式

每篇先读“一句话结论”和“不能推出的结论”，再沿“源码调用链与数据流”进入代码。遇到 README、外部文章、旧笔记与当前实现不一致时，以当前源码、有效 composition 和可执行测试为准；测试证明的是其覆盖路径，外部文章只提供提问视角，所有超出代码事实的解释都应保留适用边界。
