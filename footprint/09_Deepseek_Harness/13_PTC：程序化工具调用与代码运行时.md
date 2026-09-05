# DeepSeek Harness：PTC 程序化工具调用与代码运行时

## 1. 先区分两种 SDK

PTC（Programmatic Tool Calling，程序化工具调用）让模型写程序来调用本会话工具。这里生成的工具 SDK 是模型程序内的函数集合；下一篇 TypeScript/Python 客户端 SDK 则由外部应用启动和驱动 Harness，二者不在同一个进程位置，也不拥有相同生命周期。

PTC 适合先搜索、读取、筛选和聚合，再把少量结果交给模型的工作。中间返回值交给程序，最终 print/return 决定外层工具结果；因此可以减少模型反复接收整批中间数据的成本，但并不保证任意任务都更便宜或更可靠。

## 源码阅读路线

按以下顺序打开源码；链接固定到本次核对时的实际行号。

1. [模型工具展示模式](<D:/codes/deepseek-harness/packages/core/tools/src/index.ts#L644>)：packages/core/tools/src/index.ts。
2. [run_code 和嵌套分发](<D:/codes/deepseek-harness/packages/core/tools/src/ptc.ts#L293>)：packages/core/tools/src/ptc.ts。
3. [Worker 时间与输出预算](<D:/codes/deepseek-harness/packages/code-runtime/code-runtime-worker-thread/src/index.ts#L25>)：packages/code-runtime/code-runtime-worker-thread/src/index.ts。

## 2. 从模型到真实工具

```text
SystemPrompt + ToolRuntime.schemas(agent)
  → mode=ptc：只公开 run_code + 生成的工具 SDK 说明
  → 模型提交 code/description
  → createRunCodeTool → CodeRuntime.run
  → Worker 内程序调用工具绑定
  → message-port bridge → ToolRuntime 嵌套执行
  → pre/guard/body/post → canonical value 返回程序
  → 程序选择 print / return
  → 外层 tool/result 进入模型历史
```

展示模式在 [packages/core/tools/src/index.ts](<D:/codes/deepseek-harness/packages/core/tools/src/index.ts#L1>) 定义为 native、ptc、both。native 直接给工具 schema；ptc 仅允许模型直接调用 run_code；both 同时给两类入口。只修改 prompt 提示“请用 run_code”不等于已经启用 registry 的 ptc 直接调用限制。

每次 SDK 子调用有派生 subCallId，与外层 parentCallId 相连。参数仍是需要校验的模型/worker 数据；桥接不会因为代码已通过 TypeScript 类型擦除就信任输入。子工具执行要观察 cancellation 和父调用的生命周期。

## 3. 中间结果的两条去向

| 结果 | 去向 |
| --- | --- |
| canonical output value | 返回模型编写的程序，方便结构化处理 |
| tool/code-dispatch-start 与 tool/code-dispatch | 写入 Session，保留子调用意图与结算事实 |
| 程序 print/return | 经 run_code renderer 成为外层模型结果 |

“中间结果不全部送给模型”不等于“中间工具不记日志”。`tools/ptc-dispatch-log` 是子调用日志内容的 waterfall（需 next 才委派的处理链），观察者要区分发给程序的原值和日志记录内容。图片类结果还有自己的可见内容处理，不应将所有输出简化成 JSON 字符串。

如果程序发起并发工具后提前 return，bridge 仍需处理已启动调用的结算，不能让后台副作用脱离外层工具生命周期。排查挂起时，沿 ptc.ts 的 dispatch/drain 与 worker-thread 消息协议一起读。

## 4. Worker 的限制与安全含义

代码运行时为每次执行创建 Worker（工作线程），擦除 TypeScript 类型语法并通过消息端口转发绑定。配置提供 computeMs、maxWallMs、maxOutputBytes 和 maxOldGenerationSizeMb。computeMs 衡量 worker event loop 的实际 active time，maxWallMs 是不暂停的总墙钟上限；等待工具 I/O 和同步忙循环因此不能用同一时间口径解释。

Worker 可以被 terminate，能隔离同步死循环对 Host 事件循环的直接阻塞；它和 node:vm 都不是不可信代码的安全沙箱。源码明确将这类程序视为具有 shell 等级的信任。内存、输出和时间预算提供运行约束，不提供文件、网络或凭据隔离证明。

## 5. 与 Workflow 的区别

PTC 以本会话工具绑定为中心；Workflow 以 agent/parallel/pipeline 编排子任务为中心。两者都可能使用 Worker，但不能共享一套“代码沙箱”的笼统描述。是否注册 CodeRuntime、是否公开 run_code、是否公开 workflow，分别由配置决定。

## 6. 阅读时检查的问题

1. 当前 Agent 实际模式是什么，生成 SDK 的语言是否与运行时相同？
2. 子调用如何回到工具权限管线，如何链接外层 callId？
3. 中间 canonical value、日志内容和最终模型可见内容分别在哪里变换？
4. 取消、同步死循环和输出超预算由哪个 owner 终止？

## 7. 证据索引

- [packages/core/tools/src/index.ts](<D:/codes/deepseek-harness/packages/core/tools/src/index.ts#L1>)
- [packages/core/tools/src/ptc.ts](<D:/codes/deepseek-harness/packages/core/tools/src/ptc.ts#L1>)
- [packages/core/tools/src/types.ts](<D:/codes/deepseek-harness/packages/core/tools/src/types.ts#L1>)
- [packages/code-runtime/code-runtime/src/index.ts](<D:/codes/deepseek-harness/packages/code-runtime/code-runtime/src/index.ts#L1>)
- [packages/code-runtime/code-runtime-worker-thread/src/index.ts](<D:/codes/deepseek-harness/packages/code-runtime/code-runtime-worker-thread/src/index.ts#L1>)
- [packages/preset/agent-presets/presets/ptc/agent.cordis.yml](<D:/codes/deepseek-harness/packages/preset/agent-presets/presets/ptc/agent.cordis.yml#L1>)
