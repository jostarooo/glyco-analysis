# AI 工程会话归档

本目录保存与毕设糖基化分析系统直接相关的真实 AI 编程会话工程记录。记录来源是 Codex 会话在 AgentsView 中的结构化数据，不是手工编写的进度摘要。

审阅方式和证据边界见 [REVIEW_GUIDE.md](REVIEW_GUIDE.md)。

## 归档原则

- 只归档本项目会话，不提交其他课程、私人项目或无关上下文。
- 不提交原始大型 JSONL。当前主会话超过 100 MB，且会持续变化。
- 不导出隐藏推理或 thinking_text，只保留用户目标、助手结论、命令和工具结果。
- 每条证据绑定 `session_id`、消息 `ordinal`；工具证据另绑定 `call_index` 和 `event_index`。
- 叙述是脱敏工程整理，不伪造原聊天、成功结果、命令或模型输出。
- 提交前统一替换 token、Cookie、Authorization、密码、私钥、URL token 和用户主目录。

## 目录结构

```text
agent-sessions/
├─ README.md
├─ INDEX.md
├─ REVIEW_GUIDE.md
├─ archive-plan.json
├─ SOURCES.sha256
└─ YYYY-MM-DD/
   ├─ README.md
   └─ NN-topic.md
```

## 可信度边界

- 证据哈希证明当前数据库中的选定原文没有变化，不等同于模型回答一定正确。
- 工程记录中的结论必须同时指向真实工具结果或项目产物。
- 本目录不替代周进度报告、本人手写日志总结或周视频。
- 主会话仍在增长时，不记录易变的整文件哈希，只记录选定证据的规范化行哈希。

## 维护方式

归档计划和证据选择写在 `archive-plan.json`。生成器与 `--check` 共用同一构建流程；连续运行不改变字节或 mtime，手改生成文件、缺失证据或疑似密钥残留都会失败。

当前包含 5 篇工程记录。完整入口见 [INDEX.md](INDEX.md)。
