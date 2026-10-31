# W3 Day 2 记分卡验证记录

日期：2026-10-31

仓库：`D:\wbworkspace\glyco-analysis`

开工 HEAD：`985d8975799f254bad18f05a8fcf68682ff75a72`

本轮没有重跑 F2 训练，没有重跑 Qwen3 4B 50 题，没有 push、远端重写或发布。

## 生成结果

```text
PASS: generated 8 metrics; feasibility 43/5/2
PASS: scorecard outputs are current
```

| 输出 | SHA256 | mtime_ns |
|---|---|---:|
| `scorecard.json` | `7d6657c43932f5ceff1abbf2febeff2bc4d743cc766d11dc59d2c1df2464b3d7` | `1793419026254916100` |
| `scorecard.csv` | `5f9422647575d8d2aaa7092b962f75155aaba94cbad15daf578abcf14ca87fdf` | `1793418774740723700` |
| `scorecard.md` | `8da03312ff21425321ce76b3f6189d04af3c0ecd620c0cee6c7a6c4d5578a636` | `1793419026266335300` |

连续第二次生成后，三个文件的 SHA256 和 mtime 均未变化。

## 负向控制

在临时目录复制三个输出，向 `scorecard.csv` 末尾追加一个字节，再运行：

```text
exit_code=1
stderr=SCORECARD CHECK ERROR: scorecard outputs missing or stale: scorecard.csv
```

真实仓库输出未被修改。
原始记录见 `negative_control_2026-10-31.txt`。

## 固定回归

聚焦测试：

```text
Ran 20 tests in 0.843s
OK
```

原始输出见 `scorecard_tests_2026-10-31.txt`。

全量测试环境：

```text
PYTHONPATH=D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages
PYTHONUTF8=1
Python=C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe
```

全量结果：

```text
Ran 99 tests in 24.606s
OK (skipped=1)
```

跳过项是 `test_rotary_sdpa_matches_eager_with_padding_mask` 的 GPU 门控测试，
未设置 `RUN_ESM150_GPU_TESTS=1`，属于预期跳过。
原始输出见 `unittest_2026-10-31.txt`。

## 外部证据复核

F3 summary checker：

```text
status=PASS
tasks_run=50
exact_sequence=19
all_expected_called=34
any_expected_called=41
tasks_with_tool_call=50
tasks_with_final_answer=39
tool_call_successes=78
tool_calls=110
```

原始输出见 `f3_summary_check_2026-10-31.txt`。

GlycanML 数据检查：

```text
status=PASS
datasets=5
total_bytes=30675065
glycan_link=PASS_URL_FIX
```

这些复核只读取现有证据，不产生新的训练成绩。
原始输出见 `glycanml_data_check_2026-10-31.json`。

## 源证据

生成器记录的八个源文件及 SHA256 在 `scorecard.json` 的 `sources` 数组和
`scorecard.md` 的“来源与哈希”表中。CSV 每行通过 `source_role`、`source_path` 和
`source_sha256` 指回对应源文件。

## 口径边界

- F2 对齐 GlycanML Table 3；TorchDrug 未安装，本轮是 PyG 自实现，不是逐位克隆。
- F3 的 19/50、34/50、41/50、39/50、78/110 是轨迹或输出存在性，不是答案正确率。
- 上游 Claude 18/50 和 Qwen3 15/50 使用 GPT-4o 评分，本轮未运行同一评分器。
- `reports/w2_day2/f3_qwen3_8b_50_incomplete/` 是中断目录，不是成绩。
- 工具可行性 43/5/2 是任务可用性快照，不是模型准确率。
