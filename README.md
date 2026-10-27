# 糖基化分析系统：以蛋白质语言模型预测 N-糖基化位点、以图神经网络解析糖链、并用工具调用智能体把两者串成一个可对话的分析工作台

> 2026-10-27 第一次对齐
> 代码状态：W1 的环境、数据集 v0、35M 线性探针、作者 150M LoRA 复算、三方法对拍和 10 个分歧位点人工复核均已完成。
> 数据口径见 `reports/dataset_v0.md`，探针结果见 `reports/esm35_linear_probe_v0/report.md`，
> 150M 复算结论见 `reports/mcc_repro.md`，候选位点对拍见 `reports/w1_three_method_v0/report.md`。

## 教师建议阅读顺序

1. 先读 `reports/weekly/W01_2026-10-27_progress.md`，了解本周完成项、指标和剩余动作。
2. 再读 `reports/w1_three_method_v0/report.md`，核对三种方法、130 行评估池和 10 个分歧位点。
3. 接着读 `reports/esm150_lora_repro_v0/report.md`，核对作者 `test.csv` 上的 MCC 复算。
4. 需要复查原始证据时读 `reports/mcc_repro.md` 和 `reports/esm150_lora_recheck_2026-10-26.md`。
5. 需要重跑时读 `REPRO.md`；其中的命令与 `scripts/` 内脚本一一对应。

文档、标题、表头和人工复核说明均使用中文。代码标识、JSON 与 CSV 字段名、状态枚举、模型名、路径、命令和原始软件告警保留英文，确保机器复核和哈希追溯不被破坏。

## 文档中的术语

| 术语（代码标识） | 在本文档中的含义 |
|---|---|
| 马修斯相关系数（`MCC`） | 综合阳性与阴性两侧的分类质量；1 最好，0 接近随机 |
| 序列模体（`sequon`） | N-X-S/T 序列片段，其中 X 不是脯氨酸 |
| LoRA 适配器（`adapter`） | 低秩适配器，保存作者训练得到的少量可训练参数 |
| 运行清单（`manifest`） | 记录输入、环境、设置和每个产物哈希的文件 |
| 独立核验脚本（`checker`） | 重新计算指标并核对产物，不依赖生成器自报 |
| 运行时复核（`runtime recheck`） | 重新加载模型前向若干审计样本，验证推理路径仍可运行 |
| 留一蛋白折外预测（`OOF`） | 每次留出一个蛋白做测试，汇总各折的折外预测 |
| 参数高效微调（`PEFT`） | 只更新少量参数即可适配大模型的微调方法；本项目用它加载作者 LoRA 检查点 |
| 受试者工作特征曲线下面积（`ROC AUC`） | 按概率排序计算的正负样本区分度；0.5 接近随机 |
| 混淆矩阵计数（`TP` / `FP` / `TN` / `FN`） | 真阳性、假阳性、真阴性、假阴性 |
| 模型上下文协议（`MCP`） | 把外部工具按统一协议提供给智能体调用的接口标准 |
| 缺少支持证据 | 没有找到支持证据，不等于已经证明该位点不糖基化 |

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

## 交付前检查

