# 糖基化分析系统：以蛋白质语言模型预测 N-糖基化位点、以图神经网络解析糖链、并用工具调用智能体把两者串成一个可对话的分析工作台

> 2026-10-27 第一次对齐；2026-10-28 W1 交付闭环与 W2 启动；2026-10-29 W2 核心实验收口；2026-10-30 W2 Day 3 阻断工具修正；2026-10-31 W2 Day 4 可重算记分卡；2026-11-01 W2 Day 5 web 单文件离线交付与录制功能演示；2026-11-04 W3 Day 1 登录与真实位点预测系统纵切；2026-11-05 W3 Day 2 外部模型 F3 轨迹对照；2026-11-06 W3 Day 3 F3 答案评分与覆盖对照；2026-11-07 W3 Day 4 三模型轨迹对照；2026-11-08 W3 Day 5 11/10 检查点、交付包闭环与 AI 编程会话工程归档
> 代码状态：W1 的环境、数据集 v0、35M 线性探针、作者 150M LoRA 复算、三方法对拍和 10 个分歧位点人工复核均已完成。
> 数据口径见 `reports/dataset_v0.md`，探针结果见 `reports/esm35_linear_probe_v0/report.md`，
> 150M 复算结论见 `reports/mcc_repro.md`，候选位点对拍见 `reports/w1_three_method_v0/report.md`。
>
> W1 已于 2026-10-27 正式提交（2026-10-28 核记）。正式周视频为 `02-进度报告\第一周展示视频.mp4`（6 分 00 秒），交付包为 68 个内容文件、68/68 条校验一致，正式周目录为 76 个文件、75/75 条校验一致。
>
> W2 核心实验已完成并提交到 `main`。PyG RGCN 按 GlycanML 论文 Table 3 完成 3 种子复算，免疫原性 AUPRC 为 0.7748635136784087 ± 0.009111853148723878，糖基化 Macro-F1 为 0.9377928560029268 ± 0.0038891301525018625；Doc2Agent 70 个 wrapper 中 43 个直接成功，Qwen3 4B 完成 50 题轨迹批次。W2 Day 3 用任务参数重测 17 个阻断工具，50 题最新分类为当前工具可直接完成 43、需要替代工具 5、服务失败 2。W2 Day 4 把 F1、F2、F3 和工具可行性固化为可重算记分卡，唯一数字入口是 `reports/w2_day4/scorecard.md`。W2 Day 5 新增 `web/` 交付界面与 `scripts/build_web_data.py` 数据契约，界面只读展示真实产物，并标出数据生成时的 HEAD。生产构建已用 `vite-plugin-singlefile` 内联全部 JavaScript 和 CSS，`web/dist/index.html` 可直接从磁盘打开。W2 原始 20/25/5 分类保留为历史证据。2026-11-02 经授权完成 REST 镜像发布，远端 `main` 与本地、W2 视频均为 `9b93d60`。
> 与正式 `web/` 分离的 `video-ui/` 只用于录制周视频。它提供 F1 真实候选与 Sequon 现场规则、F2 任务和 seed 切换、F3 真实工具轨迹逐步骤播放，生成单个 `video-ui/dist/index.html`，不进入正式 W02 交付目录。
>
> W3 Day 1 新增独立的 `system/` 交互系统。用户先登录，再提交蛋白序列；后端把任务放入单 GPU 工作队列，加载作者 ESM-2 150M LoRA 检查点，返回全部 N-X-S/T 候选位点。页面现场显示 HEAD、模型来源、任务阶段和真实结果。该服务只允许本机回环地址，不是临床诊断，也不替代实验验证。
>
> W3 Day 2 回应导师对本地 4B 模型档位的疑问。同一批 50 题、70 个工具、同一系统提示词和 JSON 动作协议现在分别由 `qwen3:4b` 与 `workbuddy-ai/glm-5.3` 执行。外部模型通过本机 Magpie 的 OpenAI-compatible 网关调用。本地基线参数为 `seed=0`、`num_ctx=8192`、`num_predict=512`、`think=false`；外部批次参数为 `temperature=0`、`max_tokens=512`，未发送 `seed`，上下文窗口由服务端模型控制。两边报告的 token 数不是同一计量口径，不能当作归一化成本。对照只比较工具轨迹、调用状态和最终回答存在性，不评价答案正确率。独立日志总结仍必须由本人改写，证据包在 `reports/w3_day2/log_summary_evidence.md`；项目 AI 会话归档规则在 `agent-sessions/README.md`。
>
> W3 Day 3 为两份 50 题轨迹增加答案评分。统一 judge 为 `workbuddy-ai/kimi-k3`，temperature 为 0，max_tokens 为 1500。Qwen3 4B 为 9 正确、29 错误、1 人工复核、11 缺回答；GLM-5.3 为 18 正确、3 错误、4 人工复核、25 缺回答。这是本地证据约束评分，不是上游 GPT-4o 评分。GLM-5.3 在已有最终回答中更容易被判正确，但最终回答覆盖只有 25/50，不能据此宣称整体模型优劣或模型大小因果。
>
> W3 Day 4 增加第三个模型对照。DeepSeek V4.1 Flash 的免费 Magpie 路由在运行中返回 17 次 HTTP 429，只能作为配额失败证据，不能当成模型能力结果。最终改用 `qoder-cn/dfmodel`（`DeepSeek-Flash · Qoder CN`）完成同一批 50 题，轨迹为 `exact_sequence=13`、`all_expected_called=42`、`any_expected_called=48`、有最终回答 22、148 次工具调用中 115 次成功。同一 Kimi K3 judge 评分下为 15 正确、5 错误、2 人工复核、28 缺回答，可判定正确率 15/20，可判定覆盖率 20/50。三模型报告由 `reports/w3_day4/f3_models.json` 驱动，输出 `f3_three_model_report.json` 和 `f3_three_model_report.md`。这些仍是工具轨迹和本地证据评分，不是上游 GPT-4o 答案正确率。
>
> W3 Day 5 把 F1、F2 Table 3、F3 三模型、真实系统 O75144 和最新全量回归收束为机器可复核检查点。唯一入口是 `reports/w3_day5/checkpoint.md`，JSON、源路径、字节数和 SHA256 在 `reports/w3_day5/checkpoint.json`。生成器会拒绝过期、手改或内部不一致的检查点输出。
>
> 2026-11-08 新增本项目 AI 编程会话工程归档。`agent-sessions/INDEX.md` 汇总 5 篇按日工程记录、12 个真实 Codex 会话和 33 条证据。生成器只读 AgentsView SQLite，每条证据绑定会话 ID、消息 ordinal 或工具 call/event 序号，并记录规范化行 SHA256。原始 137 MB JSONL 不进入仓库，隐藏推理 `thinking_text` 不导出，统一脱敏密码、token、Cookie、Authorization、私钥、URL token 和用户主目录。该目录是可审计工程记录，不替代本人手写日志总结，也不改写原始工具结果。
> W03 交付包由 `scripts/build_w3_delivery.py` 从固定路径复制并生成两套 SHA256 清单，正式视频仍由用户录制后放入 `01-视频/`。

