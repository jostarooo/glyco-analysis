# W3 Day5 11/10 检查点

Schema：`w3-day5-checkpoint-v1`。由 `scripts/build_w3_checkpoint.py` 从固定证据源生成，不含运行时间。

## F1 / F2 核心指标

| 指标 | 本地值 | 标准差 | 参考值 | 参考标准差 | 本地减参考 |
|---|---:|---:|---:|---:|---:|
| ESM-2 150M LoRA MCC | 0.848348842859293 |  | 0.848 |  | +0.000348842859292708 |
| 免疫原性 AUPRC | 0.774863513678409 | 0.00911185314872388 | 0.78 | 0.006 | -0.00513648632159136 |
| 糖基化 Macro-F1 | 0.937792856002927 | 0.00388913015250186 | 0.948 | 0.004 | -0.0102071439970731 |

## F3 三模型对照

| 模型 | exact | 全部期望工具 | 任一期望工具 | 有最终回答 | 工具成功/调用 | 正确/可判定 | 可判定覆盖 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3 4B (Ollama) | 19 | 34 | 41 | 39 | 78/110 | 9/38 | 38/50 |
| GLM-5.3 (Magpie) | 13 | 41 | 47 | 25 | 114/129 | 18/21 | 21/50 |
| DeepSeek-Flash (Qoder CN) | 13 | 42 | 48 | 22 | 115/148 | 15/20 | 20/50 |

F3 的列全部是工具轨迹或输出存在性指标。答案评分使用同一组 50 题、同一份 rubric、同一个
`workbuddy-ai/kimi-k3` judge，但不是上游 GPT-4o 评分，不能直接比较。

## W3 真实系统

- 样例：`O75144`，长度 302 aa。
- 候选位点：6 个，历史标签全部一致：true。
- 最大概率差：0。
- 冷启动墙钟：22.6363117000001 秒；纯推理：6.58867669999927 秒。
- 模型：`facebook/esm2_t30_150M_UR50D`，设备：`NVIDIA GeForce RTX 5060 Laptop GPU`。

## 回归

- unittest：201 项，193 通过，8 跳过。
- 耗时：41.026 秒。

## 来源与哈希

| 角色 | 路径 | SHA256 | 字节数 |
|---|---|---|---:|
| f1_metrics | `reports/esm150_lora_repro_v0/metrics.json` | `5bbfbfddbc944ae7f07f92095a7c54b590440c95690196f127151c9fc4752d26` | 473 |
| f2_recompute | `reports/w2_day1/glycanml_rgcn_recompute.json` | `546e5bb7bff0986bc4185d2671aec2ad2b92e7e4bc285e4c7a3d6aca8ac301b8` | 8125 |
| f2_references | `reports/w2_day4/reference_values.json` | `a59ff3dadcb5f88e3ee45489680a51c5db5553117d59279408d45c8a2bc4fbd8` | 1776 |
| f3_three_model | `reports/w3_day4/f3_three_model_report.json` | `d0f7d417bb478791b0f571c9af31877021738b97573c536d38007eceba99397f` | 197797 |
| system_e2e | `reports/w3_day1/real_e2e_2026-11-04.json` | `5b3c0edc019c1ef860b273f08b098aaa1dd598751a9ceefe7bd582caf936102b` | 2300 |
| validation | `reports/w3_day5/unittest_2026-11-08.txt` | `be5be000916c07e0b131d8bb0d650e15fd73fd91fb7d8d57e63c68879aa0d223` | 28852 |

## 口径边界

- F2 对齐 GlycanML 论文 Table 3，不是 Table 2；本地是 PyG 自实现，不是 TorchDrug 逐位克隆。
- F3 轨迹指标不是答案正确率；Kimi K3 是本地证据评分器，不等同于上游 GPT-4o。
- 每个模型只有一次固定 50 题运行，不能声称方差或模型大小因果。
- 系统只预测 N-X-S/T sequon，概率未做外部校准，不是实验证据或临床诊断。
