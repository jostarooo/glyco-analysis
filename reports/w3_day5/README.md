# W3 Day 5：11/10 检查点

日期：2026-11-08

本目录把 W3 已完成的真实结果收束成一份可离线复核的检查点。生成器不重新训练模型，
也不重新运行 Doc2Agent 50 题，只从固定证据源读取并校验。

## 产物

- `checkpoint.json`：机器可读检查点，包含 F1、F2、F3、真实系统、测试计数和全部源哈希。
- `checkpoint.md`：同一检查点的人类可读版本。
- `unittest_2026-11-08.txt`：全量 unittest 原始输出。
- `validation_2026-11-08.md`：本轮验证记录。

## 生成

```powershell
$env:PYTHONUTF8='1'
D:\python\python.exe scripts\build_w3_checkpoint.py
D:\python\python.exe scripts\build_w3_checkpoint.py --check
```

`--check` 会重新读取固定源产物并比较输出。源文件缺失、指标内部不一致、F3 被写成
上游 GPT-4o 等价评分、系统结果声称截断推理，或输出被手改时，检查会失败。

## 固定源

| 角色 | 路径 |
|---|---|
| F1 指标 | `reports/esm150_lora_repro_v0/metrics.json` |
| F2 复算 | `reports/w2_day1/glycanml_rgcn_recompute.json` |
| F2 论文参考 | `reports/w2_day4/reference_values.json` |
| F3 三模型 | `reports/w3_day4/f3_three_model_report.json` |
| W3 真实系统 | `reports/w3_day1/real_e2e_2026-11-04.json` |
| 回归测试 | `reports/w3_day5/unittest_2026-11-08.txt` |

## 口径

- F2 对齐 GlycanML 论文 Table 3，不是 Table 2。
- 本地 F2 是 PyG 自实现，不是 TorchDrug 逐位克隆。
- F3 轨迹数字不是答案正确率。
- Kimi K3 是本地证据评分器，`upstream_gpt4o_equivalent=false`。
- 每个模型只有一次固定 50 题运行，不能声称方差或模型大小因果。
- 系统只预测 N-X-S/T sequon，不是实验证据或临床诊断。
