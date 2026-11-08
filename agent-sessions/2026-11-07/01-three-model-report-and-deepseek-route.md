# W3 Day4：DeepSeek-Flash 三模型对照

- 归档日期：`2026-11-07`
- 文档性质：由真实 AI 编程会话汇编的脱敏工程记录，不是原始聊天，也不是本人日志总结
- 会话数量：3
- 证据数量：6

> 每条叙述都绑定真实消息或工具事件。证据摘录只保留与工程判断有关的部分，隐藏推理、无关上下文和敏感字段。

## 摘要

本日尝试 DeepSeek V4.1 免费路由，识别配额失败对轨迹的影响，随后切换到 Qoder DeepSeek-Flash 完成 50 题，并用 manifest 驱动的报告器统一三个模型。 [E1107-USER] [E1107-IDEMPOTENCE] [E1107-FINAL]

## 1. 任务与阻断条件

用户要求尝试 Magpie 中的其他模型，例如 DeepSeek V4.1 Flash，目标是在不破坏已有 Qwen 和 GLM 结果的前提下增加第三个模型。 [E1107-USER]

架构审查首先检查现有产物，发现 V4.1 目录缺少完整 summary 和对应评分，因此报告器必须 fail closed，不能在缺第三个模型时生成看似完整的结果。 [E1107-ARCH]

旧版 Qwen 产物没有运行时 prompt hash，审查方案要求使用历史代码 provenance sidecar，并明确标记它不是运行时记录。 [E1107-ARCH] [E1107-IMPL]

## 2. 报告器设计

实现采用单一 manifest 和 ModelSnapshot 统一旧版与当前版 run、grade 产物，校验三个唯一模型、参考模型、50 题对齐、prompt hash、参数和评分汇总重算。 [E1107-ARCH] [E1107-IMPL]

报告严格分开轨迹指标与答案评分指标，不生成合并 accuracy，差值只相对参考模型展示。 [E1107-IMPL]

## 3. 模型路线与失败处理

DeepSeek V4.1 Flash 免费路由在 50 题中发生 17 次 HTTP 429，只有 9 题产生最终回答，这组结果只保留为配额失败证据，不能当作模型能力结论。 [E1107-FINAL]

切换到 Qoder DeepSeek-Flash 后完成同一批 50 题。轨迹为 exact_sequence 13、全部期望工具 42、任一期望工具 48、最终回答 22/50、成功工具调用 115/148。 [E1107-FINAL]

同一 Kimi K3 judge 得到 15 个 correct、5 个 incorrect、2 个 manual_review 和 28 个 missing_answer，可判定覆盖率为 20/50。 [E1107-FINAL]

## 4. 可复现验证

三模型报告连续两跑后 JSON 和 Markdown 字节与 mtime 均不变，证明生成器没有写入时间戳或随机顺序。 [E1107-IDEMPOTENCE]

负向控制先手改临时报告，再运行 checker，退出码为 1 且状态为 FAIL，证明 checker 能发现手改输出。 [E1107-NEGATIVE]

全量回归、三份 F3 summary checker、Qoder 评分检查、git diff 检查和三模型报告检查均通过。 [E1107-FINAL] [E1107-IDEMPOTENCE]

## 判定边界

每个模型只有一次固定 50 题运行，不能据此声称方差、模型大小因果或普遍优劣。 [E1107-IMPL] [E1107-FINAL]

Kimi K3 是本地证据评分器，不是上游 GPT-4o 等价评分；轨迹指标和答案评分都不能改写为上游成绩。 [E1107-FINAL]

免费路由的 429 是服务配额事实，不是 DeepSeek 模型能力结果。 [E1107-FINAL]

## AI 使用声明

本日由 AI 辅助架构审查、报告器实现、模型路由排障、真实运行和证据整理。失败路由和成功路由都保留，没有只展示成功样本。 [E1107-USER] [E1107-ARCH] [E1107-IMPL] [E1107-FINAL]

