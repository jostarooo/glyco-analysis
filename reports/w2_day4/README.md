# W2 Day 4 可重算记分卡

本目录把已经核验的 F1、F2、F3 和工具可行性证据收束为一组确定性输出。它不重跑
F2 训练，不重跑 Qwen3 4B 50 题，也不把 F3 轨迹指标解释成答案正确率。

## 文件

| 文件 | 用途 |
|---|---|
| `reference_values.json` | 人工核对的论文与上游参考值，生成器只读 |
| `scorecard.json` | 机器读取的 8 条指标、来源哈希、工具分类和口径边界 |
| `scorecard.csv` | 便于表格审阅和 diff 的扁平行，每行带源文件 SHA256 |
| `scorecard.md` | 教师可读的中文汇总 |
| `validation_2026-10-31.md` | 生成、负向控制、回归和数据检查记录 |
| `scorecard_tests_2026-10-31.txt` | 记分卡聚焦测试原始输出 |
| `unittest_2026-10-31.txt` | 全量 unittest 原始输出 |
| `f3_summary_check_2026-10-31.txt` | F3 50 题 summary 复核原始输出 |
| `glycanml_data_check_2026-10-31.json` | GlycanML 五文件校验原始输出 |
| `negative_control_2026-10-31.txt` | 手改临时输出后 `--check` 失败的控制记录 |

## 生成与检查

```powershell
$env:PYTHONUTF8 = '1'
D:\python\python.exe scripts\build_w2_scorecard.py
D:\python\python.exe scripts\build_w2_scorecard.py --check
```

生成器固定读取八个仓库内证据源，重算 F1 混淆矩阵与 MCC、F2 三种子均值和
`statistics.stdev`，并校验 F3 计数边界、工具可行性题号集合、参考值锚点以及
源文件 SHA256。输出不写运行时间，连续两跑必须字节一致；第二次不得更新 mtime。

只有 F1 MCC、F2 免疫原性 AUPRC 和 F2 糖基化 Macro-F1 生成
`local_minus_reference` 差值。F3 五项全部标为 `not_comparable`，不得生成数值差值。

## 当前口径

- 工具可行性：当前工具可直接完成 43，需要替代工具 5，服务失败 2，合计 50。
- `get_proteins` 的 TLS 校验失败不等于服务死亡。
- `get_ligands` 返回 HTTP 200 空数组不等于 task 48 可用。
- F2 对齐 GlycanML Table 3，本地是 PyG 自实现，不是 TorchDrug 逐位克隆。
- 上游 Claude 18/50 和 Qwen3 15/50 使用 GPT-4o 评分，不能和本地轨迹指标直接比较。
