# W3 Day2：外部模型轨迹对照

- 归档日期：`2026-11-05`
- 文档性质：由真实 AI 编程会话汇编的脱敏工程记录，不是原始聊天，也不是本人日志总结
- 会话数量：4
- 证据数量：6

> 每条叙述都绑定真实消息或工具事件。证据摘录只保留与工程判断有关的部分，隐藏推理、无关上下文和敏感字段。

## 摘要

本日根据导师反馈，在同一批 50 题、同一工具协议和同一轮数上限下增加外部 GLM-5.3 对照，并把轨迹差异与答案正确率严格分开。 [E1105-MENTOR] [E1105-SUMMARY] [E1105-FINAL]

## 1. 反馈与问题重述

导师指出本地 Qwen3 4B 档位偏小，要求在同一套评测任务上增加外部接口对照，否则无法区分方法是问题还是模型规模问题。 [E1105-MENTOR]

本轮把问题限定为工具轨迹对照，不把命中期望工具或产生最终回答误写成答案正确率。 [E1105-MENTOR] [E1105-FINAL]

## 2. 方案评审

两个架构候选都拒绝复制现有工具执行循环，而是在原 runner 中加入可注入的聊天客户端，让本地 Ollama 和外部 OpenAI 兼容接口共享同一任务循环。 [E1105-ARCH-A] [E1105-ARCH-B]

候选 A 保存旧入口兼容性，候选 B 把 ChatFn、OpenAICompatibleConfig 和外部薄 CLI 进一步拆清。最终实现采用注入函数，同时保留既有 CLI 和测试路径。 [E1105-ARCH-A] [E1105-ARCH-B] [E1105-IMPL]

## 3. 实施与对照

实现新增外部 OpenAI-compatible 适配器、50 题 runner 和只读比较脚本，记录 provider、模型、完成原因、token usage 和每次工具状态。 [E1105-IMPL]

同题集对照结果显示，GLM-5.3 的期望工具命中数更高，但达到最大轮数的题更多，最终回答数反而低于本地 Qwen3 4B。 [E1105-SUMMARY] [E1105-FINAL]

summary checker 真实执行并通过，验证 50 题完整性、模型元数据和轨迹汇总可以从 task JSON 重算。 [E1105-SUMMARY] [E1105-FINAL]

## 判定边界

本日没有运行上游 GPT-4o 评分器，因此 19/34/41/39/110/78 与 13/41/47/25/129/114 只能解释为轨迹和终止行为，不是模型答对率。 [E1105-FINAL] [E1105-SUMMARY]

两端请求参数和 provider 计费口径不完全相同，token 数不能直接当作归一化成本。 [E1105-IMPL] [E1105-FINAL]

## AI 使用声明

本日由 AI 辅助比较架构、修改共享 runner、实现外部适配器并执行真实 50 题运行。记录中的结果来自实际 summary 和工具输出。 [E1105-ARCH-A] [E1105-IMPL] [E1105-SUMMARY]

## 证据索引

| 证据 | 类型 | 会话 | 原始定位 | 原始证据 SHA256 | 说明 |
|---|---|---|---|---|---|
| `E1105-MENTOR` | message | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=4750` | `0eadbd8c190142ac89ef5ce4fa9ee7670bcef4513f5448fda806913925760516` | 导师关于外部模型对照的反馈 |
| `E1105-ARCH-A` | message | `codex:01a1a9f3-f56c-7ff2-8705-9aa251a26e4e` | `ordinal=48` | `d4ba208b4343ab7d9b127616d94774b163445d5451a1110fe8c4c8ba5ed6dea1` | 外部模型适配架构候选 A |
| `E1105-ARCH-B` | message | `codex:01a1a9f3-fcf8-7d60-84ef-a7de5f4e3a95` | `ordinal=61` | `31fe25762ed321170b42e35b5317a97addc638e83cae1edfd7c745a1a25b8cef` | 外部模型适配架构候选 B |
| `E1105-IMPL` | message | `codex:01a1a9f8-fc20-7c40-8834-1a1eb057961f` | `ordinal=128` | `b7f365b22062ec5d7ca7f61a269856f18e1d8455268c8a0d1fa89a698f23f155` | 外部 runner 和比较脚本实现总结 |
| `E1105-SUMMARY` | tool | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=4914; call_index=0; event_index=0` | `eccb4380ecec1fe89a0682c69dc1f62bbc5ee31878cbb5758a1516784328bad1` | 外部 50 题 summary checker 输出 |
| `E1105-FINAL` | message | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=5068` | `9a5e39b4afb731198b1a6293935d8832ee8eec67946089fbfc234b39d75f5682` | 当日轨迹结果和不可比边界 |

## 脱敏证据摘录

### `E1105-MENTOR` 导师关于外部模型对照的反馈

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`message` / `user`
- 定位：`ordinal=4750`
- 原始证据 SHA256：`0eadbd8c190142ac89ef5ce4fa9ee7670bcef4513f5448fda806913925760516`
- 本摘录脱敏：无

```text
这周 GlycanML 复算、Doc2Agent 雏形，以及 React 四个页面且没有用假数据顶上，公开仓库也能对上提交，过程是清楚的。

