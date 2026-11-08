# W3 Day1：真实位点预测系统纵切

- 归档日期：`2026-11-04`
- 文档性质：由真实 AI 编程会话汇编的脱敏工程记录，不是原始聊天，也不是本人日志总结
- 会话数量：4
- 证据数量：7

> 每条叙述都绑定真实消息或工具事件。证据摘录只保留与工程判断有关的部分，隐藏推理、无关上下文和敏感字段。

## 摘要

本日把已有位点模型接成可登录、可排队、可由浏览器提交序列的真实系统纵切，并把架构评审、界面实现和真实 GPU 验证拆成可核对的步骤。 [E1104-USER] [E1104-TESTS] [E1104-GPU] [E1104-FINAL]

## 1. 任务与工程约束

用户要求完成第三周第一天的任务，目标不是再写一份静态说明，而是补齐一个可以现场运行的真实系统。 [E1104-USER]

两个架构候选都把登录、任务队列、模型运行时和 HTTP 接口放在独立目录，明确不改动已有的 web、video-ui 和原训练脚本。这样可以把交付演示界面与正式训练复现代码隔离。 [E1104-ARCH-A] [E1104-ARCH-B]

## 2. 方案选择

候选 A 把新系统拆成 contracts、auth、jobs、esm_runtime、http_app 等模块，并强调只在运行时模块接触模型代码。 [E1104-ARCH-A]

候选 B 进一步核对了本机依赖，确认 FastAPI、uvicorn、Flask 等框架未安装，因此采用 Python 标准库 ThreadingHTTPServer，避免为了一个演示系统再引入新框架。 [E1104-ARCH-B]

最终实现保留了独立系统边界、单模型工作线程、懒加载和复用现有 ESM-2 推理代码这几项共同结论。 [E1104-ARCH-A] [E1104-ARCH-B] [E1104-FINAL]

## 3. 实现与问题定位

单文件界面把登录、会话恢复、CSRF、序列校验、排队轮询、结果表格和研究原型免责声明放在同一页面，目标是 Edge 下可以直接演示。 [E1104-UI]

界面评审发现并如实保留了两个未完成项：当时尚未接入真实后端，HTTP 模式下浏览器仍自动请求缺失的 favicon 并产生一个 404。后续验收没有把这个 404 伪装成全部通过。 [E1104-UI]

最终纵切使用真实 ESM-2 150M LoRA 预测器，把冷启动 HTTP 时间和纯推理时间分开记录，避免把首次加载与稳态推理混成一个性能数字。 [E1104-FINAL]

## 4. 验证结果

代码编译、diff 检查和全量回归均真实执行；当时全量回归为 147 项，其中 139 项通过、8 项按设计或 GPU 门控跳过。 [E1104-TESTS] [E1104-FINAL]

真实样例 O75144 返回 6 个位点，6 个历史标签全部一致，最大概率差为 0。运行记录同时给出 RTX 5060 设备、adapter SHA256 和模型张量数，便于复核不是静态假数据。 [E1104-GPU] [E1104-FINAL]

## 判定边界

该系统只处理 N-X-S/T sequon 位点预测，概率不是实验验证，也不是临床诊断。 [E1104-ARCH-A] [E1104-UI]

147 项测试是当日代码快照的结果，不代表后续提交仍然完全等价；后续改动必须重新跑回归。 [E1104-TESTS] [E1104-FINAL]

## AI 使用声明

本日包含 AI 辅助的架构比较、界面实现、代码修改和测试执行。记录保留真实工具输出，不包含隐藏推理。 [E1104-ARCH-A] [E1104-ARCH-B] [E1104-UI] [E1104-TESTS]

## 证据索引

