# W3 Day3：Doc2Agent 答案评分与覆盖对照

- 归档日期：`2026-11-06`
- 文档性质：由真实 AI 编程会话汇编的脱敏工程记录，不是原始聊天，也不是本人日志总结
- 会话数量：4
- 证据数量：5

> 每条叙述都绑定真实消息或工具事件。证据摘录只保留与工程判断有关的部分，隐藏推理、无关上下文和敏感字段。

## 摘要

本日为已有两份 Doc2Agent 轨迹补上同一 rubric、同一本地 judge 的证据约束评分，并把可判定正确率、回答覆盖率和全 50 题正确数同时报告。 [E1106-ARCH-A] [E1106-IMPL] [E1106-FINAL]

## 1. 为什么需要答案评分

此前只有工具轨迹指标，不能回答最终答案是否正确。候选 A 明确指出，19/50、13/50 这类数字不能直接当作答案正确率。 [E1106-ARCH-A]

用户要求继续完成当日工作，本轮因此把评分器、覆盖率对照、验证、文档和归档一次闭环。 [E1106-USER] [E1106-FINAL]

## 2. 评分架构

候选 A 要求先做确定性证据审计，再调用 judge；空回答、工具失败和证据不足在调用模型前直接分流，不能把没答出来写成答错。 [E1106-ARCH-A]

候选 B 进一步把输入对齐、轨迹归一化、证据审计、judge 请求、响应解析和汇总拆开，强调模型只判断语义，其他规则由代码负责。 [E1106-ARCH-B]

最终实现采用可替换 judge adapter 加独立证据审计，加入缓存、原子写入、离线检查和六种明确状态。 [E1106-IMPL]

## 3. 真实结果

Qwen3 4B 得到 9 个 correct、29 个 incorrect、1 个 manual_review 和 11 个 missing_answer；GLM-5.3 得到 18 个 correct、3 个 incorrect、4 个 manual_review 和 25 个 missing_answer。 [E1106-FINAL]

报告同时保留可判定覆盖率和全 50 题正确数。GLM 在可判定子集上更高，但最终回答覆盖明显更低，不能据此直接写成整体模型优劣。 [E1106-FINAL]

## 4. 验证与失败边界

评分聚焦测试 18 项通过，全量测试 175 项中 167 项通过、8 项门控跳过，两份评分结果和两份 F3 summary 都能离线复核。 [E1106-IMPL] [E1106-FINAL]

## 判定边界

本日使用的是本地 Kimi K3 证据评分器，不是上游 GPT-4o 等价评分，不能与上游 Claude 18/50 或 Qwen3 15/50 直接比较。 [E1106-FINAL]

可判定正确率的分母是存在最终回答且通过证据门的题，不是全部 50 题。必须同时看 coverage 与 correct_over_task_count。 [E1106-FINAL] [E1106-ARCH-A]

## AI 使用声明

本日由 AI 完成架构比较、评分器实现、真实 judge 调用和文档整理。原始 judge 响应、逐题评分和离线 checker 保留在仓库报告中。 [E1106-ARCH-A] [E1106-ARCH-B] [E1106-IMPL] [E1106-FINAL]

## 证据索引

| 证据 | 类型 | 会话 | 原始定位 | 原始证据 SHA256 | 说明 |
|---|---|---|---|---|---|
| `E1106-USER` | message | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=5069` | `d33078b677d3c455336f100a6292aa98cf7b72c1d32d136a95cd1ea4ee796f2e` | 用户当日任务 |
| `E1106-ARCH-A` | message | `codex:01a1af1c-4ed8-7650-b1aa-7be2e378fddd` | `ordinal=28` | `6cefc1d8514c11fc88c8a03933320c8efb810b74814073e924782f5e0c93e622` | 答案评分架构候选 A |
| `E1106-ARCH-B` | message | `codex:01a1af1c-5714-7e71-a7c4-d2babf18b27d` | `ordinal=33` | `685c7210a6f5f2dbdabec735d8aeb7ab4587d9ff9b26ec8c2eb3637739bda3bf` | 答案评分架构候选 B |
| `E1106-IMPL` | message | `codex:01a1af1f-ccd5-7571-bafb-c45dd01ddefe` | `ordinal=96` | `d6a4b489283274eab66136490a5e714b62528c01e945241de865407d1ed208bc` | 评分器和比较器实现总结 |
| `E1106-FINAL` | message | `codex:01a180cf-92f6-7813-88f3-915158a80cab` | `ordinal=5460` | `8ea90da8e861de61715e1a416b9bf28407112b03e7bbdd1e1c1ff7f27062849b` | 评分结果、覆盖率和验证结论 |

## 脱敏证据摘录

### `E1106-USER` 用户当日任务

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`message` / `user`
- 定位：`ordinal=5069`
- 原始证据 SHA256：`d33078b677d3c455336f100a6292aa98cf7b72c1d32d136a95cd1ea4ee796f2e`
- 本摘录脱敏：无

```text
请完成今天的任务
```

### `E1106-ARCH-A` 答案评分架构候选 A

- 会话：`codex:01a1af1c-4ed8-7650-b1aa-7be2e378fddd`（W3 Day3 答案评分架构候选 A）
- 类型：`message` / `assistant`
- 定位：`ordinal=28`
- 原始证据 SHA256：`6cefc1d8514c11fc88c8a03933320c8efb810b74814073e924782f5e0c93e622`
- 本摘录脱敏：无

```text
**目标**