缺的是一份独立的、「用自己的话写的日志总结」。现在没有这份东西，我只能看到结果，看不到你查问题的过程。另外，F3 你用的是本地 Qwen3-4B，档位偏小；我之前问过这件事。下周请在同一套评测任务上，再加一条外部接口（云端更大模型或课程允许的 API）做对照，把两边差距写清楚。否则别人无法判断：你现在的分数，有多少是方法问题，有多少是模型太小。

下周请：

1. 交独立的日志总结，对着具体日志原文写；
2. 同一评测任务补上外部接口对照，并写明差距。本周大家交的周交付（进度报告、用自己的话写的日志总结、大约 5 分钟的进度视频）我都看过了。下面是共同标准，你们每一个同时会收到一个针对性的私人信息，注意查收。

   **一、已经有同学做到的（这是加分方向）**
   1. 视频里是现场把系统跑起来，对着屏幕讲清楚「我做了什么、结果是什么」，而不是只念事先写好的稿子或 AI 报告。
   2. 碰到数字对不上、接口限流、环境崩了这类事，会对着真实日志一步步查，并写出：你当时猜是什么原因、对照试了什么、最后排除了什么；查不清的也如实写，不装成「都顺利」。
   3. 「用自己的话写的日志总结」是对着具体实验记录或报错原文讲明白：这条报错是什么意思、你试了什么、为什么改这个 —— 不是把本周进度再摘要一遍。
   4. 一周里既有能核对的复现或训练数字，也有能点开的系统页面；仓库里能看出这几天在持续推进，而不是快到截止日期才一口气堆很多提交。
   5. 主动说明哪些段落是 AI 起草、哪些数字自己核对过；写代码时用的是能读仓库、能跑命令的工具（例如 Cursor、Claude Code），而不是整周只靠弱免费网页聊天。
   **二、也有同学还没做到的（这是扣分方向，请自己对照）**
   1. 「用自己的话写的日志总结」写成了进度摘要或报告缩写，读完仍看不出你对着哪一份日志、排除过哪个假设。
   2. 在现在有 AI 协助的条件下，一周的工作量说不过去：整周几乎只在跑官方示例脚本或官方微调的冒烟测试，仓库里指认不出你自己改过的代码；或者复现数字齐了，但登录页、首页、业务页一个都没有。
   3. 视频仍是一堆截图，或照着报告 / PPT / AI 稿念；听完别人看不出你是否亲手跑通过当前系统。
   4. 困难只停在解释（「太难了所以没做」「环境下周再弄」「方案下周落地」），没有留下最小的尝试记录；免费或低价接口一返回 429（请求过多被限流），整周就停住，没有备用接口或本地对照。
   5. 正式三样（报告、用自己的话写的日志总结、大约 5 分钟个人项目介绍视频）仍不齐，又没有事先沟通清楚 —— 几段很短的碎片演示，不能代替完整周交付。
   **三、下周继续按这三样交（下周二 24:00 前私信）**
   1. 进度报告（可以先用 AI 起草，但必须自己改过、自己能负责）
   2. 用自己的话写的日志总结（必须能讲明白日志在说什么，不要只贴进度摘要）
   3. 大约 5 分钟的个人项目进度介绍视频（优先现场演示系统；禁止读 AI 报告或 PPT）
   4. 项目中包含使用 AI 工具针对项目的会话内容（参考第四条）
   **四、下周起将新增的要求**

   从下周周交付起，除上述三样外，还请把**本 302 项目相关的、你在写代码工具（比如 cursor, CC 等）里与 AI 的对话记录**同步到自己的 **GitHub 或 Gitee**（只同步项目信息，推荐用 AI 工具使用 AgentsView 导出，也可用 Cursor / Claude Code / Codex 自带的导出

