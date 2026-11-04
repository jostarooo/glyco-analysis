# W3 Day 1 验证记录

日期：2026-11-04
开工 HEAD：`9b93d60aecb82a3328d7fab05a8cf64c6147124c`

## 1. 固定测试

系统聚焦测试覆盖密码与会话、序列规范化、sequon 规则、队列、HTTP 合同、无 sequon
懒加载和单文件 UI 合同。

```text
Ran 25 tests in 4.486s
OK
```

全量默认回归：

```text
Ran 147 tests in 29.734s
OK (skipped=8)
```

其中 8 项为既有 GPU 门控、web 环境门控和本轮真实模型门控，不是失败。
机器可读输出在 `reports/w3_day1/unittest_2026-11-04.txt`。

## 2. 真实 GPU 回归

命令显式启用 `RUN_W3_REAL_MODEL=1`，加载作者 ESM-2 150M LoRA 检查点，并将
`O75144` 的 6 个位点与 `reports/esm150_w1_candidates_v0/predictions.csv` 对拍。

```text
Ran 3 tests in 37.179s
OK
```

结果：

- 6/6 位点位置和 motif 一致。
- 6/6 预测标签一致。
- 最大概率差为 0。
- adapter SHA256 和 376 个张量一致。
- 全序列、无截断、无窗口化。

输出在 `reports/w3_day1/real_model_unittest_2026-11-04.txt`。

## 3. 真实 HTTP 纵切

测试步骤：

1. `GET /api/auth/session`。
2. `POST /api/auth/login`。
3. `GET /api/runtime`。
4. 从 runtime 读取服务端真实样例 `O75144`。
5. `POST /api/predictions`。
6. 轮询 `GET /api/predictions/{job_id}`，直到状态为 `succeeded`。
7. 与历史位点 CSV 逐项对拍。

实测：

```text
HTTP 冷启动到完成：33.907544 秒
模型纯推理：19.645788 秒
候选位点：6
序列长度：302 aa
序列 SHA256：0CA51F904C28299D8ED0B0DC85EDC28E9F28DF28A7968477D36F062D257722E0
```

结果在 `reports/w3_day1/real_e2e_2026-11-04.json`。

## 4. 浏览器现场验收

Edge 通过 Playwright 从同源 HTTP 页面完成登录、载入样例、提交、轮询和结果渲染。

```text
HTTP 状态：200
页面 HEAD 文本：9b93d60a
模型状态：ready
序列长度：302
结果表行数：6
位点：#70, #102, #137, #173, #186, #225
页面脚本错误：0
控制台错误：0
```

记录在 `reports/w3_day1/browser_e2e_2026-11-04.json`，截图为
`reports/w3_day1/system_ui_2026-11-04.png`。

## 5. 环境与来源自检

`python -m system doctor` 退出 0，检查到：

- 当前 HEAD。
- 单文件 UI 存在。
- O75144 样例存在，长度 302。
- 基础模型 revision 固定。
- adapter SHA256 固定。
- adapter 张量数 376。
- 默认设备 `cuda`、SDPA、FP32、全序列、无截断。

输出在 `reports/w3_day1/doctor_2026-11-04.txt`。

## 6. 未重跑项

- 没有重跑 F2 三种子 50 epoch。
- 没有重跑 Qwen3 4B 50 题。
- 没有修改 W2 原始分类 CSV 或 summary。
- 没有修改 `web/` 或 `video-ui/`。
- 没有 push、重写远端或运行发布脚本。
