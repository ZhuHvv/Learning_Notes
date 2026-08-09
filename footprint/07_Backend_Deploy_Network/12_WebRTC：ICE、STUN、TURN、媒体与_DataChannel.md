# 07.12 WebRTC：ICE、STUN、TURN、媒体与 DataChannel

## 1. 总体性概念

WebRTC（Web Real-Time Communication）不是一个单独的网络协议，而是一组浏览器 API、协商机制和网络协议，用于低延迟音视频、屏幕共享和点对点数据通信。

```text
WebRTC
├── 寻找可用网络路径：ICE
│   ├── STUN
│   └── TURN
├── 描述和协商能力：SDP Offer / Answer
├── 传输音视频：RTP / RTCP / SRTP
├── 传输普通数据：SCTP over DTLS
└── 建立安全通道：DTLS / DTLS-SRTP
```

它的目标是让两个端点尽可能直接通信，但“P2P 优先”不等于“不需要服务器”。真实系统通常至少需要信令服务和 STUN；网络无法直连时还要通过 TURN 中继流量。

## 2. WebRTC 架构：控制面与数据面

```text
                  Signaling Server
                  ↑              ↑
            Offer/Answer      ICE Candidate
                  │              │
               Client A       Client B
                   ╲            ╱
                    ╲          ╱
                 直连或经 TURN 的
                 WebRTC 数据通道
```

- **控制面**：双方借助应用自建的信令通道交换 SDP 和 ICE Candidate；
- **数据面**：ICE 选出路径后，媒体或 DataChannel 通过该路径持续传输；
- **中继回退**：直连失败时，TURN Server 位于数据面中转发实际流量。

普通 HTTP 请求通常由客户端访问中心服务器；WebRTC 则先借助服务器完成发现和协商，再尽可能建立端点间低延迟通道。

## 3. WebRTC 不规定信令协议

双方在连接前要交换：

- 支持的音视频编码与媒体参数；
- ICE 用户名、密码和网络候选地址；
- DTLS 指纹等安全参数；
- SDP Offer / Answer。

WebRTC 规定要交换哪些连接信息，但不规定这些信息必须通过哪种信令协议发送。应用可以选择：

```text
WebSocket
HTTP
SSE + POST
MQTT
自定义 TCP 协议
甚至人工复制 SDP
```

典型流程：

```text
Client A                    Signaling Server                 Client B
   │── SDP Offer ─────────────────────────────────────────────>│
   │<──────────────────────────────────────────── SDP Answer ──│
   │── ICE Candidate ─────────────────────────────────────────>│
   │<──────────────────────────────────────── ICE Candidate ───│
```

信令服务器只负责把这些消息送到对端，并不需要理解或转发后续媒体。

## 4. ICE、STUN 与 TURN 的分工

### 4.1 ICE：收集候选并选择可用路径

浏览器通常位于 NAT 或防火墙后，没有可被对端直接访问的固定公网 `IP:port`。ICE（Interactive Connectivity Establishment）会收集多类 Candidate，并对候选组合执行连通性检查。

```text
host candidate   ：本地网卡地址，例如 192.168.1.10:50000
srflx candidate  ：STUN 观察到的 NAT 公网映射地址
relay candidate  ：TURN Server 分配的中继地址
```

```text
A.host  ↔ B.host
A.host  ↔ B.srflx
A.srflx ↔ B.srflx
A.relay ↔ B.relay
       ...
```

ICE 不是一个固定的“穿透服务器”，而是候选收集、交换、连通性检查和路径选择框架。

### 4.2 STUN：发现公网映射

客户端知道自己的私网地址，却通常不知道 NAT 从公网看见的地址。STUN Server 会把观察结果告诉客户端：

```text
Client：192.168.1.10:5000
    │ STUN Binding Request
    ▼
STUN Server：我看到你是 203.0.113.10:62001
    │
    └── 形成 server-reflexive candidate
```

STUN 主要帮助发现映射，不负责在后续会话中持续转发媒体。

### 4.3 TURN：直连失败时中继

对称 NAT、严格防火墙或企业网络可能使候选对都无法直连，此时使用 TURN：

