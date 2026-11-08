# DeepSeek V4.1 Flash 免费路由额度失败记录

日期：2026-11-07

本次运行是失败证据，不是模型质量结果。

## 路由

- Magpie 模型：`opencode-zen/deepseek-v4.1-flash-free`
- 接口地址：`http://127.0.0.1:3425/v1/chat/completions`
- Temperature：`0`
- 最大输出 token：`512`
- 最大轮数：`4`
- 没有发送 provider 原生工具

## 结果

Runner 在 `reports/w3_day4/f3_deepseek_v41_50` 中完成了 50 个任务文件。
运行期间，免费路由达到用量限制，17 次模型调用返回 HTTP 429。结果是 23 道
题没有产生任何工具调用，只有 9 道题产生最终回答。

轨迹摘要：

| 指标 | 值 |
|---|---:|
| 任务数 | 50 |
| `exact_sequence` | 8 |
| `all_expected_called` | 26 |
| `any_expected_called` | 27 |
| 产生工具调用的任务 | 29 |
| 产生最终回答的任务 | 9 |
| 成功工具调用 | 60 |
| 工具调用 | 74 |
| 模型调用 | 114 |
| 总耗时（秒） | 651.038 |

同一 Kimi K3 judge 对这份不完整轨迹评分：

| 状态 | 数量 |
|---|---:|
| `correct` | 3 |
| `incorrect` | 4 |
| `manual_review` | 2 |
| `missing_answer` | 41 |
| `invalid_trace` | 0 |
| `judge_unavailable` | 0 |

## 决策

不要把本次运行与 Qwen3 4B 或 GLM-5.3 的结果比较，也不要把它写成模型能力
结论。本次运行测到的是免费路由额度耗尽。因此 W3 Day 4 改用
`qoder-cn/dfmodel` 的 DeepSeek-Flash 完成第三模型 50 题对照。

## 证据

- 运行摘要：`reports/w3_day4/f3_deepseek_v41_50/summary.json`
- 任务轨迹：`reports/w3_day4/f3_deepseek_v41_50/task_01.json` 至
  `task_50.json`
- 答案评分：
  `reports/w3_day4/answer_grades_kimi_k3/f3_deepseek_v41_50/summary.json`
