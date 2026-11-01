# W2 Day 3 阻断工具复测证据

日期：2026-10-30

本目录只记录 Doc2Agent 的工具可行性复测。W2 原始分类保留在
`reports/w2_day2/tool_feasibility.csv` 和
`reports/w2_day2/tool_feasibility_summary.json`，本目录不回写历史证据。

| 文件 | 用途 |
|---|---|
| `tool_blocker_recheck.csv` | 17 个阻断工具的 HTTP、内容、控制探针和 wrapper 哈希 |
| `tool_blocker_recheck_summary.json` | 工具级与任务级汇总、50 题分类和输入文件哈希 |
| `task_feasibility_corrections.csv` | 24 道分类发生变化的题目 |
| `task_feasibility_revised.csv` | 50 道题的原分类、复核分类、阻断工具和判定理由 |
| `unittest_2026-10-30.txt` | 79 项固定回归，78 项通过，1 项 GPU 门控跳过 |
| `f3_summary_check_2026-10-30.txt` | F3 50 题 summary checker PASS |
| `glycanml_data_check_2026-10-30.json` | 5 个 GlycanML CSV 的 MD5 复核 PASS |
| `validation_2026-10-30.md` | 本轮验证记录和口径边界 |

结论见 `docs/W2_D3_tool_blocker_triage.txt`。最新 50 题分类为当前工具可直接完成
43 题、需要替代工具 5 题、服务失败 2 题，合计 50 题。
