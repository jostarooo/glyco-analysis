# ESM-2 35M 探针来源追溯复核（2026-10-26）

## 结论

35M 探针产物在生成时的代码基线上通过了独立核验。复核使用
`--skip-reembed`，核对清单、行数、窗口、折分、指标和产物哈希，不重新加载模型。
本次结论只证明产物与基线一致，不等于重新训练或重新执行了 130 行 GPU 前向。

## 运行环境

- 基线提交：`29f97a502b16dd0ad169de4fb69a4dd10dd76e49`
- 临时工作树：`D:\wbworkspace\glyco-analysis-35m-recheck`
- Python：`D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe`
- UniProt 缓存：`D:\wbworkspace\glyco-analysis\data\raw\uniprot`
- 运行目录：`reports\esm35_linear_probe_v0`

## 复核命令

```powershell
$env:PYTHONUTF8 = '1'
& 'D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe' `
  'D:\wbworkspace\glyco-analysis-35m-recheck\scripts\check_esm35_linear_probe.py' `
  --run-dir 'reports\esm35_linear_probe_v0' `
  --cache-dir 'D:\wbworkspace\glyco-analysis\data\raw\uniprot' `
  --skip-reembed
```

## 实际输出

```text
rows=130 proteins=28 windows=51 release=2026_03
passed assertions: 3896
PASS
```

## 后续 HEAD 的预期报错与交付边界

35M 复核是在临时工作树中针对生成基线 `29f97a5` 执行的，实际输出为 `PASS`。
复核当时主工作树的 HEAD 为 `489d96b`，之后交付记录的最终基线为 `db8f1d8`。
在交付记录基线上直接运行同一个核验脚本，会触发来源追溯门禁：
运行清单固定记录生成时的基线 `29f97a5`，而后续文档、脚本和未跟踪文件不在该基线内。

预期报错类别为：

- 运行清单来源提交（`manifest source commit`）：运行清单记录 `29f97a5`，交付基线为 `db8f1d8`
- 后续来源改动（`manifest source changes`）：后续提交修改了 `README.md`、`REPRO.md` 和 `LESSONS.md`
  等文件
- 未跟踪来源文件（`manifest source untracked files`）：工作树还包含交付复核文档和构建脚本

这说明来源追溯门禁在正确工作，不是模型预测失败，也不是 W1 交付包失效。正式交付不得为了
消除这条报错而改写运行清单的生成基线，也不得把后续 HEAD 的核验脚本结果写成新的 35M 全量运行。

## 交付边界

- 35M 主结果仍为窗口化留一蛋白交叉验证（`leave-one-protein-out`）的 130 行评估。
- 71 行仅含 `ECO:0000255` 的推断阳性不进入指标分母。
- 48 行未标注对照不是实验确认的阴性。
- 本次复核没有执行 201 行 GPU 重算，也没有重新训练线性探针。
- 35M 与 150M 的差异同时包含窗口化、训练方式和输入上下文差异，不能只归因于模型大小。
