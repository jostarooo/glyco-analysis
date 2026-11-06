"""Compare two Doc2Agent local evidence-grounded answer grade directories."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from grade_doc2agent_answers import (
    ROOT,
    STATUSES,
    aggregate_grade_metrics,
    dumps_json,
    write_text_if_changed,
)


DEFAULT_LOCAL = ROOT / "reports" / "w3_day3" / "answer_grades" / "f3_qwen3_4b_50"
DEFAULT_EXTERNAL = ROOT / "reports" / "w3_day3" / "answer_grades" / "f3_glm53_50"
DEFAULT_JSON_OUT = ROOT / "reports" / "w3_day3" / "answer_grade_comparison.json"
DEFAULT_MD_OUT = ROOT / "reports" / "w3_day3" / "answer_grade_comparison.md"
COMPARISON_SCOPE = "local_evidence_grading"


@dataclass(frozen=True)
class LoadedGradeRun:
    summary: dict[str, Any]
    grades: dict[int, dict[str, Any]]
    metrics: dict[str, Any]


def load_grade_run(path: Path) -> LoadedGradeRun:
    summary_path = path / "summary.json"
    if not summary_path.is_file():
        raise ValueError(f"Missing summary: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError(f"Summary is not an object: {summary_path}")
    if summary.get("task_ids") != list(range(1, 51)):
        raise ValueError(f"Summary task_ids must be exactly 1..50 in {path}")
    grades: dict[int, dict[str, Any]] = {}
    for grade_path in sorted(path.glob("task_*.json")):
        grade = json.loads(grade_path.read_text(encoding="utf-8"))
        if not isinstance(grade, dict):
            raise ValueError(f"Grade is not an object: {grade_path}")
        task_id = int(grade["task_id"])
        if task_id in grades:
            raise ValueError(f"Duplicate task_id {task_id} in {path}")
        if grade.get("rubric_sha256") != summary.get("rubric_sha256"):
            raise ValueError(f"Rubric differs in {grade_path}")
        if (
            grade.get("prompt_template_sha256")
            != summary.get("prompt_template_sha256")
        ):
            raise ValueError(f"Prompt template differs in {grade_path}")
        if grade.get("judge_model_config") != summary.get("judge_model_config"):
            raise ValueError(f"Judge config differs in {grade_path}")
        if (
            grade.get("source_hashes", {}).get("tasks_file_sha256")
            != summary.get("source", {}).get("tasks_file_sha256")
        ):
            raise ValueError(f"Task source hash differs in {grade_path}")
        grades[task_id] = grade
    if sorted(grades) != list(range(1, 51)):
        raise ValueError(
            f"Grade task ids must be exactly 1..50 in {path}; got {sorted(grades)}"
        )
    metrics = aggregate_grade_metrics(grades.values())
    for key, value in metrics.items():
        if summary.get(key) != value:
            raise ValueError(f"Summary {key} differs from task grades in {path}")
    return LoadedGradeRun(summary=summary, grades=grades, metrics=metrics)


def validate_same_grading_contract(
    local: LoadedGradeRun, external: LoadedGradeRun
) -> None:
    if local.summary.get("rubric_sha256") != external.summary.get("rubric_sha256"):
        raise ValueError("Rubric differs between grade directories")
    if local.summary.get("rubric_version") != external.summary.get("rubric_version"):
        raise ValueError("Rubric version differs between grade directories")
    if local.summary.get("prompt_template_sha256") != external.summary.get(
        "prompt_template_sha256"
    ):
        raise ValueError("Prompt template differs between grade directories")
    if local.summary.get("judge_model_config") != external.summary.get(
        "judge_model_config"
    ):
        raise ValueError("Judge config differs between grade directories")
    if local.summary.get("source", {}).get("tasks_file_sha256") != external.summary.get(
        "source", {}
    ).get("tasks_file_sha256"):
        raise ValueError("Task source file differs between grade directories")


def build_comparison(local_dir: Path, external_dir: Path) -> dict[str, Any]:
    local = load_grade_run(local_dir)
    external = load_grade_run(external_dir)
    validate_same_grading_contract(local, external)
    task_ids = sorted(local.grades)
    if task_ids != sorted(external.grades):
        raise ValueError("Task ids differ between grade directories")

    status_delta = {
        status: external.metrics["status_counts"][status]
        - local.metrics["status_counts"][status]
        for status in STATUSES
    }
    tasks = []
    disagreement_count = 0
    for task_id in task_ids:
        local_grade = local.grades[task_id]
        external_grade = external.grades[task_id]
        local_task_hash = local_grade["source_hashes"]["authoritative_task_sha256"]
        external_task_hash = external_grade["source_hashes"][
            "authoritative_task_sha256"
        ]
        if local_task_hash != external_task_hash:
            raise ValueError(f"Task definition differs for task_id {task_id}")
        same_status = local_grade["status"] == external_grade["status"]
        disagreement_count += int(not same_status)
        tasks.append(
            {
                "task_id": task_id,
                "local_status": local_grade["status"],
                "external_status": external_grade["status"],
                "same_status": same_status,
                "local_reason_codes": local_grade["reason_codes"],
                "external_reason_codes": external_grade["reason_codes"],
            }
        )

    return {
        "schema_version": 1,
        "comparison_scope": COMPARISON_SCOPE,
        "upstream_gpt4o_equivalent": False,
        "interpretation": (
            "Local evidence-grounded judging only. This is not the upstream "
            "GPT-4o grader, and status differences do not establish a model-size "
            "effect or any other causal attribution."
        ),
        "rubric_version": local.summary.get("rubric_version"),
        "rubric_sha256": local.summary.get("rubric_sha256"),
        "prompt_template_sha256": local.summary.get("prompt_template_sha256"),
        "judge_model_config": local.summary.get("judge_model_config"),
        "validation": {
            "same_rubric": True,
            "same_prompt_template": True,
            "same_judge_config": True,
            "same_task_set": True,
            "tasks_compared": len(task_ids),
            "status_disagreement_count": disagreement_count,
        },
        "runs": {
            "local": {
                "run_id": local.summary.get("run_id"),
                **local.metrics,
            },
            "external": {
                "run_id": external.summary.get("run_id"),
                **external.metrics,
            },
        },
        "status_delta_external_minus_local": status_delta,
        "tasks": tasks,
    }


def render_markdown(report: dict[str, Any]) -> str:
    local = report["runs"]["local"]
    external = report["runs"]["external"]
    lines = [
        "# Doc2Agent answer-grade comparison",
        "",
        "This report uses local evidence-grounded judging.",
        "It is not equivalent to the upstream GPT-4o grader.",
        "Status differences are not evidence of a model-size effect or another cause.",
        "",
        f"Scope: `{report['comparison_scope']}`.",
        f"Upstream GPT-4o equivalent: `{str(report['upstream_gpt4o_equivalent']).lower()}`.",
        f"Judge: `{report['judge_model_config']['model']}`.",
        "",
        "## Summary",
        "",
        "| Metric | Local | External | Delta |",
        "|---|---:|---:|---:|",
    ]
    for metric in ("task_count", "graded_correct", "graded_incorrect"):
        lines.append(
            f"| `{metric}` | {local[metric]} | {external[metric]} | "
            f"{external[metric] - local[metric]:+d} |"
        )
    for status in STATUSES:
        lines.append(
            f"| `status:{status}` | {local['status_counts'][status]} | "
            f"{external['status_counts'][status]} | "
            f"{report['status_delta_external_minus_local'][status]:+d} |"
        )
    lines.extend(
        [
            "",
            "## Graded metrics",
            "",
            "| Metric | Local | External |",
            "|---|---|---|",
        ]
    )
    for metric in ("graded_accuracy", "graded_coverage", "answer_available_rate"):
        lines.append(
            f"| `{metric}` | {format_ratio(local[metric])} | "
            f"{format_ratio(external[metric])} |"
        )
    lines.extend(
        [
            "",
            "## Task statuses",
            "",
            "| Task | Local | External | Same |",
            "|---:|---|---|---|",
        ]
    )
    for task in report["tasks"]:
        lines.append(
            f"| {task['task_id']} | `{task['local_status']}` | "
            f"`{task['external_status']}` | "
            f"{'Y' if task['same_status'] else 'N'} |"
        )
    lines.append("")
    return "\n".join(lines)


def format_ratio(metric: dict[str, Any]) -> str:
    value = metric["value"]
    if value is None:
        return f"{metric['numerator']}/{metric['denominator']} (undefined)"
    return f"{metric['numerator']}/{metric['denominator']} ({value:.6f})"


def write_reports(
    report: dict[str, Any], json_out: Path, markdown_out: Path
) -> None:
    write_text_if_changed(json_out, dumps_json(report))
    write_text_if_changed(markdown_out, render_markdown(report))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL)
    parser.add_argument("--external-dir", type=Path, default=DEFAULT_EXTERNAL)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD_OUT)
    args = parser.parse_args(argv)
    try:
        report = build_comparison(args.local_dir, args.external_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(
            json.dumps(
                {"status": "FAIL", "errors": [str(exc)]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    write_reports(report, args.json_out, args.md_out)
    print(
        json.dumps(
            {
                "status": "PASS",
                "comparison_scope": report["comparison_scope"],
                "upstream_gpt4o_equivalent": report[
                    "upstream_gpt4o_equivalent"
                ],
                "tasks_compared": report["validation"]["tasks_compared"],
                "status_disagreement_count": report["validation"][
                    "status_disagreement_count"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
