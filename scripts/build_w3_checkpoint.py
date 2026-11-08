from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "w3-day5-checkpoint-v1"
OUTPUT_NAMES = ("checkpoint.json", "checkpoint.md")


class CheckpointValidationError(ValueError):
    pass


class CheckpointOutputError(RuntimeError):
    pass


class SourceRole(StrEnum):
    F1_METRICS = "f1_metrics"
    F2_RECOMPUTE = "f2_recompute"
    F2_REFERENCES = "f2_references"
    F3_THREE_MODEL = "f3_three_model"
    SYSTEM_E2E = "system_e2e"
    VALIDATION = "validation"


SOURCE_PATHS = {
    SourceRole.F1_METRICS: "reports/esm150_lora_repro_v0/metrics.json",
    SourceRole.F2_RECOMPUTE: "reports/w2_day1/glycanml_rgcn_recompute.json",
    SourceRole.F2_REFERENCES: "reports/w2_day4/reference_values.json",
    SourceRole.F3_THREE_MODEL: "reports/w3_day4/f3_three_model_report.json",
    SourceRole.SYSTEM_E2E: "reports/w3_day1/real_e2e_2026-11-04.json",
    SourceRole.VALIDATION: "reports/w3_day5/unittest_2026-11-08.txt",
}


class ArtifactRef(NamedTuple):
    role: SourceRole
    path: str
    sha256: str
    byte_count: int


class SourceSet(NamedTuple):
    pins: tuple[ArtifactRef, ...]

    def by_role(self, role: SourceRole) -> ArtifactRef:
        return next(pin for pin in self.pins if pin.role == role)


class F1Result(NamedTuple):
    mcc: float
    reference_mcc: float
    delta: float
    row_count: int
    confusion: dict[str, int]


class F2Result(NamedTuple):
    task: str
    metric: str
    mean: float
    std: float
    n: int
    per_seed: tuple[tuple[int, float], ...]
    reference_value: float
    reference_std: float
    delta: float


class F3Result(NamedTuple):
    reference_model: str
    judge_model: str
    task_count: int
    tool_count: int
    models: tuple[dict[str, object], ...]


class SystemResult(NamedTuple):
    sample_accession: str
    sequence_length: int
    candidate_count: int
    all_labels_match: bool
    max_probability_delta: float
    wall_seconds: float
    inference_seconds: float
    model: dict[str, object]
    site_matches: tuple[dict[str, object], ...]


class ValidationResult(NamedTuple):
    tests_run: int
    skipped: int
    passed: int
    duration_seconds: float


class Checkpoint(NamedTuple):
    f1: F1Result
    f2: tuple[F2Result, ...]
    f3: F3Result
    system: SystemResult
    validation: ValidationResult
    sources: SourceSet


def _error(source: ArtifactRef, field: str, message: str) -> CheckpointValidationError:
    return CheckpointValidationError(f"{source.role.value} {source.path}: {field}: {message}")


