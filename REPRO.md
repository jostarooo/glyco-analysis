# 复现手册（REPRO）

> 目标：任何人拿到这台机器或一台同类机器，能照本文件把三条线跑起来，并知道每个数字是怎么来的。
> 本文件随进度更新，**每次改动都写清日期与验证方式**。

## 零、当前交付状态

### W1（2026-10-27 交付，2026-10-28 核记）

截至 2026-10-27 交付：W1 的代码与实验产物基线为 `db8f1d8`，正式周视频（`02-进度报告\第一周展示视频.mp4`，6 分 00 秒）展示 `6d19f1e`。交付包为 68 个内容文件、68/68 条校验一致（连同清单共 69 个文件），正式周目录为 76 个文件、75/75 条校验一致，不一致、缺失和格式错误均为 0。已于 2026-10-27 正式提交，交付总表已改 `已交`（2026-10-28 核记）。

本节的“当前状态”只描述交付材料，不覆盖各运行清单中记录的生成时基线。例如 35M 探针的生成基线仍是 `29f97a5`，不会被改写为交付当天的 HEAD。

### W2（交付日 2026-11-03，2026-10-29 核心实验收口）

W2 核心实验已完成。交接基线为 `8fc1da68b29a2cd865b3b5c056996b14607b9479`，W2 已提交单元为 `e776c5f`、`8fc1da6` 和 `6b77fa7`。截至本记录，W2 尚未执行远端发布，远端同步状态未确认。

GlycanML 五个 CSV 共 30675065 字节，MD5 全部通过。F2 按论文 Table 3 使用 seeds 0/1/2、50 epochs、batch 64 完成复算：免疫原性 AUPRC 为 0.7748635136784087 ± 0.009111853148723878，论文为 0.780 ± 0.006；糖基化 Macro-F1 为 0.9377928560029268 ± 0.0038891301525018625，论文为 0.948 ± 0.004。TorchDrug 未安装，本轮是 PyG 自实现，不是逐位克隆。

Doc2Agent 70 个 wrapper 中 43 个直接返回 `ok`，服务存活 61 个。W2 当天用通用探针把 50 道任务分为 20 道可直接完成、25 道需要替代工具、5 道受服务失败阻断。2026-10-30 W3 用任务参数重测 17 个阻断工具后，最新分类为 43/5/2，W2 原始 CSV 和 summary 保留为历史证据。Qwen3 4B 正式批次完成 50 题，`exact_sequence=19`、`all_expected_called=34`、`any_expected_called=41`、`tasks_with_final_answer=39`，110 次工具调用中 78 次成功。这些是轨迹指标，不是答案正确率。

### W3（交付日 2026-11-10，2026-10-31 记分卡与 web 界面收口）

W3 Day 1 的本地基线是 `985d8975799f254bad18f05a8fcf68682ff75a72`。2026-10-31
新增可重算记分卡，把 F1 MCC、F2 Table 3 两项指标、F3 五项轨迹计数和工具可行性
统一到 `reports/w3_day2/scorecard.json`、`scorecard.csv`、`scorecard.md`。
`scripts/build_w3_scorecard.py --check` 会从固定源产物重算并拒绝缺失、过期或被手改的输出。
W3 Day 3 新增 `web/` 交付界面，由 `scripts/build_web_data.py` 从 12 个真实产物生成数据契约，
构建与预览验证通过，提交 `797e560`。
本轮没有重跑 F2 训练，没有重跑 Qwen3 4B 50 题，也没有执行发布。

## 一、可行性五关（项目级，W1 只验收第 1 至第 3 关）

五关按顺序过，前一关没过不进下一关。每关都留一个可检查的产物。

| # | 关卡 | 判据（可测） | 当前状态 | 产物 |
|---|---|---|---|---|
| 1 | **环境关** | Python 3.12 虚拟环境可用；`torch.cuda.is_available()` 为真；在 GPU 上跑一次真实模型前向不报错 | ✅ 通过 | `reports/env_check.md` |
| 2 | **数据关** | UniProt 人类糖蛋白检索返回 1381 条；GlyGen 单蛋白详情可取；其余接口状态有记录 | ✅ 通过（4/6 可用） | `reports/endpoint_check_2026-10-18.md` |
| 3 | **复现关** | 作者 150M 检查点在作者 `test.csv` 上复算 MCC，与论文 0.848 对表并解释差异 | ✅ 通过 | `reports/mcc_repro.md` |
| 4 | **本机训练关** | ESM2-150M + LoRA 能在 6.6 GiB 可用显存内跑通若干步且损失下降 | ⬜ 未开始（后续周） | `reports/local_train.md` |
| 5 | **系统关** | 浏览器里能用真实后端结果完成一次"序列 → 位点 → 糖链"的端到端问答；W3 Day 3 已交付只读展示前端 | 🔶 部分通过 | `web/` + `scripts/build_web_data.py`；端到端问答仍待 `docs/demo.md` |

