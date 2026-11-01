# W2 Day 5 录制台交互验证

> 验证日期：2026-11-01
> 仓库：`D:\wbworkspace\glyco-analysis`
> 分支：`main`
> 本轮未 push、未重写远端、未运行发布脚本

## 结论

录制台已从静态周报升级为 9 页可操作界面。F1、F2、F3 三个核心页面均由真实仓库产物驱动，浏览器检查不只验证静态挂载，还会实际点击控件并核对交互后的 DOM。

## 固定检查

| 检查 | 命令 | 结果 |
|---|---|---|
| 录制台聚焦测试 | `python -m unittest tests.test_video_ui -v` | 11/11 PASS |
| 录制台契约 | `python scripts/build_video_ui.py --check` | PASS |
| 浏览器与交互 | `python scripts/check_video_ui.py --browser` | PASS |
| F3 summary | `python scripts/summarize_doc2agent_run.py --run-dir reports/w2_day2/f3_qwen3_4b_50 --expected-tasks 50 --check-summary reports/w2_day2/f3_qwen3_4b_50/summary.json` | PASS |
| GlycanML | `python scripts/check_glycanml_data.py --check-only` | PASS，5 个 CSV 的 MD5 通过，`glycan_link=PASS_URL_FIX` |
| 记分卡 | `python scripts/build_w2_scorecard.py --check` | PASS |
| web 数据契约 | `python scripts/build_web_data.py --check` | PASS |
| 全量回归 | `python -m unittest discover -s tests -v` | 119 项，114 通过，5 项按设计或 GPU 门控跳过 |

原始输出：

- `reports/w2_day5/unittest_2026-11-01-interactive.txt`
- `reports/w2_day5/video_ui_browser_check_2026-11-01.txt`
- `reports/w2_day5/f3_summary_check_2026-11-01.txt`

## 现场交互

### F1

- 从 201 个真实候选中切换位点，也可点击四个代表案例。
- 页面同时展示 UniProt、Sequon、35M、150M 四种判断。
- 输入 `NST` 后规则命中 1 次；输入 `NPS` 后命中 0 次，证明浏览器现场执行了 `N-X-S/T`、X 不能为 P 的约束。
- 输入框获得焦点时，数字键不会误触翻页。

### F2

- 可在免疫原性和糖基化连接两个任务间切换。
- 可在 seed 0、1、2 之间切换，并读取真实 test、validation、best epoch 和选择依据。
- 逐种子条形图直接来自 `per_seed`，并非另手填的结果。
- 页面在 1920×1080 和 1366×768 均无溢出。
- 浏览器回归明确禁止 `[object Object]` 和 `undefined` 进入 F2 画面。

### F3

- 可从 50 道真实任务中选题，并按完整轨迹、含工具失败、无最终回答筛选。
- 点击“下一步”逐条显示真实工具名、参数、状态和错误。
- 点击“显示全部”显示最终回答是否存在及原文。
- 右侧 19/50、34/50、41/50、39/50、78/110 是轨迹或输出存在性指标，不是答案正确率。

## 数据边界

- 演示数据由 `scripts/build_video_ui.py` 从固定仓库产物生成，生成物记录每个源路径、字节数和 SHA256。
- `video-ui/dist/index.html` 不引用外部脚本、样式、图片或网络 API。
- `video-ui/` 与正式 `web/` 分离，不修改主线交付界面，不进入正式 W02 周交付目录。
- F2 对齐 GlycanML Table 3，不是 Table 2；本轮是 PyG 自实现，不是 TorchDrug 逐位克隆。
- 上游 Claude 18/50 和 Qwen3 15/50 使用 GPT-4o 评分，不能与本轮轨迹指标直接比较。
