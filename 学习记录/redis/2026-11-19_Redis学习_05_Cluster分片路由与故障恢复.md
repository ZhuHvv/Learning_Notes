# Redis 学习 05 · Cluster 分片、路由与故障恢复

记录日期：2026-11-19。对应[课程总纲](./Redis学习_总纲与进度.md)模块 10，源码主线为 Redis **8.10.3**。

本篇整理本轮实际讲过的机制、追问、两轮考察及纠正。核心主线已讲，部分机制已考察；当前按学习者要求暂停，**下次从 Cluster、Sentinel、客户端分片的方案对比继续**，随后补必要工程边界。不要从槽和连接关系重新开讲，也不要直接跳到分布式锁。考察记录见第 13 节，剩余范围见第 14 节。

证据范围：固定 tag 源码、官方文档与机制推演；未实际部署集群、运行文中命令、抓包、故障注入或压测。ASM 的整体流程依据官方文档和官方实现介绍，8.10.3 配置项已核对；`cluster_asm.c` 本轮未成功获取，不能把 ASM 全部内部状态机记为已完成源码核验。官方 latest 文档和客户端文档可能随版本更新。

贯穿示例：主节点 A、B、C，副本 A1、B1、C1；必要时为 B 增加副本 B2。D 是迁移目标主节点。节点名、槽分配、epoch、复制偏移和吞吐量均为讲解示例。网络分区默认跨侧双向不通、侧内正常；自动切换、复制时效和写入限制等前提在各节单独说明。

## 1. 分片、复制与键到槽映射

| 分片 | 示例槽范围 | 副本 |
|---|---|---|
| A | 0～5460 | A1 复制 A 的数据 |
| B | 5461～10922 | B1 复制 B 的数据 |
| C | 10923～16383 | C1 复制 C 的数据 |

分片让不同主节点保存不同部分的数据，复制让每部分数据拥有副本。B1 不保存整个集群，也不会因为能连接 A、C 就复制它们的数据。Cluster 的故障检测和副本选举由集群节点参与，正常自动切换不依赖额外 Sentinel。

普通键的路由是 `key → CRC16(key) % 16384 → 槽号 → 负责槽的节点`。键到槽由键名和算法决定，槽到节点由配置决定。扩缩容和切换会改变后者，总槽数仍为 16384。一个槽包含多个键；一个 Hash、ZSet 的字段或成员不会被 Cluster 自动拆到多个主节点。

### 1.1 hash tag 与多键布局

`user:1001:balance` 与 `user:1001:orders` 使用完整键名计算，不能保证同槽。改为 `user:{1001}:balance` 与 `user:{1001}:orders` 后，只用 `1001` 计算槽号，两者保证同槽，完整键名仍然保留。

| 键名 | 参与哈希的内容 |
|---|---|
| `user:{1001}:balance` | `1001` |
| `user:{1001}:orders` | `1001` |
| `user:{1002}:balance` | `1002` |
| `user:{}:balance` | 完整键名 |
| `user:{}:{1001}` | 完整键名，不再寻找后面的标签 |

规则是找第一个 `{`，再找其右侧第一个 `}`；中间非空才作为标签，否则哈希完整键名。相同标签保证同槽，不同标签也可能碰巧同槽。需要共同操作的键应按业务范围聚合；把所有用户都标成 `{all}` 会把它们集中到一个槽。