| 证据 | 类型 | 会话 | 原始定位 | 原始证据 SHA256 | 说明 |
|---|---|---|---|---|---|
| `E1104-USER` | message | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=4472` | `fa614fb52ed91eae9660ff9ebb4b5e15e158a60c30db3a491e50c412530e055b` | 用户当日任务 |
| `E1104-ARCH-A` | message | `codex:01a1a465-2960-70a0-9cf6-ebd15c5c1da9` | `ordinal=46` | `bd947d02cb5864fb478d7c7ce79a685882f37e634a7dcc37ea2810a6719372d1` | 候选 A 的模块边界和系统结论 |
| `E1104-ARCH-B` | message | `codex:01a1a465-3094-76e1-8d7f-709e569d270f` | `ordinal=48` | `09b6c5ea0df07c5265016e40a3089591bdb560544d01cf664db29725e32a8fc7` | 候选 B 的本机依赖核对和标准库方案 |
| `E1104-UI` | message | `codex:01a1a46e-25e8-70f2-a013-a49ca614042c` | `ordinal=79` | `8726d7ae01ca2ff65d2e7599a2bc2ba16fb90b4192567063d0603b62e6037d24` | 单文件工作台实现与未完成项 |
| `E1104-TESTS` | tool | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=4672; call_index=0; event_index=0` | `0dd28278b76774645875229a9d2aee06b38697669347b9b95fdab450c1ea3766` | 编译、diff 和 147 项回归结果 |
| `E1104-GPU` | tool | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=4710; call_index=0; event_index=0` | `20337cb7118f2b5d44ce4ee154bd4fb2fb847d75829cff7c2f00987e99e3ae1d` | 真实 GPU 端到端产物摘要 |
| `E1104-FINAL` | message | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=4749` | `f34df26e79b4f48b7a94120ae7cd90678f9290c626b253fa35ccc64d46a3e37c` | 当日完成总结和冷启动口径 |

## 脱敏证据摘录

### `E1104-USER` 用户当日任务

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`message` / `user`
- 定位：`ordinal=4472`
- 原始证据 SHA256：`fa614fb52ed91eae9660ff9ebb4b5e15e158a60c30db3a491e50c412530e055b`
- 本摘录脱敏：无

```text
请完成第三周第一天的任务
```

### `E1104-ARCH-A` 候选 A 的模块边界和系统结论

- 会话：`codex:01a1a465-2960-70a0-9cf6-ebd15c5c1da9`（W3 Day1 系统架构候选 A）
- 类型：`message` / `assistant`
- 定位：`ordinal=46`
- 原始证据 SHA256：`bd947d02cb5864fb478d7c7ce79a685882f37e634a7dcc37ea2810a6719372d1`
- 本摘录脱敏：无

```text
**候选 A：独立 W3 Live 纵切**

结论：新增独立的 `w3_live/` 服务和一套新的浏览器 UI，不把登录、API、模型调用塞进 `D:\wbworkspace\glyco-analysis\web\` 或 `video-ui\`。数据流为：浏览器 → 标准库 HTTP 服务（认证、任务、静态页）→ 单模型 worker → 现有 ESM-150M LoRA 推理代码 → GPU。

**模块边界**

| 模块 | 责任 |
|---|---|
| `w3_live/contracts.py` | 请求/任务/结果数据结构、序列校验、错误码 |
| `w3_live/auth.py` | 单演示账户、密码哈希校验、内存会话、CSRF、登录限流 |
| `w3_live/jobs.py` | `JobService`、`InferencePort`、FIFO 队列、任务状态与结果 TTL |
| `w3_live/esm_runtime.py` | 唯一接触模型代码的模块；校验 checkpoint，懒加载，执行真实推理 |
| `w3_live/http_app.py` | `ThreadingHTTPServer` 路由、静态文件、请求大小限制、安全响应头 |
| `w3_live/__main__.py` | `serve`、`doctor`、`hash-password` |
| `w3_live/static/` | 登录页和推理工作台，无 Node 构建、无外部 CDN |

现有 CLI 不能直接接收任意序列：`run_esm150_lora_repro.py` 的 `main()` 固定了作者 `test.csv` 的 SHA、列和 2554 行口径。因此服务不调用它的 CLI，而是通过 `importlib` 复用其中的 `load_model`、`residue_and_motif`、`softmax_two`、`binary_argmax`，不复制模型结构，也不改原脚本行为。`run_esm150_candidate_inference.py` 同样固定 201 行，只作为实现参考。

**数据形状**

- 提交请求：`sequence`、可选 `protein_id`。
- `JobView`：`job_id`、`status`、`stage`、`progress`、`input`、`model`、`result`、`error`、时间戳。
- `SitePrediction`：1-based `position`、`residue`、`motif`、`logit_negative`、`logit_positive`、`prob_negative`、`prob_positive`、`predicted_label`。
- `ModelInfo`：基座 ID/revision、adapter SHA-256、adapter 张量数、设备、dtype、attention backend、`full_sequence=true`、`truncation=false`、`windowing=false`、加载告警。
- 输入统一转大写，只接受 ESM 词表支持的标准/歧义残基；超过 6000 aa 直接拒绝，绝不截断。序列无 `N-X-S/T` 时返回合法空结果，不伪造位点。
- `sequence_sha256` 对规范化序列计算，用于追溯；不持久化原始序列到磁盘或日志。

**HTTP API**

| 方法/路径 | 说明 |
|---|---|
| `GET /healthz` | 公开；返回服务状态和全局模型状态 `cold/loading/ready/error`，不触发加载 |
| `POST /api/auth/login` | 校验密码，设置会话 Cookie，返回 CSRF token |
| `POST /api/auth/logout` | 注销当前会话 |
| `GET /api/auth/session` | 返回登录状态和 CSRF token |
| `GET /api/v1/model` | 登录后读取模型来源信息，不加载 GPU 模型 |
| `POST /api