为 W3 Day3 的 Doc2Agent 结果增加一份可复审的答案评分契约。当前两份运行结果只有工具轨迹指标，不能把 `19/50`、`13/50` 这类数字当成答案正确率。候选 A 的核心是先用真实工具证据做前置筛选，再让 judge 做语义判断，并把无法评分的情况单独保留。

**候选 A**

流程固定为五步。

1. 读取上游题目、`expected_answer` 和 `expected_tools`，同时读取本地 task JSON 的最终回答与工具调用。
2. 只有 `status=ok` 的调用进入证据目录。`ok` 只表示接口返回成功，不自动表示结果足以回答题目。
3. 空回答、工具失败、没有可用证据的案例在调用 judge 前直接终止，不消耗 judge，也不把“没答出来”算成“答错”。
4. 通过证据前置筛选的案例，交给本地 `workbuddy-ai/gpt-5.6-sol` 做证据约束的语义判断。judge 必须引用证据 ID，不能只给一个 SUCCESS。
5. 纯函数校验 judge 的证据引用、缺失要求和判定状态，再生成终态。任何非法引用都进入人工复核或判分错误，不能被静默算成正确。

**类型草图**

```python
Status = Literal[
    "not_answered",
    "tool_blocked",
    "insufficient_evidence",
    "graded_correct",
    "graded_incorrect",
    "manual_review",
    "judge_error",
]

@dataclass(frozen=True)
class TaskTruth:
    task_id: int
    question: str
    expected_answer: str
    expected_tools: tuple[str, ...]
    source_sha256: str

@dataclass(frozen=True)
class ToolEvidence:
    evidence_id: str          # 例如 task_01.call_02
    tool: str
    arguments: dict[str, Any]
    status: Literal["ok", "error", "unknown_tool"]
    result: object | None
    error: str | None

@dataclass(frozen=True)
class Precheck:
    has_final_answer: bool
    has_any_successful_evidence: bool
    failed_tools: tuple[str, ...]
    evidence: tuple[ToolEvidence, ...]
    gate: Literal[
        "judge",
        "not_answered",
        "tool_blocked",
        "insufficient_evidence",
    ]

@dataclass(frozen=True)
class Claim:
    text: str
    evidence_ids: tuple[str, ...]
    support: Literal["supported", "unsupported", "contradicted"]

@dataclass(frozen=True)
class JudgeDecision:
    verdict: Literal[
        "correct",
        "incorrect",
        "insufficient_evidence",
        "uncertain",
    ]
    claims: tuple[Claim, ...]
    reason: str
    missing_

... [证据摘录已按固定长度截断]
```

### `E1106-ARCH-B` 答案评分架构候选 B

- 会话：`codex:01a1af1c-5714-7e71-a7c4-d2babf18b27d`（W3 Day3 答案评分架构候选 B）
- 类型：`message` / `assistant`
- 定位：`ordinal=33`
- 原始证据 SHA256：`685c7210a6f5f2dbdabec735d8aeb7ab4587d9ff9b26ec8c2eb3637739bda3bf`
- 本摘录脱敏：无

