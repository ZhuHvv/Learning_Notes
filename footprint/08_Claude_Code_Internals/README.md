# Claude Code 源码与机制解读

本专题从 Agent Harness 工程视角理解 Claude Code，重点关注上下文组织、Prompt Cache、流式协议、输出上限、错误恢复与 Agent Loop。

知识点文件数：2

## 文件列表

- [Claude Code Prompt 前缀缓存与三级上下文](001_Claude_Code_Prompt_前缀缓存与三级上下文.md)
- [Claude Code 流式输出、max_tokens 与恢复机制](002_Claude_Code_流式输出、max_tokens_与恢复机制.md)

## 阅读边界

- Anthropic 官方文档明确说明的 API 协议和 Claude Code 行为，作为稳定结论记录。
- 从特定版本源码、source map 或第三方源码解读得到的实现细节，会明确标注“版本相关”，不把常量、重试次数等当作永久契约。
- 本专题中的 Prompt Cache 指模型服务端的前缀计算缓存，不等同于 Claude Code 本地会话文件、Memory 或语义缓存。
