# Doc2Agent 答案评分对照

本报告使用本地证据约束评分。
该评分不等同于上游 GPT-4o 评分器。
状态差异不能作为模型大小或其他原因的因果证据。

本报告范围为 `local_evidence_grading`。
上游 GPT-4o 等价为 `false`。
评分器为 `workbuddy-ai/kimi-k3`。

## 汇总

| 指标 | 本地 | 外部 | 差值 |
|---|---:|---:|---:|
| `task_count` | 50 | 50 | +0 |
| `graded_correct` | 9 | 18 | +9 |
| `graded_incorrect` | 29 | 3 | -26 |
| `status:correct` | 9 | 18 | +9 |
| `status:incorrect` | 29 | 3 | -26 |
| `status:manual_review` | 1 | 4 | +3 |
| `status:missing_answer` | 11 | 25 | +14 |
| `status:invalid_trace` | 0 | 0 | +0 |
| `status:judge_unavailable` | 0 | 0 | +0 |

## 可判定指标

| 指标 | 本地 | 外部 |
|---|---|---|
| `graded_accuracy` | 9/38 (0.236842) | 18/21 (0.857143) |
| `graded_coverage` | 38/50 (0.760000) | 21/50 (0.420000) |
| `correct_over_task_count` | 9/50 (0.180000) | 18/50 (0.360000) |
| `answer_available_rate` | 39/50 (0.780000) | 25/50 (0.500000) |

## 逐题状态

| 题号 | 本地 | 外部 | 状态相同 |
|---:|---|---|---|
| 1 | `incorrect` | `correct` | 否 |
| 2 | `incorrect` | `missing_answer` | 否 |
| 3 | `correct` | `correct` | 是 |
| 4 | `correct` | `correct` | 是 |
| 5 | `missing_answer` | `missing_answer` | 是 |
| 6 | `manual_review` | `manual_review` | 是 |
| 7 | `incorrect` | `missing_answer` | 否 |
| 8 | `incorrect` | `manual_review` | 否 |
| 9 | `incorrect` | `correct` | 否 |
| 10 | `correct` | `incorrect` | 否 |
| 11 | `correct` | `correct` | 是 |
| 12 | `incorrect` | `correct` | 否 |
| 13 | `incorrect` | `correct` | 否 |
| 14 | `incorrect` | `missing_answer` | 否 |
| 15 | `incorrect` | `incorrect` | 是 |
| 16 | `incorrect` | `correct` | 否 |
| 17 | `incorrect` | `missing_answer` | 否 |
| 18 | `incorrect` | `correct` | 否 |
| 19 | `missing_answer` | `missing_answer` | 是 |
| 20 | `incorrect` | `missing_answer` | 否 |
| 21 | `incorrect` | `correct` | 否 |
| 22 | `incorrect` | `missing_answer` | 否 |
| 23 | `incorrect` | `manual_review` | 否 |
| 24 | `missing_answer` | `missing_answer` | 是 |
| 25 | `missing_answer` | `missing_answer` | 是 |
| 26 | `incorrect` | `missing_answer` | 否 |
| 27 | `missing_answer` | `manual_review` | 否 |
| 28 | `incorrect` | `missing_answer` | 否 |
| 29 | `incorrect` | `correct` | 否 |
| 30 | `missing_answer` | `correct` | 否 |
| 31 | `missing_answer` | `missing_answer` | 是 |
| 32 | `incorrect` | `missing_answer` | 否 |
| 33 | `missing_answer` | `missing_answer` | 是 |
| 34 | `missing_answer` | `missing_answer` | 是 |
| 35 | `incorrect` | `correct` | 否 |
| 36 | `incorrect` | `correct` | 否 |
| 37 | `correct` | `missing_answer` | 否 |
| 38 | `correct` | `correct` | 是 |
| 39 | `correct` | `correct` | 是 |
| 40 | `missing_answer` | `missing_answer` | 是 |
| 41 | `incorrect` | `correct` | 否 |
| 42 | `correct` | `correct` | 是 |
| 43 | `incorrect` | `missing_answer` | 否 |
| 44 | `missing_answer` | `missing_answer` | 是 |
| 45 | `correct` | `missing_answer` | 否 |
| 46 | `incorrect` | `missing_answer` | 否 |
| 47 | `incorrect` | `incorrect` | 是 |
| 48 | `incorrect` | `missing_answer` | 否 |
| 49 | `incorrect` | `missing_answer` | 否 |
| 50 | `incorrect` | `missing_answer` | 否 |