... [证据摘录已按固定长度截断]
```

### `E1105-ARCH-A` 外部模型适配架构候选 A

- 会话：`codex:01a1a9f3-f56c-7ff2-8705-9aa251a26e4e`（W3 Day2 外部模型架构候选 A）
- 类型：`message` / `assistant`
- 定位：`ordinal=48`
- 原始证据 SHA256：`d4ba208b4343ab7d9b127616d94774b163445d5451a1110fe8c4c8ba5ed6dea1`
- 本摘录脱敏：无

```text
外部 API 适合给现有 runner 加一层传输适配，不需要另起一套 agent。GitHub 上也没有达到复用门槛的现成方案。

**推荐方案 A。** 保留 `scripts/run_doc2agent_qwen3.py` 的文件名和现有入口，在文件内加入 `ChatClient` 接口和两个实现，共享同一个工具执行循环。新增 `run_task_with_chat(task, tools, chat, max_rounds, system)` 作为统一核心；原 `run_task(task, tools, config, max_rounds, system)` 保留为 Ollama 兼容包装。新增 `compare_doc2agent_runs.py`，只读取两份 run 目录，核对 task_id、question、expected_tools 后比较指标，不改动旧 baseline。

**方案 B。** 拆出 `doc2agent_core.py`、`backends/ollama.py`、`backends/openai_chat.py`，再提供两个薄入口。边界更整齐，但会破坏现有测试用 `importlib` 直接加载单文件的路径，还需要兼容层。当前只多一个 provider，不值得先支付这次迁移成本。

**数据模型。**

```python
@dataclass(frozen=True)
class ModelReply:
    content: str
    elapsed_seconds: float
    finish_reason: str | None
    usage: dict[str, Any]

class ChatClient(Protocol):
    backend: str
    model: str
    endpoint: str
    def complete(self, messages: list[dict[str, str]]) -> ModelReply: ...

@dataclass(frozen=True)
class OpenAICompatConfig:
    endpoint: str
    model: str
    request_timeout: float
    max_tokens: int
    temperature: float = 0.0
    seed: int = 0
    api_key: str | None = None
    max_retries: int = 2
```

`OpenAICompatChatClient` 只发送 `model`、`messages`、`temperature`、`max_tokens`、`seed`、`stream=false`，不发送 Ollama 的 `options`、`think`、`format`、`num_ctx`。`TaskRun` 只增加 `model_calls`、`model_errors`、`model_elapsed_seconds`，现有 `tool_calls`、`final_answer`、`errors` 和 `score()` 形状保持不变。

**测试边界。** 现有 4 个 `parse_json_object` 测试必须原样通过。新增三类测试。第一，用假 `ChatClient` 返回“调用工具再完成”，断言工具函数只执行一次且结果回填。第二，mock `requests.post`，断言请求字段、`choices[0].message.content` 解析和异常 HTTP 响应处理。第三，断言新 summary 保留全部旧指标键，比较器拒绝题目或期望工具不一致的两批结果。

**输出与失败处理。** summary 继续保留 `tasks_run`、`exact_sequence`、`all_expected_called`、`any_expected_called`、`tasks_with_tool_call`、`tasks_with_final_answer`、`tool_call_successes`、`too

... [证据摘录已按固定长度截断]
```

### `E1105-ARCH-B` 外部模型适配架构候选 B

- 会话：`codex:01a1a9f3-fcf8-7d60-84ef-a7de5f4e3a95`（W3 Day2 外部模型架构候选 B）
- 类型：`message` / `assistant`
- 定位：`ordinal=61`
- 原始证据 SHA256：`31fe25762ed321170b42e35b5317a97addc638e83cae1edfd7c745a1a25b8cef`
- 本摘录脱敏：无

```text
目标是给 Doc2Agent 50 题增加外部 OpenAI 兼容模型，同时复用现有任务、工具目录、系统提示词和工具执行循环，只比较工具轨迹，不评价答案正确性。

**推荐方案 A**

在现有 runner 内注入模型调用函数，再增加一个很薄的外部 CLI。不要复制 `run_task`。

```python
ChatFn = Callable[[list[dict[str, str]]], ModelReply]

def run_task_with_chat(
    task: dict[str, Any],
    tools: dict[str, Tool],
    chat: ChatFn,
    max_rounds: int,
    system: str,
) -> TaskRun: ...

def run_task(
    task: dict[str, Any],
    tools: dict[str, Tool],
    config: OllamaConfig,
    max_rounds: int,
    system: str,
) -> TaskRun:
    return run_task_with_chat(
        task, tools, partial(call_ollama, config=config), max_rounds, system
    )

