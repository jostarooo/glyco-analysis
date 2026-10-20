# ESM-2 35M 冻结主干线性探针

本报告只针对 F1 v0 候选位点表的弱标签基准。正类是含 `ECO:0000269` 实验证据的 N-linked 位点；对照是同一张候选表中没有 N-linked 标注的 sequon。未标注不是实验阴性，因此本报告不估计生物特异性或真阴性率。

## 运行口径

- 模型：`facebook/esm2_t12_35M_UR50D`，revision `6fbf070e65b0b7291e7bbcd451118c216cff79d8`
- 候选表 SHA256：`A584C3814226B7287807676F65D5CFFE2F5D47A53BC00476A4B9945CB0719F1C`
- UniProt release：`2026_03`
- 切分：`leave_one_protein_out`
- 表征：`last_hidden_state_at_target_token`
- 基准：`experimental_positive_vs_unannotated_control`
- 候选来源行数：201
- 评估行数：130 = 82 实验阳性 + 48 未标注对照
- 排除仅含 `ECO:0000255` 的推断阳性：71 行
- 因此不再进入评估的蛋白：P13611
- 行数、蛋白数、唯一窗口数：130 / 28 / 51
- 分类器：`LogisticRegression`，C=1.0，class_weight=none, solver=liblinear
- 阈值：0.5
- 生成时基线 commit：`29f97a502b16dd0ad169de4fb69a4dd10dd76e49` (dirty=false)
- 设备与精度：`cuda` / `float32`

## 复现

```powershell
.venv\Scripts\python.exe scripts\run_esm35_linear_probe.py --cache-dir <uniprot-cache> --out-dir reports\esm35_linear_probe_v0 --allow-download
.venv\Scripts\python.exe scripts\check_esm35_linear_probe.py --run-dir reports\esm35_linear_probe_v0 --cache-dir <uniprot-cache>
```

## 环境

- Python 3.12.14
- torch 2.9.1+cu128
- transformers 5.20.1
- scikit-learn 1.9.1
- NumPy 2.5.4

## 结果

<!-- BEGIN GENERATED METRICS -->
| 指标 | 数值 |
|---|---:|
| MCC | 0.331975 |
| 实验阳性召回率 | 0.731707 |
| 未标注对照保持率 | 0.604167 |
| 阳性预测精确率 | 0.759494 |
| 弱标签一致率 | 0.684615 |
| ROC AUC（实验阳性 vs 未标注对照） | 0.756098 |
| 实验阳性计数 | 预测阳性=60 预测对照=22 |
| 未标注对照计数 | 预测阳性=19 预测对照=29 |

按蛋白做 2000 次重采样，共 28 个蛋白。该区间只描述这批蛋白，不代表泛化保证。
有效重采样：2000；未定义：0。

| 区间 | 95% |
|---|---:|
| MCC | [0.060051, 0.602824] |
| 实验阳性召回率 | [0.544111, 0.902778] |
| 未标注对照保持率 | [0.437460, 0.820556] |
<!-- END GENERATED METRICS -->