## 教师建议阅读顺序

1. 先读 `reports/w3_day5/checkpoint.md`，这是 11/10 检查点的唯一汇总入口；F1/F2/F3 的 W2 记分卡在 `reports/w2_day4/scorecard.md`。需要正式可视化浏览时打开 `web/` 交付界面，数据由 `scripts/build_web_data.py` 生成；需要录屏时打开 `video-ui/dist/index.html`。
2. 再读 `reports/weekly/W02_2026-11-03_progress.md`，了解 W2 Day 1 至 Day 5 的实验、证据边界和验证结果。
3. 接着读 `reports/w2_day2/f2_f3_comparison.md`、`reports/w3_day2/f3_glm53_vs_qwen3_4b.md`、`reports/w3_day3/answer_grade_comparison.md`、`reports/w3_day4/f3_three_model_report.md`、`reports/w3_day5/checkpoint.md` 与 `docs/W2_D3_tool_blocker_triage.txt`，核对论文值、轨迹对照、答案评分、三模型结果和 W2 Day 3 阻断工具分类。
4. 需要复查 W1 时读 `reports/weekly/W01_2026-10-27_progress.md`，核对交付、130 行评估池和三方法对拍。
5. 需要重跑时读 `REPRO.md`；原始证据在 `reports/w2_day1/` 至 `reports/w2_day5/`、`reports/w3_day1/` 至 `reports/w3_day5/`。
6. 需要现场验证 F1 真实推理系统时运行 `scripts/run_w3_system.ps1`，先执行 `doctor`，再执行 `serve`，然后访问 `http://127.0.0.1:8765`。W3 证据在 `reports/w3_day1/`。
7. 需要重跑外部 F3 对照时读 `reports/w3_day2/README.md`。外部 summary 与本地 summary 分别用 `scripts/summarize_doc2agent_run.py` 复核，再用 `scripts/compare_doc2agent_runs.py` 生成对照。
8. 需要复核 F3 答案评分时读 `reports/w3_day3/answer_grade_comparison.md`。两份评分目录先用 `scripts/grade_doc2agent_answers.py --check` 复核，再运行 `scripts/compare_doc2agent_answer_grades.py`。
9. 需要复核三模型轨迹和评分时读 `reports/w3_day4/README.md`。先运行 `scripts/doc2agent_three_model_report.py --check`，再对照 `reports/w3_day4/f3_three_model_report.md` 的来源哈希和边界说明。
10. 需要审计本项目 AI 使用过程时读 `agent-sessions/INDEX.md`。每条工程记录都链接真实消息或工具事件；运行 `scripts/build_agent_session_archive.py --check` 可验证源证据、脱敏结果和生成文件是否仍一致。

