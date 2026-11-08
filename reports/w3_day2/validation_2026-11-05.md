# W3 Day 2 验证记录

日期：2026-11-05

## 环境

- 仓库工作树：`D:\Codex\workspace\glyco-analysis-w3-day2-external`
- 分支：`codex/w3-day2-external-api`
- 基线提交：`7c5dc620b50b3d03c7f4ea7d609b52fa30b2ad2a`
- 外部网关：`http://127.0.0.1:3425/v1/chat/completions`
- 外部模型：`workbuddy-ai/glm-5.3`
- Python：`C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe`
- 包路径：`D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages`

## 聚焦测试

命令：

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

结果：14 项测试通过。

## 外部烟测

命令：

```powershell
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\run_doc2agent_external.py `
  --limit 1 `
  --out reports\w3_day2\f3_glm53_smoke
```

结果：一道题完成，共调用模型四次。模型调用了预期工具，并产生一次成功工具
调用，但在给出最终回答前达到 `max_rounds_reached`。烟测证明 HTTP 适配器和
共享工具循环可以工作，不构成成绩。

## 外部 50 题运行

命令：

```powershell
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  scripts\run_doc2agent_external.py `
  --out reports\w3_day2\f3_glm53_50
```

结果：

| 指标 | 值 |
|---|---:|
| 运行任务数 | 50 |
| 精确序列命中 | 13 |
| 全部预期工具命中 | 41 |
| 任一预期工具命中 | 47 |
| 产生工具调用的任务 | 49 |
| 产生最终回答的任务 | 25 |
| 成功工具调用 | 114 |
| 工具调用 | 129 |
| 模型调用 | 159 |
| `finish_reason=stop` | 155 |
| `finish_reason=length` | 4 |
| 总耗时（秒） | 1174.006 |

网关报告的 token 用量为输入 549,983、输出 18,240、合计 568,223。

## 摘要核对

命令：

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

结果：两份摘要均通过。外部与本地运行的任务编号、问题和预期工具在全部 50
道题上也通过对照对齐检查。

## 全量回归

命令：

```powershell
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8='1'
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  -m unittest discover -s tests -v
```

结果：共运行 157 项测试，149 项通过，8 项按各自文档中的门槛跳过，退出码为
0。

## 指标边界

本次对照范围为 `trajectory_only`，不评价答案正确率。本轮没有运行上游
GPT-4o 答案评分器，因此不能把本地和外部轨迹数字转换成模型准确率差异。
