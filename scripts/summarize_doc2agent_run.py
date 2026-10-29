"""Recompute aggregate metrics from a Doc2Agent runner output directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SUMMARY_METRIC_KEYS = (
    "tasks_run",
    "exact_sequence",
    "all_expected_called",
    "any_expected_called",
    "tasks_with_tool_call",
    "tasks_with_final_answer",
    "tool_call_successes",
    "tool_calls",
)


def load_runs(run_dir: Path, expected_tasks: int) -> list[dict[str, Any]]:
    paths = sorted(run_dir.glob("task_*.json"))
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    task_ids = [int(run["task_id"]) for run in runs]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("Duplicate task_id values in run directory")
    if expected_tasks and set(task_ids) != set(range(1, expected_tasks + 1)):
        missing = sorted(set(range(1, expected_tasks + 1)) - set(task_ids))
        extra = sorted(set(task_ids) - set(range(1, expected_tasks + 1)))
        raise ValueError(f"Unexpected task ids; missing={missing}, extra={extra}")
    return sorted(runs, key=lambda run: int(run["task_id"]))


def summarize(runs: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "tasks_run": len(runs),
        "exact_sequence": sum(bool(run["exact_sequence"]) for run in runs),
        "all_expected_called": sum(
            bool(run["all_expected_called"]) for run in runs
        ),
        "any_expected_called": sum(
            bool(run["any_expected_called"]) for run in runs
        ),
        "tasks_with_tool_call": sum(bool(run["tool_calls"]) for run in runs),
        "tasks_with_final_answer": sum(bool(run["final_answer"]) for run in runs),
        "tool_call_successes": sum(
            call.get("status") == "ok"
            for run in runs
            for call in run["tool_calls"]
        ),
        "tool_calls": sum(len(run["tool_calls"]) for run in runs),
    }


def compare_summary(summary_path: Path, metrics: dict[str, int]) -> None:
    recorded = json.loads(summary_path.read_text(encoding="utf-8"))
    mismatches = {
        key: {"recorded": recorded.get(key), "recomputed": metrics[key]}
        for key in SUMMARY_METRIC_KEYS
        if recorded.get(key) != metrics[key]
    }
    if mismatches:
        detail = json.dumps(mismatches, ensure_ascii=False)
        raise ValueError(f"Summary mismatch: {detail}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expected-tasks", type=int, default=0)
    parser.add_argument("--check-summary", type=Path)
    args = parser.parse_args()

    runs = load_runs(args.run_dir, args.expected_tasks)
    metrics = summarize(runs)
    if args.check_summary:
        compare_summary(args.check_summary, metrics)
    result = {"status": "PASS", "metrics": metrics}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
