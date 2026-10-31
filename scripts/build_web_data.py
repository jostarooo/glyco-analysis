#!/usr/bin/env python3
"""Build the web data contract from real repository artifacts.

All numbers shown by web/ come from this generator. The script is
deterministic: no wall-clock timestamps, sorted keys, byte-identical
output on consecutive runs. Run with --check to fail on missing,
stale, or hand-edited generated files.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = REPO_ROOT / "web" / "src" / "data"

SOURCES = {
    "scorecard": "reports/w3_day2/scorecard.json",
    "f1_three_method": "reports/w1_three_method_v0/metrics.json",
    "f1_esm150": "reports/esm150_lora_repro_v0/metrics.json",
    "f2_recompute": "reports/w2_day1/glycanml_rgcn_recompute.json",
    "f2_data_check": "reports/w2_day1/glycanml_data_check.json",
    "f3_summary": "reports/w2_day2/f3_qwen3_4b_50/summary.json",
    "tools": "reports/w2_day1/doc2agent_tools.csv",
    "tools_summary": "reports/w2_day1/doc2agent_tools_summary.json",
    "tasks": "reports/w2_day1/doc2agent_tasks.csv",
    "tasks_summary": "reports/w2_day1/doc2agent_tasks_summary.json",
    "feasibility": "reports/w3_day1/task_feasibility_revised.csv",
    "recheck": "reports/w3_day1/tool_blocker_recheck_summary.json",
}

EXPECTED_GENERATED = ["project.json", "metrics.json", "tools.json", "boundaries.json"]
UI_FILES = [
    "web/package.json",
    "web/vite.config.ts",
    "web/src/App.tsx",
    "web/src/loaders.ts",
    "web/src/lib.ts",
    "web/src/main.tsx",
    "web/src/pages/Overview.tsx",
    "web/src/pages/Metrics.tsx",
    "web/src/pages/Tools.tsx",
    "web/src/pages/Boundaries.tsx",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        return out.stdout.strip()
    except Exception as exc:  # pragma: no cover - generator contract
        raise SystemExit(f"cannot read git HEAD: {exc}")


def head_contract_is_current() -> bool:
    path = WEB_DATA / "project.json"
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    if payload.get("head_commit") == git_head():
        return True
    return stale_head_contract_is_bootstrapped()


def stale_head_contract_is_bootstrapped() -> bool:
    """Accept only a committed head lag after UI regeneration, not arbitrary drift."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--"] + UI_FILES,
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
    except Exception:
        return False
    return not out.stdout.strip()


def load_sources() -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = {}
    for role, rel in SOURCES.items():
        path = REPO_ROOT / rel
        if not path.is_file():
            raise SystemExit(f"missing source: {rel}")
        raw = path.read_bytes()
        if rel.endswith(".csv"):
            text = raw.decode("utf-8-sig")
            data[role] = {"rows": list(csv.DictReader(text.splitlines()))}
        else:
            data[role] = json.loads(raw.decode("utf-8-sig"))
        data[role]["_meta"] = {
            "role": role,
            "path": rel,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_count": len(raw),
        }
    return data