## 证据索引

| 证据 | 类型 | 会话 | 原始定位 | 原始证据 SHA256 | 说明 |
|---|---|---|---|---|---|
| `E1107-USER` | message | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=5461` | `5e0cad79da3ef971dadbe94a3fcd213c8d3188c9f9cfa55e007d9c491b8424ba` | 用户要求尝试 DeepSeek V4.1 Flash |
| `E1107-ARCH` | message | `codex:01a1b437-f32e-79a0-bc5e-2d54f7f8c695` | `ordinal=55` | `e7f54cdff741c7c80ebec8f90993833d2a5420dfe07932454ec6cfdf799bddcb` | 三模型报告的前置阻断审查 |
| `E1107-IMPL` | message | `codex:01a1b43e-4055-7b73-a3f8-ec3bb8fe9879` | `ordinal=87` | `247e987778d88ebbea7a5caf4498d6985af7f81456aa091b603e2078e0268cec` | 三模型报告器实现和验证总结 |
| `E1107-IDEMPOTENCE` | tool | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=5616; call_index=0; event_index=0` | `a05f2506614d4b6d16784d37fc77df9bec27bb4654594a3598f0add6fbfc64f6` | 连续两跑幂等性检查 |
| `E1107-NEGATIVE` | tool | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=5628; call_index=0; event_index=0` | `3b2f7c1101a2cf223a7cb50ce6ce21c6ee3fb333bef4193878acf7c5bf5ba538` | 手改报告后的负向控制 |
| `E1107-FINAL` | message | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=5712` | `e2d77b32e6e213c521a81e47ba22c6742fce35916d6bac2f67925c7028a3faeb` | 三模型轨迹、评分和路由失败总结 |

## 脱敏证据摘录

### `E1107-USER` 用户要求尝试 DeepSeek V4.1 Flash

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`message` / `user`
- 定位：`ordinal=5461`
- 原始证据 SHA256：`5e0cad79da3ef971dadbe94a3fcd213c8d3188c9f9cfa55e007d9c491b8424ba`
- 本摘录脱敏：无

```text
完成今天的任务，可以尝试调用magpie里的其他模型如deepseekv4.1flash
```

### `E1107-ARCH` 三模型报告的前置阻断审查

- 会话：`codex:01a1b437-f32e-79a0-bc5e-2d54f7f8c695`（W3 Day4 三模型报告架构审查）
- 类型：`message` / `assistant`
- 定位：`ordinal=55`
- 原始证据 SHA256：`e7f54cdff741c7c80ebec8f90993833d2a5420dfe07932454ec6cfdf799bddcb`
- 本摘录脱敏：无

