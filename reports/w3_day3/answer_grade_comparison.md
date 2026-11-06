# Doc2Agent answer-grade comparison

This report uses local evidence-grounded judging.
It is not equivalent to the upstream GPT-4o grader.
Status differences are not evidence of a model-size effect or another cause.

Scope: `local_evidence_grading`.
Upstream GPT-4o equivalent: `false`.
Judge: `workbuddy-ai/kimi-k3`.

## Summary

| Metric | Local | External | Delta |
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

## Graded metrics

| Metric | Local | External |
|---|---|---|
| `graded_accuracy` | 9/38 (0.236842) | 18/21 (0.857143) |
| `graded_coverage` | 38/50 (0.760000) | 21/50 (0.420000) |
| `correct_over_task_count` | 9/50 (0.180000) | 18/50 (0.360000) |
| `answer_available_rate` | 39/50 (0.780000) | 25/50 (0.500000) |

## Task statuses

| Task | Local | External | Same |
|---:|---|---|---|
| 1 | `incorrect` | `correct` | N |
| 2 | `incorrect` | `missing_answer` | N |
| 3 | `correct` | `correct` | Y |
| 4 | `correct` | `correct` | Y |
| 5 | `missing_answer` | `missing_answer` | Y |
| 6 | `manual_review` | `manual_review` | Y |
| 7 | `incorrect` | `missing_answer` | N |
| 8 | `incorrect` | `manual_review` | N |
| 9 | `incorrect` | `correct` | N |
| 10 | `correct` | `incorrect` | N |
| 11 | `correct` | `correct` | Y |
| 12 | `incorrect` | `correct` | N |
| 13 | `incorrect` | `correct` | N |
| 14 | `incorrect` | `missing_answer` | N |
| 15 | `incorrect` | `incorrect` | Y |
| 16 | `incorrect` | `correct` | N |
| 17 | `incorrect` | `missing_answer` | N |
| 18 | `incorrect` | `correct` | N |
| 19 | `missing_answer` | `missing_answer` | Y |
| 20 | `incorrect` | `missing_answer` | N |
| 21 | `incorrect` | `correct` | N |
| 22 | `incorrect` | `missing_answer` | N |
| 23 | `incorrect` | `manual_review` | N |
| 24 | `missing_answer` | `missing_answer` | Y |
| 25 | `missing_answer` | `missing_answer` | Y |
| 26 | `incorrect` | `missing_answer` | N |
| 27 | `missing_answer` | `manual_review` | N |
| 28 | `incorrect` | `missing_answer` | N |
| 29 | `incorrect` | `correct` | N |
| 30 | `missing_answer` | `correct` | N |
| 31 | `missing_answer` | `missing_answer` | Y |
| 32 | `incorrect` | `missing_answer` | N |
| 33 | `missing_answer` | `missing_answer` | Y |
| 34 | `missing_answer` | `missing_answer` | Y |
| 35 | `incorrect` | `correct` | N |
| 36 | `incorrect` | `correct` | N |
| 37 | `correct` | `missing_answer` | N |
| 38 | `correct` | `correct` | Y |
| 39 | `correct` | `correct` | Y |
| 40 | `missing_answer` | `missing_answer` | Y |
| 41 | `incorrect` | `correct` | N |
| 42 | `correct` | `correct` | Y |
| 43 | `incorrect` | `missing_answer` | N |
| 44 | `missing_answer` | `missing_answer` | Y |
| 45 | `correct` | `missing_answer` | N |
| 46 | `incorrect` | `missing_answer` | N |
| 47 | `incorrect` | `incorrect` | Y |
| 48 | `incorrect` | `missing_answer` | N |
| 49 | `incorrect` | `missing_answer` | N |
| 50 | `incorrect` | `missing_answer` | N |
