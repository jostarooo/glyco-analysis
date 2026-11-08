# W3 Day 5 验证记录

日期：2026-11-08

## 检查点生成

```text
PASS: generated W3 Day5 checkpoint with 2 F2 tasks, 3 F3 models, 6 system sites and 201 tests
PASS: W3 Day5 checkpoint outputs are current
```

生成器为 `scripts/build_w3_checkpoint.py`，行为测试为
`tests/test_w3_checkpoint.py`。检查点 JSON 和 Markdown 连续生成不会写入时间戳，
第二次运行不会改变已有文件的字节或 mtime。

## 测试

检查点聚焦测试：

```text
Ran 11 tests in 0.506s
OK
```

全量 unittest：

```text
Ran 201 tests in 41.026s
OK (skipped=8)
```

201 项中 193 项通过，8 项来自既有 GPU 门控或按设计跳过的环境合同测试。
原始输出在 `reports/w3_day5/unittest_2026-11-08.txt`。

## 负向控制

- 修改 F1 的 MCC 但保留旧差值时，生成器拒绝写入，并报告必须在混淆矩阵上重算。
- 修改 F3 的 `upstream_gpt4o_equivalent` 为 true 时，生成器拒绝写入。
- 修改系统结果的 `truncation` 为 true 时，生成器拒绝写入。
- 手改 `checkpoint.json` 后执行 `--check`，退出码为 1。
- 删除测试日志等固定源后，生成器返回结构性错误，退出码为 2。

## 检查点内容

本次检查点包含：

- F1 作者检查点 MCC 与论文参考差值。
- F2 免疫原性和糖基化两任务的三种子均值、标准差及论文 Table 3 差值。
- F3 三个模型的轨迹指标、同一 Kimi K3 judge 的评分状态和可判定覆盖率。
- W3 真实系统 O75144 的 6 个候选位点、标签一致性和概率差。
- 201 项回归的通过和跳过计数。
- 六份固定源的路径、字节数和 SHA256。

## W03 交付包

```text
PASS: built W03 delivery package with 15 managed files
PASS: W03 delivery package is current
```

交付包位于 `D:\毕设交付\W03_2026-11-10`。根级 `SHA256SUMS.txt` 覆盖整个包，
核心证据目录另有自己的 `SHA256SUMS.txt`。正式视频尚未由用户录制，因此
`01-视频` 当前为空；视频放入后必须重跑 `scripts/build_w3_delivery.py`。

## 边界

- 本轮没有重跑 F2 三种子训练。
- 本轮没有重跑 Qwen3 4B、GLM-5.3 或 DeepSeek-Flash 的 50 题。
- F3 仍是本地证据评分，不是上游 GPT-4o 等价评分。
- 系统结果不是实验证据、概率校准结果或临床诊断。
- 未 push、未重写远端、未运行 GitHub 发布脚本。
