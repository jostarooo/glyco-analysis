# W3 Day 2 外部 F3 对照

本目录记录同一批 Doc2Agent 50 题工具轨迹评测在两个模型后端上的结果。

## 运行

- 本地基线为 `reports/w2_day2/f3_qwen3_4b_50`，模型是 `qwen3:4b`。
- 外部对照为 `f3_glm53_50`，模型是 `workbuddy-ai/glm-5.3`，通过本地
  Magpie 的 OpenAI 兼容网关调用。
- 烟测目录为 `f3_glm53_smoke`，在 50 题批次前运行一道题。

两次运行使用同一批任务、70 个工具的目录、系统提示词、JSON 动作协议和
`max_rounds=4`，都没有使用 provider 原生工具。外部请求使用
`temperature=0` 和 `max_tokens=512`。

## 对照

- `f3_glm53_vs_qwen3_4b.json` 保存汇总和逐题轨迹值。
- `f3_glm53_vs_qwen3_4b.md` 是可阅读的对照报告。

`exact_sequence`、`all_expected_called`、`any_expected_called`、最终回答
是否存在以及工具调用状态都是轨迹指标。它们不是答案正确率。本轮没有运行
上游 GPT-4o 答案评分器。

## 复现

只有网关可用时才运行外部批次。

```powershell
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8='1'
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\run_doc2agent_external.py
```

核对两份摘要并重建对照报告。

```powershell
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\summarize_doc2agent_run.py `
  --run-dir reports\w3_day2\f3_glm53_50 `
  --expected-tasks 50 `
  --check-summary reports\w3_day2\f3_glm53_50\summary.json

& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\compare_doc2agent_runs.py
```

API key 只从 `--api-key-env` 指定的环境变量读取。不要把 key 写入任务文件、
摘要、日志或命令行。
