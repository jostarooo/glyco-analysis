# W3 Day 2 external F3 comparison

This directory records the same Doc2Agent 50-task tool-trajectory evaluation with two model backends.

## Runs

- Local baseline: `reports/w2_day2/f3_qwen3_4b_50`, model `qwen3:4b`.
- External comparison: `f3_glm53_50`, model `workbuddy-ai/glm-5.3` through the local Magpie OpenAI-compatible gateway.
- Smoke run: `f3_glm53_smoke`, one task used before the 50-task batch.

Both runs use the same tasks, 70-tool catalog, system prompt, JSON action protocol, `max_rounds=4`, and no provider-native tools. The external request uses `temperature=0` and `max_tokens=512`.

## Comparison

- `f3_glm53_vs_qwen3_4b.json` contains aggregate and per-task trajectory values.
- `f3_glm53_vs_qwen3_4b.md` is the readable comparison.

`exact_sequence`, `all_expected_called`, `any_expected_called`, final-answer presence, and tool-call status are trajectory metrics. They are not answer accuracy. The upstream GPT-4o answer grader was not run.

## Reproduce

Run the external batch only when the gateway is available.

```powershell
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8='1'
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\run_doc2agent_external.py
```

Check both summaries and rebuild the comparison.

```powershell
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\summarize_doc2agent_run.py `
  --run-dir reports\w3_day2\f3_glm53_50 `
  --expected-tasks 50 `
  --check-summary reports\w3_day2\f3_glm53_50\summary.json

& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\compare_doc2agent_runs.py
```

API keys are read only from the environment variable named by `--api-key-env`. Do not write a key into a task file, summary, log, or command line.
