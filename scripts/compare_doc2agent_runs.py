"""Compare two Doc2Agent runs using trajectory metrics only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL = ROOT / "reports" / "w2_day2" / "f3_qwen3_4b_50"
DEFAULT_EXTERNAL = ROOT / "reports" / "w3_day2" / "f3_glm53_50"
DEFAULT_JSON = ROOT / "reports" / "w3_day2" / "f3_glm53_vs_qwen3_4b.json"
DEFAULT_MD = ROOT / "reports" / "w3_day2" / "f3_glm53_vs_qwen3_4b.md"
METRICS_SCOPE = "trajectory_only"
ANSWER_CORRECTNESS = "not_evaluated"
GRADER = "not_run_upstream_requires_gpt4o_api_key"

BOOL_METRICS = (
    "exact_sequence",
    "all_expected_called",
    "any_expected_called",
)
INTEGER_METRICS = (
    "called_steps",
    "call_successes",
    "tool_calls",
)
SUMMARY_METRICS = (
    "tasks_run",
    "exact_sequence",
    "all_expected_called",
    "any_expected_called",
    "tasks_with_tool_call",
    "tasks_with_final_answer",
    "tool_call_successes",
    "tool_calls",
)


def load_runs(run_dir: Path) -> dict[int, dict[str, Any]]:
    paths = sorted(run_dir.glob("task_*.json"))
    if not paths:
        raise ValueError(f"No task_*.json files found in {run_dir}")
    runs: dict[int, dict[str, Any]] = {}
    for path in paths:
        run = json.loads(path.read_text(encoding="utf-8"))
        task_id = int(run["task_id"])
        if task_id in runs:
            raise ValueError(f"Duplicate task_id {task_id} in {run_dir}")
        runs[task_id] = run
    return runs


def load_summary(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "summary.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def validate_alignment(
    local_runs: dict[int, dict[str, Any]],
    external_runs: dict[int, dict[str, Any]],
) -> list[int]:
    local_ids = set(local_runs)
    external_ids = set(external_runs)
    if local_ids != external_ids:
        raise ValueError(
            "Task ids differ; "
            f"missing_external={sorted(local_ids - external_ids)}, "
            f"missing_local={sorted(external_ids - local_ids)}"
        )
    for task_id in sorted(local_ids):
        local = local_runs[task_id]
        external = external_runs[task_id]
        if local.get("question") != external.get("question"):
            raise ValueError(f"Question differs for task_id {task_id}")
        if local.get("expected_tools") != external.get("expected_tools"):
            raise ValueError(f"Expected tools differ for task_id {task_id}")
    return sorted(local_ids)


def run_values(run: dict[str, Any]) -> dict[str, Any]:
    tool_calls = run.get("tool_calls", [])
    return {
        "exact_sequence": bool(run["exact_sequence"]),
        "all_expected_called": bool(run["all_expected_called"]),
        "any_expected_called": bool(run["any_expected_called"]),
        "called_steps": int(run["called_steps"]),
        "call_successes": int(run["call_successes"]),
        "tool_calls": len(tool_calls),
        "has_tool_call": bool(tool_calls),
        "has_final_answer": bool(run.get("final_answer")),
        "called_tools": [str(call.get("tool", "")) for call in tool_calls],
    }


def delta_values(local: dict[str, Any], external: dict[str, Any]) -> dict[str, int]:
    return {
        metric: int(external[metric]) - int(local[metric])
        for metric in (*BOOL_METRICS, *INTEGER_METRICS)
    }


def aggregate_runs(runs: dict[int, dict[str, Any]]) -> dict[str, int]:
    values = {task_id: run_values(run) for task_id, run in runs.items()}
    return {
        "tasks_run": len(values),
        "exact_sequence": sum(item["exact_sequence"] for item in values.values()),
        "all_expected_called": sum(
            item["all_expected_called"] for item in values.values()
        ),
        "any_expected_called": sum(
            item["any_expected_called"] for item in values.values()
        ),
        "tasks_with_tool_call": sum(
            item["has_tool_call"] for item in values.values()
        ),
        "tasks_with_final_answer": sum(
            item["has_final_answer"] for item in values.values()
        ),
        "tool_call_successes": sum(
            item["call_successes"] for item in values.values()
        ),
        "tool_calls": sum(item["tool_calls"] for item in values.values()),
    }


def run_diagnostics(
    runs: dict[int, dict[str, Any]], summary: dict[str, Any]
) -> dict[str, Any]:
    model_calls = [
        call
        for run in runs.values()
        for call in run.get("model_responses", [])
    ]
    finish_reasons: dict[str, int] = {}
    for call in model_calls:
        reason = call.get("finish_reason") or "not_recorded"
        finish_reasons[reason] = finish_reasons.get(reason, 0) + 1
    return {
        "tasks_with_errors": sum(bool(run.get("errors")) for run in runs.values()),
        "tasks_with_max_rounds": sum(
            "max_rounds_reached" in run.get("errors", []) for run in runs.values()
        ),
        "tasks_with_invalid_action": sum(
            any(str(error).startswith("invalid_action:") for error in run.get("errors", []))
            for run in runs.values()
        ),
        "tool_error_statuses": sum(
            call.get("status") != "ok"
            for run in runs.values()
            for call in run.get("tool_calls", [])
        ),
        "model_calls": summary.get("model_calls"),
        "finish_reasons": finish_reasons,
        "token_usage": summary.get("token_usage"),
        "elapsed_seconds": summary.get("elapsed_seconds"),
    }


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def build_comparison(local_dir: Path, external_dir: Path) -> dict[str, Any]:
    local_runs = load_runs(local_dir)
    external_runs = load_runs(external_dir)
    local_summary = load_summary(local_dir)
    external_summary = load_summary(external_dir)
    task_ids = validate_alignment(local_runs, external_runs)
    local_aggregate = aggregate_runs(local_runs)
    external_aggregate = aggregate_runs(external_runs)
    aggregate_deltas = {
        metric: external_aggregate[metric] - local_aggregate[metric]
        for metric in SUMMARY_METRICS
    }

    tasks = []
    for task_id in task_ids:
        local = run_values(local_runs[task_id])
        external = run_values(external_runs[task_id])
        tasks.append(
            {
                "task_id": task_id,
                "question": local_runs[task_id]["question"],
                "expected_tools": local_runs[task_id]["expected_tools"],
                "local": local,
                "external": external,
                "delta": delta_values(local, external),
            }
        )

    return {
        "schema_version": 1,
        "metrics_scope": METRICS_SCOPE,
        "answer_correctness": ANSWER_CORRECTNESS,
        "grader": GRADER,
        "delta_definition": "external_minus_local",
        "note": "Trajectory metrics only. This report does not measure answer quality.",
        "inputs": {
            "local": {"run_dir": display_path(local_dir)},
            "external": {"run_dir": display_path(external_dir)},
        },
        "models": {
            "local": local_summary.get("model"),
            "external": external_summary.get("model"),
        },
        "external_runtime": {
            "provider": external_summary.get("provider"),
            "endpoint": external_summary.get("endpoint"),
            "request_options": external_summary.get("request_options"),
            "token_usage": external_summary.get("token_usage"),
            "finish_reasons": external_summary.get("finish_reasons"),
        },
        "validation": {
            "task_ids_match": True,
            "questions_match": True,
            "expected_tools_match": True,
            "tasks_validated": len(task_ids),
        },
        "aggregate": {
            "local": local_aggregate,
            "external": external_aggregate,
            "delta": aggregate_deltas,
        },
        "behavior": {
            "local": run_diagnostics(local_runs, local_summary),
            "external": run_diagnostics(external_runs, external_summary),
        },
        "tasks": tasks,
    }


def bool_label(value: bool) -> str:
    return "Y" if value else "N"


def render_markdown(report: dict[str, Any]) -> str:
    local = report["aggregate"]["local"]
    external = report["aggregate"]["external"]
    delta = report["aggregate"]["delta"]
    lines = [
        "# Doc2Agent trajectory comparison",
        "",
        f"Scope: `{report['metrics_scope']}`. Answer quality was not evaluated.",
        f"Delta definition: `{report['delta_definition']}`.",
        f"Local model: `{report['models']['local'] or 'not_recorded'}`.",
        f"External model: `{report['models']['external'] or 'not_recorded'}`.",
        "",
        "## Aggregate",
        "",
        "| Metric | Local | External | Delta |",
        "|---|---:|---:|---:|",
    ]
    for metric in SUMMARY_METRICS:
        lines.append(
            f"| `{metric}` | {local[metric]} | {external[metric]} | "
            f"{delta[metric]:+d} |"
        )
    lines.extend(
        [
            "",
            "## Behavior diagnostics",
            "",
            "| Diagnostic | Local | External |",
            "|---|---:|---:|",
        ]
    )
    for key in (
        "tasks_with_errors",
        "tasks_with_max_rounds",
        "tasks_with_invalid_action",
        "tool_error_statuses",
    ):
        lines.append(
            f"| `{key}` | {report['behavior']['local'][key]} | "
            f"{report['behavior']['external'][key]} |"
        )
    lines.extend(
        [
            "",
            "## Per task",
            "",
            "| Task | Local exact/all/any | External exact/all/any | "
            "Delta exact | Delta all | Delta called | Delta successes |",
            "|---:|---|---|---:|---:|---:|---:|",
        ]
    )
    for task in report["tasks"]:
        local_task = task["local"]
        external_task = task["external"]
        task_delta = task["delta"]
        lines.append(
            f"| {task['task_id']} | "
            f"{bool_label(local_task['exact_sequence'])}/"
            f"{bool_label(local_task['all_expected_called'])}/"
            f"{bool_label(local_task['any_expected_called'])} | "
            f"{bool_label(external_task['exact_sequence'])}/"
            f"{bool_label(external_task['all_expected_called'])}/"
            f"{bool_label(external_task['any_expected_called'])} | "
            f"{task_delta['exact_sequence']:+d} | "
            f"{task_delta['all_expected_called']:+d} | "
            f"{task_delta['called_steps']:+d} | "
            f"{task_delta['call_successes']:+d} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_reports(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL)
    parser.add_argument("--external-dir", type=Path, default=DEFAULT_EXTERNAL)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    report = build_comparison(args.local_dir, args.external_dir)
    write_reports(report, args.json_out, args.md_out)
    print(
        json.dumps(
            {
                "status": "PASS",
                "tasks_validated": report["validation"]["tasks_validated"],
                "aggregate_delta": report["aggregate"]["delta"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
