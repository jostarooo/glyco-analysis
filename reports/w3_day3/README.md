# W3 Day 3 答案评分证据

本目录保存 Doc2Agent 两份 50 题轨迹的答案评分结果和验证记录。评分只判断已有
最终回答是否被本地证据支撑，不改变原轨迹，也不重跑模型。

## 结果入口

- `answer_grades_kimi_k3/f3_qwen3_4b_50/`：Qwen3 4B 最终评分。
- `answer_grades_kimi_k3/f3_glm53_50/`：GLM-5.3 最终评分。
- `answer_grade_comparison.md`：两种模型的评分与覆盖率对照。
- `answer_grade_comparison.json`：同一对照的机器可读结果。
- `validation_2026-11-06.md`：本轮验证命令、结果和解释边界。

## Judge 选择记录

`answer_grades/` 保存 DeepSeek V4.1 Flash Free 的中断探针。该通道先返回空内容，
随后触发免费额度上限，因此只完成 3 题和 13 题。这两个目录只证明 judge 切换过程，
不是最终成绩，也不能与 `answer_grades_kimi_k3/` 混用。

最终 judge 为 `workbuddy-ai/kimi-k3`，`temperature=0`、`max_tokens=1500`。
Kimi K3 不属于本地 Qwen3 或外部 GLM-5.3 家族，降低同家族偏好。

## 解释边界

这是本地证据约束评分，不是上游 GPT-4o 评分。`graded_accuracy` 只使用
`correct + incorrect` 作分母，必须同时报告 `graded_coverage`、
`answer_available_rate` 和 `correct_over_task_count`。两组状态差异不能证明
模型大小或其他因素造成了答案质量差异。
