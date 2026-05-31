# Prometheus、Grafana、OpenTelemetry 与日志

> 所属分类：Backend / Deploy / Network  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

可观测性由指标、日志、链路追踪组成；Prometheus 采指标，Grafana 展示，OpenTelemetry 统一埋点。


## 2. 原理性解释

- 指标回答系统怎么样。
- 日志回答发生了什么。
- Trace 回答请求经过哪里。
- AI 应用还要记录 token、模型、检索和工具调用成本。

### 可观测性要同时覆盖 metrics、logs、traces

Prometheus 负责拉取指标，Grafana 展示仪表盘，OpenTelemetry 提供统一埋点标准，日志记录离散事件，trace 串联一次请求跨服务调用链。只看日志会缺少趋势，只看指标会缺少上下文，只看 trace 会缺少整体健康度。

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

## 7. 常见误区与排查思路

- 只背名词，不知道它在完整链路中的输入、输出和失败模式。
- 只看正常路径，忽略异常、超时、权限、重复和可观测性。
- 把相邻概念混用，导致设计或排查时定位错误。

## 8. 关联知识点

- 回到 00_总体索引.md 查看上下游知识点。
- 结合 00_总体知识网络图.md 理解跨模块关系。

## 9. 复习检查问题

- 它解决的核心问题是什么？
- 它的输入、输出和中间状态分别是什么？
- 它在真实项目中最容易出错的边界条件是什么？
- 它和上游、下游知识点如何连接？

## 10. 更细的工程拆解

**Prometheus、Grafana、OpenTelemetry 与日志** 需要放在“请求从客户端到服务再到下游依赖”的完整路径中看：

1. **入口层**：浏览器、客户端、代理、负载均衡、网关。
2. **服务层**：HTTP/RPC Handler、业务逻辑、连接池、缓存、数据库、MQ。
3. **运行层**：容器、Compose/Kubernetes、环境变量、挂载卷、网络策略。
4. **观测层**：日志、指标、trace、健康检查、告警。

### 最小部署/排障清单

```bash
# 1. 看容器是否运行
docker ps

# 2. 看端口是否监听
netstat -ano | findstr 9092

# 3. 看服务日志
docker logs <container>

# 4. 用 curl 验证入口
curl -v http://localhost:8080/health
```

### 工程落地要点

- 网络问题要分层排查：DNS、端口、代理、协议、认证、应用日志。
- Docker/Compose 里路径、端口、环境变量最容易出错，尤其 Windows 路径要注意冒号和绝对路径。
- 只要是线上服务，就必须有健康检查、结构化日志和关键指标，否则出错时只能猜。

## 11. 针对 `Prometheus、Grafana、OpenTelemetry 与日志` 的专项排查

后端部署和网络问题必须分层定位。检查 **Prometheus、Grafana、OpenTelemetry 与日志** 时：

- **客户端层**：请求地址、协议、端口、DNS 是否正确。
- **代理层**：正向/反向代理、网关、路径重写、header 转发是否正确。
- **服务层**：进程是否启动、端口是否监听、健康检查是否通过。
- **依赖层**：数据库、Redis、MQ、外部 API 是否可达。
- **观测层**：日志、指标、trace 是否能定位到失败点。

### 小型练习

```bash
# 练习：为 Prometheus、Grafana、OpenTelemetry 与日志 写一条最小排障链
ping <host>
curl -v http://<host>:<port>/health
docker logs <container>
```

### 面试表达模板

回答 `Prometheus、Grafana、OpenTelemetry 与日志` 时，按“流量入口 → 服务处理 → 下游依赖 → 部署运行 → 观测排障”描述，能体现整体后端视角。

## 12. 本知识点的边界与复习建议

**Prometheus、Grafana、OpenTelemetry 与日志** 的学习边界可以这样把握：先能用自己的话解释它解决的问题，再能画出输入、处理、输出三段流程，最后能写出一个最小代码或命令例子。复习时不要把它和相邻知识点混在一起：相邻知识点通常负责上游准备、下游消费或异常处理，而本文件只保留与 **Prometheus、Grafana、OpenTelemetry 与日志** 直接相关的机制。

建议你复习时做三件事：

1. **复述定义**：不用术语堆砌，说明它为什么出现。
2. **画流程图**：至少标出输入、核心机制、输出、失败点。
3. **写最小例子**：哪怕只是伪代码，也要体现真实项目中会怎样使用。

如果之后继续扩展本知识库，可以在本文件下追加“项目踩坑记录”和“面试问答”，但不要把无关项目经历混入 **Prometheus、Grafana、OpenTelemetry 与日志** 的原理解释中。