def _map(value: object, source: ArtifactRef, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _error(source, field, f"expected object, got {type(value).__name__}")
    return value


def _list(value: object, source: ArtifactRef, field: str) -> list[object]:
    if not isinstance(value, list):
        raise _error(source, field, f"expected list, got {type(value).__name__}")
    return value


def _string(value: object, source: ArtifactRef, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(source, field, f"expected non-empty string, got {value!r}")
    return value


def _int(value: object, source: ArtifactRef, field: str, low: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low:
        raise _error(source, field, f"expected integer >= {low}, got {value!r}")
    return value


def _number(value: object, source: ArtifactRef, field: str, low: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(source, field, f"expected number, got {value!r}")
    number = float(value)
    if low is not None and number < low:
        raise _error(source, field, f"expected number >= {low}, got {number}")
    return number


def _close(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return abs(left - right) <= tolerance


def _read(repo: Path, role: SourceRole) -> tuple[bytes, ArtifactRef]:
    relative = SOURCE_PATHS[role]
    path = (repo / relative).resolve()
    try:
        path.relative_to(repo)
    except ValueError as exc:
        raise CheckpointValidationError(f"{role.value} {relative}: path escapes repository") from exc
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CheckpointValidationError(f"{role.value} {relative}: unreadable source: {exc}") from exc
    return raw, ArtifactRef(role, relative, hashlib.sha256(raw).hexdigest(), len(raw))


def _load_sources(repo: Path) -> tuple[dict[SourceRole, bytes], SourceSet]:
    raws: dict[SourceRole, bytes] = {}
    pins: list[ArtifactRef] = []
    for role in SOURCE_PATHS:
        raw, pin = _read(repo, role)
        raws[role] = raw
        pins.append(pin)
    return raws, SourceSet(tuple(pins))


def _json(raw: bytes, source: ArtifactRef) -> dict[str, object]:
    try:
        return _map(json.loads(raw.decode("utf-8-sig")), source, "<root>")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(source, "JSON", str(exc)) from exc


def _parse_f1(raw: bytes, source: ArtifactRef) -> F1Result:
    data = _json(raw, source)
    mcc = _number(data.get("mcc"), source, "mcc")
    reference = _number(data.get("reference_mcc"), source, "reference_mcc")
    delta = _number(data.get("mcc_delta_from_reference"), source, "mcc_delta_from_reference")
    if not -1.0 <= mcc <= 1.0:
        raise _error(source, "mcc", "must be in [-1, 1]")
    if not _close(delta, mcc - reference):
        raise _error(source, "mcc_delta_from_reference", "must equal mcc - reference_mcc")
    confusion = _map(data.get("confusion"), source, "confusion")
    if set(confusion) != {"tp", "fp", "tn", "fn"}:
        raise _error(source, "confusion", "expected tp, fp, tn, fn")
    counts = {key: _int(confusion[key], source, f"confusion.{key}") for key in ("tp", "fp", "tn", "fn")}
    row_count = _int(data.get("row_count"), source, "row_count", 1)
    if sum(counts.values()) != row_count:
        raise _error(source, "confusion", "counts must sum to row_count")
    tp, fp, tn, fn = (counts[key] for key in ("tp", "fp", "tn", "fn"))
    positive, negative = tp + fn, tn + fp
    if min(tp + fp, positive, negative) == 0:
        raise _error(source, "confusion", "zero MCC support")
    expected_mcc = (tp * tn - fp * fn) / ((tp + fp) * positive * negative * (tn + fn)) ** 0.5
    if not _close(mcc, expected_mcc):
        raise _error(source, "mcc", "does not match confusion matrix")
    return F1Result(mcc, reference, delta, row_count, counts)


def _parse_references(raw: bytes, source: ArtifactRef) -> dict[str, dict[str, object]]:
    root = _json(raw, source)
    references: dict[str, dict[str, object]] = {}
    for index, item in enumerate(_list(root.get("references"), source, "references")):
        record = _map(item, source, f"references[{index}]")
        reference_id = _string(record.get("reference_id"), source, f"references[{index}].reference_id")
        if reference_id in references:
            raise _error(source, "references", f"duplicate id {reference_id}")
        references[reference_id] = record
    for reference_id in ("ref.f2.immunogenicity.auprc", "ref.f2.glycosylation.macro_f1"):
        if reference_id not in references:
            raise _error(source, "references", f"missing {reference_id}")
    return references


def _parse_f2(raw: bytes, source: ArtifactRef, references: dict[str, dict[str, object]]) -> tuple[F2Result, ...]:
    data = _json(raw, source)
    if data.get("status") != "PASS" or data.get("mode") != "full":
        raise _error(source, "status", "expected PASS and full mode")
    if "GlycanML Table 3" not in _string(data.get("benchmark"), source, "benchmark"):
        raise _error(source, "benchmark", "must identify GlycanML Table 3")
    seeds = _list(data.get("seeds"), source, "seeds")
    if [int(seed) for seed in seeds if isinstance(seed, int)] != [0, 1, 2]:
        raise _error(source, "seeds", "expected [0, 1, 2]")
    training = _map(data.get("training"), source, "training")
    if _int(training.get("epochs"), source, "training.epochs", 1) != 50:
        raise _error(source, "training.epochs", "expected 50")
    if _int(training.get("batch_size"), source, "training.batch_size", 1) != 64:
        raise _error(source, "training.batch_size", "expected 64")
    tasks = _map(data.get("tasks"), source, "tasks")
    specifications = (
        ("immunogenicity", "auprc", "ref.f2.immunogenicity.auprc"),
        ("glycosylation", "macro_f1", "ref.f2.glycosylation.macro_f1"),
    )
    results: list[F2Result] = []
    for task_name, metric, reference_id in specifications:
        task = _map(tasks.get(task_name), source, f"tasks.{task_name}")
        per_seed_records = _list(task.get("per_seed"), source, f"tasks.{task_name}.per_seed")
        values: list[tuple[int, float]] = []
        for index, item in enumerate(per_seed_records):
            record = _map(item, source, f"tasks.{task_name}.per_seed[{index}]")
            seed = _int(record.get("seed"), source, f"tasks.{task_name}.per_seed[{index}].seed")
            test = _map(record.get("test"), source, f"tasks.{task_name}.per_seed[{index}].test")
            values.append((seed, _number(test.get(metric), source, f"tasks.{task_name}.per_seed[{index}].test.{metric}")))
        if [seed for seed, _ in values] != [0, 1, 2]:
            raise _error(source, f"tasks.{task_name}.per_seed", "expected seeds 0, 1, 2")
        aggregate = _map(task.get("aggregate"), source, f"tasks.{task_name}.aggregate")
        statistic = _map(aggregate.get(f"test_{metric}"), source, f"tasks.{task_name}.aggregate.test_{metric}")
        mean = _number(statistic.get("mean"), source, f"tasks.{task_name}.aggregate.test_{metric}.mean")
        std = _number(statistic.get("std"), source, f"tasks.{task_name}.aggregate.test_{metric}.std")
        n = _int(statistic.get("n"), source, f"tasks.{task_name}.aggregate.test_{metric}.n", 1)
        seed_values = [value for _, value in values]
        if not _close(mean, statistics.fmean(seed_values)):
            raise _error(source, f"tasks.{task_name}.aggregate.test_{metric}.mean", "does not match seeds")
        if not _close(std, statistics.stdev(seed_values)):
            raise _error(source, f"tasks.{task_name}.aggregate.test_{metric}.std", "does not match seeds")
        if n != 3:
            raise _error(source, f"tasks.{task_name}.aggregate.test_{metric}.n", "expected 3")
        reference = references[reference_id]
        reference_value = _number(reference.get("value"), source, f"{reference_id}.value")
        reference_std = _number(reference.get("std"), source, f"{reference_id}.std")
        results.append(F2Result(task_name, metric, mean, std, n, tuple(values), reference_value, reference_std, mean - reference_value))
    return tuple(results)


def _parse_f3(raw: bytes, source: ArtifactRef) -> F3Result:
    data = _json(raw, source)
    if data.get("upstream_gpt4o_equivalent") is not False:
        raise _error(source, "upstream_gpt4o_equivalent", "must be false")
    validation = _map(data.get("validation"), source, "validation")
    if _int(validation.get("model_count"), source, "validation.model_count", 1) != 3:
        raise _error(source, "validation.model_count", "expected 3")
    task_count = _int(validation.get("tasks_per_model"), source, "validation.tasks_per_model", 1)
    tool_count = _int(validation.get("tools_available"), source, "validation.tools_available", 1)
    if task_count != 50 or tool_count != 70:
        raise _error(source, "validation", "expected 50 tasks and 70 tools")
    models = _list(data.get("models"), source, "models")
    if len(models) != 3:
        raise _error(source, "models", "expected three models")
    judge = _map(data.get("judge_model_config"), source, "judge_model_config")
    judge_model = _string(judge.get("model"), source, "judge_model_config.model")
    normalized_models: list[dict[str, object]] = []
    for index, item in enumerate(models):
        model = _map(item, source, f"models[{index}]")
        model_key = _string(model.get("key"), source, f"models[{index}].key")
        trajectory = _map(model.get("trajectory"), source, f"models[{index}].trajectory")
        answer = _map(model.get("answer_grade"), source, f"models[{index}].answer_grade")
        status_counts = _map(answer.get("status_counts"), source, f"models[{index}].answer_grade.status_counts")
        expected_statuses = {"correct", "incorrect", "manual_review", "missing_answer", "invalid_trace", "judge_unavailable"}
        if set(status_counts) != expected_statuses:
            raise _error(source, f"models[{index}].answer_grade.status_counts", "unexpected status set")
        counts = {key: _int(status_counts[key], source, f"models[{index}].answer_grade.status_counts.{key}") for key in expected_statuses}
        if sum(counts.values()) != task_count:
            raise _error(source, f"models[{index}].answer_grade.status_counts", "must sum to 50")
        for key in ("tasks_run", "exact_sequence", "all_expected_called", "any_expected_called", "tasks_with_tool_call", "tasks_with_final_answer", "tool_call_successes", "tool_calls"):
            _int(trajectory.get(key), source, f"models[{index}].trajectory.{key}")
        if _int(trajectory.get("tasks_run"), source, f"models[{index}].trajectory.tasks_run", 1) != task_count:
            raise _error(source, f"models[{index}].trajectory.tasks_run", "must equal tasks_per_model")
        if _int(trajectory.get("tool_call_successes"), source, f"models[{index}].trajectory.tool_call_successes") > _int(trajectory.get("tool_calls"), source, f"models[{index}].trajectory.tool_calls"):
            raise _error(source, f"models[{index}].trajectory", "successes exceed calls")
        graded_correct = _int(answer.get("graded_correct"), source, f"models[{index}].answer_grade.graded_correct")
        graded_incorrect = _int(answer.get("graded_incorrect"), source, f"models[{index}].answer_grade.graded_incorrect")
        if graded_correct != counts["correct"] or graded_incorrect != counts["incorrect"]:
            raise _error(source, f"models[{index}].answer_grade", "graded counts disagree with status counts")
        graded_accuracy = _fraction(answer.get("graded_accuracy"), source, f"models[{index}].answer_grade.graded_accuracy")
        graded_coverage = _fraction(answer.get("graded_coverage"), source, f"models[{index}].answer_grade.graded_coverage")
        if graded_accuracy["numerator"] != graded_correct or graded_accuracy["denominator"] != graded_correct + graded_incorrect:
            raise _error(source, f"models[{index}].answer_grade.graded_accuracy", "denominator must be correct plus incorrect")
        if graded_coverage["numerator"] != graded_accuracy["denominator"] or graded_coverage["denominator"] != task_count:
            raise _error(source, f"models[{index}].answer_grade.graded_coverage", "coverage must be graded over all tasks")
        normalized_models.append(
            {
                "key": model_key,
                "label": _string(model.get("label"), source, f"models[{index}].label"),
                "model": _string(model.get("model"), source, f"models[{index}].model"),
                "provider": _string(model.get("provider"), source, f"models[{index}].provider"),
                "trajectory": {
                    key: _int(trajectory.get(key), source, f"models[{index}].trajectory.{key}")
                    for key in ("tasks_run", "exact_sequence", "all_expected_called", "any_expected_called", "tasks_with_tool_call", "tasks_with_final_answer", "tool_call_successes", "tool_calls")
                },
                "answer_grade": {
                    "status_counts": counts,
                    "graded_correct": graded_correct,
                    "graded_incorrect": graded_incorrect,
                    "graded_accuracy": graded_accuracy,
                    "graded_coverage": graded_coverage,
                },
            }
        )
    return F3Result(_string(data.get("reference_model"), source, "reference_model"), judge_model, task_count, tool_count, tuple(normalized_models))


def _parse_system(raw: bytes, source: ArtifactRef) -> SystemResult:
    data = _json(raw, source)
    candidate_count = _int(data.get("candidate_count"), source, "candidate_count", 1)
    site_matches = _list(data.get("site_matches"), source, "site_matches")
    if len(site_matches) != candidate_count:
        raise _error(source, "site_matches", "length must equal candidate_count")
    normalized_sites: list[dict[str, object]] = []
    for index, item in enumerate(site_matches):
        site = _map(item, source, f"site_matches[{index}]")
        normalized_sites.append(
            {
                "position": _int(site.get("position"), source, f"site_matches[{index}].position", 1),
                "motif": _string(site.get("motif"), source, f"site_matches[{index}].motif"),
                "predicted_label": _int(site.get("predicted_label"), source, f"site_matches[{index}].predicted_label"),
                "prob_delta": _number(site.get("prob_delta"), source, f"site_matches[{index}].prob_delta"),
                "label_match": bool(site.get("label_match")),
            }
        )
    if not all(site["label_match"] for site in normalized_sites):
        raise _error(source, "site_matches", "all labels must match")
    if data.get("all_labels_match") is not True:
        raise _error(source, "all_labels_match", "must be true for the checkpoint")
    model = _map(data.get("model"), source, "model")
    if model.get("full_sequence") is not True or model.get("truncation") is not False:
        raise _error(source, "model", "expected full sequence with no truncation")
    return SystemResult(
        _string(data.get("sample_accession"), source, "sample_accession"),
        _int(data.get("sequence_length"), source, "sequence_length", 1),
        candidate_count,
        True,
        _number(data.get("max_probability_delta"), source, "max_probability_delta"),
        _number(data.get("wall_seconds"), source, "wall_seconds"),
        _number(data.get("inference_seconds"), source, "inference_seconds"),
        {
            "base_model_id": _string(model.get("base_model_id"), source, "model.base_model_id"),
            "base_model_revision": _string(model.get("base_model_revision"), source, "model.base_model_revision"),
            "adapter_sha256": _string(model.get("adapter_sha256"), source, "model.adapter_sha256"),
            "adapter_tensor_count": _int(model.get("adapter_tensor_count"), source, "model.adapter_tensor_count", 1),
            "device": _string(model.get("device"), source, "model.device"),
            "attention_backend": _string(model.get("attention_backend"), source, "model.attention_backend"),
            "full_sequence": True,
            "truncation": False,
            "windowing": bool(model.get("windowing")),
        },
        tuple(normalized_sites),
    )


def _parse_validation(raw: bytes, source: ArtifactRef) -> ValidationResult:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _error(source, "encoding", str(exc)) from exc
    ran = re.search(r"Ran\s+(\d+)\s+tests?\s+in\s+([0-9.]+)s", text)
    if ran is None:
        raise _error(source, "test summary", "missing Ran ... tests in ...s")
    tests_run = int(ran.group(1))
    duration = float(ran.group(2))
    if re.search(r"^FAILED\b", text, re.MULTILINE):
        raise _error(source, "status", "unittest failed")
    ok = re.search(r"^OK(?:\s+\(skipped=(\d+)\))?\s*$", text, re.MULTILINE)
    if ok is None:
        raise _error(source, "status", "missing OK summary")
    skipped = int(ok.group(1) or 0)
    if skipped > tests_run:
        raise _error(source, "skipped", "cannot exceed tests_run")
    return ValidationResult(tests_run, skipped, tests_run - skipped, duration)


def _build(repo: Path) -> Checkpoint:
    raws, sources = _load_sources(repo)
    references = _parse_references(raws[SourceRole.F2_REFERENCES], sources.by_role(SourceRole.F2_REFERENCES))
    return Checkpoint(
        _parse_f1(raws[SourceRole.F1_METRICS], sources.by_role(SourceRole.F1_METRICS)),
        _parse_f2(raws[SourceRole.F2_RECOMPUTE], sources.by_role(SourceRole.F2_RECOMPUTE), references),
        _parse_f3(raws[SourceRole.F3_THREE_MODEL], sources.by_role(SourceRole.F3_THREE_MODEL)),
        _parse_system(raws[SourceRole.SYSTEM_E2E], sources.by_role(SourceRole.SYSTEM_E2E)),
        _parse_validation(raws[SourceRole.VALIDATION], sources.by_role(SourceRole.VALIDATION)),
        sources,
    )


def _fraction(value: object, source: ArtifactRef, field: str) -> dict[str, object]:
    record = _map(value, source, field)
    numerator = _int(record.get("numerator"), source, f"{field}.numerator")
    denominator = _int(record.get("denominator"), source, f"{field}.denominator", 1)
    reported = _number(record.get("value"), source, f"{field}.value")
    if numerator > denominator:
        raise _error(source, field, "numerator exceeds denominator")
    if not _close(reported, numerator / denominator, tolerance=1e-6):
        raise _error(source, f"{field}.value", "does not equal numerator / denominator")
    return {"numerator": numerator, "denominator": denominator, "value": numerator / denominator}


def _source_dict(pin: ArtifactRef) -> dict[str, object]:
    return {"role": pin.role.value, "path": pin.path, "sha256": pin.sha256, "byte_count": pin.byte_count}


def _f2_dict(result: F2Result) -> dict[str, object]:
    return {
        "task": result.task,
        "metric": result.metric,
        "mean": result.mean,
        "std": result.std,
        "n": result.n,
        "per_seed": [{"seed": seed, "value": value} for seed, value in result.per_seed],
        "reference": {"value": result.reference_value, "std": result.reference_std},
        "delta_local_minus_reference": result.delta,
    }


def _render_json(checkpoint: Checkpoint) -> bytes:
    payload = {
        "schema_version": SCHEMA,
        "status": "PASS",
        "scope": "W3 11/10 checkpoint",
        "policy": {
            "f2_reference": "GlycanML Table 3",
            "f3_metrics": "trajectory_and_local_evidence_grading_not_upstream_gpt4o",
            "no_wall_clock_timestamp": True,
        },
        "f1": {
            "metric": "MCC",
            "local": checkpoint.f1.mcc,
            "reference": checkpoint.f1.reference_mcc,
            "delta_local_minus_reference": checkpoint.f1.delta,
            "row_count": checkpoint.f1.row_count,
            "confusion": checkpoint.f1.confusion,
        },
        "f2": [_f2_dict(result) for result in checkpoint.f2],
        "f3": {
            "reference_model": checkpoint.f3.reference_model,
            "judge_model": checkpoint.f3.judge_model,
            "task_count": checkpoint.f3.task_count,
            "tool_count": checkpoint.f3.tool_count,
            "upstream_gpt4o_equivalent": False,
            "models": list(checkpoint.f3.models),
        },
        "system": {
            "sample_accession": checkpoint.system.sample_accession,
            "sequence_length": checkpoint.system.sequence_length,
            "candidate_count": checkpoint.system.candidate_count,
            "all_labels_match": checkpoint.system.all_labels_match,
            "max_probability_delta": checkpoint.system.max_probability_delta,
            "wall_seconds": checkpoint.system.wall_seconds,
            "inference_seconds": checkpoint.system.inference_seconds,
            "model": checkpoint.system.model,
            "site_matches": list(checkpoint.system.site_matches),
        },
        "validation": {
            "tests_run": checkpoint.validation.tests_run,
            "passed": checkpoint.validation.passed,
            "skipped": checkpoint.validation.skipped,
            "duration_seconds": checkpoint.validation.duration_seconds,
            "status": "PASS",
        },
        "sources": [_source_dict(pin) for pin in checkpoint.sources.pins],
        "boundaries": [
            "F2 对齐 GlycanML Table 3，不是 Table 2；本地是 PyG 自实现，不是 TorchDrug 逐位克隆。",
            "F3 的轨迹指标不是答案正确率；Kimi K3 是本地证据评分器，不等同于上游 GPT-4o。",
            "每个模型只有一次固定 50 题运行，不能据此声称方差或模型大小因果。",
            "系统只预测 N-X-S/T sequon，不是实验证据或临床诊断。",
        ],
    }
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _fmt(value: float) -> str:
    return f"{value:.15g}"


def _render_markdown(checkpoint: Checkpoint) -> bytes:
    lines = [
        "# W3 Day5 11/10 检查点",
        "",
        f"Schema：`{SCHEMA}`。由 `scripts/build_w3_checkpoint.py` 从固定证据源生成，不含运行时间。",
        "",
        "## F1 / F2 核心指标",
        "",
        "| 指标 | 本地值 | 标准差 | 参考值 | 参考标准差 | 本地减参考 |",
        "|---|---:|---:|---:|---:|---:|",
        f"| ESM-2 150M LoRA MCC | {_fmt(checkpoint.f1.mcc)} |  | {_fmt(checkpoint.f1.reference_mcc)} |  | {checkpoint.f1.delta:+.15g} |",
    ]
    for result in checkpoint.f2:
        label = "免疫原性 AUPRC" if result.task == "immunogenicity" else "糖基化 Macro-F1"
        lines.append(
            f"| {label} | {_fmt(result.mean)} | {_fmt(result.std)} | "
            f"{_fmt(result.reference_value)} | {_fmt(result.reference_std)} | {result.delta:+.15g} |"
        )
    lines += [
        "",
        "## F3 三模型对照",
        "",
        "| 模型 | exact | 全部期望工具 | 任一期望工具 | 有最终回答 | 工具成功/调用 | 正确/可判定 | 可判定覆盖 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in checkpoint.f3.models:
        trajectory = model["trajectory"]
        answer = model["answer_grade"]
        counts = answer["status_counts"]
        graded_accuracy = answer["graded_accuracy"]
        graded_coverage = answer["graded_coverage"]
        lines.append(
            f"| {model['label']} | {trajectory['exact_sequence']} | {trajectory['all_expected_called']} | "
            f"{trajectory['any_expected_called']} | {trajectory['tasks_with_final_answer']} | "
            f"{trajectory['tool_call_successes']}/{trajectory['tool_calls']} | "
            f"{graded_accuracy['numerator']}/{graded_accuracy['denominator']} | "
            f"{graded_coverage['numerator']}/{graded_coverage['denominator']} |"
        )
    lines += [
        "",
        "F3 的列全部是工具轨迹或输出存在性指标。答案评分使用同一组 50 题、同一份 rubric、同一个",
        f"`{checkpoint.f3.judge_model}` judge，但不是上游 GPT-4o 评分，不能直接比较。",
        "",
        "## W3 真实系统",
        "",
        f"- 样例：`{checkpoint.system.sample_accession}`，长度 {checkpoint.system.sequence_length} aa。",
        f"- 候选位点：{checkpoint.system.candidate_count} 个，历史标签全部一致：{str(checkpoint.system.all_labels_match).lower()}。",
        f"- 最大概率差：{_fmt(checkpoint.system.max_probability_delta)}。",
        f"- 冷启动墙钟：{_fmt(checkpoint.system.wall_seconds)} 秒；纯推理：{_fmt(checkpoint.system.inference_seconds)} 秒。",
        f"- 模型：`{checkpoint.system.model['base_model_id']}`，设备：`{checkpoint.system.model['device']}`。",
        "",
        "## 回归",
        "",
        f"- unittest：{checkpoint.validation.tests_run} 项，{checkpoint.validation.passed} 通过，{checkpoint.validation.skipped} 跳过。",
        f"- 耗时：{_fmt(checkpoint.validation.duration_seconds)} 秒。",
        "",
        "## 来源与哈希",
        "",
        "| 角色 | 路径 | SHA256 | 字节数 |",
        "|---|---|---|---:|",
    ]
    for pin in checkpoint.sources.pins:
        lines.append(f"| {pin.role.value} | `{pin.path}` | `{pin.sha256}` | {pin.byte_count} |")
    lines += [
        "",
        "## 口径边界",
        "",
        "- F2 对齐 GlycanML 论文 Table 3，不是 Table 2；本地是 PyG 自实现，不是 TorchDrug 逐位克隆。",
        "- F3 轨迹指标不是答案正确率；Kimi K3 是本地证据评分器，不等同于上游 GPT-4o。",
        "- 每个模型只有一次固定 50 题运行，不能声称方差或模型大小因果。",
        "- 系统只预测 N-X-S/T sequon，概率未做外部校准，不是实验证据或临床诊断。",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _render(checkpoint: Checkpoint) -> dict[str, bytes]:
    return {"checkpoint.json": _render_json(checkpoint), "checkpoint.md": _render_markdown(checkpoint)}


def _write_if_changed(path: Path, data: bytes) -> None:
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def generate_checkpoint(repo_root: Path = ROOT, out_dir: Path | None = None) -> Checkpoint:
    repo = Path(repo_root).resolve()
    destination = Path(out_dir) if out_dir is not None else repo / "reports" / "w3_day5"
    checkpoint = _build(repo)
    for name, data in _render(checkpoint).items():
        _write_if_changed(destination / name, data)
    return checkpoint


def check_checkpoint(repo_root: Path = ROOT, out_dir: Path | None = None) -> None:
    repo = Path(repo_root).resolve()
    destination = Path(out_dir) if out_dir is not None else repo / "reports" / "w3_day5"
    checkpoint = _build(repo)
    stale = [
        name
        for name, data in _render(checkpoint).items()
        if not (destination / name).exists() or (destination / name).read_bytes() != data
    ]
    if stale:
        raise CheckpointOutputError(f"checkpoint outputs missing or stale: {', '.join(stale)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic W3 Day5 checkpoint.")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check:
            check_checkpoint(args.repo_root, args.out_dir)
            print("PASS: W3 Day5 checkpoint outputs are current")
        else:
            checkpoint = generate_checkpoint(args.repo_root, args.out_dir)
            print(
                "PASS: generated W3 Day5 checkpoint with "
                f"{len(checkpoint.f2)} F2 tasks, {len(checkpoint.f3.models)} F3 models, "
                f"{checkpoint.system.candidate_count} system sites and {checkpoint.validation.tests_run} tests"
            )
        return 0
    except CheckpointValidationError as exc:
        print(f"CHECKPOINT VALIDATION ERROR: {exc}", file=sys.stderr)
        return 2
    except CheckpointOutputError as exc:
        print(f"CHECKPOINT CHECK ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"CHECKPOINT IO ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