```powershell
$env:PYTHONPATH = 'D:\uv\pylibs\lora-n-gly-peft014'
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_w1_three_method.py --comparison-dir reports\w1_three_method_v0
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_esm150_lora_repro.py --run-dir reports\esm150_lora_repro_v0 --test-csv D:\wbworkspace\LoRA-N-Gly\data\N-GlycositeAltas\test.csv --adapter-dir D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint --base-model-revision a695f6045e2e32885fa60af20c13cb35398ce30c --recheck-inference
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

`scripts/build_w1_delivery.py --sync` 会把仓库内的报告、源代码和正式周附件同步到交付目录，随后重算 `SHA256SUMS.txt`。脚本会保留“视频待补入”状态，不会把目录误标成已完成。

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

# ESM-2 150M 作者检查点全量复算：2554 行，FP32，全序列，批大小为 1，SDPA
$env:PYTHONPATH = 'D:\uv\pylibs\lora-n-gly-peft014'
$env:HF_HOME = 'D:\hf'
$env:HF_HUB_OFFLINE = '1'
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\run_esm150_lora_repro.py --test-csv D:\wbworkspace\LoRA-N-Gly\data\N-GlycositeAltas\test.csv --adapter-dir D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint --base-model-revision a695f6045e2e32885fa60af20c13cb35398ce30c --attention-backend sdpa --out-dir reports\esm150_lora_repro_v0

# 独立复算 2554 行产物，并重跑 16 行审计样本
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_esm150_lora_repro.py --run-dir reports\esm150_lora_repro_v0 --test-csv D:\wbworkspace\LoRA-N-Gly\data\N-GlycositeAltas\test.csv --adapter-dir D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint --recheck-inference

# W1 三方法对拍：201 个候选位点跑作者 150M LoRA 适配器，再与 35M 折外预测和 sequon 规则合并
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\run_esm150_candidate_inference.py --candidates reports\candidates_30_lora.csv --adapter-dir D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint --base-model-revision a695f6045e2e32885fa60af20c13cb35398ce30c --attention-backend sdpa --out-dir reports\esm150_w1_candidates_v0
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\run_w1_three_method.py --out-dir reports\w1_three_method_v0
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_w1_three_method.py --comparison-dir reports\w1_three_method_v0

# 同步到 GitHub：本机 git push 通道不通，发布走 REST API（需要经典 PAT 的 `repo` 权限范围）
# 先把 token 写入 %USERPROFILE%\.github-token，或设置 GH_TOKEN；别把 token 写进仓库
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\publish_github.py --private
```

探针把 82 个含 `ECO:0000269` 的 N-连接糖基化位点作为实验阳性，把 48 个没有 N-连接
标注的候选 sequon 作为对照，并排除 71 个仅有 `ECO:0000255` 的推断阳性。评估覆盖
130 行、28 个蛋白和 51 个唯一窗口。MCC 为 0.331975，按蛋白重采样 2000 次得到的
95% 区间为 [0.060051, 0.602824]。对照组是未标注样本，不是实验验证的阴性。

作者 150M 检查点在完整 `test.csv` 上的复算 MCC 为 **0.848348842859**，与论文
**0.848** 的差为 **+0.000348842859**。评估覆盖 2554 行、939 个蛋白和 963 条唯一序列，
保留 46 条非 sequon 行，没有截断或滑窗。独立核验脚本启用推理复核后核对 16 行，
共 33294 条断言通过。

W1 三方法对拍在同一批 201 个候选位点上保留了 71 个仅含 `ECO:0000255` 的推断阳性，
但所有指标只使用 130 行诚实子集。ESM-2 35M 的留一蛋白交叉验证 MCC 为
**0.331975**，作者 150M LoRA 适配器的全序列 MCC 为 **-0.232614**，sequon 规则固定全判阳性，
MCC 为 **0.000000**。35M 使用窗口化折外预测，150M 使用全序列 LoRA 适配器推理，因此差异不能
只归因于模型大小。对拍另生成 10 个不一致位点，2026-10-23 完成人工复核：6 个实验阳性
得到独立证据支持，3 个未标注对照成为漏注释候选，1 个未找到独立证据。逐位点证据写入
`review_top10.csv`，评估标签和指标保持不变。

发布脚本会把本地历史逐提交重放到远端，并校验提交 SHA 与目录树 SHA 都与本地一致，
不一致就报错退出；空仓库的首次提交由脚本自己播种。详见 `REPRO.md` 第四节。

远端：https://github.com/jostarooo/glyco-analysis （私有仓库，`main`）

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

复现对象 `NancyFyong/LoRA-N-Gly` 仓库无许可证（`license`），论文为 CC BY-NC-ND。
本项目仅作学习与研究用途，不用于商业分发。
