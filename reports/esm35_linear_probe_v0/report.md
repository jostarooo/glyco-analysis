# ESM-2 35M 冻结主干线性探针报告

## 结论

本报告给出 F1 v0 候选位点表上的弱标签基线。正类是含 `ECO:0000269` 实验证据的 N-连接糖基化位点，对照是同一张候选表中没有 N-连接糖基化标注的 N-X-S/T 序列模体（`sequon`）。未标注样本不是实验确认的阴性，因此本报告不估计生物特异性，也不把对照比例写成真阴性率。

## 运行口径

- 模型：`facebook/esm2_t12_35M_UR50D`，版本（`revision`）`6fbf070e65b0b7291e7bbcd451118c216cff79d8`。
- 候选表 SHA256：`A584C3814226B7287807676F65D5CFFE2F5D47A53BC00476A4B9945CB0719F1C`。
- UniProt 发布版本：`2026_03`。
- 数据切分：留一蛋白交叉验证（`leave_one_protein_out`）。
- 位点表征：目标词元的最后一层隐藏状态（`last_hidden_state_at_target_token`）。
- 基准评测：实验阳性对未标注对照（`experimental_positive_vs_unannotated_control`）。
- 候选来源行数：201 行。
- 评估行数：130 行，由 82 个实验阳性和 48 个未标注对照组成。
- 仅含推断证据 `ECO:0000255` 的 71 行不进入指标分母。
- 因只有推断阳性而退出评估的蛋白：`P13611`。
- 行数、蛋白数、唯一窗口数：130 / 28 / 51。
- 分类器：`LogisticRegression`，`C=1.0`，`class_weight=none`，`solver=liblinear`。
- 判定阈值：`0.5`。
- 生成时基线提交：`29f97a502b16dd0ad169de4fb69a4dd10dd76e49`，当时工作树干净。
- 设备与精度：`cuda` / `float32`。

## 复现命令

```powershell
.venv\Scripts\python.exe scripts\run_esm35_linear_probe.py --cache-dir <uniprot-cache> --out-dir reports\esm35_linear_probe_v0 --allow-download
.venv\Scripts\python.exe scripts\check_esm35_linear_probe.py --run-dir reports\esm35_linear_probe_v0 --cache-dir <uniprot-cache>
```

## 环境

- Python：3.12.14
- `torch`：2.9.1+cu128
- `transformers`：5.20.1
- `scikit-learn`：1.9.1
- `NumPy`：2.5.4

## 结果

<!-- BEGIN GENERATED METRICS -->
| 指标 | 数值 |
|---|---:|
| MCC | 0.331975 |
| 实验阳性召回率 | 0.731707 |
| 未标注对照保持率 | 0.604167 |
| 阳性预测精确率 | 0.759494 |
| 弱标签一致率 | 0.684615 |
| ROC AUC（实验阳性对未标注对照） | 0.756098 |
| 实验阳性计数 | 预测阳性 60，预测对照 22 |
| 未标注对照计数 | 预测阳性 19，预测对照 29 |

按 28 个蛋白做 2000 次重采样。该区间只描述这批蛋白，不代表泛化保证。
有效重采样 2000 次，未定义 0 次。

| 区间 | 95% |
|---|---:|
| MCC | [0.060051, 0.602824] |
| 实验阳性召回率 | [0.544111, 0.902778] |
| 未标注对照保持率 | [0.437460, 0.820556] |
<!-- END GENERATED METRICS -->

## 核验记录

- 2026-10-20：13 项单元测试通过；独立核验脚本在重建嵌入时通过 4026 条断言。
- 2026-10-26：在基线提交 `29f97a502b16dd0ad169de4fb69a4dd10dd76e49` 上使用 `--skip-reembed` 复核，输出 `rows=130 proteins=28 windows=51 release=2026_03`，通过 3896 条断言，状态为 `PASS`。
- 该复核只证明产物与生成基线一致，不等于重新训练模型或重新执行 130 行 GPU 前向。

## 产物

`manifest.json` 记录输入、模型文件、环境、设置和全部产物的哈希。本目录同时提供 `metrics.json`、`predictions.csv`、`windows.csv`、`folds.csv` 和 `embeddings.npy`，可用于逐项复核。

## 解读边界

48 行未标注对照不是实验确认的阴性，相关比例只能称为“未标注对照保持率”。35M 与 150M 的差异同时包含模型规模、训练方式、输入上下文和推理方式差异，不能只归因于模型大小。