```text
目标是为 W3 Day3 的 Doc2Agent 答案正确性评分设计“候选 B”。交付物只包含架构、类型草图、测试和风险，不写代码，不改仓库文件。

**已核实事实**

- 仓库 HEAD 为 `355c749a43614d1adb15f46eecc6ae94be12b61e`，工作树干净。
- `D:\wbworkspace\Doc2Agent\test_glycan\glycan_tasks_classified.jsonl` 共有 50 题，50 条 `expected_answer` 和 50 条 `expected_trajectory` 均非空。
- 上游 `D:\wbworkspace\Doc2Agent\test_glycan\glycan_evaluation.py` 使用 GPT-4o 综合判断完整交互日志，返回 `DECISION: SUCCESS` 或 `DECISION: FAILURE`，调用参数为 `temperature=0`、`max_tokens=1500`。
- 本地 Qwen3 和外部 GLM-5.3 都是 50 个 task 文件，task ID 均为 1 至 50。
- 本地 run 没有 `model_responses`，外部 run 有。评分器不能把外部模型的私有字段送入 judge，再声称两边输入结构相同。

**候选 B 总体形状**

候选 B 是“可替换 judge adapter 加独立证据审计”的双层架构。模型 judge 只回答语义正确性，其他判断全部由确定性代码完成。

```text
CLI 薄壳
  -> SourceLoader / AlignmentGuard
  -> EvaluationSet
       -> TraceNormalizer
       -> EvidenceAuditor        # 纯函数，不调用模型
       -> JudgeRequestBuilder    # 纯函数，复用上游 rubric
       -> JudgeAdapter           # HTTP 或外部服务的边界
       -> JudgeResponseParser    # 纯函数
       -> GradeMerger            # 纯函数，合并审计和 judge
  -> ArtifactStore              # 原子写、内容哈希、缓存
  -> Aggregator / Checker       # 纯函数，重算汇总并校验
```

核心分工如下。

| 判断 | 负责者 | 原因 |
|---|---|---|
| task ID、题目、expected tools 是否对齐 | 确定性代码 | 这是输入契约，不应消耗模型调用 |
| 是否缺少最终回答 | 确定性代码 | 空字符串不是语义判断 |
| 是否存在成功工具调用 | 确定性代码 | 可从 `tool_calls[].status` 直接观察 |
| 工具结果是否被截断 | 确定性代码 | 现有结果已有 `truncated` 标记 |
| judge 响应能否解析 | 确定性代码 | 不允许解析失败被静默写成 FAILURE |
| 回答是否符合科研问题、expected answer 和 rubric | 模型 judge | 涉及科学语义、多路径等价和部分完成 |
| 汇总、accuracy、local/external 差值 | 确定性代码 | 必须能重算并接受 `--check` |
| 两份 run 是否可比、是否允许发布 accuracy | 确定性代码 | 同题集、同 rubric、同 judge 都必须是硬约束 |

**类型草图**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NewType, Protocol

TaskId = NewType("TaskId", int)
Sha256 = NewType("Sha256", str)
Side = Liter

... [证据摘录已按固定长度截断]
```

### `E1106-IMPL` 评分器和比较器实现总结

- 会话：`codex:01a1af1f-ccd5-7571-bafb-c45dd01ddefe`（W3 Day3 答案评分器实现）
- 类型：`message` / `assistant`
- 定位：`ordinal=96`
- 原始证据 SHA256：`d6a4b489283274eab66136490a5e714b62528c01e945241de865407d1ed208bc`
- 本摘录脱敏：无

```text
**目标与结果**
目标是给两份已有 Doc2Agent 轨迹补上同题集、同 rubric、同 judge 的本地证据语义评分，并明确它不是上游 GPT-4o 结果。实现已完成并提交，未联网调用 judge，未生成真实 100 题评分产物。

**改动文件**
- `D:\Codex\workspace\glyco-analysis-w3-day3-answer-grader\scripts\grade_doc2agent_answers.py`，提供证据审计、prompt、judge 解析、状态合并、缓存、原子写入、`--check` 和汇总。
- `D:\Codex\workspace\glyco-analysis-w3-day3-answer-grader\scripts\compare_doc2agent_answer_grades.py`，校验同题集、同 rubric、同 judge 配置，输出 comparison JSON 和 Markdown。
- `D:\Codex\workspace\glyco-analysis-w3-day3-answer-grader\tests\test_doc2agent_answer_grader.py`，覆盖全部指定状态分支、缓存、50 题完整性、summary 篡改和比较约束。

设计上按 `principle-model-the-domain` 把状态和证据集中为明确的数据结构；按 `principle-boundary-discipline` 和 `principle-type-system-discipline` 将 I/O、HTTP 与纯函数分开；按 `principle-make-operations-idempotent` 实现内容缓存、原子写入和同内容保持 mtime；按 `principle-explain-the-number` 输出带分母的 `graded_accuracy`、`graded_coverage` 和 `answer_available_rate`；按 `principle-prove-it-works` 和 `principle-sequence-verifiable-units` 先写失败测试，再逐项验证。

**验证**
- `python -m unittest tests.test_doc2agent_answer_grader -v`，16 项通过。
- 相关既有测试 13 项通过。
- `py_compile` 通过，`git diff --check` 通过。
- 只读对齐检查显示两份 run 的 50 题 `question` 和 `expected_tools` 全部与上游一致。
- 现有轨迹中缺最终回答的数量为 Qwen3 4B `11/50`、GLM-5.3 `25/50`，评分时记为 `missing_answer`，不会调用 judge。
- GitHub 检索未发现可直接依赖的现成评分器。上游 `coolkillercat/Doc2Agent` 为 33 stars，最近提交 2025-06，仅作参考。

**提交**
分支 `codex/w3-day3-answer-grader`，提交 `3d98b0836f6520634dc020f0eb325d2c0c18eb8f`。未 push。

**未决风险**
真实 judge 尚未运行，因此实际 JSON 合规率、超时率和最终状态分布仍未知。若 judge 返回空响应、畸形 JSON 或非法证据引用，系统会进入 `judge_unavailable` 或 `manual_review`，不会静默计入正确或错误。3 道结构化 `expected_answer` 已按 JSON 序

... [证据摘录已按固定长度截断]
```

