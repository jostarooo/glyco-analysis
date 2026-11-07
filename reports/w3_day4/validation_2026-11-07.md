# W3 Day 4 验证记录

日期：2026-11-07

## 真实运行

Qoder DeepSeek-Flash 使用同一批 50 道题、70 个工具、同一系统提示词和
JSON 动作协议完成运行。入口为：

- `reports/w3_day4/f3_deepseek_flash_qoder_50/`
- `reports/w3_day4/f3_deepseek_flash_qoder_50/summary.json`

运行摘要：

| 指标 | 值 |
|---|---:|
| 任务数 | 50 |
| `exact_sequence` | 13 |
| `all_expected_called` | 42 |
| `any_expected_called` | 48 |
| `tasks_with_tool_call` | 50 |
| `tasks_with_final_answer` | 22 |
| 成功工具调用 / 工具调用 | 115 / 148 |
| 模型调用 | 174 |
| 总 token 报告值 | 711332 |
| 总耗时 | 1762.294 秒 |
| `finish_reason=stop` | 173 |
| `finish_reason=length` | 1 |

50 个 task 文件和 summary 复核通过：

```text
status=PASS
tasks_run=50
exact_sequence=13
all_expected_called=42
any_expected_called=48
tasks_with_tool_call=50
tasks_with_final_answer=22
tool_call_successes=115
tool_calls=148
```

## 答案评分

同一 Kimi K3 judge 完成 50 题评分：

```text
status=PASS
task_count=50
correct=15
incorrect=5
manual_review=2
missing_answer=28
invalid_trace=0
judge_unavailable=0
graded_accuracy=15/20
```

离线 `--check`：

```text
status=PASS
tasks_checked=50
errors=[]
```

## 三模型报告

报告器使用 `reports/w3_day4/f3_models.json` 生成两份输出，三模型为
`qwen3_4b`、`glm_5_3`、`deepseek_flash_qoder`。

首次生成和第二次生成结果：

```text
status=PASS
models=qwen3_4b,glm_5_3,deepseek_flash_qoder
reference_model=qwen3_4b
tasks=50
json_changed=false
markdown_changed=false
```

连续两跑字节和 mtime 均不变：

```text
json_sha256=D0F7D417BB478791B0F571C9AF31877021738B97573C536D38007ECEBA99397F
markdown_sha256=6B9227E997739FAFF2CC288D61D998674599255EB85DED03332FA3B748C871C4
```

负向控制：在临时副本中把 JSON 的 `exact_sequence` 从 19 改成 20，
`--check` 返回退出码 1：

```text
status=FAIL
JSON report differs from regenerated output
```

## 测试

三模型报告器聚焦测试：

```text
Ran 10 tests
OK
```

全量 unittest：

```text
Ran 185 tests in 100.086s
OK (skipped=8)
```

8 项跳过均来自既有 GPU 门控或按设计跳过的环境合同测试，没有新增失败。

## 尚未改变的口径

- F2 对齐 GlycanML Table 3，不是 Table 2。
- F3 轨迹指标不是答案正确率。
- Kimi K3 是本地证据评分器，不是上游 GPT-4o 等价评分。
- V4.1 Flash 免费路由的 429 结果不是模型能力结论。
- 每个模型只有一次固定 50 题运行，不能声称方差或模型大小因果。