```text
目标是让 W3 Day 4 在不重跑模型的前提下，从已有 run 和 grade 产物生成一份可离线复算的三模型 F3 报告，并且严格分开轨迹指标与答案评分指标。

**先看阻断项**

`reports/w3_day4/f3_deepseek_v41_50` 在我检查时只有部分 task JSON，还没有 `summary.json`，也没有对应的 Kimi K3 评分目录。三模型报告必须 fail closed，不能在缺第三个模型时生成看似完整的报告。

`reports/w2_day2/f3_qwen3_4b_50/summary.json` 是旧格式，没有 `task_hash`、`prompt_hashes`、`metrics_scope`、`request_options`。因此报告最多能核验 50 个 task 的题目与工具，不能仅凭该产物证明三个模型使用了完全相同的 system prompt 和 tool catalog。要么补一份可核验的 provenance sidecar，要么在报告中把 prompt 等价性标为未验证，不能从 README 推断。

DeepSeek 的模型键也应记录真实值。当前 smoke 使用的是 `opencode-zen/deepseek-v4.1-flash-free`，不能只写“DeepSeek V4.1”。

**方案 A：清单驱动的统一快照报告，推荐**

一个深度模块负责读取三个模型的 run 和 grade 产物，把旧格式和当前格式统一成 `ModelSnapshot`，完成契约校验、指标聚合、JSON 输出和 Markdown 渲染。

结构上只有一个模型清单。每个条目包含稳定键、显示名、run 目录和 grade 目录。报告内部只保留一份模型列表、一份指标定义和一份数据快照，Markdown 不是第二份手写数据源。

优点是对两个既有报告脚本的格式差异做了归一化，不把 `local`、`external` 这样的二元概念带进三模型层。缺点是必须同时处理旧版 Qwen 产物和当前 Magma 产物，适配器要写得足够严格。

**方案 B：扩展现有两个双模型脚本，再加一个合并脚本**

分别给 `compare_doc2agent_runs.py` 和 `compare_doc2agent_answer_grades.py` 增加第三个目录参数，再写一个 `merge_three_model_report.py`，把两份双模型结果拼成三模型报告。

这是最小补丁思路，但会形成两个报告入口，且合并脚本基本只做字段搬运和改名。模型键、指标顺序、来源路径和 delta 规则会在两套脚本、合并脚本、测试和文档中重复。现有 `compare_doc2agent_answer_grades.py` 还直接导入评分脚本中的函数，扩展后更容易把内部实现当成公共 API。这个方案应拒绝。

**红黑榜**

| 检查项 | 方案 A | 方案 B |
|---|---|---|
| shallow module | 通过，一个入口隐藏加载、校验、聚合和渲染 | 不通过，合并层主要是拼接两个旧报告 |
| information leakage | 通过，适配器把旧版和当前版 run/grade 转成领域快照 | 不通过，`local`、`external` 原始报告结构泄漏到三模型层 |
| temporal decomposition | 通过，以模型产物为所有权边界，不按 load、validate、render 拆散 | 不通过，旧比较器、合并器、渲染器按执行阶段分裂 |
| pass-through method | 通过，builder 真正完成报告逻辑 | 不通过，合并方法主要是转发和复制已有结果 |
| split ownership | 通过，清单拥有模型集合，builder 拥有输出，模型快照拥有指标 | 不通过，模型列表、指标列和来源约定有多个写者和副本 |
| two ways to do one task | 有条件通过，必须迁移或删除旧双模型入口 | 不通过，双模型路径和三模型拼装路径同时存在 |
| importable internals | 通过，只暴露一个

... [证据摘录已按固定长度截断]
```

### `E1107-IMPL` 三模型报告器实现和验证总结

- 会话：`codex:01a1b43e-4055-7b73-a3f8-ec3bb8fe9879`（W3 Day4 三模型报告器实现）
- 类型：`message` / `assistant`
- 定位：`ordinal=87`
- 原始证据 SHA256：`247e987778d88ebbea7a5caf4498d6985af7f81456aa091b603e2078e0268cec`
- 本摘录脱敏：无

