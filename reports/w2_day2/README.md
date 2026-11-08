# W2 Day 2 F3 产物

具有权威性的 50 题结果是 `f3_qwen3_4b_50`。该目录包含 50 个任务 JSON
文件和一份摘要。运行
`scripts/summarize_doc2agent_run.py --expected-tasks 50 --check-summary`
可以重新计算并核对这份摘要。

`f3_qwen3_8b_50_incomplete` 是 8B 任务被中断后留下的混合过程目录。不要把
其中的摘要或任务文件当作完整的 8B 50 题结果。

`f3_qwen3_8b_smoke` 和 `f3_qwen3_8b_task31_768` 是有效的 8B 单题检查。
前者验证缩减后的运行配置，后者证明较长的 WURCS 任务需要高于 256 token
的输出上限。

`probe_*.json` 记录运行环境排查过程。这些文件说明 runner 为什么必须暴露
上下文长度、输出上限、超时和思考模式控制。它们不是答案质量基准。

`tool_feasibility.csv` 为 50 道题各指定一个主要阻断类别。
`tool_feasibility_summary.json` 记录 W2 当时的原始分类，即直接完成 20 题、
需要替代工具 25 题、服务失败 5 题，并绑定源文件哈希。这些文件作为 W2
历史结果保持不变。

2026-10-30 在 `reports/w2_day3/` 完成的任务级复测把当前分类修正为
直接完成 43 题、需要替代工具 5 题、服务失败 2 题。修正过程区分了通用
探针参数无效、wrapper 契约失败、TLS 校验失败和服务不可用。报告当前工具
状态时使用 `task_feasibility_revised.csv`。

`f2_f3_comparison.md` 解释 Table 3 对照以及 F3 轨迹指标的边界。
`unittest_2026-10-29.txt` 和 `f3_summary_check_2026-10-29.txt` 保存最终
验证输出。
