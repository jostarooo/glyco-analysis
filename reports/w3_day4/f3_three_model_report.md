# Doc2Agent 三模型报告

本报告范围为 `f3_three_model`。
参考模型为 `qwen3_4b`。
差值定义为 `model_minus_reference_model`。
工具轨迹指标与答案评分指标分开报告。
不计算合并准确率。
这是本地证据约束评分，不是上游 GPT-4o 评分器。

## 工具轨迹指标

| 指标 | Qwen3 4B (Ollama) | GLM-5.3 (Magpie) | DeepSeek-Flash (Qoder CN) |
|---|---:|---:|---:|
| `tasks_run` | 50 | 50 | 50 |
| `exact_sequence` | 19 | 13 | 13 |
| `all_expected_called` | 34 | 41 | 42 |
| `any_expected_called` | 41 | 47 | 48 |
| `tasks_with_tool_call` | 50 | 49 | 50 |
| `tasks_with_final_answer` | 39 | 25 | 22 |
| `tool_call_successes` | 78 | 114 | 115 |
| `tool_calls` | 110 | 129 | 148 |

## 答案评分指标

| 指标 | Qwen3 4B (Ollama) | GLM-5.3 (Magpie) | DeepSeek-Flash (Qoder CN) |
|---|---:|---:|---:|
| `status:correct` | 9 | 18 | 15 |
| `status:incorrect` | 29 | 3 | 5 |
| `status:manual_review` | 1 | 4 | 2 |
| `status:missing_answer` | 11 | 25 | 28 |
| `status:invalid_trace` | 0 | 0 | 0 |
| `status:judge_unavailable` | 0 | 0 | 0 |
| `task_count` | 50 | 50 | 50 |
| `graded_correct` | 9 | 18 | 15 |
| `graded_incorrect` | 29 | 3 | 5 |
| `graded_accuracy` | 9/38 (0.236842) | 18/21 (0.857143) | 15/20 (0.750000) |
| `graded_coverage` | 38/50 (0.760000) | 21/50 (0.420000) | 20/50 (0.400000) |
| `correct_over_task_count` | 9/50 (0.180000) | 18/50 (0.360000) | 15/50 (0.300000) |
| `answer_available_rate` | 39/50 (0.780000) | 25/50 (0.500000) | 22/50 (0.440000) |

## 相对参考模型的差值

| 模型 | 轨迹 `exact` | 轨迹全工具命中 | 轨迹最终回答 | 答案正确数 | 答案覆盖率 |
|---|---:|---:|---:|---:|---:|
| Qwen3 4B (Ollama) | +0 | +0 | +0 | +0 | +0.000000 |
| GLM-5.3 (Magpie) | -6 | +7 | -14 | +9 | -0.340000 |
| DeepSeek-Flash (Qoder CN) | -6 | +8 | -17 | +6 | -0.360000 |

## 来源

| 模型 | 运行摘要 SHA256 | 运行任务聚合 SHA256 | 评分摘要 SHA256 | 评分任务聚合 SHA256 |
|---|---|---|---|---|
| Qwen3 4B (Ollama) | `4ead0e26a15760a34450c55859679a5c5aeee4dd913014826540b77e5b7c66f4` | `3c66eb7f19938c4609bff19d46106d1a92a7271c682393ef4e0e50c3feb24616` | `980ea2f0fe77157415774d8a6e6a9f4731b0971db688596096915f6e657b224e` | `b8d8b8d85458521c2daa66e80c6290c215f0b8d261f8036578a5ca3a6e79062e` |
| GLM-5.3 (Magpie) | `9b144e8e7a450caa3f3b2e596ba1a01e26f35485ac3138387b5ff7abdea1dabb` | `36d9569e0366085386cfd829e341cc2696748f49d3da20cc0e814f576560e994` | `e5b9e23d0a6304ce7a14b717c5e62c8f34ed23683a460435b995c14ea751de0c` | `34cdf11ed75edbd70c8e5b29cc3532b15e1b268a774ae3568acb9c29930c8e05` |
| DeepSeek-Flash (Qoder CN) | `04a76a4061afa6cee82d14583921e890f54c0244ea74a21d74893fe03cd44d98` | `c169f8f72f620247546f07f231d25268eaf0a960da7f55e116b64e94d3d1b185` | `9d03f1fbb37432ed7ded474e4d2f10e523f49fe94bfaa0b4d1bf47bad0698891` | `4fd4c813a84dde6a7c57c656a247fac389211125d59ebc0a8fa7919178f44099` |

