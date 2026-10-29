"""Classify Doc2Agent tasks by current-wrapper feasibility.

This is a table transformation over the existing wrapper sweep. It does not
call any service or model. One primary category is assigned per task.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS = ROOT / "reports" / "w2_day1" / "doc2agent_tasks.csv"
DEFAULT_TOOLS = ROOT / "reports" / "w2_day1" / "doc2agent_tools.csv"
DEFAULT_RUNS = ROOT / "reports" / "w2_day2" / "f3_qwen3_4b_50"
DEFAULT_OUT_CSV = ROOT / "reports" / "w2_day2" / "tool_feasibility.csv"
DEFAULT_OUT_SUMMARY = ROOT / "reports" / "w2_day2" / "tool_feasibility_summary.json"

DIRECT = "current_tools_direct"
REPLACEMENT = "needs_replacement_tool"
SERVICE = "service_failure"
CATEGORIES = (DIRECT, REPLACEMENT, SERVICE)
SERVICE_FAILURE_CLASSES = frozenset({"http_424", "server_error", "timeout", "unreachable"})

FIELDS = (
    "task_id",
    "category",
    "site",
    "task_type",
    "steps",
    "expected_tools",
    "blocking_tools",
    "blocking_classes",
    "wrapper_evidence",
    "f3_non_ok_calls",
    "f3_has_final_answer",
    "source_task_json",
)


def base_tool(stem: str) -> str:
    for suffix in ("_GET", "_POST"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem.replace("___", "_")


def split_arrow(value: str) -> list[str]:
    return [part.strip() for part in value.split(" -> ") if part.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT)).replace("\\", "/")


def load_tools(path: Path) -> dict[str, dict[str, str]]:
    tools: dict[str, dict[str, str]] = {}
    duplicates: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = base_tool(row["tool"])
            if name in tools:
                duplicates.append(name)
            tools[name] = row
    if duplicates:
        raise ValueError(f"Duplicate wrapper names: {sorted(set(duplicates))}")
    return tools


def load_runs(run_dir: Path, expected_tasks: int) -> dict[int, dict[str, Any]]:
    runs: dict[int, dict[str, Any]] = {}
    for path in sorted(run_dir.glob("task_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        task_id = int(payload["task_id"])
        if task_id in runs:
            raise ValueError(f"Duplicate task_id {task_id} in run directory")
        runs[task_id] = payload
    expected_ids = set(range(1, expected_tasks + 1))
    if set(runs) != expected_ids:
        missing = sorted(expected_ids - set(runs))
        extra = sorted(set(runs) - expected_ids)
        raise ValueError(f"Unexpected run task ids; missing={missing}, extra={extra}")
    return runs


def classify_statuses(statuses: list[str]) -> str:
    if all(status == "ok" for status in statuses):
        return DIRECT
    if any(status in SERVICE_FAILURE_CLASSES for status in statuses):
        return SERVICE
    return REPLACEMENT


def wrapper_detail(tool: str, row: dict[str, str]) -> str:
    status = row.get("class", "")
    http_status = row.get("http_status", "")
    error = row.get("error", "")
    error = error.replace("\r", " ").replace("\n", " ")
    error = error[:180]
    parts = [f"tool={tool}", f"class={status or 'missing'}"]
    if http_status:
        parts.append(f"http={http_status}")
    if error:
        parts.append(f"error={error}")
    return "; ".join(parts)


def f3_non_ok_calls(run: dict[str, Any]) -> str:
    calls = []
    for call in run.get("tool_calls", []):
        status = call.get("status", "")
        if status != "ok":
            calls.append(f"{call.get('tool', '')}:{status}")
    return " | ".join(calls)


def build_records(
    task_rows: list[dict[str, str]],
    tools: dict[str, dict[str, str]],
    runs: dict[int, dict[str, Any]],
    run_dir: Path,
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for row in task_rows:
        task_id = int(row["task_id"])
        names = split_arrow(row["tools"])
        statuses = split_arrow(row["wrapper_statuses"])
        if len(names) != len(statuses):
            raise ValueError(f"Task {task_id} has mismatched tools and statuses")
        missing = [name for name in names if name not in tools]
        if missing:
            raise ValueError(f"Task {task_id} references unknown wrappers: {missing}")

        blockers: list[str] = []
        blocker_classes: list[str] = []
        evidence: list[str] = []
        for name, status in zip(names, statuses):
            if status == "ok":
                continue
            if name not in blockers:
                blockers.append(name)
            blocker_classes.append(status)
            evidence.append(wrapper_detail(name, tools[name]))

        run = runs[task_id]
        task_path = run_dir / f"task_{task_id:02d}.json"
        records.append(
            {
                "task_id": str(task_id),
                "category": classify_statuses(statuses),
                "site": row.get("site", ""),
                "task_type": row.get("task_type", ""),
                "steps": row.get("steps", ""),
                "expected_tools": " -> ".join(names),
                "blocking_tools": " | ".join(blockers),
                "blocking_classes": " | ".join(blocker_classes),
                "wrapper_evidence": " || ".join(evidence) if evidence else "all wrappers class=ok",
                "f3_non_ok_calls": f3_non_ok_calls(run),
                "f3_has_final_answer": str(bool(run.get("final_answer"))).lower(),
                "source_task_json": relative(task_path) if task_path.exists() else "",
            }
        )
    return records


def validate_records(records: list[dict[str, str]], expected_tasks: int) -> None:
    ids = [int(record["task_id"]) for record in records]
    if len(ids) != expected_tasks or set(ids) != set(range(1, expected_tasks + 1)):
        raise ValueError(f"Expected task ids 1..{expected_tasks}, got {ids}")
    categories = Counter(record["category"] for record in records)
    if set(categories) - set(CATEGORIES):
        raise ValueError(f"Unexpected categories: {sorted(set(categories) - set(CATEGORIES))}")
    if sum(categories.values()) != expected_tasks:
        raise ValueError("Category counts do not sum to the task total")


def build_summary(
    records: list[dict[str, str]],
    task_path: Path,
    tool_path: Path,
    run_dir: Path,
    expected_tasks: int,
) -> dict[str, Any]:
    validate_records(records, expected_tasks)
    category_counts = Counter(record["category"] for record in records)
    blocked_tools = Counter(
        tool
        for record in records
        for tool in record["blocking_tools"].split(" | ")
        if tool
    )
    blocked_classes = Counter(
        status
        for record in records
        for status in record["blocking_classes"].split(" | ")
        if status
    )
    f3_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    run_files = sorted(run_dir.glob("task_*.json"))
    return {
        "status": "PASS",
        "classification_scope": "wrapper-level feasibility; not answer correctness",
        "total_tasks": len(records),
        "category_counts": {
            DIRECT: category_counts.get(DIRECT, 0),
            REPLACEMENT: category_counts.get(REPLACEMENT, 0),
            SERVICE: category_counts.get(SERVICE, 0),
        },
        "category_labels_zh": {
            DIRECT: "当前工具可直接完成",
            REPLACEMENT: "需要替代工具",
            SERVICE: "服务失败",
        },
        "tasks_with_all_expected_wrappers_ok": category_counts.get(DIRECT, 0),
        "tasks_with_any_blocker": len(records) - category_counts.get(DIRECT, 0),
        "service_failure_classes": sorted(SERVICE_FAILURE_CLASSES),
        "blocked_tool_counts": dict(sorted(blocked_tools.items())),
        "blocked_class_counts": dict(sorted(blocked_classes.items())),
        "official_f3_run": {
            "model": f3_summary.get("model"),
            "tasks_run": f3_summary.get("tasks_run"),
            "tool_task_files": len(run_files),
            "exact_sequence": f3_summary.get("exact_sequence"),
            "all_expected_called": f3_summary.get("all_expected_called"),
            "any_expected_called": f3_summary.get("any_expected_called"),
            "tasks_with_final_answer": f3_summary.get("tasks_with_final_answer"),
            "tool_calls": f3_summary.get("tool_calls"),
            "tool_call_successes": f3_summary.get("tool_call_successes"),
            "grader": f3_summary.get("grader"),
        },
        "validation": {
            "expected_tasks": expected_tasks,
            "unique_task_ids": len({record["task_id"] for record in records}),
            "category_sum_equals_total": sum(category_counts.values()) == expected_tasks,
            "three_category_names_only": set(category_counts) <= set(CATEGORIES),
        },
        "sources": {
            relative(task_path): sha256(task_path),
            relative(tool_path): sha256(tool_path),
            relative(run_dir / "summary.json"): sha256(run_dir / "summary.json"),
        },
    }


def write_outputs(records: list[dict[str, str]], summary: dict[str, Any], out_csv: Path, out_summary: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    out_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--tools", type=Path, default=DEFAULT_TOOLS)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--out-summary", type=Path, default=DEFAULT_OUT_SUMMARY)
    parser.add_argument("--expected-tasks", type=int, default=50)
    args = parser.parse_args()

    with args.tasks.open(newline="", encoding="utf-8") as handle:
        task_rows = list(csv.DictReader(handle))
    tools = load_tools(args.tools)
    runs = load_runs(args.runs, args.expected_tasks)
    records = build_records(task_rows, tools, runs, args.runs)
    summary = build_summary(records, args.tasks, args.tools, args.runs, args.expected_tasks)
    write_outputs(records, summary, args.out_csv, args.out_summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
