# 糖基化分析系统：以蛋白质语言模型预测 N-糖基化位点、以图神经网络解析糖链、并用工具调用智能体把两者串成一个可对话的分析工作台。

> 本科毕业设计（张驰，指导教师王老师）· 2026-10-27 第一次对齐
> 代码状态：W1 —— 环境、F1 数据集 v0、35M 线性探针与作者 150M LoRA 复算均已验证。
> 数据口径见 `reports/dataset_v0.md`，探针结果见 `reports/esm35_linear_probe_v0/report.md`，
> 150M 复算结论见 `reports/mcc_repro.md`。

## 它解决什么问题

糖基化是最常见、也最难预测的翻译后修饰之一。现有工具各管一段：位点预测器只告诉你"这里可能挂糖"，
糖链模型只回答"这条链是什么结构"，而真实科研问题往往是一句自然语言："这个蛋白哪些位点会挂
N-糖，挂上的糖链会不会影响它做受体？"

本项目把三条线接起来：

| 线 | 做什么 | 底座 |
|---|---|---|
| **F1 位点预测** | 给定蛋白序列，预测 N-X-S/T 位点是否真被糖基化 | ESM-2（35M 线性探针 / 150M LoRA） |
| **F2 糖链模型** | 给定糖链结构，预测其性质、判断单糖/糖苷键贡献 | RGCN（PyG 自实现） |
| **F3 工具调用智能体** | 把 F1/F2 与数据库查询包装成工具，用中文任务驱动 | Doc2Agent 路线 + MCP |

## 现在能跑什么

```powershell
# 环境自检：写 reports/env_check.md，并验证 GPU 真前向
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\env_check.py

# 接口体检：一次性打印 UniProt / GlyGen / GlyConnect / GlyTouCan / KEGG / PubChem 的可用性
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_endpoints.py

# 构建 F1 数据集 v0：UniProt 实验标注 → N-X-S/T 候选位点表（带缓存，复跑 0 次网络请求）
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\build_dataset.py

# 独立复算校验：不共享代码，从原始 JSON 缓存重推并逐字段对照（PASS 才退出 0）
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_dataset.py

# ESM-2 35M 线性探针：冻结 35M 主干，只训练逐位点分类头
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\run_esm35_linear_probe.py --cache-dir D:\wbworkspace\glyco-analysis\data\raw\uniprot --out-dir reports\esm35_linear_probe_v0 --allow-download

# 独立复算探针产物：重训每个折、重算指标并核对哈希
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_esm35_linear_probe.py --run-dir reports\esm35_linear_probe_v0 --cache-dir D:\wbworkspace\glyco-analysis\data\raw\uniprot

# ESM-2 150M 作者检查点全量复算：2554 行，FP32，全序列，batch size 1，SDPA
$env:PYTHONPATH = 'D:\uv\pylibs\lora-n-gly-peft014'
$env:HF_HOME = 'D:\hf'
$env:HF_HUB_OFFLINE = '1'
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\run_esm150_lora_repro.py --test-csv D:\wbworkspace\LoRA-N-Gly\data\N-GlycositeAltas\test.csv --adapter-dir D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint --base-model-revision a695f6045e2e32885fa60af20c13cb35398ce30c --attention-backend sdpa --out-dir reports\esm150_lora_repro_v0

# 独立复算 2554 行产物，并重跑 16 行审计样本
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_esm150_lora_repro.py --run-dir reports\esm150_lora_repro_v0 --test-csv D:\wbworkspace\LoRA-N-Gly\data\N-GlycositeAltas\test.csv --adapter-dir D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint --recheck-inference

# 同步到 GitHub：本机 git push 通道不通，发布走 REST API（需要 classic PAT 的 repo scope）
# 先把 token 写入 %USERPROFILE%\.github-token，或设置 GH_TOKEN；别把 token 写进仓库
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\publish_github.py --private
```

探针把 82 个含 `ECO:0000269` 的 N-linked 位点作为实验阳性，把 48 个没有 N-linked
标注的候选 sequon 作为对照，并排除 71 个仅有 `ECO:0000255` 的推断阳性。评估覆盖
130 行、28 个蛋白和 51 个唯一窗口。MCC 为 0.331975，按蛋白重采样 2000 次得到的
95% 区间为 [0.060051, 0.602824]。对照组是未标注样本，不是实验验证的阴性。

作者 150M 检查点在完整 `test.csv` 上的复算 MCC 为 **0.848348842859**，与论文
**0.848** 的差为 **+0.000348842859**。评估覆盖 2554 行、939 个蛋白和 963 条唯一序列，
保留 46 条非 sequon 行，没有截断或滑窗。独立 checker 启用推理复核后核对 16 行，
共 33294 条断言通过。

发布脚本会把本地历史逐 commit 重放到远端，并校验 commit SHA 与 tree SHA 都与本地一致，
不一致就报错退出；空仓库的首次提交由脚本自己播种。详见 `REPRO.md` 第四节。

远端：https://github.com/jostarooo/glyco-analysis （private，`main`）

环境事实见 `REPRO.md`，复现用的三个上游仓库在 `D:\wbworkspace\`（LoRA-N-Gly / GlycanML / Doc2Agent）。

## 目录

```
glyco-analysis/
├─ scripts/          可直接运行的脚本（环境、数据、探针、校验与发布）
├─ reports/          体检、数据集、探针产物与发布记录
├─ docs/             设计与说明
├─ data/             本地数据（不入库，见 .gitignore）
└─ REPRO.md          复现手册：可行性五关、术语表、本机配置
```

## 红线

- 前端不写死任何数字；
- 不用 Mock 冒真实功能；
- 演示版本 = 仓库最新提交；
- **论文里的数字只能作为对照，不能当成自己的结果**。

## 引用与许可

复现对象 `NancyFyong/LoRA-N-Gly` 仓库无 license，论文为 CC BY-NC-ND。
本项目仅作学习与研究用途，不用于商业分发。本仓库自身的许可待定（第一次对齐时与导师确认）。