## 二、术语表

| 术语 | 含义 |
|---|---|
| **N-糖基化** | 糖链连接到天冬酰胺（N）侧链的修饰，几乎只发生在 **N-X-S/T** 序列模体上（X ≠ P） |
| **sequon** | 即 N-X-S/T 模体；有模体不等于真被糖基化，是否发生取决于酶与细胞环境 |
| **ESM-2** | Meta 的蛋白质语言模型家族（8M / 35M / 150M / 650M / 3B / 15B） |
| **线性探针** | 冻结语言模型，只在其表征上训一个简单分类器；便宜，作为基线 |
| **LoRA** | 低秩适配：冻结主干，只训少量低秩矩阵；显存友好 |
| **MCC** | 马修斯相关系数，类别不平衡下比准确率可靠；1 最好，0 等于随机 |
| **RGCN** | 关系图卷积网络，按边类型分别做卷积；糖链的糖苷键类型天然适合 |
| **MCP** | 模型上下文协议（Model Context Protocol），把工具按统一协议提供给智能体调用 |
| **提交编号（`commit`）** | 每周视频开头必须展示的 `git log -1 --oneline` 输出，用来证明演示版本 |

## 三、本机配置（2026-10-18 实测）

| 项 | 值 |
|---|---|
| 机型 / 系统 | ASUS TUF Gaming A16 FA608PM · Windows 11 专业版 build 26200 |
| CPU | AMD Ryzen 9 8940HX · 16 核 / 32 线程 |
| GPU | NVIDIA RTX 5060 Laptop，**sm_120**，总量 7.93 GiB；自检时可用 6.88 GiB，桌面/后台占用会明显波动 |
| 驱动 / CUDA | 617.42；PyTorch 用 **cu128** 轮子 |
| 内存 | 15.2 GiB（平常占 93~95%，不要开 CPU offload） |
| 磁盘 | C: 44.6 GB 可用 · D: 144.6 GB 可用（项目、缓存、模型全在 D） |
| Python | 3.12.14（uv 管理）· venv 在 `D:\wbworkspace\glyco-analysis\.venv` |
| PyTorch | **2.9.1+cu128** · `torch.version.cuda=12.8` · cuDNN 91002 · bf16 可用 |
| 环境变量 | `HF_HOME=D:\hf` · `HUGGINGFACE_HUB_CACHE=D:\hf\hub` · `HF_ENDPOINT=https://hf-mirror.com` · `TORCH_HOME=D:\torch` · `UV_CACHE_DIR=D:\uv\cache` |

2026-10-29 的 W2 收口环境另有两条限制：

- 项目 `.venv\Scripts\python.exe` 的 uv 启动器暂时找不到基础 Python。深度学习测试改用 `C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe`，并设置 `PYTHONPATH=D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages`。
- 不运行 `uv run`。本轮不重装 torch，也不重跑 F2 三种子训练或 Qwen3 4B 50 题。

## 四、三条线的复现入口

| 线 | 上游仓库 | 本地路径 | 本地形态 | 论文数字（只作对照） |
|---|---|---|---|
| F1 | `NancyFyong/LoRA-N-Gly` | `D:\wbworkspace\LoRA-N-Gly` | 必需文件快照，无 `.git`；提交 `5838d51`；25 个文件；150M 适配器已校验 376 个张量 | 150M LoRA MCC **0.848**；35M 线性探针 **0.781** |
| F2 | `GlycanML/GlycanML` | `D:\wbworkspace\GlycanML` | 完整 Git 克隆；HEAD `9f392aa`；工作区 158 个文件；状态干净 | RGCN 复算 **0.948 / 0.780** |
| F3 | `coolkillercat/Doc2Agent` | `D:\wbworkspace\Doc2Agent` | 部分文件快照，无 `.git`；提交 `3ff0da6`；18 个文件；上游约 1.4 GB | 50 道任务完成率对比表 3 |

