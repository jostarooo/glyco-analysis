# W2 Day 3 验证记录

日期：2026-10-30
仓库：`D:\wbworkspace\glyco-analysis`
分支：`main`
复测前 HEAD：`59ebbb27298bbe76808de625efb7613fa4cb6160`

## 现场复测

`scripts/retest_doc2agent_blockers.py` 于 2026-10-30 完成一次联网复测，生成
`tool_blocker_recheck_summary.json`，状态为 PASS。

| 检查 | 结果 |
|---|---|
| 阻断工具 | 17 个，全部生成证据 |
| 服务可达 | 17/17 |
| 默认传输成功 | 16/17 |
| 合法参数直接通过 | 13 |
| 需要拆查询 | 1 |
| 接口契约失败 | 2 |
| TLS 校验失败 | 1 |
| 50 题分类 | 43 直接完成、5 需要替代工具、2 服务失败 |
| 分类变化 | 24 题 |
| 三类合计 | 50 |

W2 原始 CSV 和 summary 的 SHA256 已写入 W2 Day 3 复测 summary 的 `sources` 字段，原文件未改写。

## 固定回归

| 检查 | 结果 | 证据 |
|---|---|---|
| 新增脚本与测试 `py_compile` | PASS | 本轮命令记录 |
| 聚焦测试 | 14 项全部通过 | `tests/test_doc2agent_blocker_recheck.py` |
| 全量 unittest | 79 项，78 项通过，1 项 GPU 门控跳过 | `unittest_2026-10-30.txt` |
| F3 summary checker | PASS | `f3_summary_check_2026-10-30.txt` |
| GlycanML 数据复核 | PASS，5 个 CSV MD5 一致 | `glycanml_data_check_2026-10-30.json` |
| `git diff --check` | PASS，无输出 | 提交前复跑 |

执行全量回归使用：

```powershell
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8='1'
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' -m unittest discover -s tests -v
```

## 结果口径

17 个服务可达，但 `get_ligands` 返回空数组，因此它不能把 task 48 变成当前工具可直接
完成。`get_proteins` 默认 TLS 校验失败，`verify=False` 诊断返回 HTTP 200，因此 task
20、46 记录为默认传输失败，不记录为站点死亡，也不把关闭校验当作生产修复。

F3 的 `exact_sequence=19`、`all_expected_called=34`、
`any_expected_called=41`、`tasks_with_final_answer=39` 和 78/110 次工具调用成功
都没有重算，仍是工具轨迹指标，不是答案正确率。上游 Claude 18/50 和 Qwen3 15/50
使用 GPT-4o 评分，本轮没有同口径评分器，不能直接比较。

## 未执行项

本轮没有重跑 F2 训练，没有重跑 Qwen3 4B 50 题，没有 push，没有重写远端，也没有
运行发布脚本。

## 提交后换行修正

首次提交后对提交内容运行 `git diff --check HEAD^ HEAD`，发现数据复核 JSON 使用
CRLF 换行，Git 将每行的回车标记为行尾空白。JSON 内容未变，已统一为 LF 换行并
追加一个修正提交，随后重新生成 W02 核心证据和根级 SHA256 清单。
