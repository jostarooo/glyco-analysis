# W1 三方法对拍

## 结论

三种方法在同一批 201 个候选位点上判定。指标只使用 130 行可诚实评估的样本，其中实验阳性 82 行、未标注对照 48 行。仅含推断证据的 71 行保留展示，不进入指标分母。

ESM-2 35M 的 MCC 为 `0.331975`，作者 ESM-2 150M 适配器的 MCC 为 `-0.232614`，`sequon` 规则的 MCC 为 `0.000000`。35M 使用窗口化留一蛋白交叉验证（`leave-one-protein-out`），150M 使用完整序列适配器推理，所以两者差异同时包含模型规模、训练方式、适配器和输入上下文差异，不能只归因于模型大小。

## 评估边界

- 候选来源：201 行。
- 诚实指标池：130 行，由 82 个实验阳性和 48 个未标注对照组成，覆盖 28 个蛋白。
- 仅展示的推断阳性：71 行。这些行保留在 `comparison.csv`，评估标签为空，不进入任何指标分母。
- 对照是未标注 sequon，不是实验确认的生物学阴性。这里的 sequon 指 N-X-S/T 序列模体。
- UniProt N-连接糖基化标注是本基准评测的标签来源和参考上限，不是参与对拍的方法。

## 方法

| 方法 | 判定规则 | MCC | 阳性召回率 | 未标注对照保持率 | 阳性精确率 | 弱标签一致率 | ROC AUC |
|---|---|---:|---:|---:|---:|---:|---:|
| sequon 规则 | `sequon_rule`：201 行全部判为阳性 | 0.000000 | 1.000000 | 0.000000 | 0.630769 | 0.630769 | 不适用 |
| ESM-2 35M 折外预测 | `esm35_oof`：已存概率大于等于 0.5 | 0.331975 | 0.731707 | 0.604167 | 0.759494 | 0.684615 | 0.756098 |
| ESM-2 150M 作者适配器 | `esm150_author_adapter`：`logit_positive > logit_negative` | -0.232614 | 0.865854 | 0.000000 | 0.596639 | 0.546154 | 0.618140 |

表中反引号内是机器方法标识，保留原文便于对应 CSV 和 JSON 文件。

## 分歧分层

- `both_models_oppose_experimental_positive`：9 行诚实样本
- `both_models_call_unannotated_control_positive`：19 行诚实样本
- `esm35_opposes_experimental_positive`：13 行诚实样本
- `esm150_opposes_experimental_positive`：2 行诚实样本
- `esm35_calls_unannotated_control_positive`：0 行诚实样本
- `esm150_calls_unannotated_control_positive`：29 行诚实样本
- `all_agree`：58 行诚实样本

## 复核样本

选择策略为 `w1-disagreement-v1`：只从 130 行诚实样本池中选取，先在六个优先分层之间轮转，再按每层内的置信度差值降序，最后按 accession 与 pos 打破并列。

| 排名 | 位点 | 分歧分层 | UniProt 证据 | ESM-35M 概率 | ESM-150M 概率 | 置信差值 | 复核状态 |
|---:|---|---|---|---:|---:|---:|---|
| 1 | P04114:2982 | both_models_oppose_experimental_positive | ECO:0000269 | 0.335569 | 0.003845 | 0.992310 | SUPPORTED_EXPERIMENTAL_POSITIVE |
| 2 | Q6UWL2:470 | both_models_call_unannotated_control_positive | （无） | 0.650087 | 0.999982 | 0.999964 | NO_INDEPENDENT_EVIDENCE_FOUND |
| 3 | Q8TAV3:177 | esm35_opposes_experimental_positive | ECO:0000269 | 0.000016 | 0.999132 | 0.999969 | SUPPORTED_EXPERIMENTAL_POSITIVE |
| 4 | P04114:3358 | esm150_opposes_experimental_positive | ECO:0000269 | 0.644448 | 0.008536 | 0.982928 | SUPPORTED_EXPERIMENTAL_POSITIVE |
| 5 | Q6UWL2:503 | esm150_calls_unannotated_control_positive | （无） | 0.255392 | 0.999985 | 0.999969 | MISSED_ANNOTATION_CANDIDATE |
| 6 | P04114:3465 | both_models_oppose_experimental_positive | ECO:0000269 | 0.094834 | 0.005656 | 0.988688 | SUPPORTED_EXPERIMENTAL_POSITIVE |
| 7 | Q6UWL2:542 | both_models_call_unannotated_control_positive | （无） | 0.986805 | 0.999980 | 0.999960 | MISSED_ANNOTATION_CANDIDATE |
| 8 | P19827:285 | esm35_opposes_experimental_positive | ECO:0000269 | 0.010512 | 0.999975 | 0.978976 | SUPPORTED_EXPERIMENTAL_POSITIVE |
| 9 | P04114:185 | esm150_opposes_experimental_positive | ECO:0000269 | 0.864210 | 0.352208 | 0.295585 | SUPPORTED_EXPERIMENTAL_POSITIVE |
| 10 | Q6UWL2:308 | esm150_calls_unannotated_control_positive | （无） | 0.416532 | 0.999983 | 0.999966 | MISSED_ANNOTATION_CANDIDATE |

入选位点：`P04114:2982`, `Q6UWL2:470`, `Q8TAV3:177`, `P04114:3358`, `Q6UWL2:503`, `P04114:3465`, `Q6UWL2:542`, `P19827:285`, `P04114:185`, `Q6UWL2:308`。

运行器默认写入 `PENDING_MANUAL_REVIEW`。人工复核时只修改 `review_status` 与 `reviewer_note`，原始行序和数值字段保持不变。

本次复核未读取或使用作者回放预测作为输入。

### 人工复核结论

6 个实验阳性有独立证据支持：`P04114:2982`、`Q8TAV3:177`、`P04114:3358`、`P04114:3465`、`P19827:285`、`P04114:185`。证据包括 PubMed 32125861、20805301、26787547、14760718、19159218、16335952、23090970、9425062、9677337、29671580、37074911、29741879，GlyConnect 57 与 284，PDB 9BD1、9BD8、9BDE 与 9BDT，UniCarbKB GLY_000040，GPTwiki，PDC000471，以及 GlyGen GLY_000143 与 GLY_000481。

3 个未标注对照是注释复核候选：`Q6UWL2:308`（GlyGen 已报告，PubMed 24190977 与 GLY_000143，另有经 PubMed 37074911 关联的 PDC000471）、`Q6UWL2:503`、`Q6UWL2:542`。后两者只有 DOI `10.1101/2023.09.13.557529` 与数据提交 `GLY_000888` 的候选级证据，属于注释员复核候选，不是已确认的漏注释。本轮的基准评测标签与指标保持不变。

`Q6UWL2:470` 的复核状态为 `NO_INDEPENDENT_EVIDENCE_FOUND`。没有找到该模型阳性对照的精确位点记录，也没有独立文献或结构证据支持。这是缺少支持证据（absence of evidence），不是确认的生物学阴性。
