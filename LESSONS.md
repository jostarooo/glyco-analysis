# LESSONS.md —— 本仓库踩坑与硬规则

> 规则：同一条坑在第 3 个不同日期被记到时，升级为硬规则并落进脚本校验或 AGENTS 约定。
> 条目标注 `Seen N× —— 日期列表`。

- **重叠 sequon 必须用前瞻匹配枚举。** 普通 `re.finditer(r"N[^P][ST]")` 非重叠扫描，匹配 `NNSS` 的第 1 个起点后会从第 3 位继续，吞掉第 2 个起点（真阳性样本 P40879#165）。枚举一律写 `(?=(N[^P][ST]))` 并取 `group(1)`。
  Seen 1× —— 2026-10-19
- **抽样池必须先排序再 `random.sample`。** 上游返回顺序一变，同样的 seed 也给出完全不同的样本（实测 30 条里只有 2 条相同）；seed、排序、清单三者缺一都不可复现。
  Seen 1× —— 2026-10-19
- **UniProt 同一糖基化位点有大量冗余 feature**（最大见过同一位 28 条），必须按位置去重，同时保留条数（`n_features`）作为冗余度指标。
  Seen 1× —— 2026-10-19
- **UniProt 实验标注本身有噪声**：存在标了 N-linked 但残基不是 N / 不在 sequon 上的位点（P01877#327，残基 D）。这类数据不能静默吞掉，要转成可核查的数据质量指标。
  Seen 1× —— 2026-10-19
- **PowerShell 5.1 把多行代码经 here-string 传给 `python -c` 会剥掉内部引号**，报 SyntaxError。一次性 Python 脚本一律先写临时 `.py` 文件再执行。
  Seen 1× —— 2026-10-19
- **长序列裁目标窗口后，token 下标不能再写 `pos`。** ESM 分词有 `[CLS]`，窗口内目标位置是 `1 + (pos - window_start)`；直接用原序列位置会静默读错残基。
  Seen 1× —— 2026-10-20
- **按蛋白留一法评估时，标准化器也只能在该折训练蛋白上 `fit`。** 先对全表 `fit` 会把测试蛋白分布带进训练，指标会虚高。
  Seen 1× —— 2026-10-20
- **运行记录要在任何写入前读取 Git 状态。（已升级硬规则）** 完成标记的删除、产物覆盖和临时 staging 目录都会让工作树变脏；即使 `write_run()` 开头读取，也可能晚于入口清理或 staging 创建。先读取 `git_commit` 与 `git_dirty`，再创建任何输出路径，才能留下 `dirty=false`。硬规则已落地：runner 在入口读取 Git 状态，先于任何 staging 与产物写入。
  Seen 3× —— 2026-10-20、2026-10-22、2026-10-23
- **UniProt N-linked 标注不等于实验阳性。** 201 行 label=1 中有 82 行含 `ECO:0000269`，71 行仅含 `ECO:0000255` 推断证据。训练和评估要在输入边界分流，不能把推断行混进实验阳性。
  Seen 1× —— 2026-10-20
- **Git worktree 不共享被 `.gitignore` 忽略的数据缓存。** 在 worktree 跑 checker 时必须显式传主仓库的 `--cache-dir`，否则默认相对路径找不到 UniProt 缓存。
  Seen 1× —— 2026-10-20
- **PEFT 的 missing adapter keys 告警不能直接判为无害或致命。** 必须检查当前 active adapter 路径并逐元素对照 checkpoint。150M 复算里 `classifier.original_module.out_proj` 是未激活别名，实际使用的 `classifier.modules_to_save.default.out_proj` 四个有效权重均一致。
  Seen 1× —— 2026-10-21
- **全序列 ESM-2 遇到超长蛋白时，执行后端本身会成为瓶颈。** 5179 aa 单序列在 eager 路径曾超过 12 分钟无输出；改用 CUDA SDPA 后同一验证组完成。该观察是单次测量，不写成普适加速比，最终 manifest 固定记录 `attention_backend` 与 30/30 模块计数。
  Seen 1× —— 2026-10-21
- **checker 的 artifact-only PASS 不等于重建了运行时状态。** SDPA 模块计数只有在 `--recheck-inference` 下才会重新构造并核对。最终交付必须保留 `inference_recheck=true`，不能只看 `status=PASS`。
  Seen 1× —— 2026-10-21
- **改动 venv 后必须跑一次完整 import smoke test。** 2026-10-22 的一次 `uv` 操作后，`certifi` 与 `accelerate` 从 venv 缺失，150M 推理在模型加载前连续失败；补包并以固定兼容路径导入 `torch`、`transformers`、`peft`、`accelerate`、`tokenizers` 和 `huggingface_hub` 后恢复。
  Seen 1× —— 2026-10-22
- **PowerShell 5.1 读无 BOM UTF-8 必须 `[System.IO.File]::ReadAllText($path, [Text.UTF8Encoding]::new($false))`。** `Get-Content` 默认按 ANSI 解码，中文路径全部损坏；SHA256SUMS 复核曾因此误报 35 项「找不到路径」，文件本身没有坏。
  Seen 1× —— 2026-10-24
- **生成 PowerShell 脚本不要在双引号 here-string 里用 `\$` 转义变量。** `\$false` 落盘成 `\False`，整段脚本解析失败；要生成含 `$` 的脚本一律用单引号 here-string（`@'...'@`）或 `[System.IO.File]::WriteAllText` 写单引号字符串。
  Seen 1× —— 2026-10-25
