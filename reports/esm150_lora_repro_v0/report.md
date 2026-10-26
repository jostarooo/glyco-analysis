# ESM-2 150M LoRA 作者检查点复算报告

## 结论

作者发布的 ESM-2 150M PEFT 参数高效微调适配器在作者 `test.csv` 的全部行上复算，得到 MCC `0.848348842859`。论文报告值为 `0.848`，差值为 `+0.000348842859`。

该差值按测量值记录。现有证据不能把差异单独归因到硬件、依赖版本或随机性，因此本报告不给出未经实验支持的原因。

## 运行范围

本次运行按原始顺序评估作者 `test.csv` 的每一行，不删除非规范残基或非 `sequon` 行。模型读取完整蛋白序列，使用作者适配器输出的两个分数（`logit`），按 `argmax` 得到预测标签。

## 指标

| 指标 | 数值 |
|---|---:|
| MCC | 0.848348842859 |
| 论文 MCC | 0.848 |
| 与论文差值 | +0.000348842859 |
| 准确率 | 0.923649177760 |
| 精确率 | 0.945967741935 |
| 召回率 | 0.901614142967 |
| 特异度 | 0.946528332003 |

混淆矩阵为 TP `1173`、FP `67`、TN `1186`、FN `128`。

## 数据审计

- 行数：`2554`
- 阳性 / 阴性：`1301` / `1253`
- 保留的非 `sequon` 行：`46`
- 唯一序列数 / 编码器前向次数：`963` / `963`
- 最长序列：`5179 aa`
- 注意力路径：`sdpa`，使用完整序列推理

## 兼容性说明

作者适配器使用较旧的 PEFT 布局保存。本次复算通过独立兼容路径加载作者固定的 `peft 0.14.0` 与 `transformers 4.50.3`。

`sdpa` 路径保留完整序列，并使用 PyTorch 的内存高效缩放点积注意力。它是执行优化，不改变截断或滑窗口径。运行清单 `manifest.json` 记录了本次运行选择的注意力后端。

加载告警：

- `Found missing adapter keys while loading the checkpoint: ['base_model.model.classifier.original_module.out_proj.lora_A.default.weight', 'base_model.model.classifier.original_module.out_proj.lora_B.default.weight']`

上述告警指向未激活的重复别名 `classifier.original_module.out_proj`。实际使用的 `classifier.modules_to_save.default.out_proj` 四个权重与检查点的有效键逐元素一致。详细审计见 `06-核心数据\mcc_repro.md`。

## 运行时复核

2026-10-26 使用 `check_esm150_lora_repro.py --recheck-inference` 重新加载固定基座模型与作者适配器，重建 16 行审计样本。核验结果为 `status=PASS`、`33294` 条断言、`rechecked_rows=16`、`inference_recheck=true`，MCC 为 `0.8483488428592927`。完整记录见 `reports/esm150_lora_recheck_2026-10-26.md`。

## 产物说明

`predictions.csv`、`audit_sample.csv`、`metrics.json`、`report.md` 和 `manifest.json` 均已登记在运行清单中。任何原因归因都必须同时得到运行清单、逐行预测和核验脚本结果的证据支持。
