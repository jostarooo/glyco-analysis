# 糖基化分析系统：以蛋白质语言模型预测 N-糖基化位点、以图神经网络解析糖链、并用工具调用智能体把两者串成一个可对话的分析工作台。

> 本科毕业设计（张驰，指导教师王老师）· 2026-10-27 第一次对齐
> 代码状态：W1 环境搭建阶段，可运行的东西只有接口体检脚本。

## 它解决什么问题

糖基化是最常见、也最难预测的翻译后修饰之一。现有工具各管一段：位点预测器只告诉你"这里可能挂糖"，
糖链模型只回答"这条链是什么结构"，而真实科研问题往往是一句自然语言："这个蛋白哪些位点会挂
N-糖，挂上的糖链会不会影响它做受体？"

本项目把三条线接起来：

| 线 | 做什么 | 底座 |
|---|---|---|
| **F1 位点预测** | 给定蛋白序列，预测 N-X-S/T 位点是否真被糖基化 | ESM-2（35M 线性探针 / 150M LoRA） |
| **F2 糖链模型** | 给定糖链结构，预测其性质、判断单糖/糖苷键贡献 | RGCN（PyG 自实现） |
| **F3 工具调用智能体** | 把 F1/F2 与数据库查询包装成工具，用中文任务驱动 | Doc2Agent 路线 + MCP |

## 现在能跑什么

```powershell
# 接口体检：一次性打印 UniProt / GlyGen / GlyConnect / GlyTouCan / KEGG / PubChem 的可用性
D:\wbworkspace\glyco-analysis\.venv\Scripts\python.exe scripts\check_endpoints.py
```

环境事实见 `REPRO.md`，复现用的三个上游仓库在 `D:\wbworkspace\`（LoRA-N-Gly / GlycanML / Doc2Agent）。

## 目录

```
glyco-analysis/
├─ scripts/          可直接运行的脚本（check_endpoints.py）
├─ reports/          体检与实验产出的 Markdown / CSV
├─ docs/             设计与说明
├─ data/             本地数据（不入库，见 .gitignore）
└─ REPRO.md          复现手册：可行性五关、术语表、本机配置
```

## 红线

- 前端不写死任何数字；
- 不用 Mock 冒真实功能；
- 演示版本 = 仓库最新提交；
- **论文里的数字只能作为对照，不能当成自己的结果**。

## 引用与许可

复现对象 `NancyFyong/LoRA-N-Gly` 仓库无 license，论文为 CC BY-NC-ND。
本项目仅作学习与研究用途，不用于商业分发。本仓库自身的许可待定（第一次对齐时与导师确认）。
