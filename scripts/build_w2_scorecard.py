from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import statistics
import sys
import tempfile
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple, TypeAlias
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "w2-day4-scorecard-v1"
REF_SCHEMA = "w2-day4-scorecard-references-v1"
TOL = 1e-12

class ScorecardValidationError(ValueError): pass
class ScorecardOutputError(RuntimeError): pass

Track = StrEnum("Track", {"F1": "F1", "F2": "F2", "F3": "F3"})
SourceRole = StrEnum("SourceRole", {"F1": "f1_metrics", "F2": "f2_recompute", "F3": "f3_summary", "MIRROR": "reference_mirror", "W2": "w2_tool_summary", "CSV": "feasibility_csv", "RECHECK": "recheck_summary", "CATALOG": "reference_catalog"})
Unit = StrEnum("Unit", {"MCC": "mcc", "AUPRC": "auprc", "MACRO_F1": "macro_f1", "COUNT": "count"})
Feasibility = StrEnum("Feasibility", {"DIRECT": "current_tools_direct", "REPLACEMENT": "needs_replacement_tool", "SERVICE": "service_failure"})

SOURCE_PATHS = {
    SourceRole.F1: "reports/esm150_lora_repro_v0/metrics.json",
    SourceRole.F2: "reports/w2_day1/glycanml_rgcn_recompute.json",
    SourceRole.F3: "reports/w2_day2/f3_qwen3_4b_50/summary.json",
    SourceRole.MIRROR: "reports/w2_day2/f2_f3_comparison.md",
    SourceRole.W2: "reports/w2_day2/tool_feasibility_summary.json",
    SourceRole.CSV: "reports/w2_day3/task_feasibility_revised.csv",
    SourceRole.RECHECK: "reports/w2_day3/tool_blocker_recheck_summary.json",
    SourceRole.CATALOG: "reports/w2_day4/reference_values.json",
}
REF_IDS = {Track.F1: ("ref.f1.esm150_lora.mcc",), Track.F2: ("ref.f2.immunogenicity.auprc", "ref.f2.glycosylation.macro_f1"), Track.F3: ("ref.f3.claude.answer_accuracy", "ref.f3.qwen3.answer_accuracy")}
REF_TYPES = {"ref.f1.esm150_lora.mcc": (Track.F1, Unit.MCC), "ref.f2.immunogenicity.auprc": (Track.F2, Unit.AUPRC), "ref.f2.glycosylation.macro_f1": (Track.F2, Unit.MACRO_F1), "ref.f3.claude.answer_accuracy": (Track.F3, Unit.COUNT), "ref.f3.qwen3.answer_accuracy": (Track.F3, Unit.COUNT)}
FEAS_LABELS = {Feasibility.DIRECT: "当前工具可直接完成", Feasibility.REPLACEMENT: "需要替代工具", Feasibility.SERVICE: "服务失败"}
FEAS_COUNTS = {Feasibility.DIRECT: 43, Feasibility.REPLACEMENT: 5, Feasibility.SERVICE: 2}
ORIGINAL_COUNTS = {Feasibility.DIRECT: 20, Feasibility.REPLACEMENT: 25, Feasibility.SERVICE: 5}
OUTPUT_NAMES = ("scorecard.json", "scorecard.csv", "scorecard.md")

ArtifactRef = NamedTuple("ArtifactRef", [("role", SourceRole), ("path", str), ("sha256", str), ("byte_count", int)])

class SourceSet(NamedTuple):
    pins: tuple[ArtifactRef, ...]
    def by_role(self, role: SourceRole) -> ArtifactRef:
        return next(pin for pin in self.pins if pin.role == role)

LocalValue = NamedTuple("LocalValue", [("value", int | float), ("std", float | None), ("n", int | None), ("denominator", int | None), ("source", SourceRole), ("locator", str), ("std_locator", str | None), ("denominator_locator", str | None)])
ReferenceValue = NamedTuple("ReferenceValue", [("reference_id", str), ("track", Track), ("label", str), ("value", int | float), ("std", float | None), ("n", int | None), ("denominator", int | None), ("unit", Unit), ("citation", str)])
Comparable = NamedTuple("Comparable", [("reference_id", str), ("delta_local_minus_reference", float), ("scope_note", str)])
NotComparable = NamedTuple("NotComparable", [("reference_ids", tuple[str, ...]), ("reason", str)])
Comparison: TypeAlias = Comparable | NotComparable

MetricRow = NamedTuple("MetricRow", [("metric_id", str), ("track", Track), ("subject", str), ("metric", str), ("unit", Unit), ("local", LocalValue), ("reference", ReferenceValue | None), ("comparison", Comparison)])
F1Evidence = NamedTuple("F1Evidence", [("mcc", float), ("row_count", int), ("embedded_reference_mcc", float), ("embedded_delta", float)])
F2TaskEvidence = NamedTuple("F2TaskEvidence", [("task", str), ("report_metric", str), ("mean", float), ("std", float), ("per_seed_values", tuple[float, ...])])
F3Evidence = NamedTuple("F3Evidence", [("model", str), ("tasks_run", int), ("exact_sequence", int), ("all_expected_called", int), ("any_expected_called", int), ("tasks_with_final_answer", int), ("tool_call_successes", int), ("tool_calls", int)])
FeasibilitySnapshot = NamedTuple("FeasibilitySnapshot", [("total_tasks", int), ("counts", tuple[tuple[Feasibility, int], ...]), ("original_counts", tuple[tuple[Feasibility, int], ...]), ("task_ids", tuple[tuple[Feasibility, tuple[int, ...]], ...]), ("changed_tasks", int), ("rechecked_tools", int), ("service_reachable", int), ("default_transport_ok", int)])

