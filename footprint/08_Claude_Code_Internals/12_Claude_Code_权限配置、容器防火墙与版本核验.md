# 08.12 权限配置、容器防火墙与版本核验

> 核验：2026-09-05；本地提交 `d7dbd9a09f59775726ed14bbea8fc9dfdff62f7b`。本篇从仓库实际配置与脚本入手，未启动容器或改变主机网络规则。

## 1. 不同约束位于不同执行层

```text
CLAUDE.md / Skill：指导模型怎样做
permissions：由宿主判断是否允许调用
PreToolUse：执行前校验或改参数
PostToolUse / Stop：执行后反馈
容器与系统网络规则：约束进程能到达的资源
```

这些能力不能互相替代。禁止 WebFetch 不必然阻止 Bash 的网络访问；事后审查不能撤销已推送的提交；容器内网络放行也不等于业务权限允许。

## 2. 从严格配置读到适用作用域

先读 [examples/settings/README.md](D:/codes/claude-code/examples/settings/README.md#L1)，再读 [examples/settings/settings-strict.json](D:/codes/claude-code/examples/settings/settings-strict.json#L1)。示例明确声明它们是社区维护片段，某些字段只在企业管理配置中生效。

严格示例包含 Bash 的 ask、WebSearch/WebFetch 的 deny、只允许管理规则与管理 Hook、限制已知插件市场等选项。但把 JSON 放进任意目录，不代表这些限制已被宿主加载。

阅读一个配置，应依次确认：字段存在 → 来源层级支持 → 宿主实际加载 → 工具行为验证。JSON 能解析只覆盖第一层的语法；本文未声称严格配置经过产品实测。

## 3. 容器防火墙的真实启动链

[.devcontainer/devcontainer.json](D:/codes/claude-code/.devcontainer/devcontainer.json#L55) 在容器启动后执行 `sudo /usr/local/bin/init-firewall.sh`，并等待该命令。容器配置增加 `NET_ADMIN` 与 `NET_RAW` 能力，工作区通过 bind mount（绑定挂载）映射到 `/workspace`，用户配置挂载到独立卷。

网络脚本 [.devcontainer/init-firewall.sh](D:/codes/claude-code/.devcontainer/init-firewall.sh#L1) 的主线是：读取并保留必要规则 → 建立 IP 集合 → 获取 GitHub 地址范围及解析若干域名的 IPv4 地址 → 加入宿主网络放行 → 设置默认 DROP → 放行已建立连接与集合内目标 → 拒绝其它出口 → 执行连通性检查。

脚本还提前放行 UDP 53（DNS）及 TCP 22（SSH）出口，并放行宿主网段；因此不能概括为“只允许域名集合内目的地”。这段脚本不是按每次 HTTP 请求的域名做判断，而是把解析结果放入 IP 集合，再由 iptables 按目的地址匹配。DNS（域名解析系统）结果变化、共享 IP、IPv6 和宿主网段放行都需要单独评估，不能称为严格的应用层域名白名单。

## 4. 这次只删除了一个预解析域名

相对旧基线，防火墙脚本删除 `statsig.anthropic.com`，仍保留 `statsig.com`。核对入口：[.devcontainer/init-firewall.sh](D:/codes/claude-code/.devcontainer/init-firewall.sh#L67)。

可以确认的是“预解析允许集合少了一个域名来源”；不能仅凭这行删除推出“所有遥测关闭”“所有相关地址必然不可达”或“宿主机防火墙也变化”。规则生效范围是运行该脚本的容器环境。

末尾检查 example.com 应不可达、GitHub API 应可达，只是两个烟雾检查。一次连接失败还可能来自 DNS 或外部网络故障，不能据此证明整个隔离策略正确。

## 5. 用版本对比避免把旧能力当新增

本次基线：

```powershell
git -C D:\codes\claude-code rev-parse HEAD
git -C D:\codes\claude-code diff --stat 0fa8c19d50f70f9f383fb6ff5ce5209575267d21 HEAD
git -C D:\codes\claude-code diff 0fa8c19d50f70f9f383fb6ff5ce5209575267d21 HEAD -- plugins/frontend-design/skills/frontend-design/SKILL.md .devcontainer/init-firewall.sh
```

实际变化只有 CHANGELOG.md、feed.xml、frontend-design/SKILL.md、init-firewall.sh。安全插件、Hookify、Ralph、issue 脚本是这次笔记扩展学习范围，不是此增量的新代码。

发行记录还需注意后续撤回与文档差异：例如 Bash Read deny 的 2.1.259 变更在 2.1.260 撤回；`/skill-doctor` 的日志条目版本与网页最低版本不同。保留证据来源和版本，比强行给出单一结论更适合后续复核。

## 6. 最小复核路径

源码变更：定位文件 → 跟踪执行入口 → 看分支与写入 → 查异常 → 做独立小实验。

产品更新：定位 CHANGELOG 版本 → 检查后续是否覆盖 → 核对官方页面 → 在目标发行物验证。仓库没有实现的细节，到这里就应标为待验证，不能补造类名或状态枚举。
