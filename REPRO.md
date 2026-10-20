# 复现手册（REPRO）

> 目标：任何人拿到这台机器或一台同类机器，能照本文件把三条线跑起来，并知道每个数字是怎么来的。
> 本文件随进度更新，**每次改动都写清日期与验证方式**。

## 一、可行性五关

五关按顺序过，前一关没过不进下一关。每关都留一个可检查的产物。

| # | 关卡 | 判据（可测） | 当前状态 | 产物 |
|---|---|---|---|---|
| 1 | **环境关** | Python 3.12 venv 可用；`torch.cuda.is_available()` 为真；在 GPU 上跑一次真实前向不报错 | ✅ 通过 | `reports/env_check.md` |
| 2 | **数据关** | UniProt 人类糖蛋白检索返回 1381 条；GlyGen 单蛋白详情可取；其余接口状态有记录 | ✅ 通过（4/6 可用） | `reports/endpoint_check_2026-10-18.md` |
| 3 | **复现关** | 作者 150M 检查点在作者 `test.csv` 上复算 MCC，与论文 0.848 对表并解释差异 | ⬜ 未开始 | `reports/mcc_repro.md` |
| 4 | **本机训练关** | ESM2-150M + LoRA 能在 6.6 GiB 可用显存内跑通若干步且 loss 下降 | ⬜ 未开始 | `reports/local_train.md` |
| 5 | **系统关** | 浏览器里能用真实后端结果完成一次"序列 → 位点 → 糖链"的端到端问答 | ⬜ 未开始 | 录屏 + `docs/demo.md` |

## 二、术语表

| 术语 | 含义 |
|---|---|
| **N-糖基化** | 糖链连接到天冬酰胺（N）侧链的修饰，几乎只发生在 **N-X-S/T** 序列模体上（X ≠ P） |
| **sequon** | 即 N-X-S/T 模体；有模体不等于真被糖基化，是否发生取决于酶与细胞环境 |
| **ESM-2** | Meta 的蛋白质语言模型家族（8M / 35M / 150M / 650M / 3B / 15B） |
| **线性探针** | 冻结语言模型，只在其表征上训一个简单分类器；便宜，作为基线 |
| **LoRA** | 低秩适配：冻结主干，只训少量低秩矩阵；显存友好 |
| **MCC** | Matthews 相关系数，类别不平衡下比准确率可靠；1 最好，0 等于随机 |
| **RGCN** | 关系图卷积网络，按边类型分别做卷积；糖链的糖苷键类型天然适合 |
| **MCP** | Model Context Protocol，把工具以标准协议暴露给智能体 |
| **commit 编号** | 每周视频开头必须展示的 `git log -1 --oneline` 输出，用来证明演示版本 |

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

## 四、三条线的复现入口

| 线 | 上游仓库 | 本地路径 | 本地形态 | 论文数字（只作对照） |
|---|---|---|---|
| F1 | `NancyFyong/LoRA-N-Gly` | `D:\wbworkspace\LoRA-N-Gly` | 必需文件快照，无 `.git`；commit `5838d51`；25 个文件；150M adapter 已校验 376 个张量 | 150M LoRA MCC **0.848**；35M 线性探针 **0.781** |
| F2 | `GlycanML/GlycanML` | `D:\wbworkspace\GlycanML` | 真 git clone；HEAD `9f392aa`；工作区 158 个文件；状态干净 | RGCN 复算 **0.948 / 0.780** |
| F3 | `coolkillercat/Doc2Agent` | `D:\wbworkspace\Doc2Agent` | 部分文件快照，无 `.git`；commit `3ff0da6`；18 个文件；上游约 1.4 GB | 50 道任务完成率对比 Table 3 |

> 网络约束：2026-10-18 实测 `raw.githubusercontent.com` 连接重置，GitHub git 智能协议对两个大仓库零字节卡死。
> 因 F1/F3 上游体积为 262 MB / 约 1.4 GB，先按 `UPSTREAM.md` 取复现必需文件。快照不能 `git pull`，补取入口写在各自目录的 `UPSTREAM.md`。

### F1 数据集 v0（2026-10-19）

```powershell
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\build_dataset.py    # 生成 reports/candidates_30*.csv
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_dataset.py    # 独立复算校验，PASS 才退出 0
```

30 个蛋白 / 201 个候选位点，UniProt release 2026_03；复跑 0 次网络请求且三个产物
SHA256 不变，校验器 1854 条断言全过。201 行中，82 行含 `ECO:0000269` 实验证据，
71 行仅含 `ECO:0000255` 推断证据，48 行没有 N-linked 标注。抽样口径、数据质量指标
与哈希表见 `reports/dataset_v0.md`。

### F1 ESM-2 35M 线性探针（2026-10-20）

