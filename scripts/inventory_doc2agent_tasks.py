"""Summarize Doc2Agent's 50 glycan tasks against the wrapper survival sweep."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_FILE = ROOT / "data" / "raw" / "doc2agent" / "glycan_tasks_classified.jsonl"
TOOL_CSV = ROOT / "reports" / "w2_day1" / "doc2agent_tools.csv"
OUT_DIR = ROOT / "reports" / "w2_day1"
BASELINES = {
    "claude_logs": ROOT / "data" / "raw" / "doc2agent" / "claude_evaluation_summary.json",
    "qwen3_logs": ROOT / "data" / "raw" / "doc2agent" / "qwen3_evaluation_summary.json",
}


def base_tool(stem: str) -> str:
    for suffix in ("_GET", "_POST"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem.replace("___", "_")


def load_tools() -> dict[str, dict[str, str]]:
    tools: dict[str, dict[str, str]] = {}
    with TOOL_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            tools[base_tool(row["tool"])] = row
    return tools


def load_baselines() -> dict[str, dict]:
    result = {}
    for name, path in BASELINES.items():
        if not path.exists() or path.stat().st_size < 10000:
            result[name] = {"available": False}
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        result[name] = {
            "available": True,
            "successful_tasks": payload.get("successful_tasks"),
            "total_tasks": payload.get("total_tasks"),
            "success_rate": payload.get("success_rate"),
            "grader_model": payload.get("model_used"),
        }
    return result


def main() -> int:
    tools = load_tools()
    rows = [
        json.loads(line)
        for line in TASK_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    tasks = []
    unknown_tools: Counter[str] = Counter()
    for index, row in enumerate(rows, start=1):
        trajectory = row.get("expected_trajectory", "")
        names = [part.strip() for part in trajectory.replace("→", "->").split("->")]
        statuses = []
        for name in names:
            tool = tools.get(name)
            if tool is None:
                unknown_tools[name] += 1
                statuses.append("unknown")
            else:
                statuses.append(tool["class"])
        tasks.append(
            {
                "task_id": index,
                "site": row.get("site", ""),
                "task_type": row.get("task_type", ""),
                "steps": len(names),
                "tools": " -> ".join(names),
                "wrapper_statuses": " -> ".join(statuses),
                "all_wrappers_ok": all(status == "ok" for status in statuses),
                "question": row.get("question", ""),
                "expected_trajectory": trajectory,
            }
        )

    fields = list(tasks[0])
    with (OUT_DIR / "doc2agent_tasks.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(tasks)

    single = sum(1 for task in tasks if task["steps"] == 1)
    summary = {
        "total_tasks": len(tasks),
        "single_step": single,
        "multi_step": len(tasks) - single,
        "step_distribution": dict(sorted(Counter(task["steps"] for task in tasks).items())),
        "all_wrappers_ok": sum(1 for task in tasks if task["all_wrappers_ok"]),
        "has_non_ok_wrapper": sum(1 for task in tasks if not task["all_wrappers_ok"]),
        "unknown_tools": dict(sorted(unknown_tools.items())),
        "site_counts": dict(sorted(Counter(task["site"] for task in tasks).items())),
        "upstream_baselines": load_baselines(),
    }
    (OUT_DIR / "doc2agent_tasks_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
