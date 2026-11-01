# W2 Day 5 最终验证记录

日期：2026-11-01
仓库：`D:\wbworkspace\glyco-analysis`
范围：W2 Day 3 至 Day 5 周次纠错、可重算记分卡、交付界面、交付包复核
未执行：push、远端重写、发布脚本、F2 重训、Qwen3 4B 50 题重跑

## 固定回归

命令：

```powershell
$env:PYTHONPATH='D:\wbworkspace\glyco-analysis\.venv\Lib\site-packages'
$env:PYTHONUTF8='1'
& 'C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' -m unittest discover -s tests -v
```

结果：

```text
Ran 108 tests in 21.111s
OK (skipped=5)
```

5 项跳过均为按设计或 GPU 门控跳过。原始输出见 `reports/w2_day5/unittest_2026-11-01-final.txt`。

## 内容与数据检查

| 检查 | 结果 | 证据 |
|---|---|---|
| W2 周次标签归一化 | `PASS: no accidental W3 labels remain for W2 work` | 本轮终端输出 |
| 记分卡 | `PASS: generated 8 metrics; feasibility 43/5/2`；`--check` PASS | `scorecard_check_2026-11-01.txt` |
| web 数据契约 | `web data contract PASS`；`--check` PASS | `web_data_check_2026-11-01.txt` |
| F3 summary checker | PASS；50 题，19/34/41/39，工具调用成功 78/110 | `f3_summary_check_2026-11-01.txt` |
| GlycanML | PASS；5 个 CSV，30675065 字节，`glycan_link=PASS_URL_FIX` | `glycanml_data_check_2026-11-01.json` |
| npm 生产构建 | PASS；单文件 `dist/index.html` 427469 字节 | `npm_build_2026-11-01.txt` |
| Edge `file://` | PASS；静态契约与页面挂载均通过 | `file_open_check_2026-11-01.txt` |

## 当前产物哈希

| 产物 | SHA256 |
|---|---|
| `reports/w2_day4/scorecard.json` | `8e1f4c6403c7d9ab3347c36546e8928c7463ff5dfd75effccd6621dda62ceef0` |
| `reports/w2_day4/scorecard.csv` | `5f9422647575d8d2aaa7092b962f75155aaba94cbad15daf578abcf14ca87fdf` |
| `reports/w2_day4/scorecard.md` | `00d8b132e62bfd81a3f28db4d5e1f75b34593219308e0bf9fab9d8f51f24007c` |
| `web/dist/index.html` | `b6a37f3d943b022c30b117cd687615e07a6491deaeb98618116ec080fee3a8b9` |

## 口径边界

- F2 对齐 GlycanML Table 3，不是 Table 2。
- F2 是 PyG 自实现 RGCN；TorchDrug 未安装，不是逐位克隆。
- F3 的 19/34/41/39 和 78/110 是轨迹或输出存在性，不是答案正确率。
- 上游 Claude 18/50 和 Qwen3 15/50 使用 GPT-4o 评分，本轮没有相同评分器。
- 8B 中断目录不是成绩。
- `get_proteins` TLS 校验失败不等于服务死亡；`get_ligands` 返回 HTTP 200 空数组不等于任务可用。
- 工具可行性最新分类为 43/5/2，合计 50。
- 界面页头的“数据基线”是生成 web 数据时的 HEAD；视频开头必须另外现场展示交付前最新 commit。
