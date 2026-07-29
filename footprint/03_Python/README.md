# Python：基础、数据处理、异步与 FastAPI

本目录按前置知识组织为一条由浅入深的学习主线。编号越大，越依赖前面的语言、数据模型和异步知识。

主线知识点文件数：14；排查附录：1。

## 第一阶段：运行环境与 Python 基础

1. [Conda、pip、Python 路径与包导入](001_Conda、pip、Python_路径与包导入.md)——入门：先保证解释器、pip、IDE 和包导入来自同一环境。
2. [Python 标准输入、split、map 与 range](002_Python_标准输入、split、map_与_range.md)——入门：理解文本输入、转换、惰性迭代和半开区间。
3. [可变默认参数、容器修改与复制语义](003_可变默认参数、容器修改与复制语义.md)——基础：进入 Python 对象身份、原地修改和共享状态。
4. [dataclass、TypedDict 与 Pydantic](004_dataclass、TypedDict_与_Pydantic.md)——基础到中级：区分静态类型、数据对象和运行时验证。

## 第二阶段：结构化数据与实验分析

5. [JSON、XML 与正则提取](005_JSON、XML_与正则提取.md)——中级：学习序列化、受控提取、容错和分层校验。
6. [pandas 与实验日志数据处理](006_pandas_与实验日志数据处理.md)——中级：把 JSONL 日志整理为可比较的实验指标。

## 第三阶段：异步执行模型

7. [async、await 与协程调度](007_async、await_与协程调度.md)——中级：建立 coroutine、Task、事件循环和阻塞点的基础模型。
8. [Task 聚合、取消、超时与 asyncio.wait](008_Task_聚合、取消、超时与_asyncio.wait.md)——中级到进阶：处理任务结果、异常、FIRST_COMPLETED 和取消清理。
9. [Semaphore、Queue 与异步背压](009_Semaphore、Queue_与异步背压.md)——进阶：区分并发度、QPS、缓冲和端到端背压。
10. [异步生成器、asynccontextmanager 与 yield 生命周期](010_异步生成器、asynccontextmanager_与_yield_生命周期.md)——进阶：理解逐次消费、资源进入/退出和异常清理。

## 第四阶段：FastAPI 与工程边界

11. [FastAPI 请求参数、Depends 与生命周期](011_FastAPI_请求参数、Depends_与生命周期.md)——进阶：把 Pydantic、依赖图和异步生命周期用于请求边界。
12. [FastAPI UploadFile、File 与 Form](012_FastAPI_UploadFile、File_与_Form.md)——进阶：处理 multipart、文件指针、分块读取和上传安全。
13. [FastAPI BackgroundTasks 与可靠任务边界](013_FastAPI_BackgroundTasks_与可靠任务边界.md)——进阶：区分进程内后续工作与可靠任务队列。
14. [状态模型、ORM、JSONB 与持久化边界](014_状态模型、ORM、JSONB_与持久化边界.md)——综合进阶：连接状态 Patch、运行时资源、ORM 与数据库持久化。

## 排查附录

- [通用学习与异步服务排查模板](附_通用学习与排查模板.md)

附录分成通用学习框架和异步/FastAPI 专项排查两部分，不再假设所有 Python 主题都需要使用同一套异步调试代码。
