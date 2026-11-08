# W03 周视频脚本（3 至 5 分钟）

日期：2026-11-08

视频开头必须现场运行：

```powershell
git -C D:\wbworkspace\glyco-analysis rev-parse HEAD
```

把终端中的完整 commit 和 `git status --short` 保留在画面里。不要只读本脚本。

## 0:00 至 0:20 开场

展示终端命令和当前 commit。

口述要点：

“这是第三周交付视频。当前仓库是这个 commit，工作树状态是干净的。今天不重新训练，
只把 W3 已经完成的真实结果做成 11/10 可复核检查点。”

## 0:20 至 1:10 真实系统

打开 `http://127.0.0.1:8765`，用本地演示账号登录。载入 `O75144` 样例，
提交一次位点预测，展示任务状态从排队、加载模型到完成，以及结果表的 6 个位点。

口述要点：

“这里调用的是作者 ESM-2 150M LoRA 检查点，不是 mock。O75144 返回 6 个 N-X-S/T
候选位点，历史标签全部一致，最大概率差是 0。系统只预测 sequon，不等于实验阳性，
也不是临床结论。”

## 1:10 至 2:00 F2 Table 3

打开 `reports/w3_day5/checkpoint.md` 和 `reports/w2_day4/scorecard.md`。

展示：

- F1 作者检查点 MCC 0.848348842859，参考值 0.848。
- F2 免疫原性 AUPRC 0.774863513678，论文 0.780 ± 0.006。
- F2 糖基化 Macro-F1 0.937792856003，论文 0.948 ± 0.004。

口述要点：

“F2 对齐的是 GlycanML Table 3，不是 Table 2。三种子是 0、1、2，50 epoch，
batch 64。本地是 PyG 自实现 RGCN，不是 TorchDrug 逐位克隆。TorchDrug 未安装，
所以没有逐位数值差。”

## 2:00 至 3:00 F3 三模型

打开 `reports/w3_day4/f3_three_model_report.md`，展示三模型表和答案评分表。

口述要点：

“同一批 50 题、70 个工具、同一系统提示词和 JSON 动作协议，分别跑了 Qwen3 4B、
GLM-5.3 和 Qoder DeepSeek-Flash。上半部分是工具轨迹，不是答案正确率。下半部分
才使用同一个 Kimi K3 judge 做本地证据评分，并同时报告可判定覆盖率。”

展示一个边界：

“GLM-5.3 在已有最终回答的题中更容易被判正确，但只有 25/50 有最终回答，所以不能
写成整体模型更好，也不能说模型越大正确率越高。DeepSeek V4.1 Flash 免费路由的
17 次 HTTP 429 只作为配额失败证据，不进入能力对照。”

## 3:00 至 3:50 检查点生成

运行：

```powershell
$env:PYTHONUTF8='1'
D:\python\python.exe scripts\build_w3_checkpoint.py --check
```

展示终端输出：

```text
PASS: W3 Day5 checkpoint outputs are current
```

再打开 `reports/w3_day5/checkpoint.json`，指出 `sources` 的路径、字节数和 SHA256。

口述要点：

“检查点由固定源重算，不手填数字。它重算 F1 MCC、F2 三种子均值和标准差、F3 的评分
分母和覆盖率。手改输出后 `--check` 会失败。连续两次生成不会改字节或 mtime。”

## 3:50 至 4:35 回归与问题处理

展示 `reports/w3_day5/unittest_2026-11-08.txt` 末尾：

```text
Ran 196 tests in 45.093s
OK (skipped=8)
```

口述一个真实问题：

“最初检查点的 F2 标准差用精确浮点相等去测，源文件的最后一位差了约 1e-18，测试
失败了。这里没有改源数字，而是把断言改成有明确容差的近似比较，生成器仍然用
`statistics.stdev` 重算。这样失败不是因为训练结果变了，而是测试把浮点表示当成了
数学精确值。”

## 4:35 至 5:00 收尾

展示 W03 交付目录和根级 `SHA256SUMS.txt`。

口述要点：

“第三周交付包含周报、检查点、核心证据和 SHA256 清单，不放代码、模型权重和全部
中间 task JSON。正式周视频、本人手写日志总结和私信提交由我完成。W4 继续做
UniProt 实验证据测试集和 F2 受控消融。”