... [证据摘录已按固定长度截断]
```

### `E1104-ARCH-B` 候选 B 的本机依赖核对和标准库方案

- 会话：`codex:01a1a465-3094-76e1-8d7f-709e569d270f`（W3 Day1 系统架构候选 B）
- 类型：`message` / `assistant`
- 定位：`ordinal=48`
- 原始证据 SHA256：`09b6c5ea0df07c5265016e40a3089591bdb560544d01cf664db29725e32a8fc7`
- 本摘录脱敏：无

```text
**候选 B 结论**
采用“**Python 标准库 `ThreadingHTTPServer` + 原生单文件 UI + 单模型工作线程 + 复用现有 ESM-2 推理代码**”。新建独立目录 `D:\wbworkspace\glyco-analysis\w3_server\`，不修改 `web/`、`video-ui/` 或 `scripts/run_esm150_lora_repro.py`。

本机已确认：`fastapi/uvicorn/flask/bottle/waitress` 均未安装；固定兼容环境中的 `torch 2.9.1+cu128`、`transformers 4.50.3`、`peft 0.14.0` 可用。因此不安装新框架。

**模块边界**

| 模块 | 职责 |
|---|---|
| `w3_server/__main__.py` | 参数、环境检查、依赖装配、启动/停止服务器 |
| `w3_server/http_api.py` | 路由、JSON、请求体上限、Cookie 鉴权、错误映射 |
| `w3_server/auth.py` | 单演示账号、PBKDF2 密码校验、会话、失败限流 |
| `w3_server/jobs.py` | 有界队列、单 worker、任务状态、TTL 和清理 |
| `w3_server/predictor.py` | 懒加载真实模型、校验检查点、全序列前向、sequon 打分 |
| `w3_server/ui/index.html` | 登录页和预测工作台，内联 CSS/JS，无外部资源 |
| `scripts/run_w3_server.ps1` | 设置本机 Python 路径和离线模型环境后启动 |

`predictor.py` 通过文件路径导入现有 `D:\wbworkspace\glyco-analysis\scripts\run_esm150_lora_repro.py`，复用 `load_model`、`residue_and_motif`、`softmax_two`、`binary_argmax`。任意序列的少量前向代码在新包装层中完成，并用现有预测产物做黄金样本对拍，不复制或重训模型。

**数据形状与 API**

请求仅接受原始蛋白序列，去空白、转大写；允许 ESM 词表字符 `ACDEFGHIKLMNPQRSTVWYBXZUOJ`，长度 `1..5179`，与已实测最长序列一致。不持久化原始序列，只记录 SHA256、长度、耗时和状态。

| 方法 | 路径 | 行为 |
|---|---|---|
| `POST` | `/api/auth/login` | 用户名密码登录，成功设置会话 Cookie |
| `GET` | `/api/auth/session` | 返回当前登录状态 |
| `POST` | `/api/auth/logout` | 销毁会话 |
| `POST` | `/api/predictions` | 创建推理任务，返回 `202 + job_id` |
| `GET` | `/api/predictions/{job_id}` | 查询 `queued/loading_model/running/succeeded/failed` |
| `GET` | `/api/runtime` | 需登录；返回模型是否加载、设备和检查点信息 |
| `GET` | `/healthz` | 仅表示 HTTP 进程存活，不冒充模型就绪 |

预测结果中的 `sites` 包含全部 `N-X-S/T`、`X != P` 位点，位置从 1 开始：

`position`、`motif`、`prob_positive`、`predicted_label`、`logit_negative`、`logit_positive`。

响应同时带 `sequence_sha256`、`sequence_length`、`adapter_sha256`、`base_model_revision`、`attention_backend`、`full_sequence=true`、`truncation=false`、`w