### `E1106-FINAL` 评分结果、覆盖率和验证结论

- 会话：`codex:01a180cf-92f6-7813-88f3-915158a80cab`（毕设主开发会话（2026-10-28 起））
- 类型：`message` / `assistant`
- 定位：`ordinal=5460`
- 原始证据 SHA256：`8ea90da8e861de61715e1a416b9bf28407112b03e7bbdd1e1c1ff7f27062849b`
- 本摘录脱敏：无

```text
**今日完成**

W3 Day 3 的 Doc2Agent 答案评分、覆盖率对照、文档、验证、提交和 Obsidian 归档均已完成。

**评分结果**

| 模型 | 正确 | 错误 | 人工复核 | 缺失回答 | 可判定覆盖 | 可判定正确率 | 全 50 题正确 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3 4B | 9 | 29 | 1 | 11 | 38/50 | 9/38 | 9/50 |
| GLM-5.3 | 18 | 3 | 4 | 25 | 21/50 | 18/21 | 18/50 |

两套结果中有 32 道题状态不同，18 道题状态相同。GLM-5.3 的可判定样本正确率更高，但最终回答覆盖率明显更低，因此不能据此直接写成整体模型优劣。

本次使用的是本地证据评分器 `workbuddy-ai/kimi-k3`，不是上游 GPT-4o 评分器。结果统一标记为 `local_evidence_grading`，`upstream_gpt4o_equivalent=false`，不能与上游 Claude 18/50 或 Qwen3 15/50 直接比较。

**验证结果**

- 答案评分聚焦测试 18/18 PASS。
- 全量 unittest 175 项，167 通过，8 项按设计或 GPU 门控跳过。
- 两份评分结果各 50 题，离线 `--check` 全部 PASS，0 错误。
- 本地与外部 F3 summary checker 均 PASS。
- W2 记分卡 `--check` PASS。
- GlycanML 5 个 CSV 的 MD5 全部 PASS，`glycan_link=PASS_URL_FIX`。
- `git diff --check` PASS。
- 主仓库工作树干净。

最终 HEAD：

`4719c63a37d7c626dd312195546c84f234e5bbe8`

主要证据位于 [answer_grade_comparison.md](D:/wbworkspace/glyco-analysis/reports/w3_day3/answer_grade_comparison.md) 和 [validation_2026-11-06.md](D:/wbworkspace/glyco-analysis/reports/w3_day3/validation_2026-11-06.md)。

**Obsidian 归档**

最终审计结果：

```text
笔记 410 篇 | 项目 27 个 | 工作日 34 个
任务 266 项 | 最大编号 267 | 下一编号 268
断链 0 条 | 审计通过
```

任务笔记为 [毕设 W3 Day3：Doc2Agent 答案评分与覆盖对照.md](D:/ObsidianVault/10-项目/20-毕设糖基化分析系统/毕设%20W3%20Day3：Doc2Agent%20答案评分与覆盖对照.md)。

本轮采用的关键 pstack 原则包括：用评分器和比较器替代手工判断，用六状态契约统一评分结果，把条件正确率和全题覆盖率严格分开，用真实 judge 和离线复核证明结果，并通过确定

... [证据摘录已按固定长度截断]
```
