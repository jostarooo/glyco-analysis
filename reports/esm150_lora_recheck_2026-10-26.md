# ESM-2 150M 作者检查点运行时复核记录（2026-10-26）

## 结论

作者 ESM-2 150M LoRA 检查点的独立核验脚本已完成运行时复核，退出码为 `0`，状态为 `PASS`。

复核结果：

| 项目 | 结果 |
|---|---:|
| 核对预测行数 | 2554 |
| 断言数 | 33294 |
| 重建推理行数 | 16 |
| 是否启用推理复核 | 是 |
| MCC | 0.8483488428592927 |

本次复核重新加载固定基座模型与作者适配器，并按 `audit_sample.csv` 的 16 行样本重建前向结果。其余 2538 行由核验脚本核对预测、指标、输入哈希和产物哈希。

## 运行命令

```powershell
$env:PYTHONPATH = 'D:\uv\pylibs\lora-n-gly-peft014'
cd D:\wbworkspace\glyco-analysis

& .\.venv\Scripts\python.exe scripts\check_esm150_lora_repro.py `
  --run-dir reports\esm150_lora_repro_v0 `
  --test-csv D:\wbworkspace\LoRA-N-Gly\data\N-GlycositeAltas\test.csv `
  --adapter-dir D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint `
  --base-model-revision a695f6045e2e32885fa60af20c13cb35398ce30c `
  --recheck-inference
```

## 实际输出

```json
{
  "status": "PASS",
  "assertions": 33294,
  "rows": 2554,
  "rechecked_rows": 16,
  "inference_recheck": true,
  "mcc": 0.8483488428592927
}
```

退出码：`0`。

## 告警说明

运行中出现两类告警，核验脚本仍判定通过：

1. Transformers 报告分类头权重未从基座检查点初始化。这是因为分类头由作者适配器提供，属于预期加载流程。
2. PEFT 报告 `classifier.original_module.out_proj` 的两个适配器键缺失。该路径是未激活的重复别名；实际使用的 `classifier.modules_to_save.default.out_proj` 四个权重已与检查点有效键逐元素核对一致。

告警不改变预测结果，也不是网络或 GPU 失败。完整审计见 `mcc_repro.md`。

## 复核边界

本记录只证明作者 `test.csv` 上的 150M 复算及其 16 行运行时抽样复核通过。

W1 三方法对拍的核验脚本是另一项检查。它核对 201 行候选连接、130 行评估指标、10 行人工复核与全部产物哈希，不重建 201 行 GPU 前向。两套核验脚本的结果不能混写。

## 复核环境

| 项 | 值 |
|---|---|
| 复核日期 | 2026-10-26 |
| Python | 3.12.14 |
| PyTorch | 2.9.1+cu128 |
| Transformers | 4.50.3 |
| PEFT | 0.14.0 |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU |
| 测试集 SHA256 | `D2533271159123EE1C8D537CBE7BDA115AB0E0A29D98A8DF7B7B4ACC69217D20` |
| 适配器 SHA256 | `A4A5B486862724F459F60E8343AC135C340305D5A0F2E936EB5AD1DFD34788D4` |
| 基座 revision | `a695f6045e2e32885fa60af20c13cb35398ce30c` |