```text
优先：Client A ───────── Client B

回退：Client A ─ TURN ─ Client B
```

TURN 转发真实媒体或 DataChannel 数据，会带来服务器带宽、成本和额外延迟，但能显著提高连接成功率。因此生产 WebRTC 系统不能只配置 STUN 后假定所有用户都能 P2P。

## 5. SDP 与 Offer / Answer

SDP（Session Description Protocol）用于描述会话能力和参数，例如媒体类型、编解码器、网络与安全信息。它是“会话描述”，不是负责发送这些描述的信令通道。

```text
A.createOffer()
    ↓
SDP Offer ──应用信令──> B
                         ↓
                    B.createAnswer()
                         ↓
A <────应用信令──── SDP Answer
```

双方还可在发现新 Candidate 时逐个交换，即 Trickle ICE；无需等全部候选收集完成才发送 SDP。

## 6. 音视频协议栈

WebRTC 音视频主要使用 RTP / RTCP，并以 SRTP 保护媒体：

```text
Audio / Video
      ↓
RTP + RTCP
      ↓
SRTP / SRTCP
      ↓
ICE 选出的 UDP 路径
```

- RTP 承载媒体包；
- RTCP 传递质量反馈、统计和同步信息；
- SRTP / SRTCP 提供加密、完整性和重放保护；
- DTLS-SRTP 用于协商媒体加密密钥。

实时媒体通常偏向 UDP，因为它更重视低延迟和及时性。丢失一个过期视频包往往比等待重传并阻塞后续帧更可接受；这不代表 WebRTC 不做拥塞控制、丢包反馈或恢复，只是目标不同于“所有字节必须按序到达”的文件传输。

## 7. RTCDataChannel 协议栈

`RTCDataChannel` 用于聊天、协同编辑、游戏状态、P2P 文件和远程控制等非媒体数据：

```javascript
const channel = peerConnection.createDataChannel("chat");
```

其主要协议栈是：

```text
Application Data
      ↓
SCTP
      ↓
DTLS
      ↓
ICE / UDP
```

SCTP 提供多 Stream，并支持：

- 有序或无序交付；
- 可靠或部分可靠传输；
- 多个逻辑数据通道共享同一关联。

因此 DataChannel 不等同于 WebSocket，也不是“把普通 TCP 暴露给浏览器”。应用可以按场景选择顺序与可靠性策略。

## 8. 一次完整建连流程

### 8.1 创建 PeerConnection

```javascript
const pc = new RTCPeerConnection({
  iceServers: [
    { urls: "stun:stun.example.com" },
    {
      urls: "turn:turn.example.com",
      username: "user",
      credential: "credential"
    }
  ]
});
```

### 8.2 A 创建并发送 Offer

```javascript
const offer = await pc.createOffer();
await pc.setLocalDescription(offer);
signaling.send({ type: "offer", sdp: pc.localDescription });
```

### 8.3 B 设置 Offer 并返回 Answer

```javascript
await pc.setRemoteDescription(receivedOffer);
const answer = await pc.createAnswer();
await pc.setLocalDescription(answer);
signaling.send({ type: "answer", sdp: pc.localDescription });
```

A 收到后执行：

```javascript
await pc.setRemoteDescription(receivedAnswer);
```

### 8.4 交换 ICE Candidate

```javascript
pc.onicecandidate = event => {
  if (event.candidate) {
    signaling.send({ type: "candidate", candidate: event.candidate });
  }
};
```

收到对方候选后：

```javascript
await pc.addIceCandidate(receivedCandidate);
```

### 8.5 连通性检查、DTLS 与数据传输

```text
收集 host / srflx / relay candidates
    ↓
交换 candidates
    ↓
ICE connectivity checks
    ↓
选出直连或 TURN 路径
    ↓
DTLS handshake
    ↓
媒体：SRTP
数据：SCTP over DTLS
```

## 9. 分层理解

