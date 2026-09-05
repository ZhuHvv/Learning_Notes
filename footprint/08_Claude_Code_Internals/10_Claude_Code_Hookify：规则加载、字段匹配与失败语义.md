# 08.10 Hookify：规则加载、字段匹配与失败语义

> 核验：2026-09-05；源码 `d7dbd9a09f59775726ed14bbea8fc9dfdff62f7b`。本篇讨论仓库中的 Hookify 插件，不是 Claude Code 内核。下列函数链接均指向本地实际文件。

## 1. 总体模型：配置转成确定性规则，再返回 Hook 结果

Hook（生命周期钩子）是宿主在某个事件发生时调用的扩展入口。Hookify 用 Markdown 保存规则，Python 负责解析、匹配和输出 JSON。这与把 Markdown 全部交给模型理解有本质区别。

```text
hooks.json 声明事件与命令
  → pretooluse.py.main 读取 stdin JSON
  → 按 tool_name 选择 bash / file 规则
  → config_loader.load_rules 读取当前目录的规则文件
  → RuleEngine.evaluate_rules 逐项匹配
  → stdout JSON + 退出码 0
  → 宿主按事件协议解释输出
```

注意最后两步：脚本返回 `deny` 是插件输出事实；是否符合事件协议、工具是否还没执行，是另一层问题。

## 2. 按真实入口阅读

| 顺序 | 源码入口 | 重点 |
|---|---|---|
| 1 | [plugins/hookify/hooks/hooks.json](D:/codes/claude-code/plugins/hookify/hooks/hooks.json#L1) | PreToolUse、PostToolUse、Stop、UserPromptSubmit 都有注册，命令超时 10 秒 |
| 2 | [plugins/hookify/hooks/pretooluse.py](D:/codes/claude-code/plugins/hookify/hooks/pretooluse.py#L35) | stdin JSON、工具名分类、异常输出 |
| 3 | [plugins/hookify/core/config_loader.py](D:/codes/claude-code/plugins/hookify/core/config_loader.py#L198) | `.claude/hookify.*.local.md` 搜索、event 与 enabled 过滤 |
| 4 | [plugins/hookify/core/config_loader.py](D:/codes/claude-code/plugins/hookify/core/config_loader.py#L87) | 自写的简化 YAML 解析逻辑 |
| 5 | [plugins/hookify/core/config_loader.py](D:/codes/claude-code/plugins/hookify/core/config_loader.py#L45) | 旧 pattern 转成 Condition 列表 |
| 6 | [plugins/hookify/core/rule_engine.py](D:/codes/claude-code/plugins/hookify/core/rule_engine.py#L35) | block 优先级和事件输出分支 |
| 7 | [plugins/hookify/core/rule_engine.py](D:/codes/claude-code/plugins/hookify/core/rule_engine.py#L182) | 实际检查哪个字段 |

规则目录来自进程当前工作目录，`load_rules` 没有使用输入 JSON 的 `cwd` 参数遍历祖先目录。文件读取失败或解析失败会记录错误后继续；这不是全仓强制策略加载器。

## 3. 一条规则怎样匹配

下面是供阅读的规则示例，本次没有安装到项目的 `.claude` 目录：

```yaml
---
name: review-push
enabled: true
event: bash
action: block
conditions:
  - field: command
    operator: contains
    pattern: git push
---
推送前先检查目标分支和改动范围。
```

`Rule.from_dict` 将配置变成 `Rule` 与 `Condition` 对象。`_rule_matches` 先检查 `tool_matcher`，再要求所有条件同时满足；空条件列表不匹配。不同规则可以同时匹配，但只要存在 block，返回消息只组合 block 规则，warn 消息不会一并返回。因此源码注释“所有匹配消息都会合并”不能无条件照抄。

`tool_matcher` 仅支持 `*` 或 `|` 分隔的工具名称精确匹配，不是任意正则。`regex_match` 使用忽略大小写的 Python 正则；`contains`、`equals` 等直接进行字符串比较，大小写行为不同。

## 4. Write 与 Edit 的字段映射缺口

`_extract_field` 优先直接取 `tool_input[field]`，随后才进入特殊映射：

| 输入 | 规则字段 | 实际取得内容 |
|---|---|---|
| Write 的 `content` | `content` | 写入全文 |
| Edit 的 `new_string` | `content` | 新片段 |
| Edit 的 `new_string` | `new_text` | 新片段 |
| Write 的 `content` | `new_text` | 回退读取不存在的 `new_string`，通常得到空串 |

而旧式 `event: file` + `pattern` 恰好会转换成 `field: new_text`。结果是同一危险文本可能命中 Edit，却漏过 Write。新建规则应明确使用能够覆盖目标工具的字段，并用真实输入样本校验；本文指出现状，没有替用户修改插件源码。

## 5. 输出 JSON 与阻止副作用的边界

| 事件 | 当前 RuleEngine 的 block 输出 | 应怎样解释 |
|---|---|---|
| PreToolUse | `hookSpecificOutput.permissionDecision=deny` | 执行前拒绝路径 |
| PostToolUse | 同样输出 `permissionDecision=deny` | 与当前事后事件文档不对应，不能解释成撤销执行 |
| Stop | 顶层 `decision=block` 与 reason | 请求继续当前会话 |
| 其它事件 | 只有 `systemMessage` | 当前实现只是消息提示 |

当前[官方 PostToolUse 协议](https://code.claude.com/docs/en/hooks#posttooluse-decision-control)说明工具已经执行，反馈或替换输出都不能撤销文件写入、命令或网络请求。这个差异必须写进笔记，不能因为代码中出现 deny 就概括成“所有 Hook 都能阻止操作”。本次未在 Claude Code 宿主内验证其如何处理不匹配字段。

## 6. 错误与降级：正常退出不代表规则成功加载

`pretooluse.py` 导入失败时输出 `systemMessage` 并退出 0；`main` 捕获异常，最终同样退出 0。无匹配返回空对象。非法正则记录错误后返回不匹配；未知操作符也返回不匹配。

这是一种 fail-open（故障时放行）的插件策略。它有利于避免提醒插件损坏后阻塞工作，但不适合作为唯一的强制安全边界。正常 Hook 退出码、规则解析成功、匹配成功、宿主拒绝成功应分别观测。

## 7. 本次实验与学习顺序

本次用仓库类与函数进行本地输入实验，覆盖：执行前 block、block 压过 warn、空条件、非法正则、Write/Edit 字段差异、PostToolUse 输出形状，以及未知操作符。实验没有真正运行 git push 或其它危险命令，只将字符串交给规则函数。

学习顺序建议：先复现单规则命中 → 对照工具字段 → 加两条冲突规则 → 制造格式或正则错误 → 最后在可控宿主会话里验证 Hook 协议。最后一步本次未执行。

## 8. 复习问题

1. 为什么 YAML 能解析不等于规则能匹配 Write？
2. 为什么 exit 0 和 `permissionDecision=deny` 不矛盾？
3. 为什么 PostToolUse 的拒绝字段不能代替 PreToolUse？
4. 如果规则文件无法读取，当前代码会拒绝还是放行？
