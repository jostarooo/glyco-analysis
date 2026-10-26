# ESM-2 150M LoRA 作者检查点复算

## 结论

作者发布的 ESM-2 150M PEFT 参数高效微调适配器在完整 `test.csv` 上复算得到 MCC
`0.848348842859`。论文报告值为 `0.848`，差值为 `+0.000348842859`。

该差值按测量值记录。当前证据不能把差异单独归因到硬件、依赖版本或随机性，
因此报告不给出未经实验支持的原因。

## 输入与口径

| 项 | 值 |
|---|---|
| 测试集 | `D:\wbworkspace\LoRA-N-Gly\data\N-GlycositeAltas\test.csv` |
| 测试集 SHA256 | `D2533271159123EE1C8D537CBE7BDA115AB0E0A29D98A8DF7B7B4ACC69217D20` |
| 行数 | 2554 |
| 阳性 / 阴性 | 1301 / 1253 |
| 蛋白数 | 939 |
| 唯一序列 / 编码器前向次数 | 963 / 963 |
| 最长序列 | 5179 aa |
| 非 sequon 行 | 46，全部保留 |
| 适配器 | `D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint` |
| 适配器 SHA256 | `A4A5B486862724F459F60E8343AC135C340305D5A0F2E936EB5AD1DFD34788D4` |
| 适配器张量数 | 376 |
| 基座模型 | `facebook/esm2_t30_150M_UR50D` |
| 基座版本 | `a695f6045e2e32885fa60af20c13cb35398ce30c` |
| 基座权重 SHA256 | `C3F1DA8AEA53BDDD32C246C86168C23B9FD72341FB9DB9A94436F855F5053566` |

执行契约为 FP32、完整序列、批大小为 1、无截断、无滑窗、两个输出分数（`logit`）取
`argmax`。每条唯一序列只执行一次编码器，随后读取同一隐藏状态中的目标位点。

## 指标

| 指标 | 数值 |
|---|---:|
| MCC | 0.848348842859 |
| 论文 MCC | 0.848 |
| 差值 | +0.000348842859 |
| 准确率 | 0.923649177760 |
| 精确率 | 0.945967741935 |
| 召回率 | 0.901614142967 |
| 特异度 | 0.946528332003 |

混淆矩阵：

| | 预测阳性 | 预测阴性 |
|---|---:|---:|
| 实际阳性 | TP 1173 | FN 128 |
| 实际阴性 | FP 67 | TN 1186 |

## 验证

正式运行来自干净的分离头工作树。运行清单记录：

- 代码基线 `c6577c0deb16c2aefaaa7e34e038e32078482c4e`
- `git_dirty=false`
- `attention_backend=sdpa`
- `sdpa_module_count=30`
- `sdpa_eligible_module_count=30`
- `sdpa_expected_module_count=30`
- `execution_attention_kernel=pytorch_sdpa_efficient_attention`
- 单次全量推理耗时 `115.164377` 秒

独立核验脚本启用 `--recheck-inference`，重建 SDPA 路径并复算 16 行审计样本。
结果为：

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

与 150M 相关的测试共 34 项。关闭 GPU 门控时 33 项通过、1 项跳过；启用 GPU 门控后
34 项全部通过。GPU 测试比较 `eager` 与 SDPA 在带填充掩码输入上的前向结果。
仓库完整默认测试套件为 57 项，其中 56 项通过、1 项 GPU 门控跳过；单独启用该门控后，
这项测试也通过。

## 适配器告警审计

加载检查点时 PEFT 报告两条缺失键（`missing keys`）：

```text
base_model.model.classifier.original_module.out_proj.lora_A.default.weight
base_model.model.classifier.original_module.out_proj.lora_B.default.weight
```

当前生效路径是 `classifier.modules_to_save.default.out_proj`。逐元素对照结果：

| 权重 | 与检查点有效键一致 |
|---|---|
| `base_layer.weight` | 是 |
| `base_layer.bias` | 是 |
| `lora_A` | 是 |
| `lora_B` | 是 |

因此这两条告警指向未激活的重复别名 `classifier.original_module.out_proj`。
实际用于推理的分类头权重没有漏载。

## 产物

| 文件 | SHA256 |
|---|---|
| `predictions.csv` | `372112E11FE8BFB785508BFC3CAE932DA6622566C6E1DD5D035B88C6DBC7622E` |
| `audit_sample.csv` | `591062CF58EDDE9A05BD3167B560E04BF631D55C8C056A1285142C6DB891D26E` |
| `metrics.json` | `5BBFBFDDBC944AE7F07F92095A7C54B590440C95690196F127151C9FC4752D26` |
| `report.md` | `9784D7109D96FD64D913417ECE973B4989F115AFA2D2A780B8B86886EB657D8D` |
| `manifest.json` | `9748C26F9AD47C97AE998132DDF71003DEC53770B233017078D3902E8CDCCDC8` |

自动产物位于 `reports/esm150_lora_repro_v0/`。复现命令和核验脚本命令见
`REPRO.md` 第四节的 F1 150M 小节。
