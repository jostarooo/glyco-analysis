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

### GitHub 发布

本机 `git push` 到 GitHub 的传输不稳定，项目仓库用 `POST /user/repos` + Git Data API 发布：

```powershell
# classic PAT，必须有 repo scope；不要把 token 写进仓库
$env:GH_TOKEN = '<classic-pat>'
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\publish_github.py --private
```

脚本会逐 blob 校验本地与远端 SHA，再比较 tree SHA 和远端 branch，不使用 force push。
2026-10-18 当前状态：**本地提交已完成，远端尚未发布，等待可用 token**。

## 五、复现记录

| 日期 | 做了什么 | 验证方式 | 结果 |
|---|---|---|---|
| 2026-10-18 | 建 uv + Python 3.12 venv、装 cu128 torch、设 D 盘缓存 | `scripts/env_check.py`：CUDA 可用，sm_120，512×512 真前向最大误差 4.768e-05 | ✅ 通过 |
| 2026-10-18 | 体检 UniProt / GlyGen / GlyConnect / GlyTouCan / KEGG / PubChem | `scripts/check_endpoints.py`；UniProt 返回 1381，GlyGen 584 KB | ✅ 4/6；GlyConnect `500`，GlyTouCan `404` |