文档、标题、表头和人工复核说明均使用中文。代码标识、JSON 与 CSV 字段名、状态枚举、模型名、路径、命令和原始软件告警保留英文，确保机器复核和哈希追溯不被破坏。

## 文档中的术语

| 术语（代码标识） | 在本文档中的含义 |
|---|---|
| 马修斯相关系数（`MCC`） | 综合阳性与阴性两侧的分类质量；1 最好，0 接近随机 |
| 序列模体（`sequon`） | N-X-S/T 序列片段，其中 X 不是脯氨酸 |
| LoRA 适配器（`adapter`） | 低秩适配器，保存作者训练得到的少量可训练参数 |
| 运行清单（`manifest`） | 记录输入、环境、设置和每个产物哈希的文件 |
| 独立核验脚本（`checker`） | 重新计算指标并核对产物，不依赖生成器自报 |
| 运行时复核（`runtime recheck`） | 重新加载模型前向若干审计样本，验证推理路径仍可运行 |
| 留一蛋白折外预测（`OOF`） | 每次留出一个蛋白做测试，汇总各折的折外预测 |
| 参数高效微调（`PEFT`） | 只更新少量参数即可适配大模型的微调方法；本项目用它加载作者 LoRA 检查点 |
| 受试者工作特征曲线下面积（`ROC AUC`） | 按概率排序计算的正负样本区分度；0.5 接近随机 |
| 混淆矩阵计数（`TP` / `FP` / `TN` / `FN`） | 真阳性、假阳性、真阴性、假阴性 |
| 模型上下文协议（`MCP`） | 把外部工具按统一协议提供给智能体调用的接口标准 |
| 缺少支持证据 | 没有找到支持证据，不等于已经证明该位点不糖基化 |

## 它解决什么问题

糖基化是最常见、也最难预测的翻译后修饰之一。现有工具各管一段：位点预测器只告诉你"这里可能挂糖"，
糖链模型只回答"这条链是什么结构"，而真实科研问题往往是一句自然语言："这个蛋白哪些位点会挂
N-糖，挂上的糖链会不会影响它做受体？"

本项目把三条线接起来：

| 线 | 做什么 | 底座 |
|---|---|---|
| **F1 位点预测** | 给定蛋白序列，预测 N-X-S/T 位点是否真被糖基化 | ESM-2（35M 线性探针 / 150M LoRA） |
| **F2 糖链模型** | 给定糖链结构，预测其性质；本轮完成免疫原性与糖基化两任务 | RGCN（PyG 自实现，对齐 GlycanML Table 3） |
| **F3 工具调用智能体** | 把 F1/F2 与数据库查询包装成工具，用中文任务驱动 | Doc2Agent 路线 + MCP；本轮完成 Qwen3 4B、GLM-5.3 与 DeepSeek-Flash 的 50 题轨迹和答案评分 |

## 交付前检查

```powershell
$env:PYTHONPATH = 'D:\uv\pylibs\lora-n-gly-peft014'
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_w1_three_method.py --comparison-dir reports\w1_three_method_v0
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_esm150_lora_repro.py --run-dir reports\esm150_lora_repro_v0 --test-csv D:\wbworkspace\LoRA-N-Gly\data\N-GlycositeAltas\test.csv --adapter-dir D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint --base-model-revision a695f6045e2e32885fa60af20c13cb35398ce30c --recheck-inference
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v

# W2 Day 5 web 数据契约与交付前端（构建后可直接打开 web/dist/index.html）
$env:PYTHONUTF8 = "1"
D:\python\python.exe scripts\build_web_data.py --check
D:\node\node.exe D:\node\node_modules\npm\bin\npm-cli.js run build --prefix D:\wbworkspace\glyco-analysis\web
D:\python\python.exe scripts\check_web_dist.py --browser
# AI 会话工程归档：只读抽取、脱敏、证据哈希和离线检查
D:\python\python.exe scripts\build_agent_session_archive.py --check
# W3 Day 1 真实系统：先检查模型来源，再启动登录与预测界面
& 'D:\wbworkspace\glyco-analysis\scripts\run_w3_system.ps1' doctor
& 'D:\wbworkspace\glyco-analysis\scripts\run_w3_system.ps1' serve
```