... [证据摘录已按固定长度截断]
```

### `E1104-UI` 单文件工作台实现与未完成项

- 会话：`codex:01a1a46e-25e8-70f2-a013-a49ca614042c`（W3 Day1 单文件系统界面实现）
- 类型：`message` / `assistant`
- 定位：`ordinal=79`
- 原始证据 SHA256：`8726d7ae01ca2ff65d2e7599a2bc2ba16fb90b4192567063d0603b62e6037d24`
- 本摘录脱敏：USER_HOME 1 次

```text
目标是在真实后端接通前，交付一个用于 Edge 演示的 W3 Day1 登录与位点预测单文件工作台。当前实现位于 `%USERPROFILE%\.codex\worktrees\w3-system-ui\glyco-analysis\system\static\index.html`。Git 状态只显示该未跟踪文件，未提交，未修改其他仓库文件。

**已运行检查**
- Node.js `--check` 通过，内联 JavaScript 无语法错误。
- Python `HTMLParser` 检查通过。文件为 106,130 字节，包含 1 个内联样式和 1 个内联脚本，63 个唯一 DOM ID，58 个脚本引用的 DOM ID 均存在。
- 未发现外部脚本、样式、图片 URL、`@import` 或 `http://`、`https://` 资源。
- 5 个约定 API 路径、冷加载、排队、空候选、CSRF 和免责声明文案均存在。
- Playwright 驱动 Edge 通过 HTTP 加载成功，返回 200，`data-ready=true`，页面脚本错误为 0。
- 控制台仍有一个 `404`，来自浏览器自动请求缺失的 favicon。按要求停止修改，未修复。

**关键交互**
- 登录、退出、页面加载时恢复 Cookie 会话，以及受保护请求携带 `X-CSRF-Token`。
- 模型来源 badge、完整运行配置、服务端真实样例载入。
- 序列长度、标准氨基酸字符检查和非法字符提示。
- 提交任务后轮询排队、冷加载、推理、完成和失败状态。
- 候选位点表格、两位小数百分比、logit、阳性判定、空候选状态、模型限制和 API 错误状态。
- 免责声明“研究原型，不是临床诊断，概率不是实验验证”固定展示。
- 登录首屏、分析工作台、移动端断点和 `prefers-reduced-motion` 均已实现。

**明显未完成或未验证**
- 未连接主线程即将实现的真实服务端，未完成从登录到真实预测结果的完整浏览器流程。
- 未验证真实模型的冷加载耗时、队列更新节奏和失败响应兼容性。
- 未进行桌面与移动端截图级视觉验收。
- HTTP 模式下 Edge 首屏挂载已通过，`file://` 的 `dump-dom` 冒烟未通过，但生产目标是 same-origin HTTP。
- 临时内存验证服务可能仍在 `127.0.0.1:8765` 运行。按要求未再执行清理命令。

影响实现的 `Model the Domain` 原则促成了认证、运行态和任务状态的明确状态机。`Boundary Discipline` 与 `Type System Discipline` 原则促成了所有 API 数据在请求边界解析，页面不生成预测数字。`Experience First` 原则促成了登录首屏、清楚的任务阶段和空结果、错误状态。`Laziness Protocol` 原则促成了零依赖单文件实现。`Prove It Works` 原则促成了上述语法、结构和 Edge 实际加载检查。
```

### `E1104-TESTS` 编译、diff 和 147 项回归结果

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`tool` / `write_stdin`
- 定位：`ordinal=4672; call_index=0; event_index=0`
- 原始证据 SHA256：`0dd28278b76774645875229a9d2aee06b38697669347b9b95fdab450c1ea3766`
- 本摘录脱敏：无

```text
工具：write_stdin
状态：(未标记)

参数：
{
  "chars": "",
  "max_output_tokens": 30000,
  "session_id": 84815,
  "yield_time_ms": 30000
}

结果：
Process exited with code 0
=== py_compile_2026-11-04.txt EXIT 0 ===

=== git_diff_check_2026-11-04.txt EXIT 0 ===

=== unittest_2026-11-04.txt EXIT 0 ===
Ran 147 tests in 29.734s

OK (skipped=8)
web data contract PASS
project.json
metrics.json
tools.json
boundaries.json
```

### `E1104-GPU` 真实 GPU 端到端产物摘要

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`tool` / `exec_command`
- 定位：`ordinal=4710; call_index=0; event_index=0`
- 原始证据 SHA256：`20337cb7118f2b5d44ce4ee154bd4fb2fb847d75829cff7c2f00987e99e3ae1d`
- 本摘录脱敏：无

```text
工具：exec_command
状态：(未标记)

