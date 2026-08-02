# Redis 特殊类型：HyperLogLog、Bitmap、Geo、Stream

## 1. 总体性概念

Redis 特殊类型包括 HyperLogLog、Bitmap、Geo、Stream，分别适合基数估算、位状态、地理位置和追加日志。

从底层实现看，它们大多不是全新的数据类型：Bitmap 与 HyperLogLog 底层都是 String（前者靠位操作，后者是特殊编码的字符串），Geo 底层是 ZSet（有序集合），只有 Stream 是独立的数据类型。


## 2. 原理性解释

- HyperLogLog 内存小但有误差。
- Bitmap 用 bit 表达布尔状态。
- Geo 支持附近查询。
- Stream 支持消费组和消息日志。

### 特殊类型是对常见统计/空间/流场景的高效封装

HyperLogLog 用近似算法统计基数，适合 UV 这种允许小误差的场景；Bitmap 用位表示布尔状态，适合签到；Geo 基于有序集合编码地理位置；Stream 是 Redis 内置的追加日志结构，适合轻量消息流。

```bash
PFADD uv:2026-05-30 user1 user2
PFCOUNT uv:2026-05-30
```

## 3. 机制流程

1. 识别需求。
2. 选择结构。
3. 写入数据。
4. 用专门命令查询。

### 选用流程

```text
统计去重人数但不需要精确名单 → HyperLogLog
大量用户是否签到/在线 → Bitmap
附近的人/门店距离 → Geo
需要消费组和消息 ID → Stream
```

不要用 Set 硬扛所有去重统计；如果只需要基数，HyperLogLog 内存优势很明显。

## 4. 类比理解

HLL 是估算尺，Bitmap 是打卡表，Geo 是地图，Stream 是流水账。

## 5. 应用举例 / 代码或伪代码

```bash
PFADD uv:today u1 u2
SETBIT signin:u1 129 1
GEOADD shops 116.4 39.9 shopA
XADD orders * user u1 amount 99
```

## 6. 你在讨论中的理解推进

你专门问过 HyperLogLog，这里扩展到特殊类型的选型。
