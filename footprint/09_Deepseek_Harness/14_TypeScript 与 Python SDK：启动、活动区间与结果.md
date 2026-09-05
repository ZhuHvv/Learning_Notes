# DeepSeek Harness：TypeScript 与 Python SDK

## 1. 整体模型

SDK（Software Development Kit，软件开发工具包）让外部程序启动 Harness 子进程，经标准输入输出上的 JSON-RPC（用 JSON 编码的远程过程调用）驱动同一 Agent/Session。SDK 不是重新实现模型循环，也不是浏览器 Remote Gateway 的另一个名字。

```text
业务应用
  → DeepSeekHarness / HarnessClient
  → dsh --profile sdk 或 sdk-minimal
  → SDK server initialize / session prompt
  → Agent inbox → Loop → Session 事件
  → 协议通知 → SDK 收集活动区间 → RunResult
```

## 源码阅读路线

按以下顺序打开源码；链接固定到本次核对时的实际行号。

1. [同版本启动器解析](<D:/codes/deepseek-harness/packages/sdk/client/src/launch.ts#L55>)：packages/sdk/client/src/launch.ts。
2. [TypeScript 活动区间](<D:/codes/deepseek-harness/packages/sdk/client/src/api.ts#L162>)：packages/sdk/client/src/api.ts。
3. [Python 活动区间](<D:/codes/deepseek-harness/python/sdk/src/deepseek_harness/api.py#L134>)：python/sdk/src/deepseek_harness/api.py。
4. [最小 SDK 实际组合](<D:/codes/deepseek-harness/packages/bundle/sdk-minimal/cordis.patch.yml#L1>)：packages/bundle/sdk-minimal/cordis.patch.yml。

## 2. 启动和组合

TypeScript 客户端的 launch.ts 解析并验证同版本 dsh 包。Python client 使用随安装提供的 runtime，并要求调用方显式给出 dsh_home 或非空 DSH_HOME；不能把 Python SDK 描述成会自行发现用户 ~/.dsh。cwd 是 Agent 工作目录，runtime_cwd 是启动进程目录，作用不同。

profile 与有序 patches 是公开的组合入口。sdk 叠加 base 和 sdk-app；sdk-minimal 是独立完整树，含持久 shell、编辑器、JSONL 会话等最小依赖，不继承 base 全部工具。自定义 profile 必须实际提供 SDK server，不能通过任意 argv 替换偷偷变成另一个启动协议。

初始化握手与一次任务等待分别计时。当前 TypeScript launch 的默认 initializeTimeoutMs 是 10,000，Python 默认 initialize_timeout_seconds 是 30；不要因为同协议就假定两端所有默认值相同。普通请求 timeout 由各客户端配置，源码核对不等于本机 runtime wheel 已安装或可启动。

## 3. prompt 接受和 run 完成

低层 session_prompt 返回排队消息 id，表示输入被接受。高层 Session.run 收集的是从该输入的 durable inbox receipt 到下一 whole-agent idle（整个代理没有尚欠工作的空闲点）的活动区间。

父代理可能在子代理结算后再次工作，因此单个 turn/end 不一定代表高层 run 已结束。消费者若只取第一条 completed 文本，可能丢掉后续子任务或目标续跑结果。

| 字段/观察 | 解释 |
| --- | --- |
| Python final_response / TypeScript finalResponse | 区间内最后一个已提交的根 Session assistant 文本 |
| events | 根 Session 的事件集合 |
| notifications | 根与已知后代按协议到达顺序的通知 |
| Python finish_reason | 根会话区间最后 turn/end 的 reason.kind，缺少结束时不能伪造 completed；TypeScript RunResult 没有同名字段，需检查 events |

子代理输出不能覆盖 root final_response。控制层订阅、Session 身份与后代 ancestry（祖先关系）跟踪决定某条通知属于哪个 run，不是通过文本猜测。

## 4. 流、取消和清理

普通持久事件使用 Session v2 的结算格式：完整 Assistant stream 内嵌于 message/attempt。不要指望 SDK JSONL 继续提供顶层 assistant/chunk，也不要把 Web 专用的临时 assistant/live-chunk 当成公共持久事件。

客户端需要区分初始化失败、协议失败、模型 turn failure、调用 timeout 和 transport closed。退出上下文或 close/dispose 负责关闭子进程及订阅；知道一个 session id 不等于拥有任意在其他 runtime 里的 Agent 对象。

## 5. 验证该读哪里

[snapshots/sdk/sdk.snapshot.ts](<D:/codes/deepseek-harness/snapshots/sdk/sdk.snapshot.ts#L1>) 固定 SDK 相关 Session 场景，Python tests 验证 Python 客户端协议与运行区间。仓库的普通 unit test 命令不自动等于双 SDK expected 输出都已更新。本文只核对接口与实现，没有执行安装命令、真实模型请求或 wheel 平台 smoke。

## 6. 证据索引

- [packages/sdk/client/src/index.ts](<D:/codes/deepseek-harness/packages/sdk/client/src/index.ts#L1>)
- [packages/sdk/client/src/launch.ts](<D:/codes/deepseek-harness/packages/sdk/client/src/launch.ts#L1>)
- [packages/sdk/client/src/api.ts](<D:/codes/deepseek-harness/packages/sdk/client/src/api.ts#L1>)
- [packages/sdk/server/src/index.ts](<D:/codes/deepseek-harness/packages/sdk/server/src/index.ts#L1>)
- [packages/bundle/sdk-minimal/cordis.patch.yml](<D:/codes/deepseek-harness/packages/bundle/sdk-minimal/cordis.patch.yml#L1>)
- [python/sdk/src/deepseek_harness/api.py](<D:/codes/deepseek-harness/python/sdk/src/deepseek_harness/api.py#L1>)
- [python/sdk/src/deepseek_harness/client.py](<D:/codes/deepseek-harness/python/sdk/src/deepseek_harness/client.py#L1>)
- [snapshots/sdk/sdk.snapshot.ts](<D:/codes/deepseek-harness/snapshots/sdk/sdk.snapshot.ts#L1>)