def call_openai_compatible(
    messages: list[dict[str, str]],
    config: OpenAICompatibleConfig,
) -> ModelReply: ...
```

新增 `scripts/run_doc2agent_external.py`，只负责：

- 调用现有的 `load_tasks`、`load_tools`、`compact_tool_catalog`、`system_prompt`。
- 创建 `OpenAICompatibleConfig`，默认地址 `http://127.0.0.1:3425/v1/chat/completions`，模型 `workbuddy-ai/glm-5.3`。
- 把 `call_openai_compatible` 注入 `run_task_with_chat`。
- 使用与本地相同的 `max_rounds=4`、`max_tokens=512`、`temperature=0`。`seed` 和 `response_format` 作为请求选项记录，服务端不支持时明确失败，不静默降级。
- 继续使用现有 JSON action 协议和本地 Python 工具调用。不要改用 OpenAI 原生 `tools` 或 `tool_choice`，否则轨迹语义会变。

现有 `run_doc2agent_qwen3.py` 的 CLI 参数和默认行为保持不变。原有 `run_task` 保留为 Ollama 包装器，现有测试文件不需要修改。

**数据模型**

```python
@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None

@dataclass(frozen=True)
class ModelReply:
    content: str
    elapsed_seconds: float
    usage: TokenUsage

@dataclass(frozen=True)
class RunMetadata:
    provider: str
    model: str
    endpoint: str
    prompt_version: str
    prompt_sha256: str
    tasks_sha256: str
    request_options: Mapping[str, Any]
```

在 `T

... [证据摘录已按固定长度截断]
```

### `E1105-IMPL` 外部 runner 和比较脚本实现总结

- 会话：`codex:01a1a9f8-fc20-7c40-8834-1a1eb057961f`（W3 Day2 外部模型 runner 实现）
- 类型：`message` / `assistant`
- 定位：`ordinal=128`
- 原始证据 SHA256：`b7f365b22062ec5d7ca7f61a269856f18e1d8455268c8a0d1fa89a698f23f155`
- 本摘录脱敏：无

```text
The goal was a reproducible external GLM run without changing Doc2Agent task semantics, tools, or the existing Qwen3 results. The smallest implementation reuses the existing loop through `ChatFn`, keeps HTTP parsing at one boundary, and compares only trajectory fields both runs actually record.

Code paths changed:

- `D:\Codex\workspace\glyco-analysis-w3-day2-external\scripts\run_doc2agent_qwen3.py`
- `D:\Codex\workspace\glyco-analysis-w3-day2-external\scripts\run_doc2agent_external.py`
- `D:\Codex\workspace\glyco-analysis-w3-day2-external\scripts\compare_doc2agent_runs.py`
- `D:\Codex\workspace\glyco-analysis-w3-day2-external\tests\test_doc2agent_chat_runner.py`
- `D:\Codex\workspace\glyco-analysis-w3-day2-external\tests\test_doc2agent_external_runner.py`
- `D:\Codex\workspace\glyco-analysis-w3-day2-external\tests\test_doc2agent_comparison.py`

The ignored working checklist is at `D:\Codex\workspace\glyco-analysis-w3-day2-external\.audit\w3-day2-external.todo.md`. No file under `D:\wbworkspace\glyco-analysis` was touched. Branch is `codex/w3-day2-external-api`, based on `7c5dc62`, with no commit.

Schema decisions:

- `ChatReply` carries `content`, elapsed time, `finish_reason`, and `usage`. Every shared-loop model attempt is recorded, including failures.
- External summaries retain all existing trajectory fields and add provider, model, endpoint, prompt hashes, task hash, request options, token totals, model-call count, and finish-reason counts.
- `task_hash` covers the selected task rows. Prompt hashes cover the system prompt, user template, and compact tool catalog.
- The API key comes only from `MAGPIE_API_KEY` by default, or the environment variable named by `--api-key-env`. It is never a CLI value, request output, summary field, or error log. Error text redacts

... [证据摘录已按固定长度截断]
```

### `E1105-SUMMARY` 外部 50 题 summary checker 输出

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`tool` / `exec_command`
- 定位：`ordinal=4914; call_index=0; event_index=0`
- 原始证据 SHA256：`eccb4380ecec1fe89a0682c69dc1f62bbc5ee31878cbb5758a1516784328bad1`
- 本摘录脱敏：USER_HOME 1 次

