# Kubernetes、服务发现与弹性部署

> 所属分类：Backend / Deploy / Network  
> 修订版本：v11  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Kubernetes 编排容器集群，提供部署、服务发现、滚动更新、扩缩容、健康检查和配置管理。


## 2. 原理性解释

- Pod 是最小调度单元。
- Deployment 管理副本和滚动更新。
- Service 提供稳定访问入口。
- ConfigMap/Secret 管配置。
- HPA 可自动扩缩容。

### Kubernetes 解决的是容器编排和期望状态维护

K8s 不只是“启动很多容器”，而是通过控制器不断让实际状态接近期望状态。Deployment 描述副本数，Service 提供稳定访问入口，Ingress 处理外部 HTTP 流量，ConfigMap/Secret 管配置，HPA 做弹性扩缩容。

```text
Desired replicas = 3
Controller 发现只剩 2 个 Pod → 创建新 Pod
```

## 3. 机制流程

1. 创建 Deployment。
2. 调度 Pod。
3. Service 暴露。
4. Ingress 接入外部。
5. 监控触发扩缩容。

### 服务发现流程

```text
Pod 启动并带 labels
  ↓
Service selector 匹配 labels
  ↓
生成稳定 ClusterIP/DNS
  ↓
其它服务通过 service name 访问
  ↓
kube-proxy/iptables/ipvs 转发到后端 Pod
```

学习 K8s 时先掌握 Pod、Deployment、Service、Ingress，再看配置、存储、监控和灰度发布。

## 4. 类比理解

Compose 像本地设备清单，K8s 像工厂调度系统。

## 5. 应用举例 / 代码或伪代码

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  replicas: 3
---
kind: Service
spec:
  selector:
    app: api
```

## 6. 你在讨论中的理解推进

成熟后端技术栈至少应理解 Pod、Deployment、Service、Ingress 的关系。

## 10. 更细的工程拆解

**Kubernetes、服务发现与弹性部署** 需要放在“请求从客户端到服务再到下游依赖”的完整路径中看：

1. **入口层**：浏览器、客户端、代理、负载均衡、网关。
2. **服务层**：HTTP/RPC Handler、业务逻辑、连接池、缓存、数据库、MQ。
3. **运行层**：容器、Compose/Kubernetes、环境变量、挂载卷、网络策略。
4. **观测层**：日志、指标、trace、健康检查、告警。

### 最小部署/排障清单

```bash
# 注意：K8s 1.24 起已移除 dockershim，节点运行时普遍为 containerd，
# 节点上的 docker CLI 看不到 Pod 容器，排障应使用 kubectl。

# 1. 看 Pod 是否运行、是否反复重启
kubectl get pods -n <namespace>

# 2. 看调度/拉镜像/探针等事件
kubectl describe pod <pod> -n <namespace>

# 3. 看服务日志（--previous 可看上次崩溃的日志）
kubectl logs <pod> -n <namespace>

# 4. 看 Service 是否匹配到后端 Pod
kubectl get endpoints <service> -n <namespace>

# 5. 用 curl 验证入口
curl -v http://localhost:8080/health
```

### 工程落地要点

- 网络问题要分层排查：DNS、端口、代理、协议、认证、应用日志。
- Docker/Compose 里路径、端口、环境变量最容易出错，尤其 Windows 路径要注意冒号和绝对路径。
- 只要是线上服务，就必须有健康检查、结构化日志和关键指标，否则出错时只能猜。

## 11. 针对 `Kubernetes、服务发现与弹性部署` 的专项排查

后端部署和网络问题必须分层定位。检查 **Kubernetes、服务发现与弹性部署** 时：

- **客户端层**：请求地址、协议、端口、DNS 是否正确。
- **代理层**：正向/反向代理、网关、路径重写、header 转发是否正确。
- **服务层**：进程是否启动、端口是否监听、健康检查是否通过。
- **依赖层**：数据库、Redis、MQ、外部 API 是否可达。
- **观测层**：日志、指标、trace 是否能定位到失败点。

### 小型练习

```bash
# 练习：为 Kubernetes、服务发现与弹性部署 写一条最小排障链
kubectl get pods
curl -v http://<host>:<port>/health
kubectl logs <pod>
```

### 面试表达模板

回答 `Kubernetes、服务发现与弹性部署` 时，按“流量入口 → 服务处理 → 下游依赖 → 部署运行 → 观测排障”描述，能体现整体后端视角。

