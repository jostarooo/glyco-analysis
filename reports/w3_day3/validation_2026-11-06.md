# W3 Day 3 验证记录

日期：2026-11-06

## 结论

答案评分器、两份最终评分、评分对照和覆盖指标都已完成离线复核。本地和外部
50 题轨迹没有重跑，F2 训练没有重跑，W2 原始 CSV、task JSON 和 summary
没有修改。

## 最终结果

| 指标 | Qwen3 4B | GLM-5.3 |
|---|---:|---:|
| `correct` | 9 | 18 |
| `incorrect` | 29 | 3 |
| `manual_review` | 1 | 4 |
| `missing_answer` | 11 | 25 |
| `invalid_trace` | 0 | 0 |
| `judge_unavailable` | 0 | 0 |
| 有最终回答 | 39/50 | 25/50 |
| 可判定正确率 | 9/38 = 0.236842 | 18/21 = 0.857143 |
| 可判定覆盖率 | 38/50 = 0.76 | 21/50 = 0.42 |
| 全 50 题中判为正确 | 9/50 = 0.18 | 18/50 = 0.36 |

两组使用同一题集、同一 rubric、同一提示词模板和同一
`workbuddy-ai/kimi-k3` judge。`temperature=0`，`max_tokens=1500`。
50 题中有 32 题状态不同，18 题状态相同。

## 验证结果

| 检查 | 结果 | 证据 |
|---|---|---|
| 答案评分聚焦测试 | 18/18 PASS | `answer_grader_tests_2026-11-06.txt` |
| 全量 unittest | 175 项中 167 通过，8 项按设计或 GPU 门控跳过 | `unittest_2026-11-06.txt` |
| Qwen3 评分离线复核 | PASS，50 题，0 错误 | `answer_grades_check_qwen3_2026-11-06.txt` |
| GLM-5.3 评分离线复核 | PASS，50 题，0 错误 | `answer_grades_check_glm53_2026-11-06.txt` |
| 评分对照 | PASS，50 题，32 题状态不同 | `answer_grade_comparison_2026-11-06.txt` |
| 对照幂等性 | JSON 和 Markdown 连续两跑 SHA256 不变 | `answer_grade_comparison_2026-11-06.txt` |
| 本地 F3 summary checker | PASS | `f3_qwen3_summary_check_2026-11-06.txt` |
| 外部 F3 summary checker | PASS | `f3_glm53_summary_check_2026-11-06.txt` |
| W2 记分卡 | PASS | `w2_scorecard_check_2026-11-06.txt` |
| GlycanML 数据 | PASS，`glycan_link` 为 `PASS_URL_FIX` | `glycanml_data_check_2026-11-06.json` |

## 评分规则

评分器在调用外部 judge 前先校验上游题面、期望工具和 50 题任务集。缺少最终回答时
写入 `missing_answer`，不调用 judge。题面或工具不一致时写入 `invalid_trace`。
judge 返回 `SUCCESS`，但没有成功工具证据、证据全部截断或证据编号非法时，
写入 `manual_review`。

`graded_accuracy` 只以 `correct + incorrect` 为分母。可判定覆盖率和其他分母
单独报告，避免把缺回答和人工复核合并成答错。

## 解释边界

这是本地证据约束 judge，不是上游 GPT-4o 评分器，不能与上游 Claude 18/50 或
Qwen3 15/50 直接比较。GLM-5.3 在已有最终回答中更容易被判正确，但只对 25/50 题
产生最终回答。结果不能写成外部模型整体更好，也不能单独归因于模型大小。

## 可复现命令

```powershell
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8='1'
$python='C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe'

& $python -m unittest tests.test_doc2agent_answer_grader -v
& $python scripts\grade_doc2agent_answers.py --check `
  --run-dir reports\w2_day2\f3_qwen3_4b_50 `
  --out-dir reports\w3_day3\answer_grades_kimi_k3\f3_qwen3_4b_50
& $python scripts\grade_doc2agent_answers.py --check `
  --run-dir reports\w3_day2\f3_glm53_50 `
  --out-dir reports\w3_day3\answer_grades_kimi_k3\f3_glm53_50
& $python scripts\compare_doc2agent_answer_grades.py
```