```text
┌──────────────────────────────────┐
│ Web Application / Browser API    │
│ RTCPeerConnection / MediaStream  │
├──────────────────────────────────┤
│ Signaling：应用自选协议           │
│ SDP Offer / Answer + Candidates  │
├────────────────┬─────────────────┤
│ Media          │ DataChannel     │
│ RTP/RTCP/SRTP  │ SCTP            │
├────────────────┼─────────────────┤
│ DTLS-SRTP      │ DTLS            │
├────────────────┴─────────────────┤
│ ICE / STUN / TURN                │
├──────────────────────────────────┤
│ UDP / IP                         │
└──────────────────────────────────┘
```

所以不宜简单说“WebRTC 是应用层协议”。它更像一套建立实时通信的标准体系：API 负责给应用使用，SDP 负责描述，ICE/STUN/TURN 负责找路，SRTP 和 SCTP/DTLS 分别负责媒体与数据。

## 10. 与 HTTP、SSE、WebSocket 的区别

| 技术 | 主要模型 | 典型场景 |
|---|---|---|
| HTTP 请求/响应 | Client 请求，Server 返回 | 普通 API、一次性数据 |
| SSE | Server→Client 文本事件流 | token、进度、通知 |
| WebSocket | 经服务器建立全双工消息连接 | 聊天、控制、应用事件 |
| WebRTC | 先协商实时通道，再直连或中继媒体/数据 | 音视频、屏幕共享、P2P 数据 |

WebSocket 常被用作 WebRTC 信令通道，但它不是 WebRTC 媒体通道。WebRTC 也可以通过 HTTP、SSE+POST 或其它方式完成信令。

## 11. 常见误区与排查思路

- **WebRTC 是一个像 HTTP 一样的单一协议。** 它是 API 与多种协议组成的体系。
- **WebRTC 完全不需要服务器。** 信令和 STUN 通常必需，TURN 是重要回退。
- **STUN 会中继媒体。** STUN 主要发现映射；TURN 才负责中继。
- **信令必须用 WebSocket。** WebRTC 不规定信令传输协议。
- **交换 SDP 后一定能直连。** 还要交换 Candidate、完成 ICE 检查和 DTLS 握手。
- **DataChannel 就是 WebSocket 或 TCP。** 它主要是 SCTP over DTLS over ICE/UDP，并可配置顺序和可靠性。
- **使用 UDP 就不安全。** WebRTC 要求对媒体和数据建立加密保护。

排查顺序：

```text
信令消息是否完整到达
→ local/remote description 是否设置成功
→ ICE Candidate 是否持续产生并交换
→ STUN/TURN 凭证和网络端口是否可用
→ ICE state 是否进入 connected/completed
→ DTLS state 是否成功
→ track / transceiver / DataChannel 状态是否正确
→ 统计中是否存在丢包、抖动、码率或 TURN 中继瓶颈
```

## 12. 你在讨论中的理解推进

WebRTC 应按“信令、找路、安全、媒体、普通数据”拆开理解，而不是把它当成一个单独协议。最关键的边界是：信令只交换建连信息；ICE 在 STUN/TURN 帮助下选路；连接建立后，媒体走 SRTP，DataChannel 走 SCTP/DTLS。

## 13. 关联知识点

- `07_HTTP_Streaming、SSE、WebSocket_与_gRPC_Streaming.md`：HTTP 流、SSE 和 WebSocket；
- `03_正向代理与反向代理.md`：中间网络节点与转发；
- `06_Prometheus、Grafana、OpenTelemetry_与日志.md`：连接质量指标与可观测性。

## 14. 参考资料

- [MDN：WebRTC API](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API)
- [W3C：WebRTC 1.0](https://www.w3.org/TR/webrtc/)
- [RFC 8445：ICE](https://www.rfc-editor.org/rfc/rfc8445)
- [RFC 8489：STUN](https://www.rfc-editor.org/rfc/rfc8489)
- [RFC 8656：TURN](https://www.rfc-editor.org/rfc/rfc8656)
- [RFC 8829：JSEP Offer/Answer](https://www.rfc-editor.org/rfc/rfc8829)
- [RFC 8831：WebRTC Data Channels](https://www.rfc-editor.org/rfc/rfc8831)