```text
我的目标是让 W3 Day 4 在不重跑模型和网络请求的前提下，从现有 run 与 Kimi K3 grade 产物生成一份可离线复算的三模型 F3 报告。实现和测试已在专项 worktree 完成，未触碰主仓库。

**新增内容**
- `D:\Codex\workspace\glyco-analysis-w3-day4-deepseek\scripts\doc2agent_three_model_report.py`
- `D:\Codex\workspace\glyco-analysis-w3-day4-deepseek\tests\test_doc2agent_three_model_report.py`
- `D:\Codex\workspace\glyco-analysis-w3-day4-deepseek\reports\w3_day4\f3_models.json`
- `D:\Codex\workspace\glyco-analysis-w3-day4-deepseek\reports\w3_day4\provenance\qwen3_4b_50.json`
- `D:\Codex\workspace\glyco-analysis-w3-day4-deepseek\reports\w3_day4\design.md`

报告器使用 `ModelSnapshot` 作为统一领域模型。它校验三个唯一模型、参考模型、每模型 50 题、题目和期望工具一致性、run 参数、评分契约、评分汇总重算、run summary SHA、prompt hash 三元组和全部源文件 SHA。轨迹指标与答案评分保持独立，差值只相对 `reference_model`，没有合并准确率。

旧的 Qwen run 通过历史 provenance sidecar 提供 prompt hashes，并明确标为 `historical_code_provenance_not_runtime_recorded`，不是运行时记录。JSON 和 Markdown 无时间戳，重复运行只在内容变化时写入；`--check` 会拒绝缺失、手改或源文件变化。

**验证**
- `py_compile` PASS。
- 聚焦 unittest 10 项全部通过，耗时 10.199 秒。
- 使用真实 Qwen、GLM 产物构造 3 模型探针，50 题报告生成 PASS，连续 `--check` PASS。
- 真实三模型报告暂未生成，因为专项 worktree 中还没有 DeepSeek 50 题 summary 和对应 Kimi K3 grade 目录。报告器按要求 fail closed。
- 未运行全量测试、模型、网络请求或发布脚本。

**提交**
提交为 `feat(w3): build manifest-driven three-model F3 report`。

HEAD：

`ae6a9c459d1ca4adac9107c882e7e2154a7d4e34`

工作树干净，未 push。

本轮主要采用 `principle-model-the-domain` 建立 `ModelSnapshot`，`principle-boundary-discipline` 把全部契约校验集中在产物边界，`principle-make-operations-idempotent` 实现确定性写入和 `--check`，`principle-prove-it-works` 用真实 Qwen 和 GLM 产物验证，`principle-explain-the-number` 将轨迹指标和答案评分严格分开。
```

### `E1107-IDEMPOTENCE` 连续两跑幂等性检查

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`tool` / `exec_command`
- 定位：`ordinal=5616; call_index=0; event_index=0`
- 原始证据 SHA256：`a05f2506614d4b6d16784d37fc77df9bec27bb4654594a3598f0add6fbfc64f6`
- 本摘录脱敏：无

```text
工具：exec_command
状态：(未标记)

参数：
$j='D:\wbworkspace\glyco-analysis\reports\w3_day4\f3_three_model_report.json'; $m='D:\wbworkspace\glyco-analysis\reports\w3_day4\f3_three_model_report.md'; $h1=[Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData([System.IO.File]::ReadAllBytes($j))); $h2=[Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData([System.IO.File]::ReadAllBytes($m))); $t1=[System.IO.File]::GetLastWriteTimeUtc($j).Ticks; $t2=[System.IO.File]::GetLastWriteTimeUtc($m).Ticks; Start-Sleep -Milliseconds 1200; $env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'; $env:PYTHONUTF8='1'; & 'D:\python\python.exe' scripts\doc2agent_three_model_report.py --manifest reports\w3_day4\f3_models.json --json-out reports\w3_day4\f3_three_model_report.json --md-out reports\w3_day4\f3_three_model_report.md; $h1b=[Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData([System.IO.File]::ReadAllBytes($j))); $h2b=[Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData([System.IO.File]::ReadAllBytes($m))); $t1b=[System.IO.File]::GetLastWriteTimeUtc($j).Ticks; $t2b=[System.IO.File]::GetLastWriteTimeUtc($m).Ticks; "json_sa

... [证据摘录已按固定长度截断]
```

### `E1107-NEGATIVE` 手改报告后的负向控制

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`tool` / `exec_command`
- 定位：`ordinal=5628; call_index=0; event_index=0`
- 原始证据 SHA256：`3b2f7c1101a2cf223a7cb50ce6ce21c6ee3fb333bef4193878acf7c5bf5ba538`
- 本摘录脱敏：无