参数：
$env:PYTHONUTF8='1'; D:\python\python.exe -c "from pathlib import Path; base=Path(r'D:\wbworkspace\glyco-analysis\reports\w3_day1'); names=['real_e2e_2026-11-04.json','browser_e2e_2026-11-04.json','doctor_2026-11-04.txt','validation_2026-11-04.md'];
for n in names:
 p=base/n; print('\n===== '+n+' ====='); print(p.read_text(encoding='utf-8-sig')[:12000])"

结果：
Process exited with code 0

===== real_e2e_2026-11-04.json =====
{
  "head": "eac3566d80387ce9cef7ac921aef77c6aba2a6bd",
  "run_mode": "cold_start",
  "model_state_before": "cold",
  "model": {
    "base_model_id": "facebook/esm2_t30_150M_UR50D",
    "base_model_revision": "a695f6045e2e32885fa60af20c13cb35398ce30c",
    "adapter_sha256": "A4A5B486862724F459F60E8343AC135C340305D5A0F2E936EB5AD1DFD34788D4",
    "adapter_tensor_count": 376,
    "device": "NVIDIA GeForce RTX 5060 Laptop GPU",
    "state": "ready",
    "attention_backend": "sdpa",
    "full_sequence": true,
    "truncation": false,
    "windowing": false
  },
  "sample_accession": "O75144",
  "sample_source": "reports/candidates_30_lora.csv + reports/esm150_w1_candidates_v0/predictions.csv",
  "stages": [
    [
      "loading_model",
      "首次加载真实 ESM-2 150M LoRA 检查点",
      0
    ],
    [
      "succeeded",
      "完成",
      0
    ]
  ],
  "wall_seconds": 22.63631170000008,
  "inference_seconds": 6.588676699999269,
  "candidate_count": 6,
  "sequence_length": 302,
  "sequence_sha256": "0CA51F904C28299D8ED0B0DC85EDC28E9F28DF28A7968477D36F062D257722E0",
  "site_matches": [
    {
      "position": 70,
      "motif": "NSS",
      "predicted_label": 1,
      "prob_delta": 0.0,
      "label_match": true
    },
    {
      "position": 102,
      "motif": "NVT",
      "predicted_label": 1,
      "prob_delta": 0.0,
      "label_matc

... [证据摘录已按固定长度截断]
```

### `E1104-FINAL` 当日完成总结和冷启动口径

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`message` / `assistant`
- 定位：`ordinal=4749`
- 原始证据 SHA256：`f34df26e79b4f48b7a94120ae7cd90678f9290c626b253fa35ccc64d46a3e37c`
- 本摘录脱敏：PASSWORD_CN 1 次

```text
**W3 Day1 已完成**

- 已打通登录、序列提交、有界队列、单 GPU worker、懒加载和真实 ESM-2 150M LoRA 位点预测。
- `O75144` 返回 6 个位点，6/6 与历史标签一致，最大概率差为 0。
- 冷启动 HTTP 为 `22.636312` 秒，纯推理为 `6.588677` 秒，两个口径已分开记录。
- 系统聚焦测试 25/25，真实 GPU 回归 3/3，全量测试 147 项中 139 项通过、8 项门控跳过；Edge 页面错误和控制台错误均为 0。

**当前入口**

本地服务正在运行：[http://127.0.0.1:8765](http://127.0.0.1:8765)，演示账号 `demo`，密码 [REDACTED:PASSWORD]。`/healthz` 返回 HEAD `7c5dc62`，工作树干净。

交付总表 W03 已更新为“进行中”，记录提交 `eac3566`、`f8ec171`、`7c5dc62`。最终 HEAD 为 `7c5dc620b50b3d03c7f4ea7d609b52fa30b2ad2a`，未 push。

**归档与验证**

任务笔记、冷启动和单 GPU worker 经验、项目总览、首页、任务总览及 `2026-11-04` 时间线均已更新。知识库最终审计为 404 篇笔记、27 个项目、32 个工作日、264 项任务、2170 条内链、断链 0；第二次 `reindex` 修改 0 个文件。

本轮采用的核心原则是 `principle-prove-it-works`，用真实 GPU、真实 HTTP 和 Edge 现场流程验收；以及 `principle-model-the-domain`，把会话、任务、模型来源和位点结果建成明确的数据结构与状态机。

W02 仍需你本人补充手写日志总结并完成正式提交。
```