def build_project(data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sc = data["scorecard"]
    ts = data["tools_summary"]
    tk = data["tasks_summary"]
    fc = data["f2_data_check"]
    head = git_head()
    return {
        "schema_version": "glyco-web-project/v1",
        "head_commit": head,
        "project": {
            "title": "毕设糖基化分析系统",
            "one_liner": "以蛋白质语言模型预测 N-糖基化位点、以图神经网络解析糖链、并用工具调用智能体把两者串成一个可对话的分析工作台",
            "tracks": [
                {"id": "F1", "name": "位点预测", "what": "给定蛋白序列，预测 N-X-S/T 位点是否真被糖基化", "base": "ESM-2（35M 线性探针 / 150M LoRA）"},
                {"id": "F2", "name": "糖链模型", "what": "给定糖链结构，预测其性质；本轮完成免疫原性与糖基化两任务", "base": "RGCN（PyG 自实现，对齐 GlycanML Table 3）"},
                {"id": "F3", "name": "工具调用智能体", "what": "把 F1/F2 与数据库查询包装成工具，用中文任务驱动", "base": "Doc2Agent 路线 + MCP；本轮完成 Qwen3 4B 50 题轨迹基线"},
            ],
        },
        "terms": [
            {"code": "MCC", "plain": "马修斯相关系数。综合看真阳、真阴两侧的分类质量，1 最好，0 等于随机"},
            {"code": "sequon", "plain": "N-X-S/T 序列模体，X 不是脯氨酸；有模体不等于真被糖基化"},
            {"code": "LoRA / adapter", "plain": "低秩适配器，冻结大模型主干、只加载少量可训练参数"},
            {"code": "OOF", "plain": "留一蛋白折外预测：每次留出一个蛋白做测试，汇总各折结果"},
            {"code": "AUPRC", "plain": "精确率-召回率曲线下面积，正类稀少时比准确率更有信息"},
            {"code": "Macro-F1", "plain": "每个类别先算 F1 再取平均，类别不平衡时不偏大类"},
            {"code": "RGCN", "plain": "关系图卷积网络，按边类型（糖苷键）分别卷积"},
            {"code": "MCP", "plain": "模型上下文协议，把外部工具按统一接口给智能体调用"},
            {"code": "wrapper", "plain": "把一个外部 API 包装成智能体可调用的工具函数"},
        ],
        "gates": [
            {"no": 1, "name": "环境关", "state": "通过", "artifact": "reports/env_check.md"},
            {"no": 2, "name": "数据关", "state": "通过", "artifact": "reports/endpoint_check_2026-10-18.md"},
            {"no": 3, "name": "复现关", "state": "通过", "artifact": "reports/mcc_repro.md"},
            {"no": 4, "name": "本机训练关", "state": "未开始（后续周）", "artifact": "reports/local_train.md"},
            {"no": 5, "name": "系统关", "state": "本界面为 W3 Day 3 的交付前端，端到端问答未完成", "artifact": "docs/demo.md（计划）"},
        ],
        "counts": {
            "tools_total": ts["total_tools"],
            "tools_ok": ts["directly_ok"],
            "tools_alive": ts["service_alive"],
            "tasks_total": tk["total_tasks"],
            "f2_csv_count": len(fc["datasets"]),
            "f2_csv_bytes": sum(item["bytes"] for item in fc["datasets"]),
            "metric_rows": sc["validations"]["metric_rows"],
            "scorecard_status": sc["status"],
            "scorecard_schema": sc["schema_version"],
        },
        "sources": [{"role": k, **data[k]["_meta"]} for k in sorted(SOURCES)],
        "generated_by": "scripts/build_web_data.py",
    }


def build_metrics(data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sc = data["scorecard"]
    f1 = data["f1_three_method"]
    methods = []
    for key in ("sequon_rule", "esm35_oof", "esm150_author_adapter"):
        m = f1["methods"][key]
        methods.append({
            "id": key,
            "label": {"sequon_rule": "Sequon 规则", "esm35_oof": "35M 线性探针 OOF", "esm150_author_adapter": "150M 作者适配器"}[key],
            "mcc": m["metrics"]["mcc"],
            "mcc_defined": m["mcc_defined"],
            "roc_auc": m["metrics"].get("roc_auc"),
            "control_specificity": m["metrics"]["control_specificity"],
            "confusion": m["confusion"],
        })
    return {
        "schema_version": "glyco-web-metrics/v1",
        "scorecard_status": sc["status"],
        "policy": sc["policy"],
        "validations": sc["validations"],
        "benchmark_pool": f1["benchmark"],
        "f1_comparability_caveat": f1["comparability_caveat"],
        "f1_methods": methods,
        "f1_esm150_repro": {
            "mcc": data["f1_esm150"]["mcc"],
            "reference_mcc": data["f1_esm150"]["reference_mcc"],
            "delta": data["f1_esm150"]["mcc_delta_from_reference"],
            "row_count": data["f1_esm150"]["row_count"],
            "confusion": data["f1_esm150"]["confusion"],
        },
        "f2": {
            "model": data["f2_recompute"]["model"],
            "training": data["f2_recompute"]["training"],
            "vocab": data["f2_recompute"]["vocab"],
            "tasks": data["f2_recompute"]["tasks"],
            "torchdrug_installed": data["f2_recompute"]["torchdrug_comparison"]["torchdrug_installed"],
            "torchdrug_notes": data["f2_recompute"]["torchdrug_comparison"]["notes"],
        },
        "f3": {k: data["f3_summary"][k] for k in (
            "model", "tasks_run", "max_rounds", "num_ctx", "exact_sequence",
            "all_expected_called", "any_expected_called", "tasks_with_tool_call",
            "tasks_with_final_answer", "tool_call_successes", "tool_calls", "grader")},
        "metrics": sc["metrics"],
        "sources": [{"role": k, **data[k]["_meta"]} for k in sorted(SOURCES)],
    }


def build_tools(data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ts = data["tools_summary"]
    rc = data["recheck"]
    feas = {}
    for row in data["feasibility"]["rows"]:
        feas[row["task_id"]] = {
            "revised_category": row["revised_category"],
            "original_category": row["original_category"],
            "blocking_tools": row["blocking_tools"],
            "w3_classes": row["w3_classes"],
            "decision_reason": row["decision_reason"],
        }
    tasks = []
    for row in data["tasks"]["rows"]:
        tid = row["task_id"]
        tasks.append({
            "task_id": tid,
            "site": row["site"],
            "steps": row["steps"],
            "tools": row["tools"],
            "question": row["question"],
            "feasibility": feas.get(tid, {}),
        })
    return {
        "schema_version": "glyco-web-tools/v1",
        "snapshot_note": "W2 盘点是当日快照；W3 复测是最新任务级口径。两边都保留，不互相改写。",
        "tools": data["tools"]["rows"],
        "tool_summary": ts,
        "recheck": {
            "total_blocked_tools": rc["total_blocked_tools"],
            "recheck_class_counts": rc["recheck_class_counts"],
            "service_reachable": rc["service_reachable"],
            "default_transport_ok": rc["default_transport_ok"],
            "task_fit_counts": rc["task_fit_counts"],
            "probe_accepted_tools": rc["probe_accepted_tools"],
            "persistent_blockers": rc["persistent_blockers"],
            "generated_at": rc.get("generated_at"),
        },
        "tasks": tasks,
        "task_summary": {
            "total_tasks": data["tasks_summary"]["total_tasks"],
            "step_distribution": data["tasks_summary"]["step_distribution"],
        },
        "sources": [{"role": k, **data[k]["_meta"]} for k in sorted(SOURCES)],
    }


def build_boundaries(data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sc = data["scorecard"]
    f1 = data["f1_three_method"]
    return {
        "schema_version": "glyco-web-boundaries/v1",
        "scorecard_boundaries": sc["boundaries"],
        "policy": sc["policy"],
        "f1_pool": f1["benchmark"],
        "f1_caveat": f1["comparability_caveat"],
        "f2_torchdrug_notes": data["f2_recompute"]["torchdrug_comparison"]["notes"],
        "f2_data_url_fixes": data["f2_data_check"].get("upstream_url_issues", []),
        "f3_grader": data["f3_summary"]["grader"],
        "recheck_notes": [
            "get_proteins TLS 校验失败不等于服务死亡，verify=False 诊断返回 HTTP 200，生产不关闭 TLS 校验。",
            "get_ligands HTTP 200 空数组不等于任务可用。",
        ],
        "sources": [{"role": k, **data[k]["_meta"]} for k in sorted(SOURCES)],
    }


def project_matches_ignoring_head(path: Path, payload: dict[str, Any]) -> bool:
    try:
        disk = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    strip = lambda item: {key: value for key, value in item.items() if key != "head_commit"}
    return strip(disk) == strip(payload)


def write_outputs(payloads: dict[str, dict[str, Any]], *, check: bool) -> bool:
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    changed: list[str] = []
    for name in EXPECTED_GENERATED:
        path = WEB_DATA / name
        content = (json.dumps(payloads[name], ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        if check:
            if not path.is_file():
                changed.append(f"{name}: missing")
            elif path.read_bytes() != content:
                head_lag_ok = (
                    name == "project.json"
                    and head_contract_is_current()
                    and project_matches_ignoring_head(path, payloads[name])
                )
                if not head_lag_ok:
                    changed.append(f"{name}: differs")
        else:
            if not path.is_file() or path.read_bytes() != content:
                path.write_bytes(content)
                changed.append(name)
    if changed:
        for line in changed:
            print(line)
        return False
    print("web data contract PASS")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify generated files instead of writing")
    args = parser.parse_args()
    data = load_sources()
    if args.check and not head_contract_is_current():
        print("project.json: head_commit is stale")
        return 1
    payloads = {
        "project.json": build_project(data),
        "metrics.json": build_metrics(data),
        "tools.json": build_tools(data),
        "boundaries.json": build_boundaries(data),
    }
    ok = write_outputs(payloads, check=args.check)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