> 网络约束：2026-10-18 实测 `raw.githubusercontent.com` 连接重置，GitHub git 智能协议对两个大仓库零字节卡死。
> 因 F1/F3 上游体积为 262 MB / 约 1.4 GB，先按 `UPSTREAM.md` 取复现必需文件。快照不能 `git pull`，补取入口写在各自目录的 `UPSTREAM.md`。

### F1 数据集 v0（2026-10-19）

```powershell
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\build_dataset.py    # 生成 reports/candidates_30*.csv
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_dataset.py    # 独立复算校验，通过（PASS）才退出 0
```

30 个蛋白 / 201 个候选位点，UniProt 发布版本 2026_03；复跑 0 次网络请求且三个产物
SHA256 不变，校验器 1854 条断言全过。201 行中，82 行含 `ECO:0000269` 实验证据，
71 行仅含 `ECO:0000255` 推断证据，48 行没有 N-linked 标注。抽样口径、数据质量指标
与哈希表见 `reports/dataset_v0.md`。

### F1 ESM-2 35M 线性探针（2026-10-20）

探针固定 `facebook/esm2_t12_35M_UR50D` 版本 `6fbf070e65b0b7291e7bbcd451118c216cff79d8`，
冻结主干，只训练 `StandardScaler + LogisticRegression(C=1.0)`。每个候选位点取目标残基居中的
最多 1023 个残基窗口。长蛋白不截断目标，词元下标按 `1 + (pos - window_start)` 对齐。

```powershell
$python = 'D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe'
$cache = 'D:\wbworkspace\glyco-analysis\data\raw\uniprot'

& $python scripts\run_esm35_linear_probe.py --cache-dir $cache --out-dir reports\esm35_linear_probe_v0 --allow-download
& $python scripts\check_esm35_linear_probe.py --run-dir reports\esm35_linear_probe_v0 --cache-dir $cache
& $python -m unittest discover -s tests -p 'test_esm35_probe.py' -v
```

评估采用留一蛋白交叉验证（`leave-one-protein-out`）。探针排除 71 行仅有 `ECO:0000255` 的推断阳性，保留
82 行实验阳性和 48 行未标注对照，共 130 行、28 个蛋白。`P13611` 只有推断阳性，
因此整个蛋白退出本次评估。主结果如下：

| 指标 | 数值 |
|---|---:|
| MCC | 0.331975 |
| 实验阳性召回率 | 0.731707 |
| 未标注样本保持率 | 0.604167 |
| 阳性预测精确率 | 0.759494 |
| 弱标签一致率 | 0.684615 |
| ROC AUC | 0.756098 |
| 实验阳性 | 预测阳性=60，预测对照=22 |
| 未标注对照 | 预测阳性=19，预测对照=29 |

按蛋白做 2000 次重采样，MCC 的 95% 区间为 [0.060051, 0.602824]。该区间只描述这
28 个蛋白，不是泛化置信区间。完整口径、预测和窗口审计表见
`reports/esm35_linear_probe_v0/`。

探针把产物拆成两次提交。第一次提交代码和校验逻辑，运行器在干净工作树上记录
`source.git_commit_role=pre_artifact_code_baseline` 与 `git_dirty=false`；第二次只提交
`reports/esm35_linear_probe_v0/` 下的生成文件。运行器查找最后一个改动产物目录之外文件的提交，
所以从只改产物的提交上重跑仍会得到同一份运行清单（`manifest`），不会把产物提交误当成代码基线。
校验器要求运行清单的基线等于这个提交，并要求基线之后产物目录外没有源码改动。

### F1 ESM-2 150M LoRA 作者检查点复算（2026-10-21）

复算对象是 `NancyFyong/LoRA-N-Gly` 发布的 150M PEFT 参数高效微调适配器。输入是作者
`test.csv` 的全部 2554 行，不删除非规范残基或非 sequon 行。执行口径固定为
FP32、完整序列、批大小为 1、无截断、无滑窗、两个输出分数（`logit`）取 `argmax`。

