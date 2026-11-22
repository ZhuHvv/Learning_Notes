# Redis 学习 04 · Sentinel 与故障恢复

记录日期为 2026-11-19，课程模块 09，以 Redis 8.10.3 为源码主线。

本篇记录对话中实际讲过的机制、关键追问、纠正和考察。证据范围为源码核对与纸面推演，实际部署、抓包和故障实验均待进行。

贯穿示例采用主库 M、从库 R1/R2、哨兵 S1/S2/S3、客户端 A/B。逻辑名称为 `mymaster`。除具体题目另有说明，三个哨兵已经互相发现，`quorum = 2`。网络分区例子假设跨侧双向不通、侧内正常。不同例子的节点布局和配置在对应表格中单独给出。

## 1. 连接、监控与发现

### 1.1 谁主动建立 TCP 连接

每个哨兵主动连接被监控的主库、已发现的从库和其他同组哨兵。下表箭头表示建连发起方向，连接建立后双方可以收发数据。

| 连接 | 数量与用途 |
|---|---|
| S1 → M、R1、R2 | 每个 Redis 通常各两条。一条命令连接用于 PING、INFO、发布 HELLO、提升和重配置，一条订阅连接接收 `__sentinel__:hello` 消息 |
| S1 → S2、S3 | 每个同伴各一条命令连接，用于探测、询问下线判断和请求投票。S2、S3 也各自主动连接其他哨兵 |
| R1 → M、R2 → M | 从库主动连接上游，建立复制关系后主库沿连接发送复制数据。全量复制单、双通道细节见第三篇 |
| 应用 → 可达哨兵 | 查询主库地址或副本列表 |
| 应用 → 目标 Redis | 直接执行 GET、SET、INCR 等业务命令 |

在本例一主两从、三个哨兵的稳定连接状态下，S1 主动建立的连接为 `3 × 2 + 2 × 1 = 8` 条，同伴和应用主动连入 S1 的连接另计。每个哨兵都有自己的监控连接，因而 S1 连不上 M 时，S2 仍能独立观察 M。[建连源码 `sentinelReconnectInstance()`](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L2406-L2494)

### 1.2 怎样发现节点、持续监控

