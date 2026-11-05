# 独立日志总结证据包

这份文件只整理日志原文、当时命令和可核对的结果。最终日志总结必须由本人改写，不能把本页当成提交稿。

## 案例 1：4B 模型在 4096 与 8192 上下文下的耗时

原始证据：

- `reports/w2_day2/probe_qwen3_4b_4096.json`
- `reports/w2_day2/probe_qwen3_4b_8192.json`

两次请求的 `prompt_eval_count` 都是 2498，`eval_count` 都是 520。输入和输出 token 数相同，说明 task 1 的提示词在 4096 上下文下已经放得下。

4096 记录的总耗时是 8.619 秒，其中 `load_duration` 约 0.008 秒。8192 记录的总耗时是 17.360 秒，其中 `load_duration` 约 8.692 秒。8192 的纯生成时间没有翻倍，主要变化是 Ollama 重新加载模型。

本人需要讲清：

1. 当时想排除什么原因。
2. 为什么比较 `prompt_eval_count`、`eval_count` 和 `load_duration`。
3. 哪一条记录证明“8192 更慢”不能直接归因于模型推理本身。

## 案例 2：模型写了一个看起来正确的工具名

原始证据：

- `reports/w2_day2/f3_qwen3_4b_50/task_01.json`
- `reports/w2_day3/tool_blocker_recheck.csv`

task 1 的期望工具是 `convert_iupac_extended_to_wurcs`。4B 实际调用了 `convert_iupac_extended_to_wurcs_format`，记录状态是 `unknown_tool`。最终回答还说提供的工具目录里没有转换工具。

工具目录里确实有正确工具，只是名字没有 `_format`。这不是服务失败，也不是上游缺少工具，而是模型选择了不存在的工具名。

本人需要讲清：

1. 看到 `unknown_tool` 时先检查了哪两个名字。
2. 为什么工具目录中存在正确名字，最终回答却仍然说没有。
3. 后续任务级复测怎样证明正确工具本身可用。

## 案例 3：服务可达不等于任务可用

原始证据：

- `reports/w2_day3/tool_blocker_recheck_summary.json`
- `reports/w2_day3/task_feasibility_revised.csv`

`get_proteins` 默认 TLS 校验返回证书错误。诊断时关闭校验得到 HTTP 200 和可用 JSON，因此不能写成服务死亡。生产路径不能关闭 TLS 校验。

`get_ligands` 返回 HTTP 200，但内容是空数组。服务端点可达，不代表 task 48 需要的数据已经拿到。

本人需要讲清：

1. 为什么把证书失败、HTTP 200 和任务可用性分开判断。
2. 哪个结果是诊断证据，哪个结果可以进入正式分类。
3. task 48 为什么仍然不能算“当前工具可直接完成”。

## 本人改写检查表

- [ ] 每个案例都引用至少一份日志或 JSON 原文。
- [ ] 每个案例都写了当时猜测、对照动作和排除结果。
- [ ] 没有把工具轨迹指标写成答案正确率。
- [ ] 没有把 8B 中断目录写成模型成绩。
- [ ] 没有把证书失败写成服务死亡。
- [ ] 最后一节用 2 至 4 句写清本人从这些日志里学到了什么。
