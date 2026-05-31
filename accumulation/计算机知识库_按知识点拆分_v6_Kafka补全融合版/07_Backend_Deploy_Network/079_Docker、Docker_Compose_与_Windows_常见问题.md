# Docker、Docker Compose 与 Windows 常见问题

> 所属分类：Backend / Deploy / Network  
> 修订版本：v6 Kafka 补全融合版  
> 质量要求：本文件只解释本知识点，不复用其他知识点的原理段；示例尽量给出代码、伪代码、命令或配置。

## 1. 总体性概念

Docker 打包运行环境，Compose 编排多容器；Windows 常见问题集中在 WSL/Hyper-V、路径挂载、权限和命令版本。


## 2. 原理性解释

- 镜像是模板，容器是实例。
- volume 持久化数据。
- Compose v2 是 `docker compose`。
- 容器内 localhost 指向容器自己。
- Windows 盘符路径要注意冒号。

### Docker 的核心是镜像、容器、网络、卷

镜像是只读模板，容器是镜像运行实例，volume 用于持久化数据，network 用于容器间通信。Docker Compose 则用 YAML 描述多容器应用。Windows 下常见问题集中在虚拟化、WSL2、权限、路径格式和 Docker Desktop 安装策略。

```bash
docker compose up -d
docker logs -f service_name
```

## 3. 机制流程

1. 写 Dockerfile。
2. 构建镜像。
3. 写 compose。
4. 启动并看 logs。
5. exec 进入容器调试。

### Compose 启动排查流程

```text
检查 Docker Desktop/Engine 是否运行
  ↓
检查 compose 文件版本和缩进
  ↓
检查端口映射是否冲突
  ↓
检查 volume 路径格式
  ↓
启动并查看 logs
```

错误信息通常已经指出方向：volume path、port bind、DNS resolution、permission denied、image pull failure 要分别处理。

## 4. 类比理解

Docker 是集装箱，Compose 是多集装箱启动清单。

## 5. 应用举例 / 代码或伪代码

```bash
docker compose up -d
docker compose logs -f kafka
docker exec -it kafka bash
docker compose down -v
```

## 6. 你在讨论中的理解推进

你遇到 Docker Desktop、compose、Kafka volume 问题；排查要看系统虚拟化、路径和命令版本。

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

**Docker、Docker Compose 与 Windows 常见问题** 需要放在“请求从客户端到服务再到下游依赖”的完整路径中看：

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

## 11. 针对 `Docker、Docker Compose 与 Windows 常见问题` 的专项排查

后端部署和网络问题必须分层定位。检查 **Docker、Docker Compose 与 Windows 常见问题** 时：

- **客户端层**：请求地址、协议、端口、DNS 是否正确。
- **代理层**：正向/反向代理、网关、路径重写、header 转发是否正确。
- **服务层**：进程是否启动、端口是否监听、健康检查是否通过。
- **依赖层**：数据库、Redis、MQ、外部 API 是否可达。
- **观测层**：日志、指标、trace 是否能定位到失败点。

### 小型练习

```bash
# 练习：为 Docker、Docker Compose 与 Windows 常见问题 写一条最小排障链
ping <host>
curl -v http://<host>:<port>/health
docker logs <container>
```

### 面试表达模板

回答 `Docker、Docker Compose 与 Windows 常见问题` 时，按“流量入口 → 服务处理 → 下游依赖 → 部署运行 → 观测排障”描述，能体现整体后端视角。

## 12. 本知识点的边界与复习建议

**Docker、Docker Compose 与 Windows 常见问题** 的学习边界可以这样把握：先能用自己的话解释它解决的问题，再能画出输入、处理、输出三段流程，最后能写出一个最小代码或命令例子。复习时不要把它和相邻知识点混在一起：相邻知识点通常负责上游准备、下游消费或异常处理，而本文件只保留与 **Docker、Docker Compose 与 Windows 常见问题** 直接相关的机制。

建议你复习时做三件事：

1. **复述定义**：不用术语堆砌，说明它为什么出现。
2. **画流程图**：至少标出输入、核心机制、输出、失败点。
3. **写最小例子**：哪怕只是伪代码，也要体现真实项目中会怎样使用。

如果之后继续扩展本知识库，可以在本文件下追加“项目踩坑记录”和“面试问答”，但不要把无关项目经历混入 **Docker、Docker Compose 与 Windows 常见问题** 的原理解释中。