```powershell
$env:PYTHONPATH = 'D:\uv\pylibs\lora-n-gly-peft014'
$env:HF_HOME = 'D:\hf'
$env:HUGGINGFACE_HUB_CACHE = 'D:\hf\hub'
$env:HF_HUB_OFFLINE = '1'
$python = 'D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe'
$test = 'D:\wbworkspace\LoRA-N-Gly\data\N-GlycositeAltas\test.csv'
$adapter = 'D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint'

& $python scripts\run_esm150_lora_repro.py --test-csv $test --adapter-dir $adapter `
  --base-model-revision a695f6045e2e32885fa60af20c13cb35398ce30c `
  --attention-backend sdpa --out-dir reports\esm150_lora_repro_v0

& $python scripts\check_esm150_lora_repro.py --run-dir reports\esm150_lora_repro_v0 `
  --test-csv $test --adapter-dir $adapter `
  --base-model-revision a695f6045e2e32885fa60af20c13cb35398ce30c `
  --recheck-inference

& $python -m unittest discover -s tests -p 'test_*.py' -v
```

主结果如下：

| 指标 | 数值 |
|---|---:|
| MCC | 0.848348842859 |
| 论文 MCC | 0.848 |
| 差值 | +0.000348842859 |
| 准确率 | 0.923649177760 |
| 精确率 | 0.945967741935 |
| 召回率 | 0.901614142967 |
| 特异度 | 0.946528332003 |
| TP / FP / TN / FN | 1173 / 67 / 1186 / 128 |
| 行数 / 蛋白数 / 唯一序列数 | 2554 / 939 / 963 |
| 非 sequon 行 | 46 |
| 最长序列 | 5179 aa |
| 单次全量推理耗时 | 115.164377 秒 |

运行使用 RTX 5060 Laptop、PyTorch 2.9.1+cu128 和 SDPA 高效注意力路径。
运行清单记录 30/30 个旋转注意力模块被替换。这个耗时只描述本次单次运行，
不是与 `eager` 路径或作者环境的受控加速比。

独立核验脚本核对 2554 行预测、指标、产物哈希和 16 行推理重建，结果为
`PASS`、`33294` 条断言、`recheck_inference=true`。与 150M 相关的默认测试为 34 项；
关闭 GPU 门控时 33 项通过、1 项跳过。

产物保留了 PEFT 的一条缺失键告警。核对 `adapter_model.safetensors` 后确认，
当前实际使用的 `classifier.modules_to_save.default.out_proj` 中，基础权重、基础偏置、
LoRA A 和 LoRA B 都与检查点的有效键逐元素一致。告警中的
`classifier.original_module.out_proj` 是未激活的重复别名，不是漏载的有效权重。
完整证据与哈希见 `reports/mcc_repro.md`。

### F1 W1 三方法对拍（2026-10-22）

本阶段把 sequon 规则、ESM-2 35M 留一蛋白交叉验证预测与作者 150M 适配器
放到同一张 201 行候选表上。指标只使用 82 个实验阳性和 48 个未标注对照，共
130 行、28 个蛋白。71 个仅含 `ECO:0000255` 的推断阳性保留在展示表中，不进入
任何指标分母。

```powershell
$env:PYTHONPATH = 'D:\uv\pylibs\lora-n-gly-peft014'
$env:HF_HOME = 'D:\hf'
$env:HUGGINGFACE_HUB_CACHE = 'D:\hf\hub'
$env:HF_HUB_OFFLINE = '1'
$python = 'D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe'
$adapter = 'D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint'

& $python scripts\run_esm150_candidate_inference.py `
  --candidates reports\candidates_30_lora.csv `
  --adapter-dir $adapter `
  --base-model-revision a695f6045e2e32885fa60af20c13cb35398ce30c `
  --attention-backend sdpa `
  --out-dir reports\esm150_w1_candidates_v0

& $python scripts\run_w1_three_method.py `
  --out-dir reports\w1_three_method_v0

& $python scripts\check_w1_three_method.py `
  --comparison-dir reports\w1_three_method_v0
```

重跑生成器会把 `review_top10.csv` 的复核状态重置为 `PENDING_MANUAL_REVIEW`。2026-10-23
的复核结果已提交在 `reports/w1_three_method_v0/`，复现该结果时不要覆盖已提交的
`review_top10.csv` 和 `report.md`，只运行核验脚本。

实测结果如下：

