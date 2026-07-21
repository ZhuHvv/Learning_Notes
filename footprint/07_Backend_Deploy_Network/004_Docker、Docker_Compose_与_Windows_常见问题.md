# Docker、Docker Compose 与 Windows 常见问题

> 所属分类：Backend / Deploy / Network  
> 修订版本：v9 昨日今日增量版  
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

