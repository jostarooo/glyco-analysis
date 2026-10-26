# F1 数据集 v0（2026-10-19）

> 目的：给 F1（N-糖基化位点预测）准备第一个可复现数据集。一行 = 一个 N-X-S/T 候选位点，
> 标注来自 UniProt，既不是模型预测，也不是论文里的数字。标注包含实验证据和推断证据，
> 下游训练必须按证据类型区分。
> 构建：`scripts/build_dataset.py`；独立校验：`scripts/check_dataset.py`（与构建器不共享代码，PASS 才退出 0）。

## 1. 来源与抽样

| 项 | 值 |
|---|---|
| 来源 | UniProtKB REST：`(organism_id:9606) AND (reviewed:true) AND (ft_carbohyd_exp:*)` |
| 发布版本（`Release`） | **2026_03**（响应头 `X-UniProt-Release`，可追溯） |
| 候选池 | 1381 条 reviewed 人类蛋白 |
| 抽样 | 清单**先排序**，再 `random.Random(20261020).sample(pool, 30)`；seed / 条数 / 样本身份全部落进 `dataset_v0_stats.json` |
| 原始缓存 | `data/raw/uniprot/`（不入库）；`fetched_at` 取自缓存文件 mtime，因此重跑逐字节一致 |

抽样前必须先对清单排序：UniProt 返回顺序不是字符串序（`A6NMZ7` 排在 `A6NH11` 前），
不排序时样本会随上游返回顺序漂移（实测两种顺序下 30 条里只有 2 条相同）。

## 2. 产物与哈希

| 文件 | 说明 |
|---|---|
| `reports/candidates_30.csv` | 主表，13 列 / 201 行；(accession, pos) 唯一 |
| `reports/candidates_30_lora.csv` | 作者 `test.csv` 形状 `label,id,pos,sequence`，可直接喂作者代码 |
| `reports/dataset_v0_stats.json` | 运行统计：seed、抽样清单、行数、缓存计数 |

```text
candidates_30.csv        A584C3814226B7287807676F65D5CFFE2F5D47A53BC00476A4B9945CB0719F1C
candidates_30_lora.csv   DBD51D28ABC0B0C74E78496E0A8F54CEBAA1C29F274B6E6B2716E39631A09FAB
dataset_v0_stats.json    245A621104B4F056143FF4E249DBE371DD7EE7BA786156FACBA010169A190E12
```

两个 CSV 均为 UTF-8 无 BOM、LF 换行、末尾带换行。

## 3. 统计

| 指标 | 值 |
|---|---|
| 蛋白 | 30 |
| 候选位点行 | **201** |
| label=1 | **153**（82 行含 `ECO:0000269`，71 行仅含 `ECO:0000255`） |
| label=0 | **48**（有 sequon，无 N-linked 标注） |
| 有实验阳性的蛋白 | 29 / 30 |
| 模体外 N-linked 声明 | 1（见 §5） |

- 201 = 全序列**所有** N-X-S/T 起点（含重叠 sequon）。非重叠扫描只会给出 200，
  漏掉的是 `P40879` 165 位 `NSS`——UniProt 有实验证据的真阳性，不能丢。
- 唯一的 0 候选蛋白是 `P01563`（干扰素 α-2，188 aa）：序列里没有任何 `sequon`，
  它的糖基化是 O-连接（T129，实验证据）。这解释了为什么“有实验糖基化证据”的蛋白
  不一定贡献 N-linked 候选。

## 4. 列口径（主表）

| 列 | 口径 |
|---|---|
| `pos` | **1-based**，与作者数据、UniProt feature 一致；该位残基 = `sequence[pos-1]` |
| `motif` / `sequon` | 该位点起 3 字符（如 `NLS`）；候选集只收模体位点，故 `sequon` 恒为 1 |
| `label` | 1 ⇔ UniProt 在该位有 N-linked 糖基化 feature 且该位残基为 N；否则 0。label=1 包含 82 行 `ECO:0000269` 实验证据和 71 行仅含 `ECO:0000255` 的推断证据 |
| `linkage` | `label=1` 时为 N-连接（`N-linked`）；`label=0` 留空 |
| `n_features` | 该 pos 上原始 Glycosylation feature 条数（冗余度；同一位最大见过 28 条） |
| `evidence` | 该 pos 全部证据码，去重排序后以 `;` 连接 |
| `uniprot_release` / `fetched_at` | `2026_03`；缓存文件 mtime（UTC） |

## 5. 数据质量与注意事项

- **`label=0` 只代表“有模体、UniProt 无 N-连接标注”，不代表已证明不糖基化。**
  训练与评估都不能把 0 当负例真值；与作者数据对齐时必须交代这一口径。
- **不能把 71 行 `ECO:0000255` 当作实验阳性。** ESM-2 35M 探针只保留 82 行
  `ECO:0000269` 实验阳性和 48 行未标注对照，排除 71 行推断阳性。`P13611`
  只有推断阳性，因此整个蛋白不进入探针评估。
- UniProt 实验标注自身有噪声：本样本有 1 处模体外 N-linked 声明（`P01877` 327 位，
  残基是 D，既非 N 也不在 sequon 上）。它**不进候选集**，只作为数据质量指标统计
  （`off_sequon_n_linked_total=1`）。上游 LoRA-N-Gly 的 CSV 里约 2% 的行同样不满足
  模体（test.csv 49/2554、test-hard 11/513），说明这类噪声贯穿两个数据源。
- 同一位置可能有多种连接类型的冗余记录；只有“连接类型与残基一致”（N-连接到 N、
  O-连接到 S/T）的记录才计入 `label`。`P19827` 60 位是 S-连接（半胱氨酸），不索引。
- 10/22 复算作者 MCC 时**必须原样使用作者 `test.csv`**（含约 2% 非模体行），
  否则数字对不上 0.848。这是纪律，不是可选项。

## 6. 复现

```powershell
$env:PYTHONUTF8='1'
cd D:\wbworkspace\glyco-analysis
& .\.venv\Scripts\python.exe scripts\build_dataset.py    # 首次联网 31 次请求；复跑 0 次
& .\.venv\Scripts\python.exe scripts\check_dataset.py    # 独立复算，PASS 才退出 0
```

- 2026-10-19 实测：第二次运行“网络请求 0 次，缓存命中 31 次”，三个产物 SHA256 与
  第一次完全相同；校验器结论 `PASS`（1854 条断言全过）。
- 校验器修复记录：当天首跑 FAIL 1 条（`P40879#165` 被判为「多出的候选位点」），
  定性为校验器的重叠匹配 bug（普通 `finditer` 非重叠扫描吞掉 `NNSS` 的第 2 个起点），
  改为前瞻写法后 PASS。构建器的候选集口径（枚举全部重叠起点）是正确口径。

## 7. 与作者数据形状对照 / 下一步

| 项 | 作者 `test.csv` | 本数据集 |
|---|---|---|
| 列 | `label,id,pos,sequence` | 同（`candidates_30_lora.csv`） |
| pos | 1-based | 1-based |
| 行 | 2554 | 201 |

下一步：10/22 用作者 150M 检查点在作者 `test.csv` 上复算 MCC（对表 0.848），
随后本机 LoRA 训练冒烟；本数据集随 W01 交付。
