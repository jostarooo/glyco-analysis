# W2 F2/F3 对照与解释

日期：2026-10-29

本文只解释已经落盘的 W2 产物，不重新训练 F2，也不重跑 F3。所有结果都以仓库内 JSON、CSV 和逐题 task JSON 为准。

## 证据索引

| 用途 | 文件 |
|---|---|
| F2 三种子训练与聚合 | `reports/w2_day1/glycanml_rgcn_recompute.json` |
| GlycanML 五文件校验与 URL 修正记录 | `reports/w2_day1/glycanml_data_check.json`、`docs/W2_D1_PyG_RGCN.txt` |
| 70 个 wrapper 状态 | `reports/w2_day1/doc2agent_tools.csv`、`reports/w2_day1/doc2agent_tools_summary.json` |
| 50 道任务与期望工具 | `reports/w2_day1/doc2agent_tasks.csv`、`reports/w2_day1/doc2agent_tasks_summary.json` |
| F3 Qwen3 4B 正式批次 | `reports/w2_day2/f3_qwen3_4b_50/summary.json` 与 50 个 `task_*.json` |
| 本题工具可行性分类 | `reports/w2_day2/tool_feasibility.csv`、`reports/w2_day2/tool_feasibility_summary.json` |
| 2026-10-30 任务级阻断复测 | `reports/w3_day1/tool_blocker_recheck.csv`、`reports/w3_day1/tool_blocker_recheck_summary.json` |
| 2026-10-30 逐题修正分类 | `reports/w3_day1/task_feasibility_revised.csv`、`reports/w3_day1/task_feasibility_corrections.csv` |

## F2 对齐 GlycanML Table 3

本轮目标更正为此前交接中曾误写的 Table 2。当前目标是 GlycanML 论文 Table 3 的 RGCN 行：

| 任务 | 论文指标 | 本轮三种子均值与标准差 | 论文值减本轮均值 | 判断 |
|---|---:|---:|---:|---|
| 免疫原性 AUPRC | 0.780 ± 0.006 | 0.7748635136784087 ± 0.009111853148723878 | 0.0051364863215913 | 差值小于本轮三种子标准差 |
| 糖基化 Macro-F1 | 0.948 ± 0.004 | 0.9377928560029268 ± 0.0038891301525018625 | 0.0102071439970732 | 本轮低于论文，且差值大于本轮三种子标准差 |

免疫原性的三个测试 AUPRC 为 0.7832559324152325、0.7651717289430979、0.7761628796768958。糖基化的三个测试 Macro-F1 为 0.9407962109575013、0.9333997727074045、0.9391825843438747。这里的标准差是三种子样本标准差，不是置信区间，也没有做论文值与本地均值的显著性检验。

免疫原性测试 AUROC 为 0.9730666666666666 ± 0.0012858201014657124。糖基化测试准确率为 0.9613821138211381 ± 0.003520428470668453。两项是补充指标，不替换 Table 3 指定的 AUPRC 和 Macro-F1。

实现边界必须和数字一起报告：

- TorchDrug 未安装，本轮用 PyG 自实现按关系分通道的 RGCN。它与 TorchDrug 的 `RelationalGraphConv` 结构相关，但不是逐位克隆，因此没有可测量的数值差，也没有声称逐位复现论文实现。
- 上游 `link_RGCN.yaml` 把类别数写成 2，实际 CSV 有 N、O、free 三类。本轮按数据契约使用三类，这是有意修正，不是静默改数据。
- 固定口径为 seeds 0、1、2，50 epochs，batch 64。batch 256 在 7.93 GiB 显存的 RTX 5060 Laptop 上触发 CUDA OOM，所以正式结果使用 batch 64。
- 五个 GlycanML CSV 共 30675065 字节，MD5 全部通过。`glycan_link` 的上游 URL 错误指向 `glycan_properties.csv`，该上游缺陷以 `PASS_URL_FIX` 记录在 `docs/W2_D1_PyG_RGCN.txt`。

结论：免疫原性结果与论文 RGCN 行接近，糖基化 Macro-F1 低约 0.0102。这个差异可以用于说明本地 PyG 实现和论文实现不完全等价，但不能在没有 TorchDrug 对照运行的情况下归因到某一个实现细节。

## F3 是工具轨迹结果，不是答案正确率

正式批次是 `qwen3:4b`，50 道任务全部生成了 task JSON。运行参数为 `max_rounds=4`、`num_ctx=8192`、`num_predict=512`、`think=false`，总耗时 506.686 秒。