| 方法 | 判定规则 | TP / FP / TN / FN | MCC | ROC AUC |
|---|---|---:|---:|---:|
| sequon 规则 | 201 行全部判阳性 | 82 / 48 / 0 / 0 | 0.000000 | 不适用 |
| ESM-2 35M 折外预测 | 已存概率大于等于 0.5 | 60 / 19 / 29 / 22 | 0.331975 | 0.756098 |
| ESM-2 150M 适配器 | 正类 `logit` 大于负类 `logit` | 71 / 48 / 0 / 11 | -0.232614 | 0.618140 |

150M 推理覆盖 201 行、29 个蛋白和 29 条唯一序列。运行清单固定了基座模型版本、
适配器 SHA256、376 个适配器张量、FP32、批大小为 1、完整序列、
无截断、无滑窗和 30/30 个 SDPA 模块。运行前工作树干净，运行清单记录
`git_dirty=false`。

不一致位点按六个方向分层，生成 `review_top10.csv`。10 行在生成时都是
`PENDING_MANUAL_REVIEW`。2026-10-23 完成人工复核：6 个实验阳性得到独立证据支持，
3 个未标注对照成为漏注释候选，1 个未找到独立证据。逐位点证据写入
`review_top10.csv` 的 `reviewer_note`，评估标签和指标保持不变。完整表、指标和哈希见
`reports/w1_three_method_v0/`。

当前核验脚本核对输入哈希、201 行连接、130 行指标、10 行复核选择与产物哈希，
返回 `status=PASS`。这个核验脚本没有二次重建 201 行 GPU 输出分数，因此
`inference_recheck=false`。2026-10-26 另对作者 150M `test.csv` 复算运行了
`check_esm150_lora_repro.py --recheck-inference`，结果为 `PASS`、33294 条断言、
16 行运行时抽样复核和 `inference_recheck=true`。完整默认测试为 57 项，其中 56 项通过、
1 项 GPU 门控跳过；单独启用 GPU 门控后该项通过。

### GitHub 发布

本机到 `github.com` 的 git 通道是被重置的（`Recv failure: Connection was reset`，代理端口 5899 也不再监听），
而 `api.github.com` 可达，所以发布固定走 `scripts/publish_github.py`：

```powershell
# 经典 PAT，必须包含 repo 权限范围；不要把访问令牌（token）写进仓库
$env:GH_TOKEN = '<classic-pat>'      # 或写入 %USERPROFILE%\.github-token
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\publish_github.py
```

脚本做三件事：

1. 建仓（已存在则复用）；空仓库先用 Contents API 播种一个提交——否则 Git Data API 的所有写操作都会返回
   `409 Git Repository is empty.`（连 `POST /git/blobs` 也一样）；
2. 按 `git rev-list --reverse` 逐提交重放本地历史，镜像目录树、父提交、提交信息与作者/提交时间；
3. 逐项校验：数据块 SHA、每层目录树 SHA、远端引用（`ref`），最后要求 **远端 HEAD 的提交 SHA 与本地完全相同**
   （提交信息结尾的换行要省掉再发，GitHub 会补一个，这样字节才能对齐）。

任何一项对不上就报错退出；发布记录写在 `reports/github_publish_<日期>.md`。脚本会重写远端 `main`，运行前必须确认这次发布是用户要求的。

2026-10-18 首次发布，2026-10-21 全量复现完成后再次镜像发布，2026-10-26 文档中文化
和最终校验完成后再次镜像发布。截至 2026-10-28 W1 核记，远端
https://github.com/jostarooo/glyco-analysis 为公开仓库，`main` 为 `e301353` 的网页 README 快照；
本地文档提交 `6d19f1e` 及其后的提交尚未镜像到远端，两边历史已经分叉。10/26 的发布记录是当时快照，
不再代表当前远端状态。
2026-10-29 W2 收口没有重新联网核实远端，也没有执行 push 或发布脚本。W2 的 `e776c5f`、`8fc1da6`、`6b77fa7` 及后续文档提交都只存在于本地。
后续交付记录中的历史 SHA 是当日发布快照，不代表当前交付状态；当前状态以本文第零节和交付总表为准。

### F2 GlycanML Table 3

```powershell
$python = 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe'
$env:PYTHONPATH = 'D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8 = '1'

& $python scripts\check_glycanml_data.py
& $python scripts\check_pyg_rgcn.py

# 正式训练较慢。除复核需要外，不重跑下面这条命令。
& $python scripts\train_glycanml_rgcn_pyg.py --seeds 0,1,2 --epochs 50 --batch-size 64 --out reports\w2_day1\glycanml_rgcn_recompute.json
```