`scripts/build_w1_delivery.py --sync` 会把仓库内的报告、源代码、README、REPRO 和正式周附件同步到交付目录，随后重算 `SHA256SUMS.txt`。当前视频已补入，交付包和正式周目录的校验状态均为 `PASS`；以后修改文档或重新生成交付物时再运行该命令。

## 现在能跑什么

```powershell
# 环境自检：写 reports/env_check.md，并验证 GPU 真前向
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\env_check.py

# 接口体检：一次性打印 UniProt / GlyGen / GlyConnect / GlyTouCan / KEGG / PubChem 的可用性
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_endpoints.py

# 构建 F1 数据集 v0：UniProt 实验标注 → N-X-S/T 候选位点表（带缓存，复跑 0 次网络请求）
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\build_dataset.py

# 独立复算校验：不共享代码，从原始 JSON 缓存重推并逐字段对照（PASS 才退出 0）
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_dataset.py

# ESM-2 35M 线性探针：冻结 35M 主干，只训练逐位点分类头
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\run_esm35_linear_probe.py --cache-dir D:\wbworkspace\glyco-analysis\data\raw\uniprot --out-dir reports\esm35_linear_probe_v0 --allow-download

# 独立复算探针产物：重训每个折、重算指标并核对哈希
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_esm35_linear_probe.py --run-dir reports\esm35_linear_probe_v0 --cache-dir D:\wbworkspace\glyco-analysis\data\raw\uniprot

# ESM-2 150M 作者检查点全量复算：2554 行，FP32，全序列，批大小为 1，SDPA
$env:PYTHONPATH = 'D:\uv\pylibs\lora-n-gly-peft014'
$env:HF_HOME = 'D:\hf'
$env:HF_HUB_OFFLINE = '1'
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\run_esm150_lora_repro.py --test-csv D:\wbworkspace\LoRA-N-Gly\data\N-GlycositeAltas\test.csv --adapter-dir D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint --base-model-revision a695f6045e2e32885fa60af20c13cb35398ce30c --attention-backend sdpa --out-dir reports\esm150_lora_repro_v0

# 独立复算 2554 行产物，并重跑 16 行审计样本
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_esm150_lora_repro.py --run-dir reports\esm150_lora_repro_v0 --test-csv D:\wbworkspace\LoRA-N-Gly\data\N-GlycositeAltas\test.csv --adapter-dir D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint --recheck-inference

# W1 三方法对拍：201 个候选位点跑作者 150M LoRA 适配器，再与 35M 折外预测和 sequon 规则合并
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\run_esm150_candidate_inference.py --candidates reports\candidates_30_lora.csv --adapter-dir D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint --base-model-revision a695f6045e2e32885fa60af20c13cb35398ce30c --attention-backend sdpa --out-dir reports\esm150_w1_candidates_v0
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\run_w1_three_method.py --out-dir reports\w1_three_method_v0
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_w1_three_method.py --comparison-dir reports\w1_three_method_v0

# 同步到 GitHub：本机 git push 通道不通，发布走 REST API（需要经典 PAT 的 `repo` 权限范围）
# 先把 token 写入 %USERPROFILE%\.github-token，或设置 GH_TOKEN；别把 token 写进仓库
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\publish_github.py

# W2 工具可行性分类：50 题各一个主分类
D:\python\python.exe scripts\classify_doc2agent_feasibility.py

# W2 F3 聚合复核：50 个 task JSON 与 summary 必须一致
D:\python\python.exe scripts\summarize_doc2agent_run.py --run-dir reports\w2_day2\f3_qwen3_4b_50 --expected-tasks 50 --check-summary reports\w2_day2\f3_qwen3_4b_50\summary.json

# W2 Day 3 阻断工具任务级复测：生成独立证据，不改写 W2 原始分类
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8='1'
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' scripts\retest_doc2agent_blockers.py

# W2 Day 4 可重算记分卡：从固定证据源生成，再检查输出是否过期
D:\python\python.exe scripts\build_w2_scorecard.py
D:\python\python.exe scripts\build_w2_scorecard.py --check

# W3 Day 2 外部模型 50 题轨迹对照：先复核两份 summary，再生成 external - local 差值
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8='1'
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' scripts\summarize_doc2agent_run.py --run-dir reports\w3_day2\f3_glm53_50 --expected-tasks 50 --check-summary reports\w3_day2\f3_glm53_50\summary.json
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' scripts\compare_doc2agent_runs.py

# W3 Day 3 F3 答案评分：同一 judge、同一 50 题，先检查两份输出，再生成覆盖率与状态对照
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' scripts\grade_doc2agent_answers.py --check --run-dir reports\w2_day2\f3_qwen3_4b_50 --out-dir reports\w3_day3\answer_grades_kimi_k3\f3_qwen3_4b_50
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' scripts\grade_doc2agent_answers.py --check --run-dir reports\w3_day2\f3_glm53_50 --out-dir reports\w3_day3\answer_grades_kimi_k3\f3_glm53_50
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' scripts\compare_doc2agent_answer_grades.py

# W3 Day 4 三模型报告：manifest 驱动，三份运行和评分必须同题同契约
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' scripts\doc2agent_three_model_report.py --manifest reports\w3_day4\f3_models.json --json-out reports\w3_day4\f3_three_model_report.json --md-out reports\w3_day4\f3_three_model_report.md --check

# W3 Day 5 11/10 检查点：从固定源生成，再检查输出是否过期
D:\python\python.exe scripts\build_w3_checkpoint.py
D:\python\python.exe scripts\build_w3_checkpoint.py --check

# W03 交付包：复制固定证据、生成核心证据清单和根级 SHA256
D:\python\python.exe scripts\build_w3_delivery.py
D:\python\python.exe scripts\build_w3_delivery.py --check

# W3 Day 1 真实 GPU 回归：加载作者检查点并对拍 O75144 的历史位点结果
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis;D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:HF_HOME='D:\hf'
$env:HF_HUB_CACHE='D:\hf\hub'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:RUN_W3_REAL_MODEL='1'
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' -m unittest tests.test_system_predictor_gpu -v
```

