# 07.06 Prometheus、Grafana、OpenTelemetry 与日志

## 1. 总体性概念

可观测性由指标、日志、链路追踪组成；Prometheus 采指标，Grafana 展示，OpenTelemetry 统一埋点。


## 2. 原理性解释

- 指标回答系统怎么样。
- 日志回答发生了什么。
- Trace 回答请求经过哪里。
- AI 应用还要记录 token、模型、检索和工具调用成本。

### 可观测性要同时覆盖 metrics、logs、traces

Prometheus 负责拉取指标，Grafana 展示仪表盘，OpenTelemetry 提供统一埋点标准，日志记录离散事件，trace 串联一次请求跨服务调用链。现状与数据通路：OTel 三信号（traces/metrics/logs）规范均已稳定，Prometheus 3.x 原生支持 OTLP 接收，"应用内 OTel SDK → OTLP → Prometheus/Grafana（或经 OTel Collector 中转）"是当前的标准组合。只看日志会缺少趋势，只看指标会缺少上下文，只看 trace 会缺少整体健康度。

```text
Metrics: 延迟、QPS、错误率
Logs: 具体错误内容
Traces: 请求经过哪些服务和耗时
```

## 3. 机制流程

1. 暴露 metrics。
2. Prometheus scrape。
3. Grafana 展示。
4. 日志记录细节。
5. trace 串联调用链。

### 后端监控流程

```text
服务暴露 /metrics
  ↓
Prometheus 定时 scrape
  ↓
Grafana 查询 PromQL 展示
  ↓
Alertmanager 根据规则告警
```

Agent/RAG 服务还应记录：模型延迟、token 数、检索 topK 命中、工具调用次数、失败原因和用户取消率。

## 4. 类比理解

指标是仪表盘，日志是行车记录仪，trace 是 GPS 轨迹。

## 5. 应用举例 / 代码或伪代码

```text
http_request_duration_seconds{path="/chat",status="200"} 0.42
llm_prompt_tokens{model="x"} 1200
retrieval_top_k 8
```

## 6. 你在讨论中的理解推进

你提过 Prometheus 9090 和 Agent 日志；开发日志应升级为生产可观测性闭环。