F2 数据与结果分别以 `reports/w2_day1/glycanml_data_check.json` 和 `reports/w2_day1/glycanml_rgcn_recompute.json` 为准。`glycan_link` 的上游 URL 错指 `glycan_properties.csv`，该缺陷记录在 `docs/W2_D1_PyG_RGCN.txt`。上游 YAML 的 `num_class: 2` 与 CSV 的 N、O、free 三类不一致，训练按三类执行。

### F3 Doc2Agent 与 Qwen3 4B

```powershell
D:\python\python.exe scripts\summarize_doc2agent_run.py `
  --run-dir reports\w2_day2\f3_qwen3_4b_50 `
  --expected-tasks 50 `
  --check-summary reports\w2_day2\f3_qwen3_4b_50\summary.json

D:\python\python.exe scripts\classify_doc2agent_feasibility.py

$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8='1'
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\retest_doc2agent_blockers.py
```

正式 F3 批次是 `qwen3:4b` 的 50 题结果。`reports/w2_day2/f3_qwen3_8b_50_incomplete/` 是中断目录，不是成绩。上游 Claude 18/50 和 Qwen3 15/50 均由 GPT-4o 评分，本轮没有相同评分器，不能直接比较。

### web 数据契约（2026-10-31，W3 Day 3）

```powershell
$env:PYTHONUTF8 = '1'
D:\python\python.exe scripts\build_web_data.py
D:\python\python.exe scripts\build_web_data.py --check