探针把 82 个含 `ECO:0000269` 的 N-连接糖基化位点作为实验阳性，把 48 个没有 N-连接
标注的候选 sequon 作为对照，并排除 71 个仅有 `ECO:0000255` 的推断阳性。评估覆盖
130 行、28 个蛋白和 51 个唯一窗口。MCC 为 0.331975，按蛋白重采样 2000 次得到的
95% 区间为 [0.060051, 0.602824]。对照组是未标注样本，不是实验验证的阴性。

作者 150M 检查点在完整 `test.csv` 上的复算 MCC 为 **0.848348842859**，与论文
**0.848** 的差为 **+0.000348842859**。评估覆盖 2554 行、939 个蛋白和 963 条唯一序列，
保留 46 条非 sequon 行，没有截断或滑窗。独立核验脚本启用推理复核后核对 16 行，
共 33294 条断言通过。

W1 三方法对拍在同一批 201 个候选位点上保留了 71 个仅含 `ECO:0000255` 的推断阳性，
但所有指标只使用 130 行诚实子集。ESM-2 35M 的留一蛋白交叉验证 MCC 为
**0.331975**，作者 150M LoRA 适配器的全序列 MCC 为 **-0.232614**，sequon 规则固定全判阳性，
MCC 为 **0.000000**。35M 使用窗口化折外预测，150M 使用全序列 LoRA 适配器推理，因此差异不能
只归因于模型大小。对拍另生成 10 个不一致位点，2026-10-23 完成人工复核：6 个实验阳性
得到独立证据支持，3 个未标注对照成为漏注释候选，1 个未找到独立证据。逐位点证据写入
`review_top10.csv`，评估标签和指标保持不变。

发布脚本会把本地历史逐提交重放到远端，并校验提交 SHA 与目录树 SHA 都与本地一致，
不一致就报错退出；空仓库的首次提交由脚本自己播种。脚本会重写远端 `main`，运行前必须确认这次发布是用户要求的。详见 `REPRO.md` 第四节。

远端：https://github.com/jostarooo/glyco-analysis （公开仓库）。2026-11-02 经用户明确授权，REST 发布器把本地历史精确镜像到 `main`，发布后本地、远端和 W2 视频均为 `9b93d60`。普通 `git fetch` 仍受本机到 `github.com:443` 的网络重置影响，远端状态由 GitHub REST API 独立核验。W3 Day 1 至 Day 4 的本地提交尚未发布。