```text
工具：exec_command
状态：(未标记)

参数：
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'; $env:PYTHONUTF8='1'; $py='%USERPROFILE%\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe'; & $py 'D:\Codex\workspace\glyco-analysis-w3-day2-external\scripts\summarize_doc2agent_run.py' --run-dir 'D:\Codex\workspace\glyco-analysis-w3-day2-external\reports\w3_day2\f3_glm53_50' --expected-tasks 50 --check-summary 'D:\Codex\workspace\glyco-analysis-w3-day2-external\reports\w3_day2\f3_glm53_50\summary.json'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; & $py 'D:\Codex\workspace\glyco-analysis-w3-day2-external\scripts\summarize_doc2agent_run.py' --run-dir 'D:\Codex\workspace\glyco-analysis-w3-day2-external\reports\w2_day2\f3_qwen3_4b_50' --expected-tasks 50 --check-summary 'D:\Codex\workspace\glyco-analysis-w3-day2-external\reports\w2_day2\f3_qwen3_4b_50\summary.json'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; & $py 'D:\Codex\workspace\glyco-analysis-w3-day2-external\scripts\compare_doc2agent_runs.py'

结果：
Process exited with code 0
{
  "status": "PASS",
  "metrics": {
    "tasks_run": 50,
    "exact_sequence": 13,
    "all_expected_called": 41,

... [证据摘录已按固定长度截断]
```

### `E1105-FINAL` 当日轨迹结果和不可比边界

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`message` / `assistant`
- 定位：`ordinal=5068`
- 原始证据 SHA256：`9a5e39b4afb731198b1a6293935d8832ee8eec67946089fbfc234b39d75f5682`
- 本摘录脱敏：无

```text
**完成情况**
老师 2026-11-05 的新规则已写入 `D:\ObsidianVault\10-项目\20-毕设糖基化分析系统\302 项目周交付与可复用资产规范（2026-10-29）.md`，包括独立日志总结的验收口径、同题集外部接口对照、`agent-sessions/YYYY-MM-DD/` 会话归档和脱敏边界。

W3 Day2 的外部模型对照已经完成。外部模型通过本机 Magpie 的 OpenAI-compatible 网关调用 `workbuddy-ai/glm-5.3`，与本地 Qwen3 4B 使用同样的 50 题、70 个工具、系统提示词、JSON 动作协议和 4 轮上限。

- Qwen3 4B：`19/34/41/39/110/78`
- GLM-5.3：`13/41/47/25/129/114`
- 指标顺序为 `exact_sequence`、`all_expected_called`、`any_expected_called`、最终回答数、工具调用数、成功工具调用数
- GLM-5.3 更常命中期望工具，但 20 题达到最大轮数，最终回答数反而少于本地 4B

这些数字只描述工具轨迹和终止行为，不是答案正确率。GPT-4o 评分器没有运行，因此不能写成模型答对率差异。

**文档与归档**
`README.md`、`REPRO.md`、`reports/weekly/W03_2026-11-10_progress.md` 已补上两端参数差异和 token 口径。知识库任务 #266 已从“外部对照脚手架”改为真实完成的 50 题对照，并新增跨模型评测经验页：

`D:\ObsidianVault\20-环境与踩坑\跨模型轨迹对照：同题集、同工具协议与 token 不可比.md`

最终提交为 `355c749a43614d1adb15f46eecc6ae94be12b61e`，工作树干净，未 push。`交付总表.md` 的 W03 行已加入 `355c749`，W02 仍保持“进行中”。

**验证结果**
- 全量 unittest 157 项，149 项通过，8 项按设计或 GPU 门控跳过
- 本地 Qwen3 4B summary checker：PASS
- 外部 GLM-5.3 summary checker：PASS
- task ID、question、expected tools：50/50 对齐
- `git diff --check`：通过
- Obsidian：407 篇笔记、27 个项目、33 个工作日、265 项任务、2189 条内链，断链 0
- 第二次 `reindex` 修改 0 个文件，`audit` 和 `check` 均通过

**仍需你本人完成**
独立日志总结必须由你根据具体日志原文改写，不能直接用 AI 生成的证据包代替。证据入口是 `reports/w3_day2/log_summary_evidence.md`。老师要求的 `agent-sessions/` 目录和规则已经建立，但原始 Codex 会话体积超过 100 MB，且未完成项目筛选和脱敏，因此没有直接提交，下一次交付前需要按 `agent-sessions/README.md` 导出并检查。

本轮

... [证据摘录已按固定长度截断]
```