## 逐题状态

| 题号 | Qwen3 4B (Ollama) | GLM-5.3 (Magpie) | DeepSeek-Flash (Qoder CN) |
|---:|---|---|---|
| 1 | `incorrect` | `correct` | `incorrect` |
| 2 | `incorrect` | `missing_answer` | `missing_answer` |
| 3 | `correct` | `correct` | `correct` |
| 4 | `correct` | `correct` | `missing_answer` |
| 5 | `missing_answer` | `missing_answer` | `missing_answer` |
| 6 | `manual_review` | `manual_review` | `missing_answer` |
| 7 | `incorrect` | `missing_answer` | `missing_answer` |
| 8 | `incorrect` | `manual_review` | `missing_answer` |
| 9 | `incorrect` | `correct` | `correct` |
| 10 | `correct` | `incorrect` | `correct` |
| 11 | `correct` | `correct` | `missing_answer` |
| 12 | `incorrect` | `correct` | `missing_answer` |
| 13 | `incorrect` | `correct` | `correct` |
| 14 | `incorrect` | `missing_answer` | `incorrect` |
| 15 | `incorrect` | `incorrect` | `missing_answer` |
| 16 | `incorrect` | `correct` | `correct` |
| 17 | `incorrect` | `missing_answer` | `missing_answer` |
| 18 | `incorrect` | `correct` | `missing_answer` |
| 19 | `missing_answer` | `missing_answer` | `manual_review` |
| 20 | `incorrect` | `missing_answer` | `missing_answer` |
| 21 | `incorrect` | `correct` | `missing_answer` |
| 22 | `incorrect` | `missing_answer` | `missing_answer` |
| 23 | `incorrect` | `manual_review` | `missing_answer` |
| 24 | `missing_answer` | `missing_answer` | `missing_answer` |
| 25 | `missing_answer` | `missing_answer` | `missing_answer` |
| 26 | `incorrect` | `missing_answer` | `missing_answer` |
| 27 | `missing_answer` | `manual_review` | `manual_review` |
| 28 | `incorrect` | `missing_answer` | `missing_answer` |
| 29 | `incorrect` | `correct` | `missing_answer` |
| 30 | `missing_answer` | `correct` | `missing_answer` |
| 31 | `missing_answer` | `missing_answer` | `incorrect` |
| 32 | `incorrect` | `missing_answer` | `correct` |
| 33 | `missing_answer` | `missing_answer` | `missing_answer` |
| 34 | `missing_answer` | `missing_answer` | `correct` |
| 35 | `incorrect` | `correct` | `correct` |
| 36 | `incorrect` | `correct` | `correct` |
| 37 | `correct` | `missing_answer` | `correct` |
| 38 | `correct` | `correct` | `correct` |
| 39 | `correct` | `correct` | `correct` |
| 40 | `missing_answer` | `missing_answer` | `missing_answer` |
| 41 | `incorrect` | `correct` | `incorrect` |
| 42 | `correct` | `correct` | `correct` |
| 43 | `incorrect` | `missing_answer` | `missing_answer` |
| 44 | `missing_answer` | `missing_answer` | `correct` |
| 45 | `correct` | `missing_answer` | `correct` |
| 46 | `incorrect` | `missing_answer` | `missing_answer` |
| 47 | `incorrect` | `incorrect` | `incorrect` |
| 48 | `incorrect` | `missing_answer` | `missing_answer` |
| 49 | `incorrect` | `missing_answer` | `missing_answer` |
| 50 | `incorrect` | `missing_answer` | `missing_answer` |