依据：[键分布与 hash tag](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/#key-distribution-model)。

## 2. 三类连接与正常请求

| 连接 | 建连发起方 | 用途与处理方 |
|---|---|---|
| 业务连接 | 客户端连接主节点；副本读时也连接副本 | 请求由目标节点检查路由，满足条件后本地执行并回复 |
| 主从复制连接 | 副本连接自己的主节点 | 主节点传快照和复制流，副本应用数据并发送 ACK |
| Cluster Bus | 所有节点彼此建立连接，包括主从和副本之间 | 心跳、拓扑、故障报告、选举授权等集群消息 |

稳定状态下，每个节点有 N−1 条出站和 N−1 条入站 Bus 连接。六节点时，每节点为 5 条出站加 5 条入站；复制连接和业务连接另算。Bus 默认端口为数据端口加 10000，也可配置 `cluster-port`。客户端访问数据端口，复制也连接主节点的数据服务端口。

客户端先联系入口节点获取 `CLUSTER SHARDS` 等拓扑信息，再根据槽映射直连目标节点。入口节点不是后续请求的统一处理者。一个应用客户端对象可以管理多个节点连接；预建还是按需建连、连接池大小等由客户端实现决定。

### 2.1 路由检查发生在执行之前

客户端把属于 B 的 `SET` 发给 A 时，顺序是：A 解析命令并判断槽归属 → 发现应由 B 处理 → 返回 MOVED 并结束本次处理 → 客户端向 B 重发 → B 再检查路由与其他执行条件后执行。A 没有执行这次 SET，也没有替客户端转发。

讲解曾把“客户端已收到 MOVED”和“A 执行前检查路由”写在相反叙述顺序，学习者因此追问。已明确纠正：**先检查，后产生重定向；不是返回 MOVED 后再次检查。**

### 2.2 从节点怎样处理客户端请求

在健康、槽稳定的普通键命令路径中，客户端向 B1 写入 B 的槽，B1 返回 MOVED 指向 B；写入 A 的槽，则指向 A。目标是负责该键的主节点，不一定是接收副本自己的上游。

副本普通读默认也会重定向。客户端在到 B1 的连接上执行 `READONLY` 后，可以读取 B 所负责槽的数据，B1 从本地数据回复，可能落后。其他槽仍需重定向，READONLY 不授予副本接受客户端写入的能力。Cluster 已不可服务时，普通请求可能先被 CLUSTERDOWN 拒绝，不能把所有场景概括为一定返回 MOVED。

依据：[Bus 与拓扑](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/#the-cluster-bus)、[CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/)、[READONLY](https://redis.io/docs/latest/commands/readonly/)。源码入口：[`server.c::processCommand()`](https://github.com/redis/redis/blob/8.10.3/src/server.c#L4249)、[`cluster.c::getNodeByQuery()` 副本读分支](https://github.com/redis/redis/blob/8.10.3/src/cluster.c#L1348)。

## 3. 传统槽迁移：MOVED、ASK 与 TRYAGAIN

本节明确限定 **`CLUSTER SETSLOT` + `MIGRATE` 传统路径**，ASM 另见第 12 节。

### 3.1 谁设置目标，谁搬运数据

槽 7000 从 B 迁往 D 时，管理工具先在 D 设置 IMPORTING，来源 B；在 B 设置 MIGRATING，目标 D。正式槽归属暂时仍是 B。设置状态不等于搬数据，工具随后获取槽内键并用 MIGRATE 搬运。

因此 B 知道“槽 7000 的迁移目标是 D”，但不必逐键记录“哪些键已经搬到 D”。对于普通单键请求，B 检查本地是否还有该键：有则本地处理，没有则根据迁移目标返回 ASK。此前从未存在的新键也会被引向 D，从而在目标端创建。

| 当前布局 | 请求发给 B | 处理 |
|---|---|---|
| k1 已到 D，k2 仍在 B；两者同槽 | `GET k2`、`SET k2 value` | B 本地执行，之后迁走更新后的数据 |
| 同上 | `GET k1`、`SET k1 value` | B 返回 ASK，当前写入未在 B 执行 |
| 同上 | 创建这个槽里的新键 | B 本地没有该键，返回 ASK |
| 同上 | `MGET k1 k2` | B 有部分键、缺部分键，返回 TRYAGAIN |

### 3.2 客户端怎样跟随重定向

| 回复 | 当前请求 | 后续正常路由 |
|---|---|---|
| MOVED | 向指定节点重发 | 更新槽缓存或刷新拓扑 |
| ASK | 在目标节点的同一连接先发 ASKING，再重发业务命令 | 不因本次 ASK 把整个槽的正常路由改到目标 |

ASKING 设置连接上的一次性标记。D 仍知道正式归属是 B，普通请求直接到 D 时通常会被 MOVED 回 B；带 ASKING 才能走导入期间的临时处理。客户端下一次操作 k2 仍应先去 B。MOVED 表示当前认定的归属，不代表归属永远不变。

MIGRATE 的正常成功路径是序列化并发送键 → 目标恢复并确认 → 源删除；传输超时可能使两端都保留数据，需要核查结果。大键会增加传输与处理时间。全部键搬完后，将槽的正式归属改为 D 并传播配置；持旧缓存访问 B 的客户端随后通过 MOVED 更新路由。

依据：[传统迁移与 ASK](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/#live-reconfiguration)、[MIGRATE](https://redis.io/docs/latest/commands/migrate/)、[ASKING](https://redis.io/docs/latest/commands/asking/)。源码入口：[`getNodeByQuery()` 的 ASK/TRYAGAIN 分支](https://github.com/redis/redis/blob/8.10.3/src/cluster.c#L1322)、[`askingCommand()`](https://github.com/redis/redis/blob/8.10.3/src/cluster.c#L1598)。

## 4. 故障检测、FAIL 通知与选举

### 4.1 从本地怀疑到故障确认

节点通过 Bus 探测同伴，满足超时检测条件后可将对方记为 PFAIL。这是本地观察。通过 gossip 收集有效时间窗口内的主节点故障报告，达到多数条件并满足本地判定条件后，升级为 FAIL，广播 FAIL 消息。

三主 A、B、C 的例子中，A 自己怀疑 B，再收到 C 的有效故障报告，可以达到两份。负责汇总的并非某个固定主节点，副本也可以依据主节点报告确认并传播 FAIL；副本自身观察不能代替主节点报告票数。

### 4.2 副本怎样知道要参选

B1 收到已知节点发来的 B 的 FAIL 消息后，更新本地记录，不必再独立收集一遍多数报告。之后周期任务调用切换逻辑，检查自己的主节点是否 FAIL、是否负责槽、是否禁止自动切换，以及复制时效等条件。条件满足才安排参选。

通知内容是“B 已 FAIL”，不是 A 专门命令 B1 参选。源码链路是 `clusterProcessPacket()` 接收 FAIL → 本地状态更新 → `clusterCron()` 调用 `clusterHandleSlaveFailover()`。具备足够报告时，副本也可能经本地汇总进入同一后续流程。

### 4.3 谁投票，分票怎么办

故障确认与副本升主授权是两个阶段。自动切换的选民是负责至少一个槽的主节点，需要 `floor(cluster_size / 2) + 1` 票。本例三主需要两票；B 宕机不会立即把分母变为两个，B1 需要 A、C 授权，A1、C1 不参与授权，B1 也不能给自己补一票。

若 B 有 B1、B2 两个副本，A 投 B1、C 投 B2，双方各一票，都不能升主。等待超时后，本轮失败；仍符合条件的副本按重试间隔安排新一轮，使用新 epoch 请求票，旧轮选票不能累加。没有“平票直接比较节点 ID 决出胜者”的规则。

副本发起前有固定 500 毫秒、0～499 毫秒随机延迟和 `rank × 1000 毫秒` 的延迟。rank 根据已知同上游副本的复制偏移量确定，进度靠前者通常更早参选；这减少分票，不保证不会分票或永远选到数据最新者。投票主节点同一 epoch 最多投一次，并检查候选身份、主节点故障和配置等条件。

源码中的授权等待上限 `T = max(2 × cluster-node-timeout, 2000ms)`，安排重试的阈值为 `2 × T`。这些判断围绕本地 `failover_auth_time` 进行，不能理解为发现平票立即重投，也不能把超时结束后再等整个重试阈值机械相加。具体计时和更多失败分支未做独立考察。

依据：[故障检测与选举](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/#failure-detection)。8.10.3 源码位于 `cluster_legacy.c`，该文件实现标准 Cluster Bus 集群机制：[`markNodeAsFailingIfNeeded()`](https://github.com/redis/redis/blob/8.10.3/src/cluster_legacy.c#L1796)、[FAIL 接收](https://github.com/redis/redis/blob/8.10.3/src/cluster_legacy.c#L3089)、[周期调用](https://github.com/redis/redis/blob/8.10.3/src/cluster_legacy.c#L4658)、[`clusterSendFailoverAuthIfNeeded()`](https://github.com/redis/redis/blob/8.10.3/src/cluster_legacy.c#L3852)、[`clusterHandleSlaveFailover()`](https://github.com/redis/redis/blob/8.10.3/src/cluster_legacy.c#L4086)。

## 5. 升主、其他副本跟随与客户端恢复

### 5.1 三项进度不能混为一谈

| 进度 | 动作与完成条件 |
|---|---|
| B1 升主 | 获得多数授权，切换角色，接管旧主槽，保存并发布配置；不要求先等 B2 连接 |
| B2 恢复复制 | 获知新配置，改上游为 B1，建连认证，PSYNC 后部分或全量同步并追赶数据 |
| 客户端恢复访问 | 获知新槽映射，能连接并认证到 B1，且 B1 满足请求执行条件 |

B1 发布较新槽配置，B2 更新本地映射，发现旧上游 B 已失去全部槽、B1 接管后，自行调用配置逻辑改变上游。B1 不需要像 Sentinel 执行者那样另向 B2 发送 REPLICAOF 管理命令。Bus 传播拓扑，独立的复制连接同步实际数据。

“B1 已升主但 B2 未恢复复制”可以成立。额外启用 `min-replicas-to-write` 时，新主可能因合格副本不足拒写；这是升主后的写入限制，不是升主失败。`master_link_status:down` 只说明复制链路不正常，不能断言 Bus 也断开。

### 5.2 已宕机的旧主不能发 MOVED

| 客户端遇到的情况 | 路由恢复 |
|---|---|
| B 宕机或不可达 | 客户端连接失败或超时；通过其他可达节点重新获取拓扑，例如 CLUSTER SHARDS |
| B 恢复且已更新槽归属 | 在请求允许进入路由重定向的条件下，可返回指向 B1 的 MOVED |
| 查询到的其他节点尚未收到新配置 | 可能仍得到旧信息，需要后续刷新或重试 |

B1 的 Bus 配置通知发给集群节点，普通业务客户端通常不直接接收它。客户端何时刷新、选哪个节点、重试次数和连接池行为取决于库与配置；旧 TCP 连接不会自动变成连接新主的 TCP 连接。

### 5.3 切换期间的请求结果

| 观察 | 能确定什么 |
|---|---|
| 确定建连失败、命令未发出 | 本次尝试未执行 |
| 普通命令在路由/集群状态检查处明确收到 MOVED、ASK 或 CLUSTERDOWN | 当前尝试被执行前拒绝；恢复条件后再发 |
| 命令发出后超时或断线 | 结果未知，不能认定未执行 |
| 收到 B 成功回复后 B 故障 | B 已执行，但 B1 可能未收到复制，切换后仍可能丢失 |

集群没有一个统一队列替客户端保存所有失败请求。B1 升主前也不会替客户端暂存写入、等升主后执行。客户端可以实现等待和重试，但 INCR 等非幂等命令在响应丢失后重发可能重复修改；刷新路由不解决结果未知问题。

依据：[`clusterFailoverReplaceYourMaster()`](https://github.com/redis/redis/blob/8.10.3/src/cluster_legacy.c#L4048)、[副本改变上游](https://github.com/redis/redis/blob/8.10.3/src/cluster_legacy.c#L2317)、[客户端重定向](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/#moved-redirection)、[异步复制与写入丢失](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/#redis-cluster-consistency-guarantees)。

## 6. 网络分区、完整槽覆盖与写入窗口

以下假设节点原先已相互发现，允许自动切换，候选复制时效合格，没有额外最少副本写入限制。先区分断网瞬间与故障检测已完成，再分析可达主节点多数和数据副本位置。

### 6.1 B 单独隔离

| 左侧 | 右侧 |
|---|---|
| A、C、A1、B1、C1、客户端 X | B、客户端 Y |

左侧有 A、C 两个主节点和 B 的副本 B1，满足条件后可以完成 B1 升主。右侧 B 在尚未检测出失去多数派时可能继续接受 Y 的写入；检测完成后，可达主节点只有自己 1 个，少于所需 2 个，本地集群状态变为 FAIL，停止普通写入。

**B 不需要先知道 B1 已升主才停写。角色仍为 master 与集群状态 FAIL 可以同时成立。** 两侧依据本地探测和事件推进，没有共同的精确切换时刻。

例如分区前 counter=100，Y 在检测窗口内让 B INCR 到 101，但 B1 未收到复制；B1 升主时仍为 100。网络恢复后 B 接受新配置并跟随 B1，B 的分叉写入不会自动合并。若网络在新配置形成前恢复，则可能仍由 B 担任主节点、B1 追赶，须按实际切换进展判断。

### 6.2 B 与 B1 一起隔离

| 左侧 | 右侧 |
|---|---|
| A、C、A1、C1、客户端 X | B、B1、客户端 Y |

左侧有主节点多数，但没有 B 的可达副本，无法通过自动切换恢复 B 的槽；A1/C1 没有 B 的数据。右侧虽有健康复制，但只有 B 一个主节点，故障检测完成后仍会停写。副本健康不能代替多数主节点可达。

| 配置 | 对上述布局的影响 |
|---|---|
| `cluster-require-full-coverage yes`，默认 | 确认 B 故障且槽未接管后，缺少可用覆盖导致左侧也进入 FAIL；默认读写设置下普通键请求被拒绝 |
| `cluster-require-full-coverage no` | 左侧满足多数可达等条件时可以继续服务 A、C 的槽，B 的槽仍不可用 |
| `cluster-allow-reads-when-down no`，默认 | 集群 FAIL 后普通 GET 也会被拒绝 |
| `cluster-allow-reads-when-down yes` | 可在符合槽归属等条件时读数据，但不恢复写权限，数据可能落后 |

关闭完整槽覆盖检查不会关闭多数派检查，不能让右侧 B 持续写入。具体自动副本迁移等后续拓扑调整未在这些短期分区场景中引入。

依据：[官方分区示例](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/#redis-cluster-consistency-guarantees)、[`clusterUpdateState()` 槽覆盖及多数判断](https://github.com/redis/redis/blob/8.10.3/src/cluster_legacy.c#L4931)、[8.10.3 配置](https://github.com/redis/redis/blob/8.10.3/redis.conf#L1741)。

## 7. 配置纪元、旧主回归与同步方式

### 7.1 currentEpoch 和 configEpoch

| 字段 | 作用 |
|---|---|
| currentEpoch | 本节点已知的逻辑轮次；收到更大轮次时跟进，发起选举时递增 |
| configEpoch | 主节点声明槽归属所用的配置版本；副本成功当选后采用选举版本 |

示例：槽原归 B、版本 7；B1 发起第 8 轮但分票失败，轮次前进但槽配置仍是 B/7；B1 在第 9 轮成功后，声明 B1/9。配置版本不衡量业务数据完整度。

A 收到 B1/9 后逐槽更新本地映射；B 恢复还声明 B/7 时，已知新配置的 A 可以发送 UPDATE 纠正 B，无须 B1 亲自通知。B 即使把 currentEpoch 跟进到 9，也不因此获得版本 9 的槽归属。各节点维护本地映射，传播期间视图可以不同。

在原槽全部由 B1 接管、没有其他拓扑变化的例子中，B 发现自己失去全部槽后改为 B1 的副本。配置和纪元保存到 nodes.conf，键值持久化则属于 RDB/AOF。不能用“B 有更大的 counter”推翻较新槽配置。

### 7.2 旧主不一定全量同步

先限定 B 只是网络断开、进程没有重启。B1 升主时生成新 replid，同时把旧 replid 保存为 replid2，并保存旧历史有效边界。B 降为副本时会用自身原复制 ID 和偏移构造缓存状态，尝试 PSYNC。

假设 B1 升主时已处理旧流到偏移 1000，旧 ID 为 old-id，则允许用旧 ID 请求的下一个字节起点上限为 1001。

| B 回归时的状态 | 请求 | 判断 |
|---|---|---|
| B 仍在旧历史偏移 1000 | `PSYNC old-id 1001` | 历史边界满足；B1 backlog 也满足时可以部分同步 |
| B 的旧流已前进到 1100 | `PSYNC old-id 1101` | 超出 B1 接受的旧历史边界，需要全量同步 |
| B 在 1000，但 B1 所需 backlog 已被覆盖 | `PSYNC old-id 1001` | 历史可识别但缺少增量，需要全量同步 |

请求偏移 q 还须处于新主 backlog 的可续传区间：`backlog.offset <= q <= backlog.offset + backlog.histlen`，并且 backlog 存在。右端等于当前已有流末尾的下一字节，可能无需立即补数据。复制偏移按字节计算，不是写命令数量。

隔离期间 B 接受了未复制给 B1 的写入时，不能靠部分同步先撤销分叉再续传。若“重新上线”是进程崩溃后重启，还要看启动恢复的复制历史状态；恢复出键值不自动证明能够部分同步。不同持久化恢复路径未在此系统展开。

依据：[配置纪元与旧节点回归](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/#configuration-epoch)、[`clusterUpdateSlotsConfigWith()`](https://github.com/redis/redis/blob/8.10.3/src/cluster_legacy.c#L2210)、[UPDATE 纠正](https://github.com/redis/redis/blob/8.10.3/src/cluster_legacy.c#L3036)、[`shiftReplicationId()`](https://github.com/redis/redis/blob/8.10.3/src/replication.c#L1987)、[`replicationCacheMasterUsingMyself()`](https://github.com/redis/redis/blob/8.10.3/src/replication.c#L4339)、[`masterTryPartialResynchronization()`](https://github.com/redis/redis/blob/8.10.3/src/replication.c#L921)。

## 8. 多键命令、Pipeline、事务与 Lua

| 方式 | 执行组织者 | 本轮讲清的边界 |
|---|---|---|
| MGET 等原生多键命令 | 一个节点 | 键要同槽；不同槽碰巧在同节点也不满足 |
| 普通非事务 Cluster Pipeline | 支持该能力的客户端按节点分组 | 可批量分发到不同节点，但整批没有原子性，单条命令仍要合法 |
| MULTI/EXEC | 一个节点 | 整个事务涉及的键同槽，不能只看每条命令分别是否单键 |
| 常规 Lua/EVAL | 一个节点执行脚本 | 声明键同槽；服务端完成读取、判断、修改，不自动跨节点执行 |

跨槽 MGET 若由应用拆成两个 GET，再汇总结果，就失去了服务端单条 MGET 的共同原子读取时刻。Pipeline 允许连续发多条命令后收回复以减少逐条等待；客户端按调用顺序返回数组，不代表不同节点存在相同执行顺序。A 的写入成功、B 的写入失败时，不会自动撤销 A；重试仍需处理结果未知。

redis-py 的 ClusterPipeline 文档展示了按节点分组发送和收集响应；不同客户端要另核查。某些名为 pipeline 的 API 还可启用事务模式，不能仅按 API 名推断语义。

MULTI/EXEC 执行组内命令时不插入其他客户端命令，但不提供数据库式错误自动回滚。Lua 的 `allow-cross-slot-keys` 标志可放宽某些脚本内部跨槽访问限制，声明键仍要求同槽，也不提供跨节点事务。这里只讲 Cluster 执行边界，WATCH、错误分支、脚本缓存和完整原子性语义保留到模块 04。

依据：[MGET](https://redis.io/docs/latest/commands/mget/)、[Pipeline](https://redis.io/docs/latest/develop/using-commands/pipelining/)、[redis-py 集群批处理与事务](https://redis.readthedocs.io/en/stable/advanced_features.html#pipelines-in-clusters)、[事务](https://redis.io/docs/latest/develop/using-commands/transactions/)、[EVAL](https://redis.io/docs/latest/commands/eval/)、[Lua 标志](https://redis.io/docs/latest/develop/programmability/lua-api/#script-flags)。源码：[`extractSlotFromKeysResult()`](https://github.com/redis/redis/blob/8.10.3/src/cluster.c#L1083)、[`getNodeByQuery()` 的 EXEC 检查](https://github.com/redis/redis/blob/8.10.3/src/cluster.c#L1163)。

## 9. SCAN、统计与迁移中的可见性

直接向 A 执行 SCAN，遍历的是 A 的本地数据库，不会自动扫描 B、C。拓扑稳定时，客户端或工具需要获取主节点列表，对各节点分别完成扫描并汇总。每个节点有独立游标，A 的游标不能拿到 B 或新主上当作同一轮的续接位置。

| SCAN 概念 | 含义 |
|---|---|
| 起始游标 0 | 开始一轮遍历 |
| 返回游标非 0 | 使用返回值继续，即使本批键列表为空 |
| 返回游标为 0 | 本轮遍历结束 |
| COUNT | 工作量提示，不保证每次准确返回该数量 |
| MATCH | 模式筛选，不把结果变成一致性快照 |

完整遍历保证返回整轮期间持续存在于被遍历集合中的元素，可能重复；期间变化的元素是否返回不确定。SCAN 不在开始时冻结数据快照。

以下是跨节点扫描的机制推演：先在 A 读到 key-x，迁往 B 后又扫描 B，可能重复；若先扫完 B，再将 key-x 从 A 迁到 B，随后扫描 A，可能漏掉。键始终存在于集群不等于始终存在于某个本地扫描集合。按键名去重不能补回遗漏。

Redis 8.0 起可优化能够推断单槽的模式，例如 `SCAN 0 MATCH user:{1001}:* COUNT 100`；`*{1001}:*` 因标签前的通配符不能使用同样的单槽优化。该优化只缩小本地遍历范围，不自动去正确节点查询。迁移时仍要结合路径和可见性规则判断。

DBSIZE 也由单节点执行；主节点数量相加可以统计静止、稳定场景，不应再加副本造成重复。在线分时查询没有统一快照保证。**ASM 导入/清理期间还存在过滤规则**，DBSIZE 不应一概解释为物理内存里全部键的数量，详见第 12 节。

依据：[SCAN](https://redis.io/docs/latest/commands/scan/)、[模式优化](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/#glob-style-patterns)、[DBSIZE](https://redis.io/docs/latest/commands/dbsize/)。源码：[`db.c::scanGenericCommand()` 的本地遍历](https://github.com/redis/redis/blob/8.10.3/src/db.c#L1812)、[`scanCommand()` / `dbsizeCommand()`](https://github.com/redis/redis/blob/8.10.3/src/db.c#L2013)。

## 10. 扩容、热点和大键

空主节点 D 加入一个槽已分配完整的集群后，还需管理工具安排槽和数据迁移，才会分担对应负载。槽数量均匀不等于键数、内存、请求频率或命令成本均匀。

| 压力来源 | 扩容的作用与限制 |
|---|---|
| 很多不同键共同造成压力 | 迁出部分槽，可把数据和请求分给新主节点 |
| 单个热点键造成主要压力 | 迁移只改变热点所在节点，不能把同一键的写入分给多个主节点 |
| 单个巨大 Hash/ZSet | 成员不会自动按节点拆分；需要业务拆成不同键才可能分片 |
| 热点读取 | 新增副本且客户端实际启用副本读，可以分担部分读负载，但可能读旧数据 |
| 热点写入 | 仍由负责槽的主节点执行，增加副本不能直接增加同键写入处理能力 |

热点关注访问频率和执行成本，大键关注空间或元素数量，两者可同时存在。全服榜一个 ZSet 仍是一个键；按赛季、区域拆成多个键可以分散，但跨榜查询需重新设计。hash tag 聚合范围过大也会限制分散能力。

传统 MIGRATE 的序列化、传输和恢复成本受数据大小影响；每批 10 个键不保证工作量小，其中可能有大键。该路径可能阻塞命令处理并影响两端延迟，不能直接套用为 ASM 的全部实现结论。新增副本也会增加复制资源成本。

依据：[扩容流程](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/#live-reconfiguration)、[分片模型](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/#redis-cluster-data-sharding)、[副本读取](https://redis.io/docs/latest/commands/readonly/)、[传统 MIGRATE 成本](https://redis.io/docs/latest/commands/migrate/)。未做容量测算或压测。

## 11. 排障：连接、集群状态和复制分别验证

| 客户端现象 | 下一步检查 |
|---|---|
| 建连失败或超时 | 实际地址、网络路径、节点是否运行；写入超时需保留结果未知判断 |
| MOVED | 客户端是否刷新/重定向，返回的业务地址是否可达 |
| ASK | 是否在目标同一连接先发 ASKING，迁移状态是否符合预期 |
| CROSSSLOT | 键名和 hash tag，命令/事务/脚本整体涉及的槽 |
| CLUSTERDOWN | 本节点对多数可达、槽覆盖的判断，以及相关配置 |

### 11.1 观察入口及口径

| 命令 | 观察内容与限制 |
|---|---|
| CLUSTER SHARDS | 当前返回节点掌握的槽和主从拓扑；用于客户端路由 |
| CLUSTER INFO | 本节点的 cluster_state、槽统计、已知节点数与负责槽的主节点数 |
| CLUSTER NODES | 本节点记录的节点角色、上游 ID、fail?/fail、配置纪元、槽范围、Bus 链路 |
| CLUSTER LINKS | Bus 入站/出站连接和缓冲等信息 |
| INFO replication | 本实例真实复制角色、上游、链路、同步状态、复制 ID 和偏移 |

`cluster_slots_assigned:16384` 只说明全部槽有归属记录，不代表负责节点健康；还应看 `cluster_slots_ok`、`cluster_slots_fail` 等。`cluster_known_nodes` 是已知节点总数，`cluster_size` 是负责至少一个槽的主节点数。分区时多个节点的视图可能不同。

CLUSTER NODES 的 `connected` 表示 Bus 链路状态，不证明复制正常。B2 可以同时与 B1 的 Bus 连通、上游配置指向 B1，但 `master_link_status:down`；需检查复制认证、数据端口与同步日志。`master_link_status:up` 也不单独证明已追平，要结合复制历史和偏移。

客户端能连入口 A，但 MOVED 返回的 B1 地址不可达时，服务端可能已正确路由，故障在地址宣告或网络路径。普通客户端需要访问实际负责请求的节点；入口可达不代表所有节点都可达。认证、NAT、宣告参数的完整配置仍待补充。

依据：[CLUSTER INFO](https://redis.io/docs/latest/commands/cluster-info/)、[CLUSTER NODES](https://redis.io/docs/latest/commands/cluster-nodes/)、[CLUSTER LINKS](https://redis.io/docs/latest/commands/cluster-links/)、[INFO replication](https://redis.io/docs/latest/commands/info/#replication)、[端口要求](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/#redis-cluster-tcp-ports)。本节仅讲观察方法，没有实际排障实验结果。

## 12. 版本补充：原子槽迁移 ASM

ASM 从 Redis 8.4 引入，8.10.3 支持；前面传统迁移的逐键分散、ASK 和 TRYAGAIN 情景不能无条件套到 ASM。

### 12.1 先复制，后交接服务权

| 阶段 | B（源主节点） | D（目标主节点） |
|---|---|---|
| 复制阶段 | 保留并继续服务待迁移槽，产生相关增量 | 接收槽快照并追赶增量，收到某个键不等于取得该键服务权 |
| 交接阶段 | 达到条件后暂停写入，等待目标接管 | 应用剩余增量，接管槽，发布新配置 |
| 交接后 | 收到配置后恢复请求处理，旧路由请求转为 MOVED；清理旧数据 | 服务迁入槽 |

任务在目标主节点发起，如 `CLUSTER MIGRATION IMPORT 7000 7000`。返回任务 ID 表示启动，不代表完成；可用 `CLUSTER MIGRATION STATUS ID <任务ID>` 查看状态。D 为指定槽建立迁移连接并接收快照和增量，不会因此整体变成 B 的从节点。

“原子”聚焦服务权交接，不表示复制传输瞬间完成，也不表示写入完全没有暂停。讲解采用官方正常流程；取消、重试、两端故障、清理等完整状态机尚未展开。

### 12.2 阈值、暂停与可见性

| 配置/状态 | 含义 |
|---|---|
| `cluster-slot-migration-handoff-max-lag-bytes` | 触发交接的剩余增量阈值；较大可更早交接但暂停可能更长，较小可能更难追到 |
| `cluster-slot-migration-write-pause-timeout` | 源端交接暂停的上限；目标未及时接管时，源端恢复写入并判任务失败 |
| 暂停上限设得过低 | 目标仍在延迟交接时源端恢复写入，后续目标再发布配置可能形成丢写窗口；不是无损回滚保证 |
| 导入或清理中的非归属槽数据 | 可能被 SCAN、KEYS、DBSIZE、GETKEYSINSLOT 等过滤；INFO KEYSPACE 仍反映包括导入数据在内的实际数量 |

物理上持有键、当前负责该槽、扫描与统计展示该键，是不同层次。ASM 本身也不会把逐节点扫描变成全局一致性快照。

依据：[8.4 引入说明](https://redis.io/docs/latest/develop/whats-new/8-4/#atomic-cluster-operations)、[官方 ASM 实现介绍](https://redis.io/blog/atomic-slot-migration/)、[CLUSTER MIGRATION 与可见性](https://redis.io/docs/latest/commands/cluster-migration/)、[8.10.3 交接配置与风险说明](https://github.com/redis/redis/blob/8.10.3/redis.conf#L1861)。ASM 内部源码获取未成功，证据范围见篇首。

## 13. 考察、追问与纠正记录

### 13.1 第一轮：网络分区的时间和配置前提

共同前提：三主 A/B/C，各一副本；自动切换允许、候选合格，没有额外最少副本写入限制。

| 题目 | 学习者原回答要点 | 判定与后续补充 |
|---|---|---|
| 左侧 A/C/A1/B1/C1，右侧 B/Y；检测已完成，B1 已升主，但 B 不知情。B 是否接受 INCR？ | 答“可能会接受”，区分发现之前能响应、发现其他主节点断连后可能停止；明确不需要知道 B1 是否升主 | “无需知道新主”理解正确；忽略题设已检测完成。已纠正为确定拒写，并补充 master 角色与 cluster_state=fail 可同时存在。纠正未独立复述 |
| 左侧 A/C/A1/C1，右侧 B/B1；检测已完成，full-coverage=no。A/C 能否服务自己的键？ | 答“可能是，需要根据集群配置判断” | 题目已给 no，且左侧有多数，因此确定可以。配置与题设代入不足，补充后未独立复述 |
| 同上一布局，B 能否写？ | 答发现其他主节点断连后停止，否则可接受 | 阶段区分方向正确，但题设检测已完成，确定拒写；B1 正常复制不能补主节点多数。未独立复述纠正 |
| 同上一布局，左侧能否自动恢复 B 的槽？ | 答不能，因为没有 B 的从节点可升主 | 核心判断正确。准确表述是 B1 仍存在，但在不可达的右侧，左侧没有可达的 B 的副本 |

此轮后学习者回复“明白，继续”，仅记录收到解释，不升级为全部条件已独立掌握。

### 13.2 第二轮：传统迁移与三种恢复进度

| 题目 | 学习者原回答要点 | 判定与后续补充 |
|---|---|---|
| 槽 7000 归 B，B 迁往 D；k1 在 D，k2 在 B。向 B GET k1，为什么不改全槽路由？ | 答 B 查本地，不在则 ASK 去 D；正式归属仍在 B，未迁完的键还在 B | 机制和保留路由理由正确。补充题设已确定 k1 不在 B，以及同一目标连接先 ASKING 再 GET；ASKING 未独立复述 |
| 同一布局，MGET k1 k2 能否因同槽而成功？ | 答不能，部分数据在 D、部分在 B | 判断正确。补充具体是 TRYAGAIN，不是 CROSSSLOT，也不由 B 跨节点拼接；错误名未独立复述 |
| A 记录 B1 已升主接管槽；B2 上游=B1 但复制 down；客户端仍连 B 超时。是否说明升主失败？ | 答不对，B1 已升主，B2 更新配置但未连好，客户端仍访问旧 B | 正确区分三项进度；补充 down 仅指复制链路，Bus 可能正常 |
| 上一题中，三项恢复还需什么条件？ | 答 B1 升主还需和其他从节点建立连接；B2 建连并主从同步；客户端向其他节点获取新映射地址 | 后两项方向正确；“升主需先连其他副本”错误，已纠正。补充升主完成不以 B2 建连为前提；最少副本写入限制可能使新主已升主却拒写。纠正未独立复述 |

### 13.3 关键追问的解释状态

| 追问 | 已给出的解释 | 状态 |
|---|---|---|
| A 已告诉客户端重定向，为何还检查路由？ | 原叙述顺序有歧义；先检查路由才产生 MOVED | 已纠正说明，未独立复述 |
| B 不知道键是否已迁到 D，怎样知道 ASK 去哪里？ | 管理工具预先设置槽迁移目标 D；本地键检查决定是否 ASK | 已解释，迁移机制在第二轮部分复述正确 |
| 所有节点互连吗？写给副本用 MOVED 吗？ | Bus 全互连；正常稳定普通写按目标槽主节点重定向，复制上游不是所有节点 | 已解释确认，未逐项独立考察 |
| 从节点如何获知 FAIL，多个副本分票怎么办？ | FAIL 消息与本地周期检查；无多数不升主，超时后新轮次重试 | 已讲，未独立考察 |
| B 已不可达，谁告诉客户端 B1 升主？ | 客户端经可达节点刷新拓扑；旧主不可达时不能回复 MOVED | 已讲，第二轮正确指出客户端需获取新映射 |
| 新主怎样通知其他副本，复制是不是主从复制？ | Bus 传播槽配置，副本自行改上游，再通过主从复制同步 | 已讲，未独立完整复述 |
| 原主回归一定全量同步吗？ | 不一定；旧复制 ID 有效边界、请求偏移和 backlog 决定，进程重启另需看恢复状态 | 已讲，未独立考察 |

配置纪元、扫描、Pipeline/事务/Lua、热点与容量、诊断字段、ASM 均已讲解，但尚未独立考察。学习者多次表示“明白/继续”，不据此补写不存在的掌握证明。

## 14. 暂停点与下次续接

学习者在本轮明确要求先整理 Cluster 内容，下次继续。本次只保存记录，不继续授课、部署或实验。

### 下次优先顺序

1. **Cluster、Sentinel、客户端分片的职责和选型对比**：哪些方案提供分片，谁路由、谁切换，业务要承担什么；此前仅零散比较，尚未系统讲完。
2. **必要工程边界**：认证与各类连接、节点地址宣告/NAT，计划内主从切换；副本不足及迁移失败的处理思路。基础地址可达性和失败现象已讲，不需重复整章。
3. **收尾考察与记录**：择机巩固题设时间/配置代入、ASKING、升主不依赖其他副本连接等，不必从头重新提问。

预计还有约 2～3 个收尾小节，加一轮必要巩固；这是范围估计，不是完成承诺。选举资格/时效参数、自动副本迁移、ASM 完整异常状态机等可列为后续回访，不作为本轮所有分支必须穷尽的前提。实际部署、抓包、客户端实现验证、故障演练和压测均未开展。

整体架构继续暂停；模块 03～07 仍暂缓。事务和脚本在本篇只覆盖分片边界，不代表模块 04 已完成。Cluster 收尾后再按学习者选择继续总纲，回到扩展类型时从 Bitmap 接续。复制与 Sentinel 的既有回访项继续保留。
