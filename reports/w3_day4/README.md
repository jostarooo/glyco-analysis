# W3 Day 4：Doc2Agent 三模型对照

日期：2026-11-07

本轮把 F3 从 Qwen3 4B 与 GLM-5.3 的两模型对照，扩展为同一套
50 道任务、70 个工具、系统提示词和 JSON 动作协议的三模型对照。

## 最终模型

| 角色 | provider | model | 运行目录 |
|---|---|---|---|
| 本地基线 | `ollama` | `qwen3:4b` | `reports/w2_day2/f3_qwen3_4b_50/` |
| 外部对照一 | `local_magpie` | `workbuddy-ai/glm-5.3` | `reports/w3_day2/f3_glm53_50/` |
| 外部对照二 | `local_magpie` | `qoder-cn/dfmodel` | `reports/w3_day4/f3_deepseek_flash_qoder_50/` |

Manifest 为 `reports/w3_day4/f3_models.json`。每个模型必须提供恰好 50 个
运行 task、50 个评分 task、同一组 expected tools、同一 judge 契约和完整源哈希。

## 轨迹结果

| 指标 | Qwen3 4B | GLM-5.3 | DeepSeek-Flash |
|---|---:|---:|---:|
| `exact_sequence` | 19 | 13 | 13 |
| `all_expected_called` | 34 | 41 | 42 |
| `any_expected_called` | 41 | 47 | 48 |
| `tasks_with_tool_call` | 50 | 49 | 50 |
| `tasks_with_final_answer` | 39 | 25 | 22 |
| `tool_call_successes` | 78 | 114 | 115 |
| `tool_calls` | 110 | 129 | 148 |

DeepSeek-Flash 完成 50 题，174 次模型调用，148 次工具调用中 115 次成功。
24 道题以 `max_rounds_reached` 结束诊断。本批次未观察到 HTTP 429。

这些数字只描述工具轨迹、调用状态和最终回答存在性，不是答案正确率。

## 答案评分

三份运行使用同一个 `workbuddy-ai/kimi-k3` judge，temperature 为 0，
max_tokens 为 1500。

| 状态 | Qwen3 4B | GLM-5.3 | DeepSeek-Flash |
|---|---:|---:|---:|
| `correct` | 9 | 18 | 15 |
| `incorrect` | 29 | 3 | 5 |
| `manual_review` | 1 | 4 | 2 |
| `missing_answer` | 11 | 25 | 28 |
| `invalid_trace` | 0 | 0 | 0 |
| `judge_unavailable` | 0 | 0 | 0 |
| 可判定正确率 | 9/38 | 18/21 | 15/20 |
| 可判定覆盖率 | 38/50 | 21/50 | 20/50 |

DeepSeek-Flash 在已有最终回答的题目中判对比例为 15/20，但最终回答覆盖只有
22/50，可判定覆盖只有 20/50。三模型都只有一次固定 50 题运行，不能据此声称
方差、模型大小因果或普遍优劣。

这是本地证据约束评分，`upstream_gpt4o_equivalent=false`，不能与上游
Claude 18/50 或 Qwen3 15/50 的 GPT-4o 评分直接比较。

## DeepSeek V4.1 Flash 失败记录

先尝试了 Magpie 免费路由 `opencode-zen/deepseek-v4.1-flash-free`。
50 题运行中发生 17 次 HTTP 429，23 题没有产生工具调用，只有 9 题产生最终回答。
该运行只作为配额失败证据，不进入三模型能力对照：

- `deepseek_v41_quota_failure.md`
- `f3_deepseek_v41_50/summary.json`
- `answer_grades_kimi_k3/f3_deepseek_v41_50/summary.json`

最终第三模型改用 `qoder-cn/dfmodel`（Magpie 显示名
`DeepSeek-Flash · Qoder CN`），完整跑完 50 题。

## 可重算入口

```powershell
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8='1'
$python='C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe'

& $python scripts\summarize_doc2agent_run.py `
  --run-dir reports\w3_day4\f3_deepseek_flash_qoder_50 `
  --expected-tasks 50 `
  --check-summary reports\w3_day4\f3_deepseek_flash_qoder_50\summary.json

& $python scripts\grade_doc2agent_answers.py --check `
  --run-dir reports\w3_day4\f3_deepseek_flash_qoder_50 `
  --out-dir reports\w3_day4\answer_grades_kimi_k3\f3_deepseek_flash_qoder_50

& 'D:\python\python.exe' scripts\doc2agent_three_model_report.py `
  --manifest reports\w3_day4\f3_models.json `
  --json-out reports\w3_day4\f3_three_model_report.json `
  --md-out reports\w3_day4\f3_three_model_report.md `
  --check
```

最终报告为 `f3_three_model_report.json` 和 `f3_three_model_report.md`。
生成器会校验 manifest、50 个运行 task、50 个评分 task、prompt/rubric 契约、
源 summary 哈希、聚合哈希和输出幂等性。

## 边界

- F2 仍对齐 GlycanML 论文 Table 3，不是 Table 2。
- F2 仍是 PyG 自实现 RGCN，不是 TorchDrug 逐位克隆。
- F3 轨迹指标不是答案正确率。
- Kimi K3 不等于上游 GPT-4o 评分器。
- V4.1 免费路由配额失败不是模型能力结论。
- Qwen3 4B 的 prompt 哈希来自历史代码 provenance，不是运行时记录。
