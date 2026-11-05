# Doc2Agent trajectory comparison

Scope: `trajectory_only`. Answer quality was not evaluated.
Delta definition: `external_minus_local`.
Local model: `qwen3:4b`.
External model: `workbuddy-ai/glm-5.3`.

## Aggregate

| Metric | Local | External | Delta |
|---|---:|---:|---:|
| `tasks_run` | 50 | 50 | +0 |
| `exact_sequence` | 19 | 13 | -6 |
| `all_expected_called` | 34 | 41 | +7 |
| `any_expected_called` | 41 | 47 | +6 |
| `tasks_with_tool_call` | 50 | 49 | -1 |
| `tasks_with_final_answer` | 39 | 25 | -14 |
| `tool_call_successes` | 78 | 114 | +36 |
| `tool_calls` | 110 | 129 | +19 |

## Behavior diagnostics

| Diagnostic | Local | External |
|---|---:|---:|
| `tasks_with_errors` | 21 | 28 |
| `tasks_with_max_rounds` | 9 | 20 |
| `tasks_with_invalid_action` | 2 | 5 |
| `tool_error_statuses` | 32 | 15 |

## Per task

| Task | Local exact/all/any | External exact/all/any | Delta exact | Delta all | Delta called | Delta successes |
|---:|---|---|---:|---:|---:|---:|
| 1 | N/N/N | N/Y/Y | +0 | +1 | +1 | +2 |
| 2 | N/N/N | N/Y/Y | +0 | +1 | +2 | +1 |
| 3 | N/Y/Y | Y/Y/Y | +1 | +0 | -2 | -2 |
| 4 | Y/Y/Y | Y/Y/Y | +0 | +0 | +0 | +0 |
| 5 | N/Y/Y | N/Y/Y | +0 | +0 | +0 | +1 |
| 6 | Y/Y/Y | Y/Y/Y | +0 | +0 | +0 | +0 |
| 7 | N/N/N | N/Y/Y | +0 | +1 | +1 | +4 |
| 8 | N/N/N | N/N/N | +0 | +0 | +0 | +1 |
| 9 | Y/Y/Y | Y/Y/Y | +0 | +0 | +0 | +1 |
| 10 | Y/Y/Y | N/Y/Y | -1 | +0 | +1 | +0 |
| 11 | N/Y/Y | N/Y/Y | +0 | +0 | +1 | +1 |
| 12 | Y/Y/Y | Y/Y/Y | +0 | +0 | +0 | +0 |
| 13 | N/Y/Y | Y/Y/Y | +1 | +0 | -2 | -2 |
| 14 | Y/Y/Y | N/Y/Y | -1 | +0 | +1 | +0 |
| 15 | N/N/N | N/Y/Y | +0 | +1 | +1 | +1 |
| 16 | N/Y/Y | N/Y/Y | +0 | +0 | +1 | +2 |
| 17 | N/Y/Y | N/Y/Y | +0 | +0 | +1 | +1 |
| 18 | N/N/N | N/Y/Y | +0 | +1 | -1 | +2 |
| 19 | N/Y/Y | N/N/N | +0 | -1 | -4 | -4 |
| 20 | Y/Y/Y | N/Y/Y | -1 | +0 | +3 | +3 |
| 21 | N/Y/Y | N/Y/Y | +0 | +0 | -1 | +0 |
| 22 | N/N/N | N/Y/Y | +0 | +1 | +2 | +2 |
| 23 | Y/Y/Y | Y/Y/Y | +0 | +0 | +0 | +0 |
| 24 | N/Y/Y | N/Y/Y | +0 | +0 | -2 | -1 |
| 25 | N/Y/Y | N/Y/Y | +0 | +0 | +0 | +4 |
| 26 | N/N/N | N/Y/Y | +0 | +1 | +3 | +4 |
| 27 | Y/Y/Y | Y/Y/Y | +0 | +0 | +0 | +0 |
| 28 | Y/Y/Y | N/Y/Y | -1 | +0 | +3 | +3 |
| 29 | N/N/N | N/N/N | +0 | +0 | +1 | +1 |
| 30 | N/Y/Y | N/Y/Y | +0 | +0 | -2 | -2 |
| 31 | N/N/Y | N/N/Y | +0 | +0 | +0 | +0 |
| 32 | N/N/Y | N/N/Y | +0 | +0 | +3 | +0 |
| 33 | N/Y/Y | N/Y/Y | +0 | +0 | +0 | +0 |
| 34 | N/Y/Y | N/Y/Y | +0 | +0 | +0 | +1 |
| 35 | Y/Y/Y | Y/Y/Y | +0 | +0 | +0 | +1 |
| 36 | N/N/Y | Y/Y/Y | +1 | +1 | +0 | +0 |
| 37 | Y/Y/Y | N/Y/Y | -1 | +0 | +2 | +2 |
| 38 | Y/Y/Y | Y/Y/Y | +0 | +0 | +0 | +0 |
| 39 | Y/Y/Y | Y/Y/Y | +0 | +0 | +0 | +0 |
| 40 | N/Y/Y | N/Y/Y | +0 | +0 | +0 | -1 |
| 41 | N/N/Y | N/N/Y | +0 | +0 | -2 | +0 |
| 42 | Y/Y/Y | N/N/Y | -1 | -1 | +0 | +0 |
| 43 | N/N/Y | N/N/Y | +0 | +0 | +1 | +1 |
| 44 | N/N/Y | N/Y/Y | +0 | +1 | +0 | +2 |
| 45 | Y/Y/Y | N/Y/Y | -1 | +0 | +2 | +2 |
| 46 | Y/Y/Y | N/Y/Y | -1 | +0 | +2 | +1 |
| 47 | N/Y/Y | N/N/Y | +0 | -1 | -2 | -1 |
| 48 | Y/Y/Y | N/Y/Y | -1 | +0 | +2 | +2 |
| 49 | Y/Y/Y | Y/Y/Y | +0 | +0 | +0 | +0 |
| 50 | N/N/Y | N/Y/Y | +0 | +1 | +3 | +3 |