初始配置指定主库地址和逻辑名称。哨兵从主库的 INFO 发现副本，再主动连接它们。各哨兵在受监控 Redis 的 `__sentinel__:hello` 频道发布自己的地址和配置，订阅该频道的其他哨兵据此发现同伴并建立直连。M 失联后，已经建立的哨兵间连接仍可用于协调。[自动发现机制](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/#sentinels-and-replicas-auto-discovery)

哨兵事件循环遍历每个节点的本地记录，异步发送命令，在回复回调中更新状态。等待 M 回复期间，也能继续处理 R1、R2。

| 操作 | 默认节奏与作用 |
|---|---|
| PING | 约 1 秒检查可达性，实际发送受最近收发时间、配置和调度影响。有效回复更新可用时间 |
| INFO | 正常约 10 秒刷新角色、上游、复制进度和优先级。主库 ODOWN、切换进行中，或副本报告复制链路已断开等条件下，对相关副本加快到约 1 秒 |
| HELLO | 默认约 2 秒发布一次，消息包含自己的身份、current_epoch、主库地址和 config_epoch |

`S1 → R1` 探测正常与 `R1 → M` 复制断开可以同时成立。S1 从 R1 的 PING 和 INFO 分别获得这两种观察。PING 等待时间从最早尚未获得有效回复的探测开始累计，后续补发不会把计时归零。源码接受 PONG、LOADING、MASTERDOWN 作为有效可达响应。[周期命令与 PING 计时](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L3104-L3185) · [回复处理](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L2801-L2822)

### 1.3 客户端连接、重连与副本读取

主库模式先查询 `SENTINEL get-master-addr-by-name mymaster`，再向返回地址建立业务连接，通过 ROLE 核实角色。后续读写可以复用业务连接。查完地址后是否关闭、复用哨兵连接，由客户端库决定。

业务连接失败后，客户端重新查询可达哨兵，获得地址后重新连接。连接池发现主库地址变化时，也要刷新旧连接。具体等待、重试和事件订阅策略取决于客户端实现。哨兵执行节点重配置时还会要求断开相关客户端连接，促使客户端重新发现主库。[客户端重连规范](https://redis.io/docs/latest/develop/reference/sentinel-clients/#handle-reconnections)

副本读取需要应用或客户端显式启用，查询入口是 `SENTINEL replicas mymaster`。客户端选择可用副本、连接并验证角色，再发送读请求。同一应用可以同时维护主库写连接和副本读连接。主库模式客户端在 R1 升主后连接 R1，此时连接目标仍是当前主库。分区例子中的“B 读取 R1 旧数据”以 B 已使用副本读取为前提。[副本连接规范](https://redis.io/docs/latest/develop/reference/sentinel-clients/#connect-to-replicas)

## 2. 下线、选举和重试

### 2.1 SDOWN、ODOWN 和执行授权

例如 `sentinel monitor mymaster 10.0.0.10 6379 2` 设置 quorum 为 2，`sentinel down-after-milliseconds mymaster 5000` 设置本地探测超时为 5 秒。若 S1 等待 M 的有效 PING 回复超过 5 秒，便会在本地标记 SDOWN。另一种情形是 M 能回复 PING，却持续在 INFO 中报告自己是副本。角色与监控配置不符的时间超过 `down-after-milliseconds + 2 × INFO 周期` 时，S1 也会把 M 标记为 SDOWN。[本地 SDOWN 条件](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L4619-L4637)

S1 通过 `SENTINEL is-master-down-by-addr` 询问同伴。S1 仍判 M 为 SDOWN，且自己的判断加上同伴近期对 M 的下线判断达到 quorum 时，S1 在本地标记 ODOWN。网络分区时，M 的进程仍可能在另一侧运行。副本也可以被标记 SDOWN，自动切换流程中的 ODOWN 检查用于主库。[ODOWN 计数](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L4654-L4671)

| 阶段 | 所需数量 | 三个哨兵、quorum=2 |
|---|---|---|
| 主库 ODOWN | quorum 份下线判断，包含自己 | 2 份 |
| 某哨兵当选本轮执行者 | 同一候选者票数同时达到 quorum 和已知哨兵总数的严格多数 | 至少 2 票 |

五个哨兵、quorum=2 时，下线判断两份可以达到 ODOWN，但授权需要至少三票。三个哨兵分区后，即使右侧只剩 S2，分母仍是已知的三个。quorum 改为 1 后，S2 可以达到 ODOWN，但仍凑不出当选所需的两票。[计票源码 `sentinelGetLeader()`](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L4848-L4905)

### 2.2 分票后怎样进入新 epoch

针对同一主库，每个哨兵同一 epoch 最多投一次票。三者可能各得一票而无人当选。若第三票尚未投出，也可能随后形成两票多数。候选者选举等待上限取默认 10 秒与 failover-timeout 的较小值，未当选则退出自己的本次尝试。

每个哨兵定时检查本地三个条件，决定能否发起自动切换。

1. 当前记录的主库仍是 ODOWN。
2. 自己针对它没有正在进行的切换尝试。
3. 距记录的 `failover_start_time` 已经过 `2 × failover-timeout`。

在新轮次实际给别人投票时，也会更新自己的尝试时间，并带少量随机偏移。间隔从记录的开始时间计算。若 failover-timeout 为 60 秒，本轮约 10 秒未当选退出后，自己的下次发起资格约在距记录起点 120 秒时恢复。其他哨兵有各自的状态和时间。满足条件后执行 `failover_epoch = ++current_epoch`，并向同伴请求投票。[投票与延迟](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L4792-L4816) · [发起条件](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L5015-L5042) · [选举等待](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L5151-L5179)

S2 是某个主库某轮切换的执行者。M 健康且其他哨兵正常访问 M 时，仅 S2 宕机不会触发主库故障转移。若 M 和 S2 先后宕机，剩余哨兵是否需要重选，取决于它们已知的主库配置和本地的发起条件，具体时序见第 5.1 节。

## 3. 选择、提升与配置传播

### 3.1 根据什么选择新主库

当选执行者先过滤下线、断连、响应或 INFO 过旧、复制断开太久、`replica-priority = 0` 的副本。健康且与哨兵连通的副本，也可能因早已和旧主失去复制联系而被排除。无合格候选时中止本次尝试。

合格候选依次比较正 priority、复制偏移量、run_id。正 priority 越小越优先，只有相同才比较偏移量，偏移量越大越优先，再相同则选 run_id 字典序较小者。

| 候选 | priority | 执行者已知的复制偏移量 | counter |
|---|---|---|---|
| R1 | 100 | 1200 | 101 |
| R2 | 10 | 1100 | 100 |

假设两者均合格，上表会选择 R2。若两者 priority 都为 100，则选择 R1。最终保留的数据取决于实际提升的副本。[选择函数 `sentinelSelectSlave()` 与比较函数](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L5077-L5145)

### 3.2 从命令发出到客户端查到新主

以下沿用 R1、R2 的 priority 都为 100 的情形。S2 根据已知复制偏移量选中 R1。

| 阶段 | 执行者 S2 的动作和观察 | 向 S2 查询主库地址 |
|---|---|---|
| 选中 R1 | 本地记下目标副本 | 仍是 M |
| 发送提升命令 | 向 R1 发 SLAVEOF NO ONE，进入 WAIT_PROMOTION | 尚未确认时仍是 M |
| INFO 确认提升 | R1 报告 role:master，S2 将本轮 failover_epoch 写入 config_epoch，进入 RECONF_SLAVES | 已可以返回 R1 |
| 重配置其他副本 | 命令 R2 跟随 R1，观察新上游和链路状态，按条件完成收尾 | 返回 R1 |

R1 已经执行提升，但 S2 还没收到 INFO 时，两者的状态会短暂不同。等待超过 failover-timeout 仍未确认提升，S2 会中止本次尝试。[提升等待源码](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L5231-L5238) · [确认与地址发布](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L2685-L2709) · [地址查询](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L1667-L1680)

R2 收到重配置命令后主动连接 R1，按复制 ID 和 backlog 条件部分或全量同步。S2 处理 R2 的 INFO 时，先核对上游是否已变成 R1，再检查复制链路是否为 up。若同一份 INFO 同时满足两项条件，S2 可以在一次回调中连续推进两个状态。新主地址已经可用时，R2 可能仍在同步或不可达。要确认某一笔写入是否已复制，仍需查看相应复制进度。[副本重配置观察](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L2748-L2772)

### 3.3 S1 为什么会继续传播配置

HELLO 始终周期发送。S1 收到版本 8 的新配置，比较发现高于本地版本 7，就将本地主库地址改为 R1、config_epoch 改为 8。下一次组装 HELLO 时，这些新值会进入消息，S3 收到后也按版本比较更新。

S1 发送由定时条件触发，发送内容由本地记录决定。执行者 S2 在确认提升时，另外调用 `sentinelForceHelloUpdateForMaster()` 加快下一次发布。新配置经 Redis 的 Pub/Sub 等路径传给其他哨兵，普通副本通过收到的复制重配置命令改变上游。[接收更新](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L2949-L2969) · [HELLO 消息组装](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L3025-L3065) · [周期发送条件](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L3176-L3185)

## 4. 请求、分区与写入限制

### 4.1 切换期间的一次 INCR

请求一直发往客户端实际连接的 Redis。哨兵负责发现和切换，业务请求的等待与重试由客户端或应用处理。

| 请求状态 | 能确定什么 | 后续影响 |
|---|---|---|
| 连接失败，确定命令尚未发出 | 本次尝试没有执行 | 找到新主后可以发送 |
| 命令发出，读取回复时超时或断线 | 执行结果未知 | 旧主可能已执行，也可能已经复制。自动重发可能重复修改 |
| 收到旧主返回 101，随后故障 | 旧主已执行 | 若接管副本只有 100，重新读取仍可能得到 100 |
| 明确收到 NOREPLICAS | 当前命令在执行前被拒绝 | 本次 INCR 没有增加计数 |

例如 M 和 R1 已经从 100 递增到 101，但 M 的回复丢失。客户端重连新主 R1 后重发 INCR，会得到 102。读取超时不能据此确定服务端没有执行。GET 重试通常没有重复写入问题，但跨实例读取仍可能由 101 退回 100。具体请求重试策略取决于客户端库和业务语义。[客户端重连](https://redis.io/docs/latest/develop/reference/sentinel-clients/#handle-reconnections) · [故障时写入保留边界](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/#fundamental-things-to-know-about-sentinel-before-deploying)

### 4.2 写前限制与写后 WAIT

| 机制 | 检查时机和依据 | 条件未满足时 |
|---|---|---|
| `min-replicas-to-write 1`、`min-replicas-max-lag 5` | 写入前读取已维护的合格副本数 `repl_good_slaves_count`，要求至少为 1 | 返回 NOREPLICAS，拒绝当前写命令 |
| 同一连接执行 `INCR` 后调用 `WAIT 1 1000` | 等待至少一个副本确认到覆盖此前写入的复制偏移量，最长等待 1000 毫秒 | 超时返回实际确认数，已执行的 INCR 保留 |

M 刷新合格副本数时，统计状态为 ONLINE 且 `repl_ack_time` 距今不超过 5 秒的副本。部分重同步成功时，M 会先将该副本置为 ONLINE，把 `repl_ack_time` 设为当前时间并刷新计数。新连接可能还没发回第一条 ACK。平时即使 ACK 很新，确认的偏移量也可能落后。例如，M 允许执行 INCR 后复制链路立即断开，本次递增尚未复制，随后 `WAIT 1 1000` 超时可返回 0。将 min-replicas-to-write 设为 0 会关闭写前限制。[部分重同步时初始化计时](https://github.com/redis/redis/blob/8.10.3/src/replication.c#L1059-L1089) · [刷新和读取合格计数](https://github.com/redis/redis/blob/8.10.3/src/replication.c#L4798-L4823) · [写入前检查](https://github.com/redis/redis/blob/8.10.3/src/server.c#L4713-L4718) · [WAIT](https://redis.io/docs/latest/commands/wait/)

### 4.3 两种分区布局

以下假设 M 和潜在新主都配置至少一个合格副本才允许写入，左侧 M 与 R2 的复制保持正常。

| 分区布局 | 左侧行为 | 右侧行为 |
|---|---|---|
| 左侧 M、R2、S1、A；右侧 R1、S2、S3、B；quorum=2 | M 有 R2 持续回 ACK，A 可继续写 M | S2、S3 有多数票，可提升 R1。但 R1 没有合格从库，B 连上新主后写入仍会被 NOREPLICAS 拒绝 |
| 左侧 M、R2、S1、S3、A；右侧 R1、S2、B；quorum=2 | A 仍可写 M | S2 只有自己的下线判断，无法达到 ODOWN |
| 保持上一行布局，quorum 改为 1 | A 仍可写 M | S2 可达到 ODOWN，但只有一票，无法当选执行者 |

第一行中，假设分区前 counter=100，A 在左侧递增到 101，R2 已确认，而 R1 仍为 100。即使 A 的 WAIT 返回 1，确认副本也是 R2。实际新主是 R1，网络恢复、旧主及 R2 向 R1 对齐后，在没有额外写入的前提下最终都为 100。

另一种已讨论的布局是旧主与所有从库断开。M 察觉复制断连或 ACK 过期、合格计数刷新后，会拒绝新写入。若 M 身边始终有 R2 回 ACK，则写入限制可能持续满足。[官方分区示例](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/#example-2-basic-setup-with-three-boxes)

### 4.4 网络恢复时，哪一边决定主库

在表中右侧仅有 R1、S2、B 的布局下，S2 继续监控、尝试重连同伴和 M。quorum=1 时可以尝试选举，但等再久也需要足够票数才能当选。R1 保持从库角色，尝试重连 M。B 按主库模式查询仍得到 M，跨侧业务连接失败。

若 B 显式读取 R1，默认 `replica-serve-stale-data yes` 下可以得到旧数据。默认只读副本拒绝 INCR，返回 READONLY。配置为 `replica-serve-stale-data no` 时，上游断连期间普通 GET 也会被拒绝。[副本配置](https://github.com/redis/redis/blob/8.10.3/redis.conf#L621-L650)

跨侧网络恢复后，S2 重连同伴、重新收到 M 的有效回复、R1 恢复复制，这些事件的先后顺序会影响结果。以下沿用第 4.3 节的两种布局。

**右侧只有 S2，左侧两个哨兵一直能访问 M。** 分区持续期间，S2 单独无法当选。

| 恢复时的条件 | 结果 |
|---|---|
| quorum=2 | S2 始终凑不齐两份下线判断，无法启动切换。M 继续为主。 |
| quorum=1，S2 在没有进行中选举时已确认 M 健康 | S2 清除下线标记，失去发起下一轮选举的条件。M 继续为主。 |
| quorum=1，S2 仍在等待选票，先恢复了与同伴的连接 | 若 S2 在清除 SDOWN 前发出求票请求，同伴可在同一回复中报告“M 在线”并投票给 S2。若在选举超时前取得多数票，S2 仍可能继续切换。 |

前两行中，R1 按原配置向 M 请求 PSYNC，B 重连 M 且满足写入条件后可恢复写入。最后一行中的选票是在网络恢复后取得的。[求票条件](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L4752-L4773) · [同伴分别回复下线判断和选票](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L3996-L4015)

**右侧有 S2、S3。** 这一侧在分区期间已有足够票数，恢复时还要看切换已走到哪一步。

| 恢复时的阶段 | 结果 |
|---|---|
| 尚未发起切换，哨兵先确认 M 健康 | 下线标记清除，R1 按原配置与 M 续接复制。 |
| 已启动切换，尚未确认新主 | 已启动的状态机会继续按当前阶段检查条件。例如，执行者已经当选并选中 R1，即使随后清除了 M 的 ODOWN，仍可能继续提升 R1。 |
| 已确认 R1 升主并形成新配置 | 哨兵传播新配置，旧 M 和其他副本改为跟随 R1。第 4.3 节 `counter` 最终为 100 的例子采用这一结果。 |

ODOWN 是自动发起切换的条件。切换一旦启动，执行者按所处阶段处理选举、提升或副本重配置。[切换发起条件](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L5015-L5042) · [进行中的状态机](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L5374-L5395)

恢复方向由实际生效的主从配置决定。网络恢复本身不会把客户端先前失败的请求自动重放。[复制重连机制](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/) · [旧主和错误上游的纠正](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/#sentinel-reconfiguration-of-instances-outside-the-failover-procedure)

## 5. 执行哨兵故障与持久状态

### 5.1 执行者 S2 在不同时刻故障

| S2 故障时刻 | 剩余哨兵掌握的状态 | 后续处理 |
|---|---|---|
| 当选后，发出提升命令前 | M 仍下线，R1/R2 仍是副本 | 条件满足后重新选举，获胜者重新选择并提升副本 |
| R1 已执行提升，S2 尚未从 INFO 确认 | R1 实际是主库，S1/S3 的 mymaster 配置仍指向 M | 仅观察到 R1 自报 master 不会生成新配置。若 M 持续 ODOWN，条件满足时可以重新选举 |
| S2 已确认 R1 升主并成功保存新配置，其他哨兵尚未收到 | S2 的配置文件已记录 R1 和新的 config_epoch，S1/S3 仍记录 M | 若 S2 及时重启，可以从磁盘恢复这份配置并通过 HELLO 传播。若它持续离线，S1/S3 仍按旧视图判断能否另起选举 |
| 至少一个存活哨兵已采用新配置，其他副本尚未全部改好 | 该哨兵已经知道 R1 和较新的 config_epoch | 周期 HELLO 继续传播，日常上游检查在条件满足后修复剩余副本 |

第二种情况下，R1 改变了真实复制角色，INFO、ROLE 反映该变化。S1 持续查 INFO，可同时保存“R1 的 role_reported 为 master”和“mymaster 配置主库为 M”。观察者仅凭前一条信息不会直接生成新配置。执行者在本地标记了目标副本且正在 WAIT_PROMOTION，才在该确认路径中更新 config_epoch。

S2 确认提升后先更新 config_epoch、进入 RECONF_SLAVES 并保存配置，再加快下一次 HELLO 发布。源码中的 `crash-after-promotion` 故障点就在保存与加快发布之间。因而 S2 自己能够从磁盘恢复新地址，与其他哨兵已知新地址，是两个不同的时刻。[确认、保存与发布顺序](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L2685-L2709) · [写入配置文件的主库地址](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L2061-L2078)

重选由各哨兵自己的 ODOWN、进行中状态和重试间隔决定。S1 无须先确认 S2 已死亡。M 健康而单独 S2 宕机的场景，则没有主库故障需要处理。[角色观察与提升确认](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L2658-L2709) · [重新发起条件](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L5015-L5042) · [日常副本修复](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L2711-L2745)

### 5.2 哨兵自身暂停与 TILT

假设 M 正常，但 S1 所在虚拟机暂停 8 秒。恢复后 S1 的探测记录可能全部显得过期。每次定时处理开始时，哨兵检查距离上次调用的时间差，若为负或严格大于默认 2000 毫秒阈值，就进入 TILT。

TILT 期间继续连接和收集监控信息，暂缓本地下线判定及切换动作，对同伴询问返回否定的下线判断。默认连续约 30 秒无新的时间异常后退出，异常再次出现会推迟退出。S2、S3 仍按各自状态运行。[TILT 检查源码](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L5501-L5511) · [官方说明](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/#tilt-mode)

### 5.3 重启后如何记住轮次和配置

| 状态 | 含义与作用 |
|---|---|
| current_epoch | 哨兵已知的最大轮次，进程范围 |
| failover_epoch | 某次切换尝试采用的轮次，用于本轮执行和提升确认 |
| leader_epoch | 针对某个主库最后投票的轮次，保存后重启恢复，可阻止同轮再投新票 |
| config_epoch | 某个主库当前配置的版本，用于比较、采用和传播拓扑 |

配置文件保存主库地址、current_epoch、各主库的 leader_epoch/config_epoch、已发现节点等。第 8 轮选举开始时，配置版本仍可能为 7，提升确认后才采用新版本。

假设 S1 在第 8 轮投给 S2，状态已成功保存，再用该配置重启。S3 请求第 8 轮投票时，`leader_epoch < 请求 epoch` 不成立，因而拿不到新票。持久化的 leader_epoch 已足够阻止同轮重复投票，原候选者身份不必恢复。若 S1 已保存“R1、版本 8”，重启后收到“M、版本 7”也会保留较新配置。[投票检查与保存](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L4792-L4816) · [配置恢复](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L1918-L1941) · [配置版本比较](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L2949-L2969)

## 6. 认证与排障

### 6.1 每条连接分别认证

| 连接 | 认证和权限在哪里生效 |
|---|---|
| 应用 → 哨兵 | 哨兵上的查询账号与权限，凭据由应用提供 |
| 应用 → Redis | 目标 Redis 上的业务账号、命令和键权限 |
| 哨兵 → Redis | 哨兵配置 `sentinel auth-user/auth-pass`，目标 Redis 需允许监控、提升、重配置等操作 |
| 哨兵 → 同伴 | `sentinel sentinel-user/sentinel-pass` 配置对方哨兵认可的身份 |
| 从库 → 主库 | 从库配置 `masteruser/masterauth`，主库上的账号允许复制 |

R1 具备哨兵管理账号而缺少业务账号时，可能成功升主，应用也查询到地址并建立 TCP，但业务认证失败。PING、INFO、HELLO 等日常监控与发现权限均具备，但缺少提升命令权限时，监控可以正常，切换却卡在等待角色变化。R2 复制认证失败时，新主可能因合格副本不足而返回 NOREPLICAS。潜在主库和旧主都要按角色转换后的连接需求准备配置。[认证说明](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/#redis-access-control-list-authentication) · [复制认证配置](https://github.com/redis/redis/blob/8.10.3/redis.conf#L603-L619)

### 6.2 从查询、事件到业务错误

| 查询入口 | 观察内容 |
|---|---|
| SENTINEL MASTER mymaster | 当前哨兵记录的主库和下线标记 |
| SENTINEL SENTINELS mymaster | 已知哨兵列表和本地观察状态 |
| SENTINEL CKQUORUM mymaster | 当前可用哨兵数量是否满足 quorum 与多数派条件 |
| SENTINEL REPLICAS mymaster | 副本状态、优先级、进度等 |
| SENTINEL get-master-addr-by-name mymaster | 当前客户端会获得的主库地址 |
| Redis 上的 ROLE、INFO replication | 节点实际角色、上游、复制链路、偏移量、合格副本数量等 |

查询各哨兵可以比较不同视图。CKQUORUM 通过后，还需实际获得选票、找到合格副本并完成提升。INFO 中的 `min_slaves_good_slaves` 可用于观察启用写入限制时的合格副本数。[查询命令](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/#sentinel-commands) · [复制监控字段](https://redis.io/docs/latest/commands/info/#replication)

| 同一次尝试的日志进展 | 继续检查 |
|---|---|
| +sdown 后没有 +odown | 同伴是否也判断 M 下线，判断能否传来 |
| +try-failover 后没有 +elected-leader | 是否分票、是否够票、是否到达超时 |
| 已当选但没选中副本 | 候选是否被健康、时效、复制断开时间或 priority 条件排除 |
| 已选中 R1，但没有 +promoted-slave | 提升命令权限、命令执行、INFO 回复和实际角色 |
| 哨兵已返回 R1，业务仍失败 | 应用是否仍连旧 M，R1 地址是否可达，业务认证是否正确，是否收到 NOREPLICAS |

日志需关联主库名称、时间和 epoch。新主产生、其余副本追上、客户端恢复写入分别有自己的条件。[事件说明](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/#pubsub-messages) · [状态机源码](https://github.com/redis/redis/blob/8.10.3/src/sentinel.c#L5374-L5395)

## 7. 考察与纠正记录

| 题目 | 学习者回答 | 结论与补充 |
|---|---|---|
| 左侧 M、R2、S1、S3，右侧 R1、S2，quorum=2 | M 有健康从库可写，S2 无法达到 ODOWN，不能提升 R1 | 判断正确 |
| 同样分区把 quorum 改为 1，能否 ODOWN、能否当选 | 仅答“可以”，没有分别回答两个问题 | 随后明确补充 ODOWN 可以，但三哨兵至少两票，无法当选。未独立复述 |
| R1 升主，R2 复制认证失败，最少副本数为 1 或 0 | 正确判断拒写或可写，但原因解释为从库尚未执行当前写入成功 | 补充写前读取已维护的合格副本计数，写后 WAIT 按本连接的目标复制偏移量统计 ACK。未独立复述 |
| R1 升主，S2 未确认传播就故障，ROLE 与哨兵地址为何不同 | 正确理解实际角色与 S1 记录不同；误以为其他哨兵没有查询 INFO，等待上一轮超时后重选 | 补充持续查询会更新角色等观察记录，但不会仅凭 role:master 改写主库配置；重选检查各哨兵本地状态和重试间隔。未独立复述 |

学习者还追问了每个哨兵的连接数量、客户端是否断开哨兵连接、分票及新 epoch、监控方法、分区前后右侧运行、客户端是否连接从库、S1 怎样知道该发送 HELLO。这些均已解释，尚未逐项独立考察。

M 与 S2 先后故障时，仍记录旧 M 的哨兵可在本地条件满足后重选。已有存活哨兵采用新配置时，它可以继续传播配置，其他副本随后向新主对齐。若仅 S2 故障且 M 健康，其余哨兵继续监控。S1 收到较新配置后，下一次按周期发送的 HELLO 会带上新地址和配置版本。原执行者确认提升时还会加快下一次发布。

## 8. 续接

Sentinel 核心主线已讲，部分机制已考察。保留 quorum 与多数票、写前限制与 WAIT、角色上报与配置确认三项复述回访。实际部署、抓包、客户端库具体策略、地址宣告和 NAT 细节未实测或系统展开。

后续对话已完成 Cluster 核心主线讲解及部分考察，整理于[第五篇：Cluster 分片、路由与故障恢复](./2026-11-19_Redis学习_05_Cluster分片路由与故障恢复.md)。当前按学习者要求暂停，下次从 Cluster、Sentinel、客户端分片的方案对比继续，再补必要工程边界；不从 Cluster 开篇重讲。具体考察纠正和续接范围见第五篇第 13～14 节，Sentinel 以上三项复述回访仍保留。
