# W3 Day 2 validation

Date: 2026-11-05

## Environment

- Repository worktree: `D:\Codex\workspace\glyco-analysis-w3-day2-external`
- Branch: `codex/w3-day2-external-api`
- Base commit: `7c5dc620b50b3d03c7f4ea7d609b52fa30b2ad2a`
- External gateway: `http://127.0.0.1:3425/v1/chat/completions`
- External model: `workbuddy-ai/glm-5.3`
- Python: `C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe`
- Package path: `D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages`

## Focused tests

Command:

```powershell
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8='1'
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  -m unittest `
  tests.test_doc2agent_runner `
  tests.test_doc2agent_chat_runner `
  tests.test_doc2agent_external_runner `
  tests.test_doc2agent_comparison -v
```

Result: 14 tests passed.

## External smoke

Command:

```powershell
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\run_doc2agent_external.py `
  --limit 1 `
  --out reports\w3_day2\f3_glm53_smoke
```

Result: one task completed with four model calls. It called the expected tool and produced one successful tool call, but hit `max_rounds_reached` before a final answer. The smoke run proves the HTTP adapter and shared tool loop work. It is not a score.

## External 50-task run

Command:

```powershell
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\run_doc2agent_external.py `
  --out reports\w3_day2\f3_glm53_50
```

Result:

| Metric | Value |
|---|---:|
| tasks run | 50 |
| exact sequence | 13 |
| all expected called | 41 |
| any expected called | 47 |
| tasks with tool call | 49 |
| tasks with final answer | 25 |
| successful tool calls | 114 |
| tool calls | 129 |
| model calls | 159 |
| finish reason stop | 155 |
| finish reason length | 4 |
| elapsed seconds | 1174.006 |

Token usage reported by the gateway: 549,983 prompt tokens, 18,240 completion tokens, and 568,223 total tokens.

## Summary checks

Commands:

```powershell
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\summarize_doc2agent_run.py `
  --run-dir reports\w3_day2\f3_glm53_50 `
  --expected-tasks 50 `
  --check-summary reports\w3_day2\f3_glm53_50\summary.json

& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\summarize_doc2agent_run.py `
  --run-dir reports\w2_day2\f3_qwen3_4b_50 `
  --expected-tasks 50 `
  --check-summary reports\w2_day2\f3_qwen3_4b_50\summary.json
```

Result: both summaries PASS. The external and local task IDs, questions, and expected tools also pass the comparison alignment check for all 50 tasks.

## Full regression

Command:

```powershell
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8='1'
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  -m unittest discover -s tests -v
```

Result: 157 tests ran, 149 passed, and 8 skipped by their documented gates. Exit code 0.

## Metric boundary

The comparison is `trajectory_only`. It does not measure answer accuracy. The upstream GPT-4o answer grader was not run, so the local and external numbers cannot be converted into a model accuracy difference.
