# W02 周视频脚本（3 至 5 分钟）

交付日：2026-11-03

建议控制总时长 4 分 20 秒。录制前关闭无关窗口，提前打开仓库根目录和交付目录。

## 0:00 至 0:20 展示最新 commit

画面：PowerShell 位于 `D:\wbworkspace\glyco-analysis`，终端字号放大。

操作：

```powershell
git -C D:\wbworkspace\glyco-analysis rev-parse HEAD
git -C D:\wbworkspace\glyco-analysis log -1 --oneline
git -C D:\wbworkspace\glyco-analysis status --short
```

旁白：

“这是第二周周视频。录制前仓库最新提交是屏幕上的完整 SHA，短 SHA 为屏幕第二行。工作树没有未提交改动。本周没有 push，也没有改写远端。”

注意：录制时必须重新执行这两条命令，不能照读本文件里的旧 SHA。

## 0:20 至 0:45 本周目标与 W1 状态

画面：打开 `reports/weekly/W02_2026-11-03_progress.md` 的第一节。

旁白：

“第一周已于 10 月 27 日提交。第二周的目标是把三条线从能跑推进到可对照、可解释。五项核心任务是 PyG RGCN 路线、GlycanML 数据核验、F2 Table 3 三种子复算、Doc2Agent 工具与任务盘点，以及 Qwen3 4B 的 50 题轨迹基线。”

## 0:45 至 1:45 F2 Table 3

画面：打开 `reports/w2_day1/glycanml_rgcn_recompute.json`，定位两个 `aggregate` 字段。

旁白：

“F2 对齐的是论文 Table 3，不是 Table 2。使用 0、1、2 三个种子，每个 50 个 epoch，batch size 64。batch 256 会在本机 7.93 GiB 显存上 OOM。”

“免疫原性 AUPRC 是 0.7748635，三种子标准差 0.0091119，论文是 0.780 加减 0.006。糖基化 Macro-F1 是 0.9377929，标准差 0.0038891，论文是 0.948 加减 0.004。免疫原性接近论文，糖基化低约 0.0102。”

“本轮选的是 PyG 自实现 RGCN。TorchDrug 没有安装，所以不能声称和 TorchDrug 逐位一致，也没有虚构数值差。”

画面可短暂切到 `reports/w2_day2/f2_f3_comparison.md` 的 Table 3 对照表。

## 1:45 至 2:30 Doc2Agent 工具盘点

画面：打开 `reports/w2_day1/doc2agent_tools_summary.json`，再打开 `reports/w2_day2/tool_feasibility_summary.json`。

旁白：

“Doc2Agent 共盘点 70 个 wrapper，43 个直接成功，服务存活 61 个。50 道任务里，20 道当前的期望工具全部正常，25 道需要替代工具，5 道被服务失败阻断，三类合计正好 50。”

“服务失败主要是 `get_proteins` 不可达、`convert_composition_to_wurcs` 返回 500、`convert_composition_text_to_wurcs_format` 返回 424。其他阻断集中在糖链图片、compound property tables 和 WURCS 格式转换。”

## 2:30 至 3:30 F3 50 题轨迹

画面：打开 `reports/w2_day2/f3_qwen3_4b_50/summary.json`。

旁白：

“正式 F3 批次使用 Qwen3 4B，50 道任务全部生成了结果。工具轨迹完全匹配 19 道，所有期望工具都调用到 34 道，任意期望工具调用到 41 道，最终回答字段非空 39 道。110 次工具调用中 78 次成功。”

“这里必须说清楚，19/50 是轨迹指标，不是答对 19 道。上游 Claude 18/50 和 Qwen3 15/50 使用 GPT-4o 评分，本轮没有相同评分器，所以不能直接比较。”

“8B 的中断目录不是成绩，目录里只有部分调试结果，没有完整 50 题结果。”

## 3:30 至 4:00 验证与交付物

画面：打开 `reports/w2_day2/unittest_2026-10-29.txt` 末尾和 `D:\毕设交付\W02_2026-11-03\03-附件材料\W02_核心证据\2026-10-29_W02_验证记录.md`。

旁白：

“固定回归现在是 65 项，64 项通过，1 项 GPU 门控跳过。新增的 4 项是工具可行性分类测试。F3 summary checker 返回 PASS，GlycanML 五个 CSV 的 MD5 全部通过，`git diff --check` 没有输出。”

“交付目录只放周报、核心证据、验证记录和 SHA256 清单，不放源代码、模型权重和全部 50 个中间 task JSON。”

## 4:00 至 4:20 W3 计划与提交

画面：打开周报的 W3 计划。

旁白：

“第三周先修高频阻断工具，补 GPT-4o 同口径答案评分，再做 F2 的受控消融，最终形成论文值、本地值、差异和解释四列对照。视频录制完成后，我会在 11 月 3 日 20 点前提交，并把交付总表 W02 改为已交。”

结束画面停留在最新 commit、交付目录和 W02 状态。

## 录制后检查

1. 视频长度为 3 至 5 分钟，开头能看到最新 commit。
2. 保存为 `D:\毕设交付\W02_2026-11-03\01-视频\2026-11-03_W02_周视频.mp4`。
3. 重新生成交付目录 `SHA256SUMS.txt`，确保视频也进入清单。
4. 11/03 20:00 前正式提交。
5. 提交成功后把 `D:\毕设交付\交付总表.md` 的 W02 状态改为 `已交`，并填写实际提交时间。
