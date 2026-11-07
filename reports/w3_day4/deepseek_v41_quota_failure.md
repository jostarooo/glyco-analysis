# DeepSeek V4.1 Flash free-route quota failure

Date: 2026-11-07

This run is failure evidence, not a model-quality result.

## Route

- Magpie model: `opencode-zen/deepseek-v4.1-flash-free`
- Endpoint: `http://127.0.0.1:3425/v1/chat/completions`
- Temperature: `0`
- Max tokens: `512`
- Max rounds: `4`
- Provider-native tools: not sent

## Result

The runner completed 50 task files in `reports/w3_day4/f3_deepseek_v41_50`.
During the run, 17 model calls returned HTTP 429 because the free route reached
its usage limit. As a result, 23 tasks produced no tool call and only 9 tasks
produced a final answer.

Trajectory summary:

| Metric | Value |
|---|---:|
| Tasks | 50 |
| `exact_sequence` | 8 |
| `all_expected_called` | 26 |
| `any_expected_called` | 27 |
| Tasks with a tool call | 29 |
| Tasks with a final answer | 9 |
| Successful tool calls | 60 |
| Tool calls | 74 |
| Model calls | 114 |
| Elapsed seconds | 651.038 |

The same Kimi K3 judge graded the partial traces:

| Status | Count |
|---|---:|
| `correct` | 3 |
| `incorrect` | 4 |
| `manual_review` | 2 |
| `missing_answer` | 41 |
| `invalid_trace` | 0 |
| `judge_unavailable` | 0 |

## Decision

Do not compare this run with Qwen3 4B or GLM-5.3 as a model capability result.
The run measured free-route quota exhaustion. W3 Day 4 therefore uses
`qoder-cn/dfmodel` DeepSeek-Flash for the complete 50-task third-model
comparison.

## Evidence

- Run summary: `reports/w3_day4/f3_deepseek_v41_50/summary.json`
- Task traces: `reports/w3_day4/f3_deepseek_v41_50/task_01.json` through
  `task_50.json`
- Answer grades:
  `reports/w3_day4/answer_grades_kimi_k3/f3_deepseek_v41_50/summary.json`