| 指标 | 数值 | 含义 |
|---|---:|---|
| `exact_sequence` | 19 / 50 | 实际调用工具名及顺序与期望步骤完全一致 |
| `all_expected_called` | 34 / 50 | 所有期望工具至少被调用一次，不要求顺序一致 |
| `any_expected_called` | 41 / 50 | 至少调用了一个期望工具 |
| `tasks_with_tool_call` | 50 / 50 | 每道题都产生了工具调用 |
| `tasks_with_final_answer` | 39 / 50 | 最终回答字段非空，不代表回答正确 |
| 工具调用成功 | 78 / 110 | 110 次调用中 78 次状态为 `ok` |

`exact_sequence=19` 和 `tasks_with_final_answer=39` 都不能写成“答对 19 题”或“答对 39 题”。它们分别衡量轨迹和输出是否存在，本轮没有运行与上游一致的 GPT-4o 答案评分器。上游目录记录 Claude 为 18/50、Qwen3 为 15/50，二者使用 GPT-4o 评分，因此和本轮 19/50 轨迹指标不是同一把尺子，不能直接比较高低。

`reports/w2_day2/f3_qwen3_8b_50_incomplete/` 是中断的 8B 调试目录，不是完整的 50 题成绩。`f3_qwen3_8b_smoke` 和 `f3_qwen3_8b_task31_768` 仅证明单题运行时可用，也不进入主结果。

## 50 道任务的当前工具可行性

分类以每题的期望 wrapper 状态为准。优先级为服务失败、需要替代工具、当前工具可直接完成。每题只保留一个主分类，三类合计必须为 50。

| 分类 | 题数 | task_id |
|---|---:|---|
| 当前工具可直接完成 | 20 | 2、4、7、8、9、17、19、22、24、25、26、27、29、30、33、38、39、43、45、49 |
| 需要替代工具 | 25 | 1、3、5、6、10、11、12、13、14、15、16、18、23、28、32、34、35、36、40、41、42、44、47、48、50 |
| 服务失败 | 5 | 20、21、31、37、46 |

70 个 wrapper 中 43 个直接返回 `ok`，服务存活为 61/70，即 0.8714。W2 当天把 `get_proteins` 探测失败、`convert_composition_to_wurcs` 返回 500、`convert_composition_text_to_wurcs_format` 返回 424 等行为归入服务失败类；包装器契约、参数或返回格式问题使另外 25 题需要替代工具。当前工具可直接完成只表示期望 wrapper 都返回 `ok`，不表示模型一定理解问题或答案正确。W3 已证明 `get_proteins` 是 TLS 校验问题，不是站点不可达。

### 2026-10-30 W3 任务级修正

上面的 20/25/5 是 W2 当天的历史分类，原始 CSV 和 summary 不改写。W3 用任务问题中的参数重测 17 个阻断工具后，最新分类为 43/5/2：

| 最新分类 | 题数 | task_id |
|---|---:|---|
| 当前工具可直接完成 | 43 | 原 20 题，加上 1、3、6、10、11、12、13、14、15、16、18、23、31、32、34、35、36、37、40、41、42、44、47 |
| 需要替代工具 | 5 | 5、21、28、48、50 |
| 服务失败 | 2 | 20、46 |
| 合计 | 50 | `reports/w3_day1/task_feasibility_revised.csv` |

17 个阻断工具中，服务可达 17 个，默认传输成功 16 个。13 个工具在合法参数下直接通过，1 个任务需要拆查询，2 个仍有接口契约问题，1 个默认 TLS 校验失败。`get_ligands` 返回 HTTP 200 和空数组，因此不能把“可达”写成“任务可用”。`get_proteins` 的 `verify=False` 诊断请求返回 HTTP 200，因此 task 20、46 记录为默认传输失败，不记录为服务死亡，也不把关闭 TLS 校验当作生产修复。

## 对 W3 的直接含义

1. F3 下一步先修工具目录和参数契约，再讨论模型能力。当前有 30 道题被至少一个非 `ok` wrapper 阻断。
2. 需要补一个与上游一致的答案评分器，才能报告 F3 的答案正确率，并把 Claude、Qwen3 与本地结果放在同一口径下。
3. F2 下一轮应做受控消融，优先比较关系通道、池化方式和 batch 64 下的稳定性，不应把当前差异只归因到 PyG 或 TorchDrug。
