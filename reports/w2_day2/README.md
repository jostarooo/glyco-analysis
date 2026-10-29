# W2 Day 2 F3 artifacts

The authoritative 50-task result is `f3_qwen3_4b_50`. It contains 50 task JSON files and a summary that recomputes with `scripts/summarize_doc2agent_run.py --expected-tasks 50 --check-summary`.

`f3_qwen3_8b_50_incomplete` is a mixed, interrupted process directory. Do not use its summary or task files as a completed 8B 50-task result.

`f3_qwen3_8b_smoke` and `f3_qwen3_8b_task31_768` are valid single-task 8B checks. The first verifies the reduced runtime profile. The second verifies that a long WURCS task needs a larger output cap than 256 tokens.

The `probe_*.json` files record the runtime investigation. They show why the runner must expose context, output-cap, timeout, and thinking controls. They are not an answer-quality benchmark.

`tool_feasibility.csv` assigns one primary blocker category to each of the 50
tasks. `tool_feasibility_summary.json` records the 20 direct, 25 replacement,
and 5 service-failure totals and binds them to the source-file hashes.

`f2_f3_comparison.md` explains the Table 3 comparison and the limits of the F3
trajectory metrics. `unittest_2026-10-29.txt` and
`f3_summary_check_2026-10-29.txt` preserve the final verification output.
