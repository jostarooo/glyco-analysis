# AI 编程会话工程归档验证记录

日期：2026-11-08

## 目标

把与毕设项目直接相关的真实 AI 编程会话整理为可审计工程记录，满足以下条件：

- 不直接提交 137 MB 原始 JSONL。
- 不归档其他课程、私人项目或无关上下文。
- 不导出隐藏推理 `thinking_text`。
- 每条叙述绑定真实消息或工具事件。
- 每条证据都有稳定会话定位和规范化行 SHA256。
- 密码、token、Cookie、Authorization、私钥和用户主目录在提交前脱敏。
- 生成文件可离线检查，手改或陈旧输出必须失败。

## 实现

生成器：`scripts/build_agent_session_archive.py`

计划：`agent-sessions/archive-plan.json`

测试：`tests/test_agent_session_archive.py`

输入边界是 AgentsView SQLite，使用 `mode=ro` 和 `PRAGMA query_only=ON`。计划固定
12 个项目会话。消息证据使用 `session_id + ordinal`，工具证据使用
`session_id + message ordinal + call_index + event_index`。

## 当前归档

- 工程记录：5 篇
- 真实 Codex 会话：12 个
- 证据：33 条
- 按日目录：2026-11-04 至 2026-11-08
- 脱敏命中：中文密码 1 次、用户主目录 2 次
- 原始大型 JSONL：未上传
- 隐藏推理：未导出

主要输出：

- `agent-sessions/INDEX.md`
- `agent-sessions/SOURCES.sha256`
- `agent-sessions/2026-11-04/01-real-system-vertical-slice.md`
- `agent-sessions/2026-11-05/01-external-model-trajectory-comparison.md`
- `agent-sessions/2026-11-06/01-doc2agent-answer-grading.md`
- `agent-sessions/2026-11-07/01-three-model-report-and-deepseek-route.md`
- `agent-sessions/2026-11-08/01-chinese-report-delivery-and-session-gap.md`

## 哈希

| 文件 | SHA256 |
|---|---|
| `agent-sessions/SOURCES.sha256` | `31B9FFC16751B2F13F415F32D0678F01F0AC5149057D2920207C00068B154202` |
| `agent-sessions/INDEX.md` | `EB99353A57972AA3338779EE1402895216FF0C185BD325C16D713FBF45CC076B` |
| `agent-sessions/archive-plan.json` | `9A98442A8300637B47C834A85D9E34874659FE9469F56B33EF9E8E752A6710C8` |
| `scripts/build_agent_session_archive.py` | `DF71CFA355D58DC7D88235DA3EB9EC67EE1B5A92E38F1481F6F706A856D6D313` |

## 验证

聚焦测试：

```text
Ran 13 tests
OK
```

全量测试：

```text
Ran 214 tests in 50.288s
OK (skipped=8)
```

完整原始输出：`reports/w3_day5/agent_session_archive_unittest_2026-11-08.txt`

生成器检查：

```text
PASS: 5 篇工程记录，12 个会话，33 条证据
脱敏：PASSWORD_CN=1、USER_HOME=2
PASS: 生成文件、源证据和脱敏检查一致
```

幂等性：连续两次生成，所有生成文件 SHA256 和 mtime 都不变，第二次修改 0 个文件。

负向控制：复制真实归档后手改 `README.md` 并注入假 GitHub token，
`--check` 返回 1，首条错误为“生成文件已过期或被手改：README.md”。

## 判定边界

- 本归档是真实会话的脱敏工程整理，不伪造原聊天、成功结果、命令或工具输出。
- 工程叙述中的结论必须引用真实证据；隐藏推理不导出。
- 证据哈希证明数据库中的选定原文没有变化，不证明模型回答一定正确。
- 主会话仍在增长，因此只校验选定证据行，不校验易变的整文件哈希。
- 本归档不替代本人手写日志总结、周报或周视频。