Scorecard = NamedTuple("Scorecard", [("schema_version", str), ("metrics", tuple[MetricRow, ...]), ("references", tuple[ReferenceValue, ...]), ("feasibility", FeasibilitySnapshot), ("sources", SourceSet)])

def _err(source: ArtifactRef, field: str, message: str) -> ScorecardValidationError:
    return ScorecardValidationError(f"{source.role.value} {source.path}: {field}: {message}")
def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=TOL)
def _num(value: object, source: ArtifactRef, field: str, low: float | None = None, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise _err(source, field, f"expected finite number, got {value!r}")
    number = float(value)
    if (low is not None and number < low) or (high is not None and number > high):
        raise _err(source, field, f"expected range [{low}, {high}], got {number}")
    return number
def _int(value: object, source: ArtifactRef, field: str, low: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or (low is not None and value < low):
        raise _err(source, field, f"expected integer >= {low}, got {value!r}")
    return value
def _map(value: object, source: ArtifactRef, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _err(source, field, f"expected object, got {type(value).__name__}")
    return value
def _list(value: object, source: ArtifactRef, field: str) -> list[object]:
    if not isinstance(value, list):
        raise _err(source, field, f"expected list, got {type(value).__name__}")
    return value
def _str(value: object, source: ArtifactRef, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _err(source, field, f"expected non-empty string, got {value!r}")
    return value
def _json(raw: bytes, source: ArtifactRef) -> dict[str, object]:
    try:
        return _map(json.loads(raw.decode("utf-8-sig")), source, "<root>")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _err(source, "invalid JSON", str(exc)) from exc
def _int_map(value: object, source: ArtifactRef, field: str, expected: dict[str, int]) -> None:
    actual_map = _map(value, source, field)
    actual = {str(key): _int(raw, source, f"{field}.{key}", 0) for key, raw in actual_map.items()}
    if actual != expected:
        raise _err(source, field, f"expected {expected}, got {actual}")
def _read(repo: Path, role: SourceRole) -> tuple[bytes, ArtifactRef]:
    relative = SOURCE_PATHS[role]
    path = (repo / relative).resolve()
    try:
        path.relative_to(repo)
    except ValueError as exc:
        raise ScorecardValidationError(f"{role.value} {relative}: path escapes repo") from exc
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ScorecardValidationError(f"{role.value} {relative}: unreadable source: {exc}") from exc
    return raw, ArtifactRef(role, relative, hashlib.sha256(raw).hexdigest(), len(raw))
def _load(repo: Path) -> tuple[dict[SourceRole, bytes], SourceSet]:
    raws: dict[SourceRole, bytes] = {}
    pins: list[ArtifactRef] = []
    for role in SOURCE_PATHS:
        raw, pin = _read(repo, role)
        raws[role] = raw
        pins.append(pin)
    return raws, SourceSet(tuple(pins))

def _parse_references(raw: bytes, source: ArtifactRef) -> tuple[ReferenceValue, ...]:
    root = _json(raw, source)
    if root.get("schema_version") != REF_SCHEMA:
        raise _err(source, "schema_version", f"expected {REF_SCHEMA}")
    references: list[ReferenceValue] = []
    for index, item in enumerate(_list(root.get("references"), source, "references")):
        field = f"references[{index}]"
        row = _map(item, source, field)
        try:
            track, unit = Track(row.get("track")), Unit(row.get("unit"))
        except ValueError as exc:
            raise _err(source, field, f"unknown track/unit: {exc}") from exc
        denominator = None if row.get("denominator") is None else _int(row.get("denominator"), source, f"{field}.denominator", 1)
        value = _int(row.get("value"), source, f"{field}.value", 0) if unit == Unit.COUNT else _num(row.get("value"), source, f"{field}.value")
        if denominator is not None and not 0 <= value <= denominator:
            raise _err(source, f"{field}.value", "outside denominator")
        references.append(ReferenceValue(
            _str(row.get("reference_id"), source, f"{field}.reference_id"), track,
            _str(row.get("label"), source, f"{field}.label"), value,
            None if row.get("std") is None else _num(row.get("std"), source, f"{field}.std", 0.0),
            None if row.get("n") is None else _int(row.get("n"), source, f"{field}.n", 1),
            denominator, unit, _str(row.get("citation"), source, f"{field}.citation"),
        ))
    by_id = {reference.reference_id: reference for reference in references}
    if len(by_id) != len(references):
        raise _err(source, "references", "duplicate reference id")
    missing = set(REF_TYPES) - set(by_id)
    if missing:
        raise _err(source, "references", f"missing ids {sorted(missing)}")
    for reference_id, expected in REF_TYPES.items():
        actual = by_id[reference_id]
        if (actual.track, actual.unit) != expected:
            raise _err(source, reference_id, f"expected {expected}, got {(actual.track, actual.unit)}")
    for reference_id in REF_IDS[Track.F3]:
        if by_id[reference_id].denominator != 50:
            raise _err(source, reference_id, "F3 denominator must be 50")
    return tuple(references)
def _one(pattern: str, text: str, source: ArtifactRef, field: str) -> re.Match[str]:
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if len(matches) != 1:
        raise _err(source, field, f"expected one anchor, got {len(matches)}")
    return matches[0]
def _cross_check_mirror(raw: bytes, source: ArtifactRef, refs: dict[str, ReferenceValue]) -> None:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _err(source, "encoding", str(exc)) from exc
    patterns = {
        "ref.f2.immunogenicity.auprc": r"^\|\s*免疫原性 AUPRC\s*\|\s*([0-9.]+)\s*±\s*([0-9.]+)\s*\|",
        "ref.f2.glycosylation.macro_f1": r"^\|\s*糖基化 Macro-F1\s*\|\s*([0-9.]+)\s*±\s*([0-9.]+)\s*\|",
    }
    for reference_id, pattern in patterns.items():
        match, reference = _one(pattern, text, source, reference_id), refs[reference_id]
        if not _close(float(reference.value), float(match.group(1))) or reference.std is None or not _close(reference.std, float(match.group(2))):
            raise _err(source, reference_id, "catalog differs from Markdown anchor")
    sentence = _one(r"上游目录记录 Claude 为\s*(\d+)/50、Qwen3 为\s*(\d+)/50，二者使用 GPT-4o 评分", text, source, "F3 anchor")
    for reference_id, mirrored in zip(REF_IDS[Track.F3], map(int, sentence.groups())):
        if not _close(float(refs[reference_id].value), float(mirrored)):
            raise _err(source, reference_id, "catalog differs from Markdown anchor")

def _parse_f1(raw: bytes, source: ArtifactRef, reference: ReferenceValue) -> F1Evidence:
    data = _json(raw, source)
    mcc = _num(data.get("mcc"), source, "mcc", -1.0, 1.0)
    reported = {key: _num(data.get(key), source, key, 0.0, 1.0) for key in ("accuracy", "precision", "recall", "specificity")}
    conf = _map(data.get("confusion"), source, "confusion")
    if set(conf) != {"tp", "fp", "tn", "fn"}:
        raise _err(source, "confusion", "expected tp/fp/tn/fn")
    tp, fp, tn, fn = (_int(conf[key], source, f"confusion.{key}", 0) for key in ("tp", "fp", "tn", "fn"))
    rows = _int(data.get("row_count"), source, "row_count", 1)
    if tp + fp + tn + fn != rows or rows != 2554:
        raise _err(source, "row_count", f"confusion sum must equal snapshot 2554, got {rows}")
    pos, neg = tp + fn, tn + fp
    if min(tp + fp, pos, neg) == 0:
        raise _err(source, "confusion", "zero MCC support")
    expected = {
        "accuracy": (tp + tn) / rows,
        "precision": tp / (tp + fp),
        "recall": tp / pos,
        "specificity": tn / neg,
        "mcc": (tp * tn - fp * fn) / math.sqrt((tp + fp) * pos * neg * (tn + fn)),
    }
    for key, value in expected.items():
        actual = mcc if key == "mcc" else reported[key]
        if not _close(actual, value):
            raise _err(source, key, f"recomputed {value}, source has {actual}")
    embedded_reference = _num(data.get("reference_mcc"), source, "reference_mcc", -1.0, 1.0)
    embedded_delta = _num(data.get("mcc_delta_from_reference"), source, "mcc_delta_from_reference", -2.0, 2.0)
    if not _close(embedded_reference, float(reference.value)):
        raise _err(source, "reference_mcc", "differs from catalog")
    if not _close(embedded_delta, mcc - embedded_reference):
        raise _err(source, "mcc_delta_from_reference", "must equal mcc - reference_mcc")
    return F1Evidence(mcc, rows, embedded_reference, embedded_delta)

def _parse_f2_task(key: str, task: dict[str, object], source: ArtifactRef) -> F2TaskEvidence:
    spec = {
        "immunogenicity": (1320, {"train": 1026, "valid": 149, "test": 145}, {"0": 684, "1": 636}, {"0": 0, "1": 1}, "auprc"),
        "glycosylation": (1683, {"train": 1356, "valid": 163, "test": 164}, {"0": 937, "1": 668, "2": 78}, {"N": 0, "O": 1, "free": 2}, "macro_f1"),
    }[key]
    rows, splits, labels, classes, metric = spec
    if _int(task.get("rows"), source, f"{key}.rows", 1) != rows:
        raise _err(source, f"{key}.rows", f"expected {rows}")
    _int_map(task.get("split_counts"), source, f"{key}.split_counts", splits)
    _int_map(task.get("label_counts"), source, f"{key}.label_counts", labels)
    class_map = _map(task.get("class_mapping"), source, f"{key}.class_mapping")
    if {str(k): _int(v, source, f"{key}.class_mapping.{k}") for k, v in class_map.items()} != classes:
        raise _err(source, f"{key}.class_mapping", "unexpected mapping")
    if task.get("report_metric") != metric:
        raise _err(source, f"{key}.report_metric", f"expected {metric}")
    _int(task.get("num_classes"), source, f"{key}.num_classes", 1)
    per_seed = _list(task.get("per_seed"), source, f"{key}.per_seed")
    if len(per_seed) != 3:
        raise _err(source, f"{key}.per_seed", f"expected 3 seeds, got {len(per_seed)}")
    values: dict[int, float] = {}
    for index, item in enumerate(per_seed):
        record = _map(item, source, f"{key}.per_seed[{index}]")
        seed = _int(record.get("seed"), source, f"{key}.per_seed[{index}].seed")
        test = _map(record.get("test"), source, f"{key}.per_seed[{index}].test")
        values[seed] = _num(test.get(metric), source, f"{key}.per_seed[{index}].test.{metric}", 0.0, 1.0)
    if set(values) != {0, 1, 2}:
        raise _err(source, f"{key}.per_seed", "expected seeds 0,1,2")
    aggregate = _map(task.get("aggregate"), source, f"{key}.aggregate")
    aggregate_key = f"test_{metric}"
    stat = _map(aggregate.get(aggregate_key), source, f"{key}.aggregate.{aggregate_key}")
    mean = _num(stat.get("mean"), source, f"{key}.aggregate.{aggregate_key}.mean", 0.0, 1.0)
    std = _num(stat.get("std"), source, f"{key}.aggregate.{aggregate_key}.std", 0.0)
    n = _int(stat.get("n"), source, f"{key}.aggregate.{aggregate_key}.n", 1)
    seeds = tuple(values[seed] for seed in (0, 1, 2))
    if not _close(mean, statistics.fmean(seeds)):
        raise _err(source, f"{key}.aggregate.{aggregate_key}.mean", "does not match three seeds")
    if not _close(std, statistics.stdev(seeds)):
        raise _err(source, f"{key}.aggregate.{aggregate_key}.std", "stdev does not match three seeds")
    if n != 3:
        raise _err(source, f"{key}.aggregate.{aggregate_key}.n", f"expected 3, got {n}")
    return F2TaskEvidence(key, metric, mean, std, seeds)
def _parse_f2(raw: bytes, source: ArtifactRef) -> tuple[F2TaskEvidence, ...]:
    data = _json(raw, source)
    for key, expected in (("status", "PASS"), ("benchmark", "GlycanML Table 3 RGCN F2 recompute"), ("mode", "full")):
        if data.get(key) != expected:
            raise _err(source, key, f"expected {expected!r}")
    training = _map(data.get("training"), source, "training")
    if _int(training.get("epochs"), source, "training.epochs", 1) != 50:
        raise _err(source, "training.epochs", "expected 50")
    if _int(training.get("batch_size"), source, "training.batch_size", 1) != 64:
        raise _err(source, "training.batch_size", "expected 64")
    if training.get("deterministic_seed_control") is not True:
        raise _err(source, "training.deterministic_seed_control", "expected true")
    seeds = [_int(seed, source, f"seeds[{index}]") for index, seed in enumerate(_list(data.get("seeds"), source, "seeds"))]
    if seeds != [0, 1, 2]:
        raise _err(source, "seeds", f"expected [0,1,2], got {seeds}")
    tasks = _map(data.get("tasks"), source, "tasks")
    if not {"immunogenicity", "glycosylation"}.issubset(tasks):
        raise _err(source, "tasks", "missing immunogenicity or glycosylation")
    return tuple(_parse_f2_task(key, _map(tasks[key], source, f"tasks.{key}"), source) for key in ("immunogenicity", "glycosylation"))

def _parse_f3(raw: bytes, source: ArtifactRef) -> F3Evidence:
    data = _json(raw, source)
    if data.get("model") != "qwen3:4b":
        raise _err(source, "model", "expected qwen3:4b")
    tasks = _int(data.get("tasks_run"), source, "tasks_run", 1)
    if tasks != 50 or _int(data.get("tools_available"), source, "tools_available", 1) != 70:
        raise _err(source, "tasks_run", "expected 50 tasks and 70 tools")
    if data.get("grader") != "not_run_upstream_requires_gpt4o_api_key":
        raise _err(source, "grader", "unexpected grader")
    values = {key: _int(data.get(key), source, key, 0) for key in (
        "exact_sequence", "all_expected_called", "any_expected_called", "tasks_with_tool_call",
        "tasks_with_final_answer", "tool_call_successes", "tool_calls",
    )}
    if not 0 <= values["exact_sequence"] <= values["all_expected_called"] <= values["any_expected_called"] <= tasks:
        raise _err(source, "exact_sequence", "sequence counts are not monotonic")
    if values["tasks_with_tool_call"] != tasks or values["tasks_with_final_answer"] > tasks:
        raise _err(source, "tasks_with_final_answer", "invalid task count")
    if values["tool_call_successes"] > values["tool_calls"]:
        raise _err(source, "tool_call_successes", "successes exceed calls")
    return F3Evidence("qwen3:4b", tasks, values["exact_sequence"], values["all_expected_called"], values["any_expected_called"], values["tasks_with_final_answer"], values["tool_call_successes"], values["tool_calls"])
def _read_counts(value: object, source: ArtifactRef, field: str) -> dict[Feasibility, int]:
    raw = _map(value, source, field)
    if set(raw) != {item.value for item in Feasibility}:
        raise _err(source, field, "expected exactly three feasibility categories")
    return {item: _int(raw[item.value], source, f"{field}.{item.value}", 0) for item in Feasibility}

def _parse_feasibility(csv_raw: bytes, csv_source: ArtifactRef, w2_raw: bytes, w2_source: ArtifactRef, recheck_raw: bytes, recheck_source: ArtifactRef) -> FeasibilitySnapshot:
    try:
        reader = csv.DictReader(io.StringIO(csv_raw.decode("utf-8-sig"), newline=""), strict=True)
        required = {"task_id", "original_category", "revised_category", "blocking_tools", "decision_reason", "evidence"}
        if not required.issubset(set(reader.fieldnames or ())):
            raise _err(csv_source, "header", "missing required columns")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise _err(csv_source, "invalid CSV", str(exc)) from exc
    if len(rows) != 50:
        raise _err(csv_source, "rows", f"expected 50 data rows, got {len(rows)}")
    ids: dict[Feasibility, list[int]] = {item: [] for item in Feasibility}
    seen: set[int] = set()
    original: Counter[str] = Counter()
    for index, row in enumerate(rows):
        if None in row:
            raise _err(csv_source, f"rows[{index}]", "extra column")
        try:
            raw_task_id = int(row["task_id"])
        except ValueError as exc:
            raise _err(csv_source, f"rows[{index}].task_id", "not an integer") from exc
        task_id = _int(raw_task_id, csv_source, f"rows[{index}].task_id", 1)
        if task_id in seen:
            raise _err(csv_source, "task_id", f"duplicate {task_id}")
        seen.add(task_id)
        try:
            old, new = Feasibility(row["original_category"]), Feasibility(row["revised_category"])
        except ValueError as exc:
            raise _err(csv_source, f"rows[{index}].category", str(exc)) from exc
        if new != Feasibility.DIRECT and (not row["blocking_tools"].strip() or not row["evidence"].strip()):
            raise _err(csv_source, f"rows[{index}]", "non-direct task needs blocker and evidence")
        ids[new].append(task_id)
        original[old.value] += 1
    if seen != set(range(1, 51)):
        raise _err(csv_source, "task_id", "expected ids 1..50")
    counts = {item: len(ids[item]) for item in Feasibility}
    if counts != FEAS_COUNTS:
        raise _err(csv_source, "revised_category", f"expected 43/5/2, got {counts}")
    if tuple(sorted(ids[Feasibility.REPLACEMENT])) != (5, 21, 28, 48, 50):
        raise _err(csv_source, "needs_replacement_tool", "task ids differ from 5,21,28,48,50")
    if tuple(sorted(ids[Feasibility.SERVICE])) != (20, 46):
        raise _err(csv_source, "service_failure", "task ids differ from 20,46")
    original_counts = {item: original[item.value] for item in Feasibility}
    if original_counts != ORIGINAL_COUNTS:
        raise _err(csv_source, "original_category", "expected 20/25/5")
    w2, recheck = _json(w2_raw, w2_source), _json(recheck_raw, recheck_source)
    if w2.get("status") != "PASS" or _read_counts(w2.get("category_counts"), w2_source, "category_counts") != ORIGINAL_COUNTS:
        raise _err(w2_source, "category_counts", "expected PASS and 20/25/5")
    if recheck.get("status") != "PASS":
        raise _err(recheck_source, "status", "expected PASS")
    reclass = _map(recheck.get("w2_task_reclassification"), recheck_source, "w2_task_reclassification")
    recheck_original = _read_counts(reclass.get("original_counts"), recheck_source, "w2_task_reclassification.original_counts")
    recheck_revised = _read_counts(reclass.get("revised_counts"), recheck_source, "w2_task_reclassification.revised_counts")
    if recheck_original != ORIGINAL_COUNTS:
        raise _err(recheck_source, "original_counts", "historical counts differ from W2 summary")
    if recheck_revised != counts:
        raise _err(recheck_source, "revised_counts", "counts differ from revised CSV")
    changed = sum(row["original_category"] != row["revised_category"] for row in rows)
    if _int(reclass.get("changed_tasks"), recheck_source, "changed_tasks", 0) != changed:
        raise _err(recheck_source, "changed_tasks", f"expected {changed}")
    validation = _map(recheck.get("validation"), recheck_source, "validation")
    for field, value, expected in (("unique_tools", validation.get("unique_tools"), 17), ("service_reachable", recheck.get("service_reachable"), 17), ("default_transport_ok", recheck.get("default_transport_ok"), 16)):
        if _int(value, recheck_source, field, 0) != expected:
            raise _err(recheck_source, field, f"expected {expected}")
    return FeasibilitySnapshot(50, tuple((item, counts[item]) for item in Feasibility), tuple((item, original_counts[item]) for item in Feasibility), tuple((item, tuple(sorted(ids[item]))) for item in Feasibility), changed, 17, 17, 16)

def _rows(f1: F1Evidence, f2: tuple[F2TaskEvidence, ...], f3: F3Evidence, refs: dict[str, ReferenceValue]) -> tuple[MetricRow, ...]:
    f1_ref = refs["ref.f1.esm150_lora.mcc"]
    rows = [MetricRow(
        "f1.esm150_lora.mcc", Track.F1, "ESM-2 150M LoRA 作者检查点", "MCC", Unit.MCC,
        LocalValue(f1.mcc, None, None, None, SourceRole.F1, "/mcc", None, None), f1_ref,
        Comparable(f1_ref.reference_id, f1.mcc - float(f1_ref.value), "作者检查点复算；差值方向为本地减参考。"),
    )]
    labels = {
        "immunogenicity": ("GlycanML 免疫原性", "AUPRC", Unit.AUPRC, "ref.f2.immunogenicity.auprc"),
        "glycosylation": ("GlycanML 糖基化", "Macro-F1", Unit.MACRO_F1, "ref.f2.glycosylation.macro_f1"),
    }
    for evidence in f2:
        subject, metric, unit, reference_id = labels[evidence.task]
        reference = refs[reference_id]
        locator = f"/tasks/{evidence.task}/aggregate/test_{evidence.report_metric}"
        rows.append(MetricRow(
            f"f2.{evidence.task}.{evidence.report_metric}", Track.F2, subject, metric, unit,
            LocalValue(evidence.mean, evidence.std, 3, None, SourceRole.F2, f"{locator}/mean", f"{locator}/std", None),
            reference, Comparable(reference_id, evidence.mean - float(reference.value), "论文 Table 3 RGCN 数值对照；本地为 PyG 自实现，不是 TorchDrug 逐位克隆。"),
        ))
    f3_refs = tuple(refs[reference_id] for reference_id in REF_IDS[Track.F3])
    claude_sentence = (
        f"工具轨迹或输出存在性，不是答案正确率。上游 Claude {f3_refs[0].value}/50、"
        f"Qwen3 {f3_refs[1].value}/50 使用 GPT-4o 评分，本轮未运行同一评分器，不能生成差值。"
    )
    f3_values = (
        ("exact_sequence", "精确工具序列", f3.exact_sequence, 50, "/exact_sequence", "/tasks_run"),
        ("all_expected_called", "全部期望工具已调用", f3.all_expected_called, 50, "/all_expected_called", "/tasks_run"),
        ("any_expected_called", "任一期望工具已调用", f3.any_expected_called, 50, "/any_expected_called", "/tasks_run"),
        ("tasks_with_final_answer", "存在最终回答", f3.tasks_with_final_answer, 50, "/tasks_with_final_answer", "/tasks_run"),
        ("tool_call_successes", "工具调用成功数", f3.tool_call_successes, f3.tool_calls, "/tool_call_successes", "/tool_calls"),
    )
    for key, metric, value, denominator, locator, denominator_locator in f3_values:
        rows.append(MetricRow(
            f"f3.qwen3_4b.{key}", Track.F3, "Qwen3 4B，50 道任务", metric, Unit.COUNT,
            LocalValue(value, None, None, denominator, SourceRole.F3, locator, None, denominator_locator),
            None, NotComparable(tuple(reference.reference_id for reference in f3_refs), claude_sentence),
        ))
    return tuple(rows)

def _validate(rows: tuple[MetricRow, ...], refs: dict[str, ReferenceValue], sources: SourceSet) -> None:
    expected_ids = {"f1.esm150_lora.mcc", "f2.immunogenicity.auprc", "f2.glycosylation.macro_f1", "f3.qwen3_4b.exact_sequence", "f3.qwen3_4b.all_expected_called", "f3.qwen3_4b.any_expected_called", "f3.qwen3_4b.tasks_with_final_answer", "f3.qwen3_4b.tool_call_successes"}
    if len(rows) != 8 or {row.metric_id for row in rows} != expected_ids:
        raise ScorecardValidationError("metrics: expected exactly eight core metric rows")
    for row in rows:
        if isinstance(row.comparison, Comparable):
            reference = refs[row.comparison.reference_id]
            if reference.track != row.track or reference.unit != row.unit:
                raise ScorecardValidationError(f"{row.metric_id}: reference unit or track mismatch")
            if not _close(row.comparison.delta_local_minus_reference, float(row.local.value) - float(reference.value)):
                raise ScorecardValidationError(f"{row.metric_id}: delta mismatch")
        elif row.track != Track.F3 or len(row.comparison.reference_ids) != 2:
            raise ScorecardValidationError(f"{row.metric_id}: unexpectedly not comparable")

def _build(repo: Path) -> Scorecard:
    raws, sources = _load(repo)
    references = _parse_references(raws[SourceRole.CATALOG], sources.by_role(SourceRole.CATALOG))
    refs = {reference.reference_id: reference for reference in references}
    _cross_check_mirror(raws[SourceRole.MIRROR], sources.by_role(SourceRole.MIRROR), refs)
    f1 = _parse_f1(raws[SourceRole.F1], sources.by_role(SourceRole.F1), refs["ref.f1.esm150_lora.mcc"])
    f2 = _parse_f2(raws[SourceRole.F2], sources.by_role(SourceRole.F2))
    f3 = _parse_f3(raws[SourceRole.F3], sources.by_role(SourceRole.F3))
    feasibility = _parse_feasibility(raws[SourceRole.CSV], sources.by_role(SourceRole.CSV), raws[SourceRole.W2], sources.by_role(SourceRole.W2), raws[SourceRole.RECHECK], sources.by_role(SourceRole.RECHECK))
    rows = _rows(f1, f2, f3, refs)
    _validate(rows, refs, sources)
    return Scorecard(SCHEMA, rows, references, feasibility, sources)
def _artifact_dict(pin: ArtifactRef) -> dict[str, object]:
    return {"role": pin.role.value, "path": pin.path, "sha256": pin.sha256, "byte_count": pin.byte_count}

def _reference_dict(reference: ReferenceValue) -> dict[str, object]:
    return {"reference_id": reference.reference_id, "track": reference.track.value, "label": reference.label, "value": reference.value, "std": reference.std, "n": reference.n, "denominator": reference.denominator, "unit": reference.unit.value, "citation": reference.citation}
def _metric_dict(row: MetricRow) -> dict[str, object]:
    local, reference, comparison = row.local, row.reference, row.comparison
    comparison_value = {"kind": "comparable", "reference_id": comparison.reference_id, "delta_local_minus_reference": comparison.delta_local_minus_reference, "scope_note": comparison.scope_note} if isinstance(comparison, Comparable) else {"kind": "not_comparable", "reference_ids": list(comparison.reference_ids), "reason": comparison.reason}
    return {
        "metric_id": row.metric_id, "track": row.track.value, "subject": row.subject,
        "metric": row.metric, "unit": row.unit.value, "local": {"value": local.value, "std": local.std, "n": local.n, "denominator": local.denominator, "source": local.source.value, "locator": local.locator, "std_locator": local.std_locator, "denominator_locator": local.denominator_locator},
        "reference": None if reference is None else _reference_dict(reference), "comparison": comparison_value,
    }
def _feasibility_dict(feasibility: FeasibilitySnapshot) -> dict[str, object]:
    return {"total_tasks": feasibility.total_tasks, "counts": {item.value: count for item, count in feasibility.counts}, "original_counts": {item.value: count for item, count in feasibility.original_counts}, "task_ids": {item.value: list(ids) for item, ids in feasibility.task_ids}, "changed_tasks": feasibility.changed_tasks, "rechecked_tools": feasibility.rechecked_tools, "service_reachable": feasibility.service_reachable, "default_transport_ok": feasibility.default_transport_ok, "comparison_note": "这是任务可用性分类，不是模型答案正确率。TLS 失败不等于服务死亡，HTTP 200 空数组也不等于任务可用。"}

def _render_json(card: Scorecard) -> bytes:
    payload = {
        "schema_version": card.schema_version, "status": "PASS", "policy": {"delta_sign": "local_minus_reference", "timestamp_policy": "no_wall_clock_timestamp", "f3_comparison": "trajectory_metrics_not_answer_accuracy", "f2_comparison": "paper_table_row_not_bitwise_clone"},
        "metrics": [_metric_dict(row) for row in card.metrics],
        "references": [_reference_dict(reference) for reference in card.references],
        "feasibility": _feasibility_dict(card.feasibility),
        "sources": [_artifact_dict(pin) for pin in card.sources.pins],
        "validations": {
            "metric_rows": len(card.metrics), "f1_row_count": 2554, "f2_seeds": 3,
            "f3_tasks": 50, "feasibility_total": 50,
        },
        "boundaries": [
            "F2 对齐 GlycanML Table 3；本地是 PyG 自实现，不是 TorchDrug 逐位克隆。",
            "F3 指标是工具轨迹与输出存在性，不是 GPT-4o 评分的答案正确率。",
            "get_proteins 的 TLS 校验失败不等于服务死亡，不能关闭生产 TLS 校验。",
            "get_ligands 的 HTTP 200 空数组不代表任务可用。",
        ],
    }
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")

CSV_FIELDS = ("metric_id", "track", "subject", "metric", "unit", "local_value", "local_std", "local_n", "local_denominator", "source_role", "source_path", "source_sha256", "source_locator", "source_std_locator", "source_denominator_locator", "reference_id", "reference_track", "reference_value", "reference_std", "reference_n", "reference_denominator", "delta_local_minus_reference", "comparison_kind", "comparison_note")
def _render_csv(card: Scorecard) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in card.metrics:
        pin = card.sources.by_role(row.local.source)
        reference = row.reference
        comparison = row.comparison
        writer.writerow({
            "metric_id": row.metric_id, "track": row.track.value, "subject": row.subject,
            "metric": row.metric, "unit": row.unit.value, "local_value": row.local.value,
            "local_std": row.local.std, "local_n": row.local.n,
            "local_denominator": row.local.denominator, "source_role": pin.role.value,
            "source_path": pin.path, "source_sha256": pin.sha256, "source_locator": row.local.locator,
            "source_std_locator": row.local.std_locator,
            "source_denominator_locator": row.local.denominator_locator,
            "reference_id": reference.reference_id if reference else "",
            "reference_track": reference.track.value if reference else "",
            "reference_value": reference.value if reference else "",
            "reference_std": reference.std if reference else "",
            "reference_n": reference.n if reference else "",
            "reference_denominator": reference.denominator if reference else "",
            "delta_local_minus_reference": comparison.delta_local_minus_reference if isinstance(comparison, Comparable) else "",
            "comparison_kind": "comparable" if isinstance(comparison, Comparable) else "not_comparable",
            "comparison_note": comparison.scope_note if isinstance(comparison, Comparable) else comparison.reason,
        })
    return buffer.getvalue().encode("utf-8")
def _fmt(value: int | float) -> str:
    return str(value)

def _render_markdown(card: Scorecard) -> bytes:
    f3_local = "、".join(f"{row.local.value}/{row.local.denominator}" for row in card.metrics if row.track == Track.F3)
    f3_refs = {reference.reference_id: reference for reference in card.references if reference.track == Track.F3}
    claude = next(ref for key, ref in f3_refs.items() if "claude" in key)
    qwen = next(ref for key, ref in f3_refs.items() if "qwen" in key)
    lines = [
        "# W2 Day 4 可重算记分卡", "",
        f"Schema：`{card.schema_version}`。由 `scripts/build_w2_scorecard.py` 从固定证据源生成，不包含运行时间。", "",
        "差值方向统一为 `local_minus_reference`。只有 F1 MCC、F2 AUPRC、F2 Macro-F1 生成差值。", "",
        "## 八条核心指标", "",
        "| 指标 ID | 赛道 | 对象 | 指标 | 本地值 | 本地标准差 | 参考值 | 参考标准差 | 差值（本地减参考） | 比较状态 | 口径 |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in card.metrics:
        reference = row.reference
        comparison = row.comparison
        if isinstance(comparison, Comparable):
            delta, status, note = f"{comparison.delta_local_minus_reference:+.17g}", "comparable", comparison.scope_note
        else:
            delta, status, note = "不计算", "not_comparable", comparison.reason
        lines.append(
            f"| `{row.metric_id}` | {row.track.value} | {row.subject} | {row.metric} | {(f'{row.local.value}/{row.local.denominator}' if row.local.denominator is not None else _fmt(row.local.value))} | "
            f"{'' if row.local.std is None else _fmt(row.local.std)} | "
            f"{'' if reference is None else _fmt(reference.value)} | "
            f"{'' if reference is None or reference.std is None else _fmt(reference.std)} | "
            f"{delta} | {status} | {note} |"
        )
    lines += [
        "", "## 工具可行性", "",
        "| 分类 | 题数 | task_id |", "|---|---:|---|",
    ]
    for category, count in card.feasibility.counts:
        ids = next(values for item, values in card.feasibility.task_ids if item == category)
        lines.append(f"| {FEAS_LABELS[category]} | {count} | {'、'.join(map(str, ids))} |")
    lines += [
        f"| 合计 | {card.feasibility.total_tasks} | 三类合计必须为 50 |", "",
        "## 口径边界", "",
        "- F2 对齐 GlycanML 论文 Table 3。本地是 PyG 自实现，不是 TorchDrug 逐位克隆，TorchDrug 未安装。",
        f"- F3 的 {f3_local} 是工具轨迹或输出存在性，不是答案正确率。",
        f"- 上游 Claude {claude.value}/50 和 Qwen3 {qwen.value}/50 使用 GPT-4o 评分，本轮未运行同一评分器，不能直接比较或计算差值。",
        "- W2 Day 3 工具可行性是任务可用性分类，不是模型准确率。`get_proteins` 的 TLS 校验失败不等于服务死亡。",
        "- `get_ligands` 返回 HTTP 200 空数组只说明服务可达，不代表任务可用。", "",
        "## 来源与哈希", "",
        "| 角色 | 路径 | SHA256 | 字节数 |", "|---|---|---|---:|",
    ]
    for pin in card.sources.pins:
        lines.append(f"| {pin.role.value} | `{pin.path}` | `{pin.sha256}` | {pin.byte_count} |")
    return ("\n".join(lines) + "\n").encode("utf-8")
def _render(card: Scorecard) -> dict[str, bytes]:
    return {"scorecard.json": _render_json(card), "scorecard.csv": _render_csv(card), "scorecard.md": _render_markdown(card)}

def _write_if_changed(path: Path, data: bytes) -> None:
    if path.exists() and path.read_bytes() == data: return
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def generate_scorecard(repo_root: Path = ROOT, out_dir: Path | None = None) -> Scorecard:
    repo = Path(repo_root).resolve()
    destination = Path(out_dir) if out_dir is not None else repo / "reports" / "w2_day4"
    card = _build(repo)
    for name, data in _render(card).items(): _write_if_changed(destination / name, data)
    return card
def check_scorecard(repo_root: Path = ROOT, out_dir: Path | None = None) -> None:
    repo = Path(repo_root).resolve()
    destination = Path(out_dir) if out_dir is not None else repo / "reports" / "w2_day4"
    card = _build(repo)
    stale = [name for name, data in _render(card).items() if not (destination / name).exists() or (destination / name).read_bytes() != data]
    if stale:
        raise ScorecardOutputError(f"scorecard outputs missing or stale: {', '.join(stale)}")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic W2 Day 4 F1/F2/F3 scorecard.")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check:
            check_scorecard(args.repo_root, args.out_dir); print("PASS: scorecard outputs are current")
        else:
            card = generate_scorecard(args.repo_root, args.out_dir)
            counts = "/".join(str(count) for _, count in card.feasibility.counts)
            print(f"PASS: generated {len(card.metrics)} metrics; feasibility {counts}")
        return 0
    except ScorecardValidationError as exc:
        print(f"SCORECARD ERROR: {exc}", file=sys.stderr); return 2
    except ScorecardOutputError as exc:
        print(f"SCORECARD CHECK ERROR: {exc}", file=sys.stderr); return 1
    except OSError as exc:
        print(f"SCORECARD IO ERROR: {exc}", file=sys.stderr); return 1
if __name__ == "__main__":
    raise SystemExit(main())
