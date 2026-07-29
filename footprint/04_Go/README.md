# Go 学习目录

按文件编号顺序阅读。编号同时表达前置关系和难度变化：基础语义 → Web 工程 → 并发 → Runtime → RPC → 流式与 AI 应用。

## 01｜语言与工程基础

- [001 Go Module、包与导入路径](001_Go_Module、包与导入路径.md)
- [002 Go 接口、方法集与指针接收器](002_Go_接口、方法集与指针接收器.md)
- [003 Go 错误处理：error、panic 与 recover](003_Go_错误处理：error、panic_与_recover.md)

## 02｜Web 工程

- [004 Gin Handler：闭包与依赖注入](004_Gin_Handler：闭包与依赖注入.md)
- [005 Gin Middleware：BasicAuth、Session 与 Cookie](005_Gin_Middleware：BasicAuth、Session_与_Cookie.md)
- [006 GoFrame g.Meta：声明式路由绑定](006_GoFrame_g.Meta：声明式路由绑定.md)

## 03｜并发模型

- [007 Go 并发模型：goroutine、channel、select 与 Context](007_Go_并发模型：goroutine、channel、select_与_Context.md)
- [008 Goroutine：数量、调度与性能边界](008_Goroutine：数量、调度与性能边界.md)
- [009 Channel：关闭、方向限制与 select 读就绪](009_Channel：关闭、方向限制与_select_读就绪.md)
- [010 Go Context：请求取消、超时与值传递](010_Go_Context：请求取消、超时与值传递.md)
- [011 sync.Mutex：Lock、TryLock 与锁模型](011_sync.Mutex：Lock、TryLock_与锁模型.md)

## 04｜Runtime 与内存

- [012 Go 逃逸分析、闭包与内存泄漏](012_Go_逃逸分析、闭包与内存泄漏.md)
- [013 Go 内存分配器：mcache、mcentral、mheap 与 mspan](013_Go_内存分配器：mcache、mcentral、mheap_与_mspan.md)
- [014 Go GC：三色标记、混合写屏障与 Green Tea](014_Go_GC：三色标记、混合写屏障与_Green_Tea.md)

## 05｜Protobuf 与 gRPC

- [015 Protobuf Go 代码生成：go_package、输出路径与文件组织](015_Protobuf_Go_代码生成：go_package、输出路径与文件组织.md)
- [016 gRPC 服务注册：RegisterServer、UnimplementedServer 与接口实现](016_gRPC_服务注册：RegisterServer、UnimplementedServer_与接口实现.md)

## 06｜流式与 AI 应用

- [017 Go SSE：text/event-stream 与流式响应](017_Go_SSE：text_event-stream_与流式响应.md)
- [018 Eino：RAG、Graph 与 Agent 编排](018_Eino：RAG、Graph_与_Agent_编排.md)

## 附录

- [通用学习与排查方法](附_通用学习与排查方法.md)