探针固定 `facebook/esm2_t12_35M_UR50D` revision `6fbf070e65b0b7291e7bbcd451118c216cff79d8`，
冻结主干，只训练 `StandardScaler + LogisticRegression(C=1.0)`。每个候选位点取目标残基居中的
最多 1023 个残基窗口。长蛋白不截断目标，token 下标按 `1 + (pos - window_start)` 对齐。

```powershell
$python = 'D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe'
$cache = 'D:\wbworkspace\glyco-analysis\data\raw\uniprot'

& $python scripts\run_esm35_linear_probe.py --cache-dir $cache --out-dir reports\esm35_linear_probe_v0 --allow-download
& $python scripts\check_esm35_linear_probe.py --run-dir reports\esm35_linear_probe_v0 --cache-dir $cache
& $python -m unittest discover -s tests -p 'test_esm35_probe.py' -v
```

评估采用 leave-one-protein-out。探针排除 71 行仅有 `ECO:0000255` 的推断阳性，保留
82 行实验阳性和 48 行未标注对照，共 130 行、28 个蛋白。`P13611` 只有推断阳性，
因此整个蛋白退出本次评估。主结果如下：

| 指标 | 数值 |
|---|---:|
| MCC | 0.331975 |
| 实验阳性召回率 | 0.731707 |
| 未标注对照保持率 | 0.604167 |
| 阳性预测精确率 | 0.759494 |
| 弱标签一致率 | 0.684615 |
| ROC AUC | 0.756098 |
| 实验阳性 | 预测阳性=60，预测对照=22 |
| 未标注对照 | 预测阳性=19，预测对照=29 |

按蛋白做 2000 次重采样，MCC 的 95% 区间为 [0.060051, 0.602824]。该区间只描述这
28 个蛋白，不是泛化置信区间。完整口径、预测和窗口审计表见
`reports/esm35_linear_probe_v0/`。

### GitHub 发布

本机到 `github.com` 的 git 通道是被重置的（`Recv failure: Connection was reset`，代理端口 5899 也不再监听），
而 `api.github.com` 可达，所以发布固定走 `scripts/publish_github.py`：

```powershell
# classic PAT，必须有 repo scope；不要把 token 写进仓库
$env:GH_TOKEN = '<classic-pat>'      # 或写入 %USERPROFILE%\.github-token
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\publish_github.py --private
```

脚本做三件事：

1. 建仓（已存在则复用）；空仓库先用 Contents API 播种一个提交——否则 Git Data API 的所有写操作都会返回
   `409 Git Repository is empty.`（连 `POST /git/blobs` 也一样）；
2. 按 `git rev-list --reverse` 逐 commit 重放本地历史，镜像 tree、父提交、提交信息与作者/提交时间；
3. 逐项校验：blob SHA、每层 tree SHA、远端 ref，最后要求 **远端 HEAD 的 commit SHA 与本地完全相同**
   （提交信息结尾的换行要省掉再发，GitHub 会补一个，这样字节才能对齐）。

任何一项对不上就报错退出；发布记录写在 `reports/github_publish_<日期>.md`。

2026-10-18 状态：**已发布** → https://github.com/jostarooo/glyco-analysis
（private，`main` = `59c53b7`，与本地 `HEAD` 及 tree 逐字节一致，10 个文件）。

## 五、复现记录

| 日期 | 做了什么 | 验证方式 | 结果 |
|---|---|---|---|
| 2026-10-18 | 建 uv + Python 3.12 venv、装 cu128 torch、设 D 盘缓存 | `scripts/env_check.py`：CUDA 可用，sm_120，512×512 真前向最大误差 4.768e-05 | ✅ 通过 |
| 2026-10-18 | 体检 UniProt / GlyGen / GlyConnect / GlyTouCan / KEGG / PubChem | `scripts/check_endpoints.py`；UniProt 返回 1381，GlyGen 584 KB | ✅ 4/6；GlyConnect `500`，GlyTouCan `404` |
| 2026-10-18 | 建 GitHub 私有仓库并把本地两次提交镜像上去 | `scripts/publish_github.py --private`；远端 HEAD 与 tree 均与本地逐字节一致，10 个文件 | ✅ 通过 |
| 2026-10-19 | 构建 F1 数据集 v0（UniProt 实验标注 → 30 蛋白 / 201 候选位点，release 2026_03） | 复跑 0 次网络请求且三产物 SHA256 不变；`scripts/check_dataset.py` 独立复算 1854 断言全过 | ✅ 通过；口径见 `reports/dataset_v0.md` |
| 2026-10-20 | 跑通 F1 ESM-2 35M 冻结主干线性探针 | 13 个单元测试通过；独立 checker 重嵌入并核对 4021 条断言；MCC 0.331975，28 蛋白重采样区间 [0.060051, 0.602824] | ✅ 通过；产物见 `reports/esm35_linear_probe_v0/` |
