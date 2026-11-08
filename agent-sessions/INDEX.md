# AI 工程会话归档索引

本索引汇总本项目真实 AI 编程会话的脱敏工程记录。所有摘录可回溯到会话 ID、消息序号或工具事件序号，并附原始证据哈希。

材料范围、证据强度和不能证明的内容见 [REVIEW_GUIDE.md](REVIEW_GUIDE.md)。

## 记录

| 日期 | 记录 | 标题 | 证据数 | SHA256 |
|---|---|---|---:|---|
| 2026-11-04 | [01-real-system-vertical-slice.md](2026-11-04/01-real-system-vertical-slice.md) | W3 Day1：真实位点预测系统纵切 | 7 | `39bf906ecbcdb47fad46ff67f965fc5c755101ff1be58510da2b5d796fa40ce2` |
| 2026-11-05 | [01-external-model-trajectory-comparison.md](2026-11-05/01-external-model-trajectory-comparison.md) | W3 Day2：外部模型轨迹对照 | 6 | `dba1b3e2d211b0f21a1c21149f7887943e18b65f3c4dca436315d940c5ed49ca` |
| 2026-11-06 | [01-doc2agent-answer-grading.md](2026-11-06/01-doc2agent-answer-grading.md) | W3 Day3：Doc2Agent 答案评分与覆盖对照 | 5 | `26b0699d3300c9b3f2a01424f4d187470f589be85c3d8845f56b1d5c42dbc7b8` |
| 2026-11-07 | [01-three-model-report-and-deepseek-route.md](2026-11-07/01-three-model-report-and-deepseek-route.md) | W3 Day4：DeepSeek-Flash 三模型对照 | 6 | `6ffbcb36475e6e35f2475d6d00402388659488955641e5bc18c70b90161ecc87` |
| 2026-11-08 | [01-chinese-report-delivery-and-session-gap.md](2026-11-08/01-chinese-report-delivery-and-session-gap.md) | W3 Day5：中文报告、交付收尾与 AI 会话缺口 | 9 | `6b36775396c279130fa9fd1c49dcc88df2d5f2536cff92f00f0ed7833cdcb653` |

## 会话清单

| 会话 | 说明 | 项目 | 开始时间 | 源文件策略 |
|---|---|---|---|---|
| `codex:01a180cf-92f6-7813-88f3-915158a80cab` | 毕设主开发会话（2026-10-28 起） | `workspace` | `2026-10-28T04:41:07.626Z` | 只校验选定证据；主会话仍在增长，整文件哈希会变化；改为逐条校验选定消息和工具事件的规范化行哈希 |
| `codex:01a1a465-2960-70a0-9cf6-ebd15c5c1da9` | W3 Day1 系统架构候选 A | `workspace` | `2026-11-04T02:30:55.717Z` | 源文件 SHA256 `c382b91aa74a9944bdebd0b898923b9470c1d07bd37620203d3022ec942fd871` |
| `codex:01a1a465-3094-76e1-8d7f-709e569d270f` | W3 Day1 系统架构候选 B | `workspace` | `2026-11-04T02:30:57.548Z` | 源文件 SHA256 `0c5b0cef5aa9b8d33f6fe756aafb573646be2c47b1341591bbde649c267f4406` |
| `codex:01a1a46e-25e8-70f2-a013-a49ca614042c` | W3 Day1 单文件系统界面实现 | `workspace` | `2026-11-04T02:40:44.711Z` | 源文件 SHA256 `352b078386b8ad1771275ed6db5482a4695af331b591fa29c939db584096fe34` |
| `codex:01a1a9f3-f56c-7ff2-8705-9aa251a26e4e` | W3 Day2 外部模型架构候选 A | `glyco_analysis` | `2026-11-05T04:25:00.786Z` | 源文件 SHA256 `c3074a2af0fb91be74c6ef74bdd6da2751d6935eb48681d9a50d1067a49a113c` |
| `codex:01a1a9f3-fcf8-7d60-84ef-a7de5f4e3a95` | W3 Day2 外部模型架构候选 B | `glyco_analysis` | `2026-11-05T04:25:02.715Z` | 源文件 SHA256 `1354bb80a49bc17ae107094e2f5b733d3bb8ac19002c784fb9f6bd7d21c50fed` |
| `codex:01a1a9f8-fc20-7c40-8834-1a1eb057961f` | W3 Day2 外部模型 runner 实现 | `glyco_analysis` | `2026-11-05T04:30:30.15Z` | 源文件 SHA256 `a9fd5b718382d427f2c55296a0d3de0138f8650c4a213ac95cc4c73a957841cd` |
| `codex:01a1af1c-4ed8-7650-b1aa-7be2e378fddd` | W3 Day3 答案评分架构候选 A | `glyco_analysis` | `2026-11-06T04:27:11.233Z` | 源文件 SHA256 `e407aff41185e0ad68d512aa1a8feded3d2fd7947189e470abd02f7721eed700` |
| `codex:01a1af1c-5714-7e71-a7c4-d2babf18b27d` | W3 Day3 答案评分架构候选 B | `glyco_analysis` | `2026-11-06T04:27:13.349Z` | 源文件 SHA256 `d0bfbdc05aab489b9f4420f93a21672a59c3c2d2fb5a0dfd97f6e294f269c780` |
| `codex:01a1af1f-ccd5-7571-bafb-c45dd01ddefe` | W3 Day3 答案评分器实现 | `glyco_analysis` | `2026-11-06T04:31:00.106Z` | 源文件 SHA256 `1ce6cecb7536629267b678a0d029b60793f5fef27434f2ebc3c250f8fb8a8dc1` |
| `codex:01a1b437-f32e-79a0-bc5e-2d54f7f8c695` | W3 Day4 三模型报告架构审查 | `glyco_analysis` | `2026-11-07T04:15:28.62Z` | 源文件 SHA256 `848d58be6d2887af94bed99d0a3b46f561a86e46b50330ac4310270411e46ea1` |
| `codex:01a1b43e-4055-7b73-a3f8-ec3bb8fe9879` | W3 Day4 三模型报告器实现 | `glyco_analysis` | `2026-11-07T04:22:21.569Z` | 源文件 SHA256 `ec3508ca7d0a47db287644c03d7a8b6478c1cc7a9639c39c3d76e46b0018b36d` |

## 统计

- 工程记录：5 篇
- 会话：12 个
- 证据：33 条
- 原始大型 JSONL：未上传
- 隐藏推理、thinking_text：未导出

## 复现

```powershell
$env:PYTHONUTF8='1'
D:\python\python.exe scripts\build_agent_session_archive.py `
  --db D:\AppData\agentsview\sessions.db `
  --plan agent-sessions\archive-plan.json `
  --out agent-sessions

D:\python\python.exe scripts\build_agent_session_archive.py `
  --db D:\AppData\agentsview\sessions.db `
  --plan agent-sessions\archive-plan.json `
  --out agent-sessions --check
```
