#!/usr/bin/env python3
"""Build the recording-only weekly presentation from repository evidence.

The output is a single self-contained HTML file. Every scientific number
visible in the deck is extracted into video-ui/src/story.json before the
renderer runs. The generator is deterministic and supports --check for
missing, stale, or hand-edited outputs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VIDEO_ROOT = REPO_ROOT / "video-ui"
STORY_REL = Path("src/story.json")
INDEX_REL = Path("dist/index.html")

SOURCE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("w1_weekly", "reports/weekly/W01_2026-10-27_progress.md", "W1 周报"),
    ("w1_manifest", "reports/w1_three_method_v0/manifest.json", "W1 三方法核验"),
    ("w1_esm150", "reports/esm150_lora_repro_v0/metrics.json", "150M 作者检查点复算"),
    ("f2_recompute", "reports/w2_day1/glycanml_rgcn_recompute.json", "F2 Table 3 复算"),
    ("f3_summary", "reports/w2_day2/f3_qwen3_4b_50/summary.json", "F3 Qwen3 4B 轨迹"),
    ("tools_summary", "reports/w2_day1/doc2agent_tools_summary.json", "Doc2Agent 工具盘点"),
    ("feasibility_csv", "reports/w2_day3/task_feasibility_revised.csv", "50 题可行性分类"),
    ("recheck_summary", "reports/w2_day3/tool_blocker_recheck_summary.json", "阻断工具复测"),
    ("scorecard", "reports/w2_day4/scorecard.json", "W2 可重算记分卡"),
    ("w2_weekly", "reports/weekly/W02_2026-11-03_progress.md", "W2 周报"),
)

SOURCE_LABELS = {role: label for role, _path, label in SOURCE_SPECS}

W2_DAYS = (
    {
        "day": "Day 1",
        "date": "10.28",
        "title": "技术路线与数据基线",
        "work": "确定 PyG 自实现 RGCN，核验 GlycanML 五张表，盘点 70 个 wrapper。",
        "purpose": "先确认数据、环境和工具到底哪些能用，不把未知留到结果阶段。",
    },
    {
        "day": "Day 2",
        "date": "10.29",
        "title": "F2 复算与 F3 起跑",
        "work": "完成 F2 三随机种子训练，跑通 Qwen3 4B 的 50 题工具轨迹。",
        "purpose": "让两个研究问题第一次拥有可执行、可复查的结果。",
    },
    {
        "day": "Day 3",
        "date": "10.30",
        "title": "阻断工具任务级复测",
        "work": "按任务参数重测 17 个阻断工具，分离服务可达、传输成功和任务可用。",
        "purpose": "把“工具报错”拆成真实根因，修正过粗的任务可行性判断。",
    },
    {
        "day": "Day 4",
        "date": "10.31",
        "title": "可重算记分卡",
        "work": "把 F1、F2、F3 和工具可行性收束到一个生成器与一组固定指标。",
        "purpose": "建立唯一数字入口，让每个结论都能回到源文件和哈希。",
    },
    {
        "day": "Day 5",
        "date": "11.01",
        "title": "单文件交付界面",
        "work": "完成只读数据契约、自包含页面和本地 file:// 验证。",
        "purpose": "让结果可以脱离开发服务器，直接用于检查和录屏。",
    },
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    head = completed.stdout.strip()
    if len(head) != 40:
        raise RuntimeError(f"unexpected git HEAD: {head!r}")
    return head


def read_source(path: Path) -> Any:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    if path.suffix.lower() == ".csv":
        return list(csv.DictReader(text.splitlines()))
    return text


def load_sources(root: Path) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for role, rel, label in SOURCE_SPECS:
        path = root / rel
        if not path.is_file():
            raise SystemExit(f"missing source: {rel}")
        raw = path.read_bytes()
        loaded[role] = {
            "payload": read_source(path),
            "meta": {
                "role": role,
                "label": label,
                "path": rel,
                "sha256": sha256_bytes(raw),
                "bytes": len(raw),
            },
        }
    return loaded


def metric_by_id(scorecard: dict[str, Any], metric_id: str) -> dict[str, Any]:
    for metric in scorecard["metrics"]:
        if metric.get("metric_id") == metric_id:
            return metric
    raise RuntimeError(f"scorecard metric missing: {metric_id}")


def feasibility_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts = Counter(row["revised_category"] for row in rows)
    return {
        "current_tools_direct": counts["current_tools_direct"],
        "needs_replacement_tool": counts["needs_replacement_tool"],
        "service_failure": counts["service_failure"],
    }


def build_story(root: Path = REPO_ROOT, head: str | None = None) -> dict[str, Any]:
    sources = load_sources(root)
    source_head = head or git_head(root)

    w1_manifest = sources["w1_manifest"]["payload"]
    w1_esm150 = sources["w1_esm150"]["payload"]
    f2 = sources["f2_recompute"]["payload"]
    f3 = sources["f3_summary"]["payload"]
    tools = sources["tools_summary"]["payload"]
    feasibility_rows = sources["feasibility_csv"]["payload"]
    recheck = sources["recheck_summary"]["payload"]
    scorecard = sources["scorecard"]["payload"]

    benchmark = w1_manifest["benchmark"]
    if benchmark["evaluation_rows"] != (
        benchmark["experimental_positive"] + benchmark["unannotated_control"]
    ):
        raise RuntimeError("W1 evaluation pool no longer reconciles")

    review_counts = w1_manifest["manual_review"]["status_counts"]
    f1_methods = w1_manifest["metric_summary"]
    f2_immuno = f2["tasks"]["immunogenicity"]
    f2_glyco = f2["tasks"]["glycosylation"]
    f2_immuno_ref = metric_by_id(scorecard, "f2.immunogenicity.auprc")
    f2_glyco_ref = metric_by_id(scorecard, "f2.glycosylation.macro_f1")

    revised = feasibility_counts(feasibility_rows)
    scorecard_revised = scorecard["feasibility"]["counts"]
    if revised != scorecard_revised:
        raise RuntimeError("feasibility CSV and scorecard disagree")
    classification_total = sum(revised.values())
    if classification_total != len(feasibility_rows):
        raise RuntimeError("feasibility categories do not cover every task")

    sources_meta = [sources[role]["meta"] for role, _path, _label in SOURCE_SPECS]
    source_meta_by_role = {item["role"]: item for item in sources_meta}

    tracks = [
        {
            "code": "F1",
            "name": "位点预测",
            "question": "一个 N-X-S/T 候选位点，是否真的会被糖基化？",
            "what": "把序列规则、蛋白语言模型和作者检查点放到同一评估池里比较。",
            "purpose": "先建立可解释的预测基线，再讨论误差来自模型、上下文还是标签。",
            "headline": {
                "label": "作者检查点复算 MCC",
                "value": w1_esm150["mcc"],
                "format": "mcc12",
            },
            "methods": [
                {
                    "id": "sequon_rule",
                    "label": "Sequon 规则",
                    "mcc": f1_methods["sequon_rule"]["mcc"],
                    "note": "全部候选判阳，作为下限基线",
                },
                {
                    "id": "esm35_oof",
                    "label": "ESM-2 35M 线性探针",
                    "mcc": f1_methods["esm35_oof"]["mcc"],
                    "note": "窗口化留一蛋白 OOF",
                },
                {
                    "id": "esm150_author_adapter",
                    "label": "ESM-2 150M 作者 adapter",
                    "mcc": f1_methods["esm150_author_adapter"]["mcc"],
                    "note": "全序列推理，不能只归因模型大小",
                },
            ],
        },
        {
            "code": "F2",
            "name": "糖链图模型",
            "question": "糖链图结构能否预测免疫原性和糖基化连接类型？",
            "what": "用 PyG 自实现 RGCN 复算 GlycanML Table 3，并固定三种子与训练配置。",
            "purpose": "验证图神经网络路线是否可复现，并诚实记录与论文的偏差。",
            "table": "Table 3",
            "implementation": "PyG 自实现 RGCN",
            "torchdrug_installed": f2["torchdrug_comparison"]["torchdrug_installed"],
            "training": {
                "seeds": len(f2_immuno["per_seed"]),
                "epochs": f2["training"]["epochs"],
                "batch_size": f2["training"]["batch_size"],
            },
            "tasks": {
                "immunogenicity": {
                    "label": "免疫原性",
                    "metric": "AUPRC",
                    "mean": f2_immuno["aggregate"]["test_auprc"]["mean"],
                    "std": f2_immuno["aggregate"]["test_auprc"]["std"],
                    "rows": f2_immuno["rows"],
                    "reference_mean": f2_immuno_ref["reference"]["value"],
                    "reference_std": f2_immuno_ref["reference"]["std"],
                    "delta": f2_immuno_ref["comparison"]["delta_local_minus_reference"],
                },
                "glycosylation": {
                    "label": "糖基化连接",
                    "metric": "Macro-F1",
                    "mean": f2_glyco["aggregate"]["test_macro_f1"]["mean"],
                    "std": f2_glyco["aggregate"]["test_macro_f1"]["std"],
                    "rows": f2_glyco["rows"],
                    "reference_mean": f2_glyco_ref["reference"]["value"],
                    "reference_std": f2_glyco_ref["reference"]["std"],
                    "delta": f2_glyco_ref["comparison"]["delta_local_minus_reference"],
                },
            },
        },
        {
            "code": "F3",
            "name": "工具调用智能体",
            "question": "模型能不能把预测、数据库查询和格式转换串成一条可执行轨迹？",
            "what": "用 Doc2Agent 任务集跑 Qwen3 4B，记录工具调用、期望工具命中和最终回答。",
            "purpose": "先验证任务轨迹和工具生态，再把答案质量评分单独处理。",
            "trajectory": {
                "tasks_run": f3["tasks_run"],
                "exact_sequence": f3["exact_sequence"],
                "all_expected_called": f3["all_expected_called"],
                "any_expected_called": f3["any_expected_called"],
                "tasks_with_final_answer": f3["tasks_with_final_answer"],
                "tool_call_successes": f3["tool_call_successes"],
                "tool_calls": f3["tool_calls"],
                "grader": f3["grader"],
            },
            "tools": {
                "total": tools["total_tools"],
                "direct_ok": tools["directly_ok"],
                "service_alive": tools["service_alive"],
            },
            "feasibility": {
                "direct": revised["current_tools_direct"],
                "replacement": revised["needs_replacement_tool"],
                "service_failure": revised["service_failure"],
                "total": classification_total,
                "rechecked_tools": recheck["total_blocked_tools"],
            },
        },
    ]

    scorecard_boundaries = list(scorecard["boundaries"])
    boundaries = [
        *[{"kind": "claim", "text": text} for text in scorecard_boundaries],
        {
            "kind": "benchmark",
            "text": (
                f"{benchmark['unannotated_control']} 条未标注对照不是阴性，"
                "只能报告未标注样本保持率；"
                f"{benchmark['inferred_display_only']} 条推断阳性只展示，不进指标。"
            ),
        },
        {
            "kind": "f3",
            "text": (
                "本地 F3 轨迹指标不能与上游 GPT-4o 评分的答案准确率直接比较；"
                "8B 中断目录不是成绩。"
            ),
        },
    ]

    story: dict[str, Any] = {
        "schema_version": "glyco-recording-story/v1",
        "meta": {
            "project": "毕设糖基化分析系统",
            "period": "W01 2026-10-18 至 10-27；W02 2026-10-28 至 11-03",
            "head_commit": source_head,
            "head_short": source_head[:8],
            "slide_count": 8,
            "generated_by": "scripts/build_video_ui.py",
            "sources": sources_meta,
        },
        "weeks": [
            {
                "slide": 1,
                "id": "cover",
                "chapter": "开场",
                "range": "W01 10.18-10.27 / W02 10.28-11.03",
                "title": "从可信基线到可运行系统",
                "thesis": "一个毕设项目如何把蛋白预测、糖链图模型和工具智能体接成可验证的交付链。",
                "work": "",
                "purpose": "这一段视频只回答两个问题：前两周做了什么，这些事情让系统现在能做什么。",
                "source_roles": ["w2_weekly"],
                "notes": (
                    "先现场运行 git rev-parse HEAD，证明当前演示版本。"
                    "然后用一句话说明：前两周不是堆功能，而是先建立可信数字，再跑通三条研究线，最后收束为可检查的交付物。"
                ),
            },
            {
                "slide": 2,
                "id": "w1",
                "chapter": "W1",
                "range": "2026-10-18 - 10-27",
                "title": "第一周先解决的不是模型，而是可信",
                "thesis": "同一个位点，三种判断；每个数字都能回到真实产物。",
                "work": (
                    "统一候选位点、评估池和证据口径；对拍序列规则、35M 线性探针和 "
                    "150M 作者 adapter；再人工复核最值得看的分歧位点。"
                ),
                "purpose": (
                    "没有可信基线，后面所有模型数字都无法解释。第一周把“能复现”"
                    "变成后续工作的硬前提。"
                ),
                "source_roles": ["w1_manifest", "w1_esm150", "w1_weekly"],
                "notes": (
                    "重点讲评估池：评估只看实验阳性和未标注对照，推断阳性只展示。"
                    "人工复核结果按 6 个有独立实验证据、3 个漏注释候选、1 个未找到独立证据来读。"
                    "作者检查点复算 MCC 与论文值接近，但这是复算，不是宣称我们自己重新训练出了同样模型。"
                ),
            },
            {
                "slide": 3,
                "id": "w2",
                "chapter": "W2",
                "range": "2026-10-28 - 11-03",
                "title": "第二周把问题拆成三条可验证的线",
                "thesis": "每天只推进一个能留下证据的问题。",
                "work": "从技术选型开始，依次完成复算、工具复测、记分卡和单文件界面。",
                "purpose": (
                    "让研究结果、工程证据和交付展示各自有明确位置，"
                    "而不是最后一天把截图和数字拼在一起。"
                ),
                "days": list(W2_DAYS),
                "source_roles": ["w2_weekly", "scorecard"],
                "notes": (
                    "按五张日程卡讲，不要逐字念文件名。"
                    "Day 1 解决能不能做，Day 2 得到第一批结果，Day 3 修正工具判断，"
                    "Day 4 建立唯一数字入口，Day 5 把结果做成可打开、可录屏的页面。"
                ),
            },
            {
                "slide": 4,
                "id": "tracks",
                "chapter": "三线",
                "range": "F1 / F2 / F3",
                "title": "三条线回答三个不同层级的问题",
                "thesis": "位点、糖链、任务，不是三个孤立模型，而是一条逐渐接近应用的链路。",
                "work": "F1 给位点概率，F2 给糖链属性，F3 把模型和数据库工具组合成任务轨迹。",
                "purpose": "明确每条线的输入、输出和评价方式，避免把不同指标混成一个“准确率”。",
                "source_roles": ["w1_manifest", "f2_recompute", "f3_summary"],
                "notes": (
                    "这一页只建立系统地图。F1 是序列位点预测，F2 是糖链图性质预测，"
                    "F3 是工具调用。三条线的数据对象、输出和指标都不同，所以不能说谁的分数更高就代表整条系统更好。"
                ),
            },
            {
                "slide": 5,
                "id": "f2",
                "chapter": "F2",
                "range": "GlycanML Table 3",
                "title": "F2 复算：接近论文，但不冒充逐位克隆",
                "thesis": "三随机种子、固定训练配置、保留论文参照值和真实偏差。",
                "work": "在本地 PyG 实现上完成免疫原性与糖基化连接两个任务。",
                "purpose": "证明图模型路线能跑通、结果量级合理，同时把实现差异写在结果旁边。",
                "source_roles": ["f2_recompute", "scorecard"],
                "notes": (
                    "先说对齐的是 Table 3，不是 Table 2。"
                    "再报两个本地均值加减标准差。免疫原性落在论文报告值的一个本地实测标准差内；"
                    "糖基化 Macro-F1 低于论文值，需要如实说明。TorchDrug 没有安装，所以不能声称逐位复刻。"
                ),
            },
            {
                "slide": 6,
                "id": "f3",
                "chapter": "F3",
                "range": "Doc2Agent / Qwen3 4B",
                "title": "F3 与工具：先看轨迹，再谈答案",
                "thesis": "工具有没有被调用、是否调对、服务是否可用，必须和答案正确率分开。",
                "work": "记录 50 题的工具轨迹，盘点 70 个 wrapper，并修正任务级可行性分类。",
                "purpose": "找出真正阻断任务的原因，为下一周修工具契约和统一评分做准备。",
                "source_roles": [
                    "f3_summary",
                    "tools_summary",
                    "feasibility_csv",
                    "recheck_summary",
                ],
                "notes": (
                    "这一页最容易讲错。轨迹匹配、期望工具命中和最终回答存在性都不是答案正确率。"
                    "本地没有 GPT-4o grader，所以不能拿这些数字直接和上游 18/50、15/50 比。"
                    "工具任务分类才是当前工具能不能完成任务的判断。"
                ),
            },
            {
                "slide": 7,
                "id": "delivery",
                "chapter": "闭环",
                "range": "W2 Delivery",
                "title": "交付闭环：数字、证据、界面都能重算",
                "thesis": "报告里的每个核心数字，都应能沿着 JSON、CSV 和 SHA256 回到源产物。",
                "work": "记分卡统一指标入口，主界面读取真实数据契约，录制界面只负责叙事。",
                "purpose": "把“我做过”变成“别人能打开、能检查、能重复生成”。",
                "source_roles": ["scorecard", "w2_weekly"],
                "notes": (
                    "这里展示闭环，不要重新报一遍所有指标。"
                    "强调记分卡是唯一数字入口，源文件带哈希；主交付界面和录制界面职责分开。"
                    "这一页之后，观众应该知道项目不是只有几张结果图。"
                ),
            },
            {
                "slide": 8,
                "id": "boundaries",
                "chapter": "边界",
                "range": "Claims / Next",
                "title": "现在能说什么，下一步补什么",
                "thesis": "把边界说清楚，是结果可信的一部分，不是给项目减分。",
                "work": "两条研究线已经可复现，工具任务已有分类，但端到端问答和统一答案评分还没完成。",
                "purpose": "下一周集中修工具契约、补一致性实验，并把 F1、F2、F3 接成可演示的完整流程。",
                "source_roles": ["scorecard", "w2_weekly", "f2_recompute", "f3_summary"],
                "notes": (
                    "最后不要用“全部完成”收尾。"
                    "准确说法是：前两周完成了可信基线、三线核心实验和可重算交付；"
                    "下一周才进入系统串联、工具修复和一致性评分。"
                ),
            },
        ],
        "tracks": tracks,
        "delivery": {
            "status": scorecard["status"],
            "metric_rows": scorecard["validations"]["metric_rows"],
            "source_count": len(scorecard["sources"]),
            "f2_seeds": scorecard["validations"]["f2_seeds"],
            "f3_tasks": scorecard["validations"]["f3_tasks"],
            "feasibility_total": scorecard["validations"]["feasibility_total"],
            "proof_points": [
                {
                    "label": "可重算指标",
                    "value": scorecard["validations"]["metric_rows"],
                    "unit": "条",
                    "detail": "F1、F2、F3 与工具可行性都有固定源路径和 SHA256。",
                },
                {
                    "label": "F2 独立种子",
                    "value": scorecard["validations"]["f2_seeds"],
                    "unit": "个",
                    "detail": "训练配置固定，均值和标准差由逐种子结果重算。",
                },
                {
                    "label": "工具任务分类",
                    "value": scorecard["validations"]["feasibility_total"],
                    "unit": "题",
                    "detail": "当前工具、替代工具和服务失败三类合计必须完整覆盖。",
                },
            ],
            "closure": (
                "主线 web 负责可浏览的交付数据；video-ui 只负责录屏叙事。"
                "两者都读取仓库事实，但构建和产物彼此隔离。"
            ),
        },
        "boundaries": boundaries,
        "next": [
            "修工具契约和查询参数，继续缩小服务失败与替代工具两类。",
            "补 F2 超参稳定性和更严格的模型对照，不把实现差异藏在单个均值里。",
            "用同一套评分协议处理 F3 答案质量，再与上游结果比较。",
            "把 F1、F2、F3 串成一次可现场演示的端到端问答。",
        ],
    }

    # Keep source labels next to slides without duplicating them into the
    # renderer. The presentation reads these from the generated story.
    for slide in story["weeks"]:
        slide["sources"] = [
            {
                "role": role,
                "label": SOURCE_LABELS[role],
                "path": source_meta_by_role[role]["path"],
            }
            for role in slide["source_roles"]
        ]
        if slide["id"] == "w1":
            slide["benchmark"] = {
                "evaluation_rows": benchmark["evaluation_rows"],
                "experimental_positive": benchmark["experimental_positive"],
                "unannotated_control": benchmark["unannotated_control"],
                "inferred_display_only": benchmark["inferred_display_only"],
            }
            slide["review_counts"] = {
                "supported": review_counts["SUPPORTED_EXPERIMENTAL_POSITIVE"],
                "missed": review_counts["MISSED_ANNOTATION_CANDIDATE"],
                "no_evidence": review_counts["NO_INDEPENDENT_EVIDENCE_FOUND"],
            }
            slide["review_counts"]["reviewed_total"] = sum(slide["review_counts"].values())

    return story


def replace_once(text: str, marker: str, value: str) -> str:
    count = text.count(marker)
    if count != 1:
        raise RuntimeError(f"template marker {marker!r} occurs {count} times")
    return text.replace(marker, value)


def render_bundle(root: Path, story: dict[str, Any]) -> tuple[bytes, bytes]:
    template = (root / "video-ui/src/template.html").read_text(encoding="utf-8")
    css = (root / "video-ui/src/deck.css").read_text(encoding="utf-8")
    script = (root / "video-ui/src/deck.js").read_text(encoding="utf-8")
    story_json = json.dumps(
        story,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    html = replace_once(template, "__STORY_JSON__", story_json)
    html = replace_once(html, "__DECK_CSS__", css)
    html = replace_once(html, "__DECK_JS__", script)
    story_bytes = (
        json.dumps(story, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    return story_bytes, html.encode("utf-8")


def write_bundle(artifact_root: Path, story_bytes: bytes, html_bytes: bytes) -> None:
    story_path = artifact_root / STORY_REL
    index_path = artifact_root / INDEX_REL
    story_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    story_path.write_bytes(story_bytes)
    index_path.write_bytes(html_bytes)


def verify_bundle(
    artifact_root: Path,
    story_bytes: bytes,
    html_bytes: bytes,
) -> list[str]:
    expected = {
        STORY_REL: story_bytes,
        INDEX_REL: html_bytes,
    }
    failures: list[str] = []
    for rel, content in expected.items():
        path = artifact_root / rel
        if not path.is_file():
            failures.append(f"{rel.as_posix()}: missing")
        elif path.read_bytes() != content:
            failures.append(f"{rel.as_posix()}: differs")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify generated output instead of writing it",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    story = build_story(root)
    story_bytes, html_bytes = render_bundle(root, story)
    artifact_root = root / "video-ui"

    if args.check:
        failures = verify_bundle(artifact_root, story_bytes, html_bytes)
        if failures:
            print(f"FAIL video-ui contract: {artifact_root}")
            for failure in failures:
                print(f"- {failure}")
            return 1
        print(f"PASS video-ui contract: {artifact_root}")
        return 0

    write_bundle(artifact_root, story_bytes, html_bytes)
    print(f"built {artifact_root / STORY_REL}")
    print(f"built {artifact_root / INDEX_REL}")
    print(f"head {story['meta']['head_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