环境事实见 `REPRO.md`，复现用的三个上游仓库在 `D:\wbworkspace\`（LoRA-N-Gly / GlycanML / Doc2Agent）。

W1 正式交付目录为 `D:\毕设交付\W01_2026-10-27`。完整离线复核包位于
`D:\毕设交付\W1_完整交付_v1`，包含中文报告、核心数据、人工复核、源代码和逐文件
SHA256 清单。新录的 6 分 00 秒展示视频是正式周视频，3 分 34 秒的 10/26
版本保留备查。交付总表已改为 `已交`。

W2 正式交付目录为 `D:\毕设交付\W02_2026-11-03`。交付材料包含周报、核心证据、
验证记录、单文件交付界面和 SHA256 清单，不放源代码、模型权重或全部中间 task JSON。
W2 Day 3 阻断工具复测、50 题修正分类和验证日志已加入核心证据。W2 周视频与最终材料已进入交付目录，正式提交仍由用户完成。

W2 Day 4 记分卡保存在 `reports/w2_day4/`。生成器会重算 F1 混淆矩阵和 MCC、F2 三种子
均值与样本标准差，并校验 F3 计数、工具可行性 43/5/2、源文件 SHA256 和跨源参考值。
F3 的五个数都是工具轨迹或输出存在性，不是答案正确率；F2 是 PyG 自实现，
不是 TorchDrug 逐位复刻。

W3 Day 5 检查点保存在 `reports/w3_day5/`。生成器从 F1、F2 Table 3、F3 三模型、
真实系统结果和最新 unittest 日志重新计算，输出 JSON、Markdown 和源哈希。`--check`
会拒绝缺失、过期、手改或内部不一致的输出；该检查点不重新训练 F2，也不重新运行
任何 Doc2Agent 50 题。

## 目录

```
glyco-analysis/
├─ scripts/          可直接运行的脚本（环境、数据、探针、校验、检查点与 web 数据契约）
├─ reports/          体检、数据集、探针产物与发布记录
├─ agent-sessions/   本项目 AI 编程会话的脱敏、证据链接式工程归档
├─ docs/             设计与说明
├─ web/              交付前端界面（React + Vite，数据由 scripts/build_web_data.py 生成）
├─ system/           W3 登录、任务队列、真实 ESM-150M 推理服务与单文件 UI
├─ video-ui/         录制专用周报界面，与正式 web/ 分离
├─ data/             本地数据（不入库，见 .gitignore）
└─ REPRO.md          复现手册：可行性五关、术语表、本机配置
```

## 红线

- 前端不写死任何数字；
- 不用 Mock 冒真实功能；
- 界面标记的“数据基线”是生成 `web/src/data/` 时的 HEAD；视频开头必须另外现场运行 `git rev-parse HEAD`，不能拿界面短哈希替代最新提交证据；
- 生产前端必须是单个自包含的 `web/dist/index.html`，并用 `scripts/check_web_dist.py --browser` 从 `file://` 实际验证；
- **论文里的数字只能作为对照，不能当成自己的结果**；
- `web/` 界面只读展示 `web/src/data/` 的契约数据，不写死指标、不使用 Mock；
- `system/` 的 `serve` 必须装配真实 `Esm150Predictor`，测试替身只能由测试注入；
- `system/` 默认只绑定 `127.0.0.1`，非回环地址必须配置环境密码哈希，不能用本地演示账号；
- 页面上的位点概率来自作者检查点现场推理，不是实验阳性证据，也不是临床结论；
- F3 的 `exact_sequence`、期望工具覆盖、最终回答存在性和工具调用成功数都是轨迹指标，不是答案正确率；
- F3 答案评分必须同时报告可判定覆盖率，不能把 `judge_unavailable`、`manual_review` 或 `missing_answer` 合并成答错；
- 本轮 judge 是本地证据约束的 Kimi K3，不等于上游 GPT-4o 评分，也不能据此归因模型大小；
- 外部模型对照必须复用同一任务、工具目录、系统提示词和动作协议，不能静默改用 provider 原生工具协议；
- V4.1 Flash 免费路由的 429 结果不是模型能力结论，不能进入三模型能力对照；

## 引用与许可

复现对象 `NancyFyong/LoRA-N-Gly` 仓库无许可证（`license`），论文为 CC BY-NC-ND。
本项目仅作学习与研究用途，不用于商业分发。