```text
工具：exec_command
状态：(未标记)

参数：
$d='D:\wbworkspace\glyco-analysis\.audit\w3-day4-negative'; [System.IO.Directory]::CreateDirectory($d) | Out-Null; $j=Join-Path $d 'report.json'; $m=Join-Path $d 'report.md'; $env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'; $env:PYTHONUTF8='1'; & 'D:\python\python.exe' scripts\doc2agent_three_model_report.py --manifest reports\w3_day4\f3_models.json --json-out $j --md-out $m | Out-Null; $orig=[System.IO.File]::ReadAllText($j,[System.Text.UTF8Encoding]::new($false)); $changed=$orig.Replace('"exact_sequence": 19','"exact_sequence": 20'); [System.IO.File]::WriteAllText($j,$changed,[System.Text.UTF8Encoding]::new($false)); $out=& 'D:\python\python.exe' scripts\doc2agent_three_model_report.py --manifest reports\w3_day4\f3_models.json --json-out $j --md-out $m --check 2>&1; $code=$LASTEXITCODE; "EXIT=$code"; $out

结果：
Process exited with code 0
EXIT=1
{
  "status": "FAIL",
  "errors": [
    "JSON report differs from regenerated output: D:\\wbworkspace\\glyco-analysis\\.audit\\w3-day4-negative\\report.json"
  ]
}
```

### `E1107-FINAL` 三模型轨迹、评分和路由失败总结

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`message` / `assistant`
- 定位：`ordinal=5712`
- 原始证据 SHA256：`e2d77b32e6e213c521a81e47ba22c6742fce35916d6bac2f67925c7028a3faeb`
- 本摘录脱敏：无

```text
**今日完成**

- 试跑了 Magpie 的 `opencode-zen/deepseek-v4.1-flash-free`。50 题运行中发生 17 次 HTTP 429，只有 9 题产生最终回答，这组数据只作为配额失败证据，不能当作模型能力结果。
- 改用 `qoder-cn/dfmodel`（`DeepSeek-Flash · Qoder CN`）完成同一批 50 题。轨迹指标为 `exact_sequence=13`、`all_expected_called=42`、`any_expected_called=48`、有最终回答 22/50、工具调用成功 115/148。
- 同一 Kimi K3 judge 评分：15 正确、5 错误、2 人工复核、28 缺少回答；可判定正确率 15/20，可判定覆盖率 20/50。
- 新增 manifest 驱动的三模型报告器，轨迹指标和答案评分分开，不生成合并 accuracy。报告文件为 `reports/w3_day4/f3_three_model_report.json` 和 `reports/w3_day4/f3_three_model_report.md`。
- 更新了 `README.md`、`REPRO.md`、`reports/weekly/W03_2026-11-10_progress.md`、`D:\毕设交付\交付总表.md`。W03 状态保持“进行中”。

**验证**

- 三模型报告器聚焦测试：10/10 通过。
- 全量 unittest：185 项，177 项通过，8 项按设计或 GPU 门控跳过。
- 三份 F3 summary checker：全部 PASS。
- Qoder 答案评分 `--check`：PASS。
- 三模型报告连续两跑字节和 mtime 不变；手改临时 JSON 后 `--check` 正确返回 1。
- `git diff --check`：PASS。

**提交与归档**

- `3b068cc` `feat(w3): add DeepSeek Flash three-model comparison`
- `74f8920` `docs(w3): record W3 Day4 model comparison`
- 最终 HEAD：`74f8920b21601514003350818306b41e7f971061`
- 未 push，未重写远端。
- Obsidian 已写入任务 #268 和环境笔记，项目总览、首页、任务总览、2026-11-07 时间线均已同步。
- 当前知识库审计：413 篇笔记、27 个项目、35 个工作日、267 项任务、断链 0。

边界保持不变：F3 的这些数字是工具轨迹指标，不是答案正确率；Kimi K3 是本地证据评分器，不等同于上游 GPT-4o；V4.1 的 429 不能写成模型能力结论。W03 还未正式提交，周视频和本人手写日志总结仍需要完成。
```
