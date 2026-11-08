"""Build a deterministic three-model Doc2Agent report from one manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TASK_IDS = tuple(range(1, 51))
PROMPT_HASH_KEYS = ("system", "user_template", "tool_catalog")
GRADE_STATUSES = (
    "correct",
    "incorrect",
    "manual_review",
    "missing_answer",
    "invalid_trace",
    "judge_unavailable",
)
TRAJECTORY_KEYS = (
    "tasks_run",
    "exact_sequence",
    "all_expected_called",
    "any_expected_called",
    "tasks_with_tool_call",
    "tasks_with_final_answer",
    "tool_call_successes",
    "tool_calls",
)
ANSWER_GRADE_COUNT_KEYS = (
    "task_count",
    "graded_correct",
    "graded_incorrect",
)
ANSWER_GRADE_RATIO_KEYS = (
    "graded_accuracy",
    "graded_coverage",
    "correct_over_task_count",
    "answer_available_rate",
)


class ReportError(ValueError):
    """A deterministic report input or contract error."""


@dataclass(frozen=True)
class SourceRef:
    path: str
    sha256: str
    file_count: int | None = None

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "path": self.path,
            "sha256": self.sha256,
        }
        if self.file_count is not None:
            value["file_count"] = self.file_count
        return value


@dataclass(frozen=True)
class ModelSnapshot:
    key: str
    label: str
    provider: str
    model: str
    run_summary: dict[str, Any]
    grade_summary: dict[str, Any]
    run_tasks: dict[int, dict[str, Any]]
    grade_tasks: dict[int, dict[str, Any]]
    prompt_provenance: dict[str, Any]
    sources: dict[str, dict[str, Any]]
    trajectory: dict[str, int]
    diagnostics: dict[str, Any]
    answer_grade: dict[str, Any]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ReportError(f"missing {label}: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReportError(f"invalid {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReportError(f"{label} must be a JSON object: {path}")
    return value


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _resolve_manifest_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ReportError(f"{label} must be a non-empty path string")
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReportError(f"{label} must be a non-empty string")
    return value


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReportError(f"{label} must be a JSON object")
    return value


def _require_task_payloads(directory: Path, label: str) -> tuple[
    dict[int, dict[str, Any]], dict[str, Any]
]:
    expected_names = {
        f"task_{task_id:02d}.json": task_id for task_id in EXPECTED_TASK_IDS
    }
    paths = sorted(directory.glob("task_*.json"))
    actual_names = {path.name: path for path in paths}
    missing = sorted(set(expected_names) - set(actual_names))
    extra = sorted(set(actual_names) - set(expected_names))
    if missing or extra:
        raise ReportError(
            f"{label} task files must be exactly task_01..task_50; "
            f"missing={missing}, extra={extra}"
        )

    tasks: dict[int, dict[str, Any]] = {}
    entries: list[dict[str, str]] = []
    for name, task_id in sorted(expected_names.items(), key=lambda item: item[1]):
        path = actual_names[name]
        payload = _load_json_object(path, f"{label} {name}")
        record_id = payload.get("task_id", task_id)
        if isinstance(record_id, bool) or not isinstance(record_id, int):
            raise ReportError(f"{label} {name}: task_id must be an integer")
        if record_id != task_id:
            raise ReportError(
                f"{label} {name}: task_id {record_id} does not match filename"
            )
        tasks[task_id] = payload
        entries.append({"path": name, "sha256": _file_sha256(path)})

    aggregate = {
        "path": _display_path(directory),
        "sha256": _sha256_text(_canonical_json(entries)),
        "file_count": len(entries),
        "aggregate_method": (
            "sha256 of canonical JSON list of task filename and SHA256 pairs"
        ),
    }
    return tasks, aggregate


def _validate_run_task(task_id: int, task: dict[str, Any], label: str) -> None:
    prefix = f"{label} task {task_id:02d}"
    question = task.get("question")
    if not isinstance(question, str) or not question:
        raise ReportError(f"{prefix}: question must be a non-empty string")
    expected_tools = task.get("expected_tools")
    if not isinstance(expected_tools, list) or not all(
        isinstance(item, str) and item for item in expected_tools
    ):
        raise ReportError(f"{prefix}: expected_tools must be a string list")
    if not isinstance(task.get("tool_calls"), list):
        raise ReportError(f"{prefix}: tool_calls must be a list")
    if not isinstance(task.get("errors"), list):
        raise ReportError(f"{prefix}: errors must be a list")
    if not isinstance(task.get("final_answer"), str):
        raise ReportError(f"{prefix}: final_answer must be a string")
    for key in (
        "exact_sequence",
        "all_expected_called",
        "any_expected_called",
    ):
        if not isinstance(task.get(key), bool):
            raise ReportError(f"{prefix}: {key} must be boolean")
    for index, call in enumerate(task["tool_calls"], start=1):
        if not isinstance(call, dict):
            raise ReportError(f"{prefix}: tool call {index} must be an object")
        if not isinstance(call.get("tool"), str):
            raise ReportError(f"{prefix}: tool call {index} tool must be a string")
        if not isinstance(call.get("status"), str):
            raise ReportError(
                f"{prefix}: tool call {index} status must be a string"
            )


def _trajectory_metrics(tasks: dict[int, dict[str, Any]]) -> dict[str, int]:
    return {
        "tasks_run": len(tasks),
        "exact_sequence": sum(bool(task["exact_sequence"]) for task in tasks.values()),
        "all_expected_called": sum(
            bool(task["all_expected_called"]) for task in tasks.values()
        ),
        "any_expected_called": sum(
            bool(task["any_expected_called"]) for task in tasks.values()
        ),
        "tasks_with_tool_call": sum(bool(task["tool_calls"]) for task in tasks.values()),
        "tasks_with_final_answer": sum(
            bool(task["final_answer"]) for task in tasks.values()
        ),
        "tool_call_successes": sum(
            call.get("status") == "ok"
            for task in tasks.values()
            for call in task["tool_calls"]
        ),
        "tool_calls": sum(len(task["tool_calls"]) for task in tasks.values()),
    }


def _validate_recorded_counts(
    summary: dict[str, Any],
    recomputed: dict[str, int],
    label: str,
) -> None:
    for key in TRAJECTORY_KEYS:
        if key not in summary:
            raise ReportError(f"{label} summary is missing {key}")
        if summary[key] != recomputed[key]:
            raise ReportError(
                f"{label} summary {key} is {summary[key]!r}; "
                f"recomputed {recomputed[key]!r}"
            )


def _diagnostics(
    tasks: dict[int, dict[str, Any]], summary: dict[str, Any]
) -> dict[str, Any]:
    finish_reasons = summary.get("finish_reasons")
    if not isinstance(finish_reasons, dict):
        finish_reasons = {}
        for task in tasks.values():
            for call in task.get("model_responses", []):
                reason = call.get("finish_reason") or "not_recorded"
                finish_reasons[reason] = finish_reasons.get(reason, 0) + 1
    normalized_finish_reasons = {
        str(reason): int(count)
        for reason, count in sorted(finish_reasons.items())
    }

    model_calls = summary.get("model_calls")
    if model_calls is None:
        if any("model_responses" in task for task in tasks.values()):
            model_calls = sum(
                len(task.get("model_responses", [])) for task in tasks.values()
            )
    if model_calls is not None and (
        isinstance(model_calls, bool) or not isinstance(model_calls, int)
    ):
        raise ReportError("run summary model_calls must be an integer")

    token_usage = summary.get("token_usage")
    if token_usage is not None and not isinstance(token_usage, dict):
        raise ReportError("run summary token_usage must be an object")
    elapsed_seconds = summary.get("elapsed_seconds")
    if elapsed_seconds is not None and (
        isinstance(elapsed_seconds, bool)
        or not isinstance(elapsed_seconds, (int, float))
    ):
        raise ReportError("run summary elapsed_seconds must be numeric")

    return {
        "tasks_with_errors": sum(bool(task.get("errors")) for task in tasks.values()),
        "tasks_with_max_rounds": sum(
            "max_rounds_reached" in task.get("errors", [])
            for task in tasks.values()
        ),
        "tasks_with_invalid_action": sum(
            any(
                str(error).startswith("invalid_action:")
                for error in task.get("errors", [])
            )
            for task in tasks.values()
        ),
        "tool_error_statuses": sum(
            call.get("status") != "ok"
            for task in tasks.values()
            for call in task["tool_calls"]
        ),
        "model_calls": model_calls,
        "finish_reasons": normalized_finish_reasons,
        "token_usage": token_usage,
        "elapsed_seconds": elapsed_seconds,
    }


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": round(numerator / denominator, 6) if denominator else None,
    }


def _answer_grade_metrics(
    tasks: dict[int, dict[str, Any]], label: str
) -> dict[str, Any]:
    status_counts = {status: 0 for status in GRADE_STATUSES}
    answer_available = 0
    for task_id, task in tasks.items():
        status = task.get("status")
        if status not in status_counts:
            raise ReportError(
                f"{label} task {task_id:02d}: invalid grade status {status!r}"
            )
        status_counts[status] += 1
        evidence = task.get("evidence_audit")
        if not isinstance(evidence, dict) or not isinstance(
            evidence.get("has_final_answer"), bool
        ):
            raise ReportError(
                f"{label} task {task_id:02d}: evidence_audit.has_final_answer "
                "must be boolean"
            )
        answer_available += int(evidence["has_final_answer"])

    total = len(tasks)
    graded_correct = status_counts["correct"]
    graded_incorrect = status_counts["incorrect"]
    graded_total = graded_correct + graded_incorrect
    return {
        "task_count": total,
        "status_counts": status_counts,
        "graded_correct": graded_correct,
        "graded_incorrect": graded_incorrect,
        "graded_accuracy": _ratio(graded_correct, graded_total),
        "graded_coverage": _ratio(graded_total, total),
        "correct_over_task_count": _ratio(graded_correct, total),
        "answer_available_rate": _ratio(answer_available, total),
    }


def _validate_grade_summary(
    summary: dict[str, Any],
    recomputed: dict[str, Any],
    label: str,
) -> None:
    if summary.get("task_count") != 50:
        raise ReportError(f"{label} summary task_count must be 50")
    if summary.get("task_ids") != list(EXPECTED_TASK_IDS):
        raise ReportError(f"{label} summary task_ids must be exactly 1..50")
    for key in ANSWER_GRADE_COUNT_KEYS:
        if summary.get(key) != recomputed[key]:
            raise ReportError(
                f"{label} summary {key} is {summary.get(key)!r}; "
                f"recomputed {recomputed[key]!r}"
            )
    if summary.get("status_counts") != recomputed["status_counts"]:
        raise ReportError(f"{label} summary status_counts do not match task grades")
    for key in ANSWER_GRADE_RATIO_KEYS:
        if summary.get(key) != recomputed[key]:
            raise ReportError(
                f"{label} summary {key} does not match task grades"
            )


def _grade_source_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ReportError(f"{label} must be a 64-character SHA256 string")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ReportError(f"{label} must be hexadecimal") from exc
    return value


def _validate_grade_task(
    *,
    task_id: int,
    task: dict[str, Any],
    run_task_path: Path,
    run_summary_sha256: str,
    grade_summary: dict[str, Any],
    label: str,
) -> None:
    prefix = f"{label} task {task_id:02d}"
    for key in (
        "rubric_sha256",
        "rubric_version",
        "prompt_template_sha256",
        "judge_model_config",
    ):
        if task.get(key) != grade_summary.get(key):
            raise ReportError(f"{prefix}: {key} does not match grade summary")
    source_hashes = task.get("source_hashes")
    if not isinstance(source_hashes, dict):
        raise ReportError(f"{prefix}: source_hashes must be an object")
    if source_hashes.get("run_summary_sha256") != run_summary_sha256:
        raise ReportError(
            f"{prefix}: run_summary_sha256 does not match actual run summary"
        )
    if source_hashes.get("run_task_sha256") != _file_sha256(run_task_path):
        raise ReportError(f"{prefix}: run_task_sha256 does not match run task")
    summary_tasks_sha = grade_summary.get("source", {}).get("tasks_file_sha256")
    if source_hashes.get("tasks_file_sha256") != summary_tasks_sha:
        raise ReportError(
            f"{prefix}: tasks_file_sha256 does not match grade summary"
        )
    _grade_source_hash(
        source_hashes.get("authoritative_task_sha256"),
        f"{prefix} authoritative_task_sha256",
    )


def _validate_prompt_hashes(value: Any, label: str) -> dict[str, str]:
    hashes = _require_dict(value, label)
    result: dict[str, str] = {}
    for key in PROMPT_HASH_KEYS:
        result[key] = _grade_source_hash(hashes.get(key), f"{label}.{key}")
    return result


def _load_sidecar(
    entry: dict[str, Any], model_key: str
) -> tuple[dict[str, str], dict[str, Any], SourceRef] | None:
    raw_path = entry.get("provenance_sidecar")
    if raw_path is None:
        return None
    path = _resolve_manifest_path(raw_path, f"{model_key}.provenance_sidecar")
    payload = _load_json_object(path, f"{model_key} provenance sidecar")
    hashes = _validate_prompt_hashes(
        payload.get("prompt_hashes"), f"{model_key} sidecar prompt_hashes"
    )
    _require_string(
        payload.get("verification_method"),
        f"{model_key} sidecar verification_method",
    )
    runtime_recorded = payload.get("runtime_recorded", False)
    if not isinstance(runtime_recorded, bool):
        raise ReportError(
            f"{model_key} sidecar runtime_recorded must be boolean"
        )
    source = SourceRef(
        path=_display_path(path),
        sha256=_file_sha256(path),
    )
    return hashes, payload, source


def _prompt_provenance(
    entry: dict[str, Any],
    model_key: str,
    run_summary: dict[str, Any],
    run_summary_source: SourceRef,
) -> dict[str, Any]:
    sidecar = _load_sidecar(entry, model_key)
    runtime_hashes = run_summary.get("prompt_hashes")
    if runtime_hashes is not None:
        hashes = _validate_prompt_hashes(
            runtime_hashes, f"{model_key} runtime prompt_hashes"
        )
        provenance: dict[str, Any] = {
            "verification_method": "runtime_recorded",
            "runtime_recorded": True,
            "prompt_hashes": hashes,
            "source": run_summary_source.as_dict(),
        }
        if sidecar is not None:
            sidecar_hashes, _, source = sidecar
            if sidecar_hashes != hashes:
                raise ReportError(
                    f"{model_key}: sidecar prompt hashes differ from runtime hashes"
                )
            provenance["sidecar"] = source.as_dict()
        return provenance

    if sidecar is None:
        raise ReportError(
            f"{model_key}: prompt provenance missing; expected run summary "
            "prompt_hashes or a manifest provenance_sidecar"
        )
    hashes, payload, source = sidecar
    runtime_recorded = payload.get("runtime_recorded", False)
    return {
        "verification_method": _require_string(
            payload.get("verification_method"),
            f"{model_key} sidecar verification_method",
        ),
        "runtime_recorded": runtime_recorded,
        "prompt_hashes": hashes,
        "source": source.as_dict(),
        "historical_facts": payload.get("historical_facts"),
    }


def _task_trajectory(task: dict[str, Any]) -> dict[str, Any]:
    tool_calls = task["tool_calls"]
    return {
        "exact_sequence": bool(task["exact_sequence"]),
        "all_expected_called": bool(task["all_expected_called"]),
        "any_expected_called": bool(task["any_expected_called"]),
        "called_steps": int(task.get("called_steps", len(tool_calls))),
        "call_successes": sum(call.get("status") == "ok" for call in tool_calls),
        "tool_calls": len(tool_calls),
        "has_tool_call": bool(tool_calls),
        "has_final_answer": bool(task["final_answer"]),
        "called_tools": [str(call.get("tool", "")) for call in tool_calls],
    }


def _load_snapshot(entry: dict[str, Any]) -> ModelSnapshot:
    key = _require_string(entry.get("key"), "model key")
    label = _require_string(entry.get("label"), f"{key}.label")
    run_dir = _resolve_manifest_path(entry.get("run_dir"), f"{key}.run_dir")
    grade_dir = _resolve_manifest_path(entry.get("grade_dir"), f"{key}.grade_dir")
    run_summary_path = run_dir / "summary.json"
    grade_summary_path = grade_dir / "summary.json"
    run_summary = _load_json_object(run_summary_path, f"{key} run summary")
    grade_summary = _load_json_object(grade_summary_path, f"{key} grade summary")
    run_tasks, run_tasks_source = _require_task_payloads(run_dir, f"{key} run")
    grade_tasks, grade_tasks_source = _require_task_payloads(
        grade_dir, f"{key} grade"
    )
    for task_id, task in run_tasks.items():
        _validate_run_task(task_id, task, f"{key} run")

    trajectory = _trajectory_metrics(run_tasks)
    _validate_recorded_counts(run_summary, trajectory, f"{key} run")
    answer_grade = _answer_grade_metrics(grade_tasks, f"{key} grade")
    _validate_grade_summary(grade_summary, answer_grade, f"{key} grade")

    run_summary_sha = _file_sha256(run_summary_path)
    grade_source = grade_summary.get("source")
    if not isinstance(grade_source, dict):
        raise ReportError(f"{key} grade summary source must be an object")
    if grade_source.get("run_summary_sha256") != run_summary_sha:
        raise ReportError(
            f"{key} grade summary run_summary_sha256 does not match actual "
            "run summary"
        )
    _grade_source_hash(
        grade_source.get("tasks_file_sha256"),
        f"{key} grade summary tasks_file_sha256",
    )
    for task_id, task in grade_tasks.items():
        _validate_grade_task(
            task_id=task_id,
            task=task,
            run_task_path=run_dir / f"task_{task_id:02d}.json",
            run_summary_sha256=run_summary_sha,
            grade_summary=grade_summary,
            label=f"{key} grade",
        )

    provider = run_summary.get("provider", entry.get("provider"))
    model = run_summary.get("model", entry.get("model"))
    provider = _require_string(provider, f"{key} provider")
    model = _require_string(model, f"{key} model")
    if entry.get("provider") not in (None, provider):
        raise ReportError(f"{key}: manifest provider differs from run summary")
    if entry.get("model") not in (None, model):
        raise ReportError(f"{key}: manifest model differs from run summary")

    run_summary_source = SourceRef(
        path=_display_path(run_summary_path),
        sha256=run_summary_sha,
    )
    prompt_provenance = _prompt_provenance(
        entry, key, run_summary, run_summary_source
    )
    sources = {
        "run_summary": run_summary_source.as_dict(),
        "run_tasks": run_tasks_source,
        "grade_summary": SourceRef(
            path=_display_path(grade_summary_path),
            sha256=_file_sha256(grade_summary_path),
        ).as_dict(),
        "grade_tasks": grade_tasks_source,
    }
    if "sidecar" in prompt_provenance:
        sources["provenance_sidecar"] = prompt_provenance["sidecar"]
    elif prompt_provenance["verification_method"] != "runtime_recorded":
        sidecar_source = prompt_provenance.get("source")
        if isinstance(sidecar_source, dict):
            sources["provenance_sidecar"] = sidecar_source

    return ModelSnapshot(
        key=key,
        label=label,
        provider=provider,
        model=model,
        run_summary=run_summary,
        grade_summary=grade_summary,
        run_tasks=run_tasks,
        grade_tasks=grade_tasks,
        prompt_provenance=prompt_provenance,
        sources=sources,
        trajectory=trajectory,
        diagnostics=_diagnostics(run_tasks, run_summary),
        answer_grade=answer_grade,
    )


def _load_manifest(manifest_path: Path) -> tuple[str, list[dict[str, Any]]]:
    manifest = _load_json_object(manifest_path, "manifest")
    if manifest.get("schema_version") != 1:
        raise ReportError("manifest schema_version must be 1")
    entries = manifest.get("models")
    if not isinstance(entries, list):
        raise ReportError("manifest models must be a list")
    if len(entries) != 3:
        raise ReportError(f"manifest must contain exactly 3 models; got {len(entries)}")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ReportError(f"manifest models[{index}] must be an object")
        key = _require_string(entry.get("key"), f"manifest models[{index}].key")
        if key in seen:
            raise ReportError(f"duplicate model key: {key}")
        seen.add(key)
        normalized.append(entry)
    reference = _require_string(
        manifest.get("reference_model"), "manifest reference_model"
    )
    if reference not in seen:
        raise ReportError(
            f"reference_model {reference!r} is not present in models"
        )
    return reference, normalized


def _validate_alignment(snapshots: list[ModelSnapshot]) -> None:
    baseline = snapshots[0]
    for task_id in EXPECTED_TASK_IDS:
        expected = baseline.run_tasks[task_id]
        expected_task_hash = baseline.grade_tasks[task_id]["source_hashes"][
            "authoritative_task_sha256"
        ]
        for snapshot in snapshots[1:]:
            task = snapshot.run_tasks[task_id]
            if task.get("question") != expected.get("question"):
                raise ReportError(
                    f"question differs for task {task_id:02d} in "
                    f"{snapshot.key} versus {baseline.key}"
                )
            if task.get("expected_tools") != expected.get("expected_tools"):
                raise ReportError(
                    f"expected_tools differ for task {task_id:02d} in "
                    f"{snapshot.key} versus {baseline.key}"
                )
            task_hash = snapshot.grade_tasks[task_id]["source_hashes"][
                "authoritative_task_sha256"
            ]
            if task_hash != expected_task_hash:
                raise ReportError(
                    f"authoritative task hash differs for task {task_id:02d} "
                    f"in {snapshot.key} versus {baseline.key}"
                )


def _aligned_optional_field(
    snapshots: list[ModelSnapshot], field: str
) -> int | None:
    values: list[tuple[str, Any]] = [
        (snapshot.key, snapshot.run_summary.get(field))
        for snapshot in snapshots
        if field in snapshot.run_summary
    ]
    if not values:
        return None
    if len(values) != len(snapshots):
        missing = [snapshot.key for snapshot in snapshots if field not in snapshot.run_summary]
        raise ReportError(f"{field} is missing for models: {missing}")
    distinct = {value for _, value in values}
    if len(distinct) != 1:
        detail = {key: value for key, value in values}
        raise ReportError(f"{field} differs across models: {detail}")
    value = values[0][1]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReportError(f"{field} must be an integer")
    return value


def _validate_grade_contract(snapshots: list[ModelSnapshot]) -> None:
    baseline = snapshots[0].grade_summary
    for field in (
        "rubric_sha256",
        "rubric_version",
        "prompt_template_sha256",
        "judge_model_config",
    ):
        expected = baseline.get(field)
        for snapshot in snapshots[1:]:
            if snapshot.grade_summary.get(field) != expected:
                raise ReportError(
                    f"grade {field} differs in {snapshot.key} versus "
                    f"{snapshots[0].key}"
                )
    expected_tasks_sha = baseline.get("source", {}).get("tasks_file_sha256")
    for snapshot in snapshots[1:]:
        tasks_sha = snapshot.grade_summary.get("source", {}).get(
            "tasks_file_sha256"
        )
        if tasks_sha != expected_tasks_sha:
            raise ReportError(
                f"authoritative tasks file hash differs in {snapshot.key} "
                f"versus {snapshots[0].key}"
            )


def _validate_prompt_contract(snapshots: list[ModelSnapshot]) -> dict[str, str]:
    baseline = snapshots[0].prompt_provenance["prompt_hashes"]
    for snapshot in snapshots[1:]:
        hashes = snapshot.prompt_provenance["prompt_hashes"]
        if hashes != baseline:
            raise ReportError(
                f"prompt hash contract differs in {snapshot.key} versus "
                f"{snapshots[0].key}"
            )
    return dict(baseline)


def _answer_grade_delta(
    reference: dict[str, Any], model: dict[str, Any]
) -> dict[str, Any]:
    return {
        "status_counts": {
            status: model["status_counts"][status]
            - reference["status_counts"][status]
            for status in GRADE_STATUSES
        },
        **{
            key: model[key] - reference[key]
            for key in ANSWER_GRADE_COUNT_KEYS
        },
        **{
            key: (
                model[key]["value"] - reference[key]["value"]
                if reference[key]["value"] is not None
                and model[key]["value"] is not None
                else None
            )
            for key in ANSWER_GRADE_RATIO_KEYS
        },
    }


def _trajectory_delta(
    reference: dict[str, int], model: dict[str, int]
) -> dict[str, int]:
    return {key: model[key] - reference[key] for key in TRAJECTORY_KEYS}


def _build_task_rows(snapshots: list[ModelSnapshot], reference: str) -> list[dict[str, Any]]:
    reference_snapshot = next(
        snapshot for snapshot in snapshots if snapshot.key == reference
    )
    rows: list[dict[str, Any]] = []
    for task_id in EXPECTED_TASK_IDS:
        baseline = reference_snapshot.run_tasks[task_id]
        by_model: dict[str, Any] = {}
        for snapshot in snapshots:
            values = _task_trajectory(snapshot.run_tasks[task_id])
            baseline_values = _task_trajectory(baseline)
            by_model[snapshot.key] = {
                "trajectory": values,
                "answer_grade": {
                    "status": snapshot.grade_tasks[task_id]["status"],
                    "reason_codes": list(
                        snapshot.grade_tasks[task_id].get("reason_codes", [])
                    ),
                },
                "delta_vs_reference": {
                    "reference_model": reference,
                    "trajectory": {
                        key: values[key] - baseline_values[key]
                        for key in (
                            "exact_sequence",
                            "all_expected_called",
                            "any_expected_called",
                            "called_steps",
                            "call_successes",
                            "tool_calls",
                        )
                    },
                },
            }
        rows.append(
            {
                "task_id": task_id,
                "question": baseline["question"],
                "expected_tools": list(baseline["expected_tools"]),
                "by_model": by_model,
            }
        )
    return rows


def build_report(manifest_path: Path) -> dict[str, Any]:
    reference, entries = _load_manifest(manifest_path)
    snapshots = [_load_snapshot(entry) for entry in entries]
    reference_snapshot = next(
        snapshot for snapshot in snapshots if snapshot.key == reference
    )
    _validate_alignment(snapshots)
    max_rounds = _aligned_optional_field(snapshots, "max_rounds")
    tools_available = _aligned_optional_field(snapshots, "tools_available")
    _validate_grade_contract(snapshots)
    prompt_hashes = _validate_prompt_contract(snapshots)

    models: list[dict[str, Any]] = []
    for snapshot in snapshots:
        models.append(
            {
                "key": snapshot.key,
                "label": snapshot.label,
                "provider": snapshot.provider,
                "model": snapshot.model,
                "prompt_provenance": snapshot.prompt_provenance,
                "sources": snapshot.sources,
                "trajectory": snapshot.trajectory,
                "diagnostics": snapshot.diagnostics,
                "answer_grade": snapshot.answer_grade,
                "delta_vs_reference": {
                    "reference_model": reference,
                    "trajectory": _trajectory_delta(
                        reference_snapshot.trajectory, snapshot.trajectory
                    ),
                    "answer_grade": _answer_grade_delta(
                        reference_snapshot.answer_grade, snapshot.answer_grade
                    ),
                },
            }
        )

    baseline_grade = reference_snapshot.grade_summary
    return {
        "schema_version": 1,
        "scope": "f3_three_model",
        "reference_model": reference,
        "upstream_gpt4o_equivalent": False,
        "judge_model_config": baseline_grade.get("judge_model_config"),
        "validation": {
            "model_count": len(snapshots),
            "tasks_per_model": len(EXPECTED_TASK_IDS),
            "questions_match": True,
            "expected_tools_match": True,
            "authoritative_task_hashes_match": True,
            "max_rounds": max_rounds,
            "tools_available": tools_available,
            "same_rubric": True,
            "same_rubric_version": True,
            "same_prompt_template": True,
            "same_judge_config": True,
            "same_tasks_file": True,
            "run_summary_sha_matches_grade": True,
            "grade_summary_recomputed": True,
            "prompt_contract_match": True,
            "prompt_hashes": prompt_hashes,
            "delta_definition": "model_minus_reference_model",
            "reference_model": reference,
        },
        "models": models,
        "tasks": _build_task_rows(snapshots, reference),
    }


def _format_ratio(metric: dict[str, Any]) -> str:
    value = metric.get("value")
    if value is None:
        return f"{metric['numerator']}/{metric['denominator']}（未定义）"
    return f"{metric['numerator']}/{metric['denominator']} ({value:.6f})"


def _format_delta(value: Any) -> str:
    if value is None:
        return "不适用"
    if isinstance(value, float):
        return f"{value:+.6f}"
    return f"{value:+d}"


def render_markdown(report: dict[str, Any]) -> str:
    models = report["models"]
    labels = {model["key"]: model["label"] for model in models}
    keys = [model["key"] for model in models]
    reference = report["reference_model"]
    lines = [
        "# Doc2Agent 三模型报告",
        "",
        f"本报告范围为 `{report['scope']}`。",
        f"参考模型为 `{reference}`。",
        "差值定义为 `model_minus_reference_model`。",
        "工具轨迹指标与答案评分指标分开报告。",
        "不计算合并准确率。",
        "这是本地证据约束评分，不是上游 GPT-4o 评分器。",
        "",
        "## 工具轨迹指标",
        "",
        "| 指标 | " + " | ".join(labels[key] for key in keys) + " |",
        "|---|" + "|".join("---:" for _ in keys) + "|",
    ]
    for metric in TRAJECTORY_KEYS:
        row = [str(model["trajectory"][metric]) for model in models]
        lines.append(f"| `{metric}` | " + " | ".join(row) + " |")

    lines.extend(
        [
            "",
            "## 答案评分指标",
            "",
            "| 指标 | " + " | ".join(labels[key] for key in keys) + " |",
            "|---|" + "|".join("---:" for _ in keys) + "|",
        ]
    )
    for status in GRADE_STATUSES:
        row = [str(model["answer_grade"]["status_counts"][status]) for model in models]
        lines.append(f"| `status:{status}` | " + " | ".join(row) + " |")
    for metric in (*ANSWER_GRADE_COUNT_KEYS, *ANSWER_GRADE_RATIO_KEYS):
        row = []
        for model in models:
            value = model["answer_grade"][metric]
            row.append(str(value) if isinstance(value, int) else _format_ratio(value))
        lines.append(f"| `{metric}` | " + " | ".join(row) + " |")

    lines.extend(
        [
            "",
            "## 相对参考模型的差值",
            "",
            "| 模型 | 轨迹 `exact` | 轨迹全工具命中 | "
            "轨迹最终回答 | 答案正确数 | 答案覆盖率 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for model in models:
        delta = model["delta_vs_reference"]
        lines.append(
            f"| {model['label']} | "
            f"{_format_delta(delta['trajectory']['exact_sequence'])} | "
            f"{_format_delta(delta['trajectory']['all_expected_called'])} | "
            f"{_format_delta(delta['trajectory']['tasks_with_final_answer'])} | "
            f"{_format_delta(delta['answer_grade']['graded_correct'])} | "
            f"{_format_delta(delta['answer_grade']['graded_coverage'])} |"
        )

    lines.extend(
        [
            "",
            "## 来源",
            "",
            "| 模型 | 运行摘要 SHA256 | 运行任务聚合 SHA256 | "
            "评分摘要 SHA256 | 评分任务聚合 SHA256 |",
            "|---|---|---|---|---|",
        ]
    )
    for model in models:
        sources = model["sources"]
        lines.append(
            f"| {model['label']} | `{sources['run_summary']['sha256']}` | "
            f"`{sources['run_tasks']['sha256']}` | "
            f"`{sources['grade_summary']['sha256']}` | "
            f"`{sources['grade_tasks']['sha256']}` |"
        )

    lines.extend(
        [
            "",
            "## 逐题状态",
            "",
            "| 题号 | "
            + " | ".join(labels[key] for key in keys)
            + " |",
            "|---:|" + "|".join("---" for _ in keys) + "|",
        ]
    )
    for task in report["tasks"]:
        statuses = [
            f"`{task['by_model'][key]['answer_grade']['status']}`" for key in keys
        ]
        lines.append(f"| {task['task_id']} | " + " | ".join(statuses) + " |")
    lines.append("")
    return "\n".join(lines)


def _dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_text_if_changed(path: Path, text: str) -> bool:
    encoded = text.encode("utf-8")
    if path.is_file() and path.read_bytes() == encoded:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return True


def _compare_output(path: Path, expected: str, label: str) -> str | None:
    if not path.is_file():
        return f"missing {label}: {path}"
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        return f"{label} differs from regenerated output: {path}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--md-out", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_report(args.manifest)
    except (ReportError, OSError, KeyError, TypeError) as exc:
        print(
            json.dumps(
                {"status": "FAIL", "errors": [str(exc)]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    json_text = _dumps_json(report)
    markdown_text = render_markdown(report)
    if args.check:
        errors = [
            error
            for error in (
                _compare_output(args.json_out, json_text, "JSON report"),
                _compare_output(args.md_out, markdown_text, "Markdown report"),
            )
            if error
        ]
        print(
            json.dumps(
                {
                    "status": "PASS" if not errors else "FAIL",
                    "errors": errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if not errors else 1

    json_changed = _write_text_if_changed(args.json_out, json_text)
    markdown_changed = _write_text_if_changed(args.md_out, markdown_text)
    print(
        json.dumps(
            {
                "status": "PASS",
                "models": [model["key"] for model in report["models"]],
                "reference_model": report["reference_model"],
                "tasks": len(report["tasks"]),
                "json_changed": json_changed,
                "markdown_changed": markdown_changed,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