cd /d D:\wbworkspace\glyco-analysis\web
D:\node\node.exe D:\node\node_modules\npm\bin\npm-cli.js run build
D:\node\node.exe D:\node\node_modules\npm\bin\npm-cli.js run preview
```

`scripts/build_web_data.py` 从 12 个真实产物生成 `web/src/data/{project,metrics,tools,boundaries}.json`，
记录每个源的相对路径、字节数和 SHA256，并在 `project.json` 写入当时 `git rev-parse HEAD`。
生成器不写运行时间，连续两跑输出必须字节一致；`--check` 在文件缺失、过期或被手改时退出 1。
`web/` 界面只读展示这些数据，不写死指标、不使用 Mock。构建命令为 `web/` 下的 `npm run build`，
预览命令为 `npm run preview`。本节是 REPRO.md 第 5 关系统关的第一个交付前端，端到端问答仍未完成。
### W3 可重算 F1/F2/F3 记分卡

```powershell
$env:PYTHONUTF8 = '1'
D:\python\python.exe scripts\build_w3_scorecard.py
D:\python\python.exe scripts\build_w3_scorecard.py --check
D:\python\python.exe -m unittest tests\test_w3_scorecard.py -v
```

`reference_values.json` 是人工核对的版本化输入，生成器不覆盖它。生成器会重新读取
八个固定证据源并记录相对路径、字节数和 SHA256；F1 混淆矩阵、MCC、F2 三种子聚合、
F3 计数上限、工具可行性题号集合和 Markdown 参考锚点都必须在同一轮校验中成立。
连续两跑必须字节一致且第二次不更新 mtime，手改任一输出后 `--check` 必须退出 1。
验证记录见 `reports/w3_day2/validation_2026-10-31.md`。

## 五、复现记录

| 日期 | 做了什么 | 验证方式 | 结果 |
|---|---|---|---|
| 2026-10-18 | 建 uv + Python 3.12 venv、装 cu128 torch、设 D 盘缓存 | `scripts/env_check.py`：CUDA 可用，sm_120，512×512 真前向最大误差 4.768e-05 | ✅ 通过 |
| 2026-10-18 | 体检 UniProt / GlyGen / GlyConnect / GlyTouCan / KEGG / PubChem | `scripts/check_endpoints.py`；UniProt 返回 1381，GlyGen 584 KB | ✅ 4/6；GlyConnect `500`，GlyTouCan `404` |
| 2026-10-18 | 建 GitHub 私有仓库并把本地两次提交镜像上去 | `scripts/publish_github.py --private`；远端 HEAD 与目录树均与本地逐字节一致，10 个文件 | ✅ 通过 |
| 2026-10-19 | 构建 F1 数据集 v0（UniProt 实验标注 → 30 蛋白 / 201 候选位点，发布版本 `2026_03`） | 复跑 0 次网络请求且三产物 SHA256 不变；`scripts/check_dataset.py` 独立复算 1854 断言全过 | ✅ 通过；口径见 `reports/dataset_v0.md` |
| 2026-10-20 | 跑通 F1 ESM-2 35M 冻结主干线性探针 | 13 个单元测试通过；独立核验脚本重嵌入并核对 4026 条断言；MCC 0.331975，28 蛋白重采样区间 [0.060051, 0.602824] | ✅ 通过；产物见 `reports/esm35_linear_probe_v0/` |
| 2026-10-21 | 复算作者 ESM-2 150M LoRA 检查点 | 2554 行全量推理；核验脚本启用 16 行推理复核并通过 33294 条断言；MCC 0.848348842859，论文值 0.848，差 +0.000348842859 | ✅ 通过；产物见 `reports/esm150_lora_repro_v0/` |
| 2026-10-22 | W1 三方法对拍与 10 个不一致位点选取 | 201 行推理；130 行指标；71 行仅展示；53 项测试通过、1 项 GPU 门控跳过；核验脚本返回 PASS | ✅ 通过；产物见 `reports/w1_three_method_v0/` |
| 2026-10-23 | W1 10 个不一致位点人工复核 | GlyGen 缓存证据逐条核对；6 个实验阳性得到独立支持、3 个漏注释候选、1 个未找到独立证据；核验脚本返回 PASS；56 项测试中 55 项通过、1 项 GPU 门控跳过 | ✅ 通过；证据写入 `review_top10.csv` 与 `report.md` |
| 2026-10-26 | 交付文档中文化与 150M 运行时复核 | 三份生成报告改为中文并重算运行清单；150M 核验脚本以 `--recheck-inference` 运行；完整默认测试 57 项，56 项通过、1 项 GPU 门控跳过 | ✅ 150M 核验脚本 `PASS`，33294 断言，16 行重算；单独启用 GPU 门控后该项通过 |
| 2026-10-26 | 周视频补入与交付状态同步 | 旧版周视频 3 分 34 秒（正式版自 2026-10-27 起为 6 分 00 秒新视频）；交付包与正式周目录完成 SHA256 校验；全部文档状态改为“材料已齐、等待正式提交” | ✅ 当时两套目录均为 `PASS`；2026-10-28 补记时已重算为 68/68 与 75/75 |
| 2026-10-27 | 交付日提交 | 用户放入改编版进度报告、6 分 00 秒正式周视频与日志总结，完成正式提交 | ✅ 用户确认已提交；交付总表改 `已交`；交付包清单重算 68/68（2026-10-28 核记） |
| 2026-10-28 | W2 Day 1：PyG RGCN、GlycanML 数据、Doc2Agent 盘点 | 5 个 CSV MD5 通过；F2 三种子完成；70 个 wrapper 与 50 道任务盘点完成 | ✅ 提交 `e776c5f`；产物见 `reports/w2_day1/` |
| 2026-10-29 | W2 Day 2：Qwen3 4B 50 题与可行性分类 | 50 个 task JSON 与 summary 重算一致；三分类 20/25/5 合计 50 | ✅ 运行提交 `8fc1da6`，分类提交 `6b77fa7`；产物见 `reports/w2_day2/` |
| 2026-10-30 | W3 Day 1：17 个阻断工具任务级复测 | 服务可达 17/17；工具体 13/1/2/1；50 题修正为 43/5/2 | 本地 W3 提交见当日 Git 历史；产物见 `reports/w3_day1/`，边界见 `docs/W3_D1_tool_blocker_triage.txt` |
| 2026-10-31 | W3 Day 2：F1/F2/F3 可重算记分卡 | 8 条指标与 43/5/2 从固定源重算；连续两跑字节一致；手改输出后 `--check` 返回 1；全量测试 99 项，98 项通过、1 项 GPU 门控跳过 | ✅ 生成与检查通过；产物见 `reports/w3_day2/`，验证见 `reports/w3_day2/validation_2026-10-31.md` |
| 2026-10-31 | W3 Day 3：web 交付界面数据契约 | 12 个源产物生成 4 个数据契约文件；build_web_data.py 连续两跑字节一致；web build 通过 | ✅ 生成与检查通过；产物见 `web/src/data/` 与 `scripts/build_web_data.py` |
