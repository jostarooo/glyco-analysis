# W3 Day 2 可重算记分卡

Schema：`w3-scorecard-v1`。由 `scripts/build_w3_scorecard.py` 从固定证据源生成，不包含运行时间。

差值方向统一为 `local_minus_reference`。只有 F1 MCC、F2 AUPRC、F2 Macro-F1 生成差值。

## 八条核心指标

| 指标 ID | 赛道 | 对象 | 指标 | 本地值 | 本地标准差 | 参考值 | 参考标准差 | 差值（本地减参考） | 比较状态 | 口径 |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| `f1.esm150_lora.mcc` | F1 | ESM-2 150M LoRA 作者检查点 | MCC | 0.8483488428592927 |  | 0.848 |  | +0.00034884285929270842 | comparable | 作者检查点复算；差值方向为本地减参考。 |
| `f2.immunogenicity.auprc` | F2 | GlycanML 免疫原性 | AUPRC | 0.7748635136784087 | 0.009111853148723878 | 0.78 | 0.006 | -0.0051364863215913603 | comparable | 论文 Table 3 RGCN 数值对照；本地为 PyG 自实现，不是 TorchDrug 逐位克隆。 |
| `f2.glycosylation.macro_f1` | F2 | GlycanML 糖基化 | Macro-F1 | 0.9377928560029268 | 0.0038891301525018625 | 0.948 | 0.004 | -0.01020714399707312 | comparable | 论文 Table 3 RGCN 数值对照；本地为 PyG 自实现，不是 TorchDrug 逐位克隆。 |
| `f3.qwen3_4b.exact_sequence` | F3 | Qwen3 4B，50 道任务 | 精确工具序列 | 19/50 |  |  |  | 不计算 | not_comparable | 工具轨迹或输出存在性，不是答案正确率。上游 Claude 18/50、Qwen3 15/50 使用 GPT-4o 评分，本轮未运行同一评分器，不能生成差值。 |
| `f3.qwen3_4b.all_expected_called` | F3 | Qwen3 4B，50 道任务 | 全部期望工具已调用 | 34/50 |  |  |  | 不计算 | not_comparable | 工具轨迹或输出存在性，不是答案正确率。上游 Claude 18/50、Qwen3 15/50 使用 GPT-4o 评分，本轮未运行同一评分器，不能生成差值。 |
| `f3.qwen3_4b.any_expected_called` | F3 | Qwen3 4B，50 道任务 | 任一期望工具已调用 | 41/50 |  |  |  | 不计算 | not_comparable | 工具轨迹或输出存在性，不是答案正确率。上游 Claude 18/50、Qwen3 15/50 使用 GPT-4o 评分，本轮未运行同一评分器，不能生成差值。 |
| `f3.qwen3_4b.tasks_with_final_answer` | F3 | Qwen3 4B，50 道任务 | 存在最终回答 | 39/50 |  |  |  | 不计算 | not_comparable | 工具轨迹或输出存在性，不是答案正确率。上游 Claude 18/50、Qwen3 15/50 使用 GPT-4o 评分，本轮未运行同一评分器，不能生成差值。 |
| `f3.qwen3_4b.tool_call_successes` | F3 | Qwen3 4B，50 道任务 | 工具调用成功数 | 78/110 |  |  |  | 不计算 | not_comparable | 工具轨迹或输出存在性，不是答案正确率。上游 Claude 18/50、Qwen3 15/50 使用 GPT-4o 评分，本轮未运行同一评分器，不能生成差值。 |

## 工具可行性

| 分类 | 题数 | task_id |
|---|---:|---|
| 当前工具可直接完成 | 43 | 1、2、3、4、6、7、8、9、10、11、12、13、14、15、16、17、18、19、22、23、24、25、26、27、29、30、31、32、33、34、35、36、37、38、39、40、41、42、43、44、45、47、49 |
| 需要替代工具 | 5 | 5、21、28、48、50 |
| 服务失败 | 2 | 20、46 |
| 合计 | 50 | 三类合计必须为 50 |

## 口径边界

- F2 对齐 GlycanML 论文 Table 3。本地是 PyG 自实现，不是 TorchDrug 逐位克隆，TorchDrug 未安装。
- F3 的 19/50、34/50、41/50、39/50、78/110 是工具轨迹或输出存在性，不是答案正确率。
- 上游 Claude 18/50 和 Qwen3 15/50 使用 GPT-4o 评分，本轮未运行同一评分器，不能直接比较或计算差值。
- W3 工具可行性是任务可用性分类，不是模型准确率。`get_proteins` 的 TLS 校验失败不等于服务死亡。
- `get_ligands` 返回 HTTP 200 空数组只说明服务可达，不代表任务可用。

## 来源与哈希

| 角色 | 路径 | SHA256 | 字节数 |
|---|---|---|---:|
| f1_metrics | `reports/esm150_lora_repro_v0/metrics.json` | `5bbfbfddbc944ae7f07f92095a7c54b590440c95690196f127151c9fc4752d26` | 473 |
| f2_recompute | `reports/w2_day1/glycanml_rgcn_recompute.json` | `546e5bb7bff0986bc4185d2671aec2ad2b92e7e4bc285e4c7a3d6aca8ac301b8` | 8125 |
| f3_summary | `reports/w2_day2/f3_qwen3_4b_50/summary.json` | `4ead0e26a15760a34450c55859679a5c5aeee4dd913014826540b77e5b7c66f4` | 497 |
| reference_mirror | `reports/w2_day2/f2_f3_comparison.md` | `e0b2abd858ee4a34bba577018ed3ccff8729605388b27d8def3e41392812ed17` | 7547 |
| w2_tool_summary | `reports/w2_day2/tool_feasibility_summary.json` | `ec28fa7607304395f7dbe4fb403fa0181bdbc7c93e514b31fd5c8acf34050229` | 2265 |
| feasibility_csv | `reports/w3_day1/task_feasibility_revised.csv` | `13e3c3cecf1c9dffdac3f1b9c552bed68a53b140b6889d752e8fc05abc4985ba` | 9616 |
| w3_recheck_summary | `reports/w3_day1/tool_blocker_recheck_summary.json` | `89e784ef12e60d59a20ea31524c97310ab75b7911e32e60eb5c1c7ea710f6675` | 14326 |
| reference_catalog | `reports/w3_day2/reference_values.json` | `2305b04608c052bdfefde29bc299c0aa150162ab8521e1a2c652aeeb0ee64f6e` | 1771 |
