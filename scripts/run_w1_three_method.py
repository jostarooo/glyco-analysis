"""Build the CPU-only W1 three-method comparison run.

The runner consumes immutable benchmark, 35M OOF, and 150M candidate-inference
artifacts. It never loads a model and writes all output files into a new
directory before publishing it with an atomic rename.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = REPO_ROOT / "reports" / "candidates_30.csv"
DEFAULT_ESM35_RUN_DIR = REPO_ROOT / "reports" / "esm35_linear_probe_v0"
DEFAULT_ESM150_RUN_DIR = REPO_ROOT / "reports" / "esm150_w1_candidates_v0"

SCHEMA = "glyco.w1-three-method/v1"
ESM35_SCHEMA = "glyco.esm35-linear-probe/v2"
ESM150_SCHEMA = "glyco.w1-esm150-candidates/v1"
BENCHMARK_ID = "experimental_positive_vs_unannotated_control"
REVIEW_POLICY_VERSION = "w1-disagreement-v1"

EXPECTED_CANDIDATES_SHA256 = (
    "A584C3814226B7287807676F65D5CFFE2F5D47A53BC00476A4B9945CB0719F1C"
)
EXPECTED_CANDIDATES_LORA_SHA256 = (
    "DBD51D28ABC0B0C74E78496E0A8F54CEBAA1C29F274B6E6B2716E39631A09FAB"
)
EXPECTED_ESM35_PREDICTIONS_SHA256 = (
    "6AE04C4C908BCC67A57E579C6402540D7E598A4E206387155AD6FBA94385ECA7"
)
EXPECTED_ESM35_METRICS_SHA256 = (
    "D09CF277944EACFEF082A2A07CCE8DD4F2225C424285A01F4B895160FA14AD61"
)
EXPECTED_ESM35_MANIFEST_SHA256 = (
    "927606335B13157BB8BBEEB3D790D0BB9AD649992D825BEEC3F4A53CE0697D9F"
)
EXPECTED_ADAPTER_SHA256 = (
    "A4A5B486862724F459F60E8343AC135C340305D5A0F2E936EB5AD1DFD34788D4"
)
EXPECTED_BASE_MODEL_ID = "facebook/esm2_t30_150M_UR50D"
EXPECTED_BASE_MODEL_REVISION = "a695f6045e2e32885fa60af20c13cb35398ce30c"
EXPECTED_BASE_WEIGHTS_SHA256 = (
    "C3F1DA8AEA53BDDD32C246C86168C23B9FD72341FB9DB9A94436F855F5053566"
)

EXPECTED_ROWS = 201
EXPECTED_PROTEINS = 29
EXPECTED_EVALUATED_ROWS = 130
EXPECTED_EVALUATED_PROTEINS = 28
EXPECTED_EXPERIMENTAL = 82
EXPECTED_INFERRED = 71
EXPECTED_CONTROLS = 48
REVIEW_LIMIT = 10
FLOAT_TOLERANCE = 1e-15

CANDIDATE_COLUMNS = (
    "accession",
    "protein_name",
    "seq_len",
    "pos",
    "residue",
    "motif",
    "sequon",
    "label",
    "linkage",
    "n_features",
    "evidence",
    "uniprot_release",
    "fetched_at",
)
ESM35_COLUMNS = (
    "row_id",
    "accession",
    "pos",
    "label",
    "fold_id",
    "logit",
    "probability",
    "prediction",
)
ESM150_COLUMNS = (
    "row_index",
    "accession",
    "position",
    "label",
    "sequence_sha256",
    "sequence_length",
    "token_length",
    "residue",
    "motif",
    "is_sequon",
    "logit_negative",
    "logit_positive",
    "prob_negative",
    "prob_positive",
    "predicted_label",
)
COMPARISON_COLUMNS = (
    "row_id",
    "accession",
    "protein_name",
    "pos",
    "motif",
    "seq_len",
    "uniprot_release",
    "uniprot_evidence",
    "n_features",
    "evidence_class",
    "evaluation_included",
    "evaluation_label",
    "uniprot_prediction",
    "sequence_rule_prediction",
    "esm35_row_id",
    "esm35_fold_id",
    "esm35_probability",
    "esm35_prediction",
    "esm150_row_index",
    "esm150_probability",
    "esm150_prediction",
    "available_method_count",
    "disagreement_pattern",
    "review_rank",
)
REVIEW_COLUMNS = (
    "rank",
    "selection_stratum",
    "row_id",
    "accession",
    "protein_name",
    "pos",
    "motif",
    "seq_len",
    "uniprot_release",
    "uniprot_evidence",
    "n_features",
    "evidence_class",
    "evaluation_label",
    "uniprot_prediction",
    "sequence_rule_prediction",
    "esm35_probability",
    "esm35_prediction",
    "esm35_fold_id",
    "esm150_probability",
    "esm150_prediction",
    "disagreement_pattern",
    "ranking_confidence",
    "selection_criteria",
    "manual_review_question",
    "review_status",
    "reviewer_note",
)
ARTIFACT_NAMES = (
    "comparison.csv",
    "review_top10.csv",
    "metrics.json",
    "report.md",
)

EXPERIMENTAL_CODE = "ECO:0000269"
INFERRED_CODE = "ECO:0000255"
ECO_CODE = re.compile(r"ECO:\d{7}\Z")
SEQUON = re.compile(r"N[^P][ST]\Z")

STRATA_ORDER = (
    "both_models_oppose_experimental_positive",
    "both_models_call_unannotated_control_positive",
    "esm35_opposes_experimental_positive",
    "esm150_opposes_experimental_positive",
    "esm35_calls_unannotated_control_positive",
    "esm150_calls_unannotated_control_positive",
)


class ComparisonError(RuntimeError):
    pass


@dataclass(frozen=True)
class ComparisonConfig:
    candidates: Path
    esm35_run_dir: Path
    esm150_run_dir: Path
    out_dir: Path


@dataclass(frozen=True)
class AnnotationSite:
    row_index: int
    key: tuple[str, int]
    protein_name: str
    seq_len: int
    motif: str
    n_features: int
    source_label: int
    evidence: tuple[str, ...]
    evidence_class: str
    evaluation_included: bool
    evaluation_label: int | None
    uniprot_release: str
    raw_evidence: str


@dataclass(frozen=True)
class MethodVote:
    method_id: str
    key: tuple[str, int]
    probability: float | None
    prediction: int | None
    source_row_id: str
    source_row_index: int
    source_artifact_sha256: str
    extra: Mapping[str, object]


@dataclass(frozen=True)
class ComparedSite:
    site: AnnotationSite
    uniprot_prediction: int
    sequence_rule_prediction: int
    esm35: MethodVote | None
    esm150: MethodVote
    disagreement_pattern: str
    review_rank: int | None


@dataclass(frozen=True)
class ReviewRow:
    rank: int
    stratum: str
    compared: ComparedSite
    ranking_confidence: float
    selection_criteria: str


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"JSON input not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComparisonError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ComparisonError(f"JSON object required: {path}")
    return value


def read_csv_exact(path: Path, columns: Sequence[str]) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV input not found: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != tuple(columns):
            raise ComparisonError(
                f"CSV header mismatch for {path}: {reader.fieldnames!r}"
            )
        rows = list(reader)
    return rows


def write_csv(
    path: Path,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def path_record(path: Path) -> dict[str, object]:
    return {
        "path": display_path(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def require_expected_hash(path: Path, expected: str, label: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise ComparisonError(
            f"{label} SHA256 mismatch: {actual} != {expected}"
        )


def verify_artifact_records(
    run_dir: Path,
    manifest: Mapping[str, Any],
    required: Sequence[str],
) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ComparisonError(f"{run_dir.name} manifest artifacts must be an object")
    for name in required:
        record = artifacts.get(name)
        if not isinstance(record, dict):
            raise ComparisonError(f"missing artifact record: {name}")
        path = run_dir / name
        if not path.is_file():
            raise ComparisonError(f"missing artifact: {path}")
        if record.get("bytes") != path.stat().st_size:
            raise ComparisonError(f"artifact byte count mismatch: {name}")
        if record.get("sha256") != sha256_file(path):
            raise ComparisonError(f"artifact SHA256 mismatch: {name}")


def parse_evidence(raw: str, row_id: str) -> tuple[str, ...]:
    codes = tuple(sorted({part.strip() for part in raw.split(";") if part.strip()}))
    for code in codes:
        if ECO_CODE.fullmatch(code) is None:
            raise ComparisonError(f"{row_id} has invalid evidence code {code!r}")
    return codes


def classify_evidence(label: int, codes: Sequence[str], row_id: str) -> str:
    evidence = frozenset(codes)
    if label == 1:
        if not evidence:
            raise ComparisonError(f"{row_id} is positive but has no evidence")
        if EXPERIMENTAL_CODE in evidence:
            return "experimental_positive"
        if evidence == {INFERRED_CODE}:
            return "inferred_positive"
        raise ComparisonError(f"{row_id} has unsupported evidence {sorted(evidence)}")
    if evidence:
        raise ComparisonError(f"{row_id} is a control but has evidence {sorted(evidence)}")
    return "unannotated_control"


def load_annotation_sites(path: Path) -> tuple[list[AnnotationSite], str]:
    require_expected_hash(path, EXPECTED_CANDIDATES_SHA256, "candidate table")
    raw_rows = read_csv_exact(path, CANDIDATE_COLUMNS)
    if len(raw_rows) != EXPECTED_ROWS:
        raise ComparisonError(f"candidate row count {len(raw_rows)} != {EXPECTED_ROWS}")

    sites: list[AnnotationSite] = []
    seen: set[tuple[str, int]] = set()
    release: str | None = None
    for row_index, raw in enumerate(raw_rows):
        try:
            position = int(raw["pos"])
            seq_len = int(raw["seq_len"])
            n_features = int(raw["n_features"])
        except ValueError as error:
            raise ComparisonError(f"non-integer numeric field in row {row_index}") from error
        key = (raw["accession"], position)
        row_id = f"{key[0]}:{key[1]}"
        if key in seen:
            raise ComparisonError(f"duplicate candidate key: {row_id}")
        seen.add(key)
        if raw["label"] not in {"0", "1"}:
            raise ComparisonError(f"{row_id} has invalid label")
        label = int(raw["label"])
        if raw["residue"] != "N":
            raise ComparisonError(f"{row_id} residue is not N")
        if raw["sequon"] != "1" or SEQUON.fullmatch(raw["motif"]) is None:
            raise ComparisonError(f"{row_id} is not a valid N-X-S/T sequon")
        if not 1 <= position <= seq_len:
            raise ComparisonError(f"{row_id} is outside its sequence")
        if label != int(raw["linkage"] == "N-linked"):
            raise ComparisonError(f"{row_id} label and linkage disagree")
        if release is None:
            release = raw["uniprot_release"]
        elif raw["uniprot_release"] != release:
            raise ComparisonError("candidate table contains multiple UniProt releases")

        evidence = parse_evidence(raw["evidence"], row_id)
        evidence_class = classify_evidence(label, evidence, row_id)
        included = evidence_class in {
            "experimental_positive",
            "unannotated_control",
        }
        sites.append(
            AnnotationSite(
                row_index=row_index,
                key=key,
                protein_name=raw["protein_name"],
                seq_len=seq_len,
                motif=raw["motif"],
                n_features=n_features,
                source_label=label,
                evidence=evidence,
                evidence_class=evidence_class,
                evaluation_included=included,
                evaluation_label=label if included else None,
                uniprot_release=raw["uniprot_release"],
                raw_evidence=raw["evidence"],
            )
        )

    sites.sort(key=lambda site: site.key)
    protein_count = len({site.key[0] for site in sites})
    evaluated = [site for site in sites if site.evaluation_included]
    class_counts = {
        name: sum(site.evidence_class == name for site in sites)
        for name in (
            "experimental_positive",
            "inferred_positive",
            "unannotated_control",
        )
    }
    if protein_count != EXPECTED_PROTEINS:
        raise ComparisonError(f"protein count {protein_count} != {EXPECTED_PROTEINS}")
    if len(evaluated) != EXPECTED_EVALUATED_ROWS:
        raise ComparisonError(
            f"evaluated row count {len(evaluated)} != {EXPECTED_EVALUATED_ROWS}"
        )
    if class_counts != {
        "experimental_positive": EXPECTED_EXPERIMENTAL,
        "inferred_positive": EXPECTED_INFERRED,
        "unannotated_control": EXPECTED_CONTROLS,
    }:
        raise ComparisonError(f"evidence-class counts do not match contract: {class_counts}")
    if len({site.key[0] for site in evaluated}) != EXPECTED_EVALUATED_PROTEINS:
        raise ComparisonError("evaluated protein count does not match contract")
    p13611 = [site for site in sites if site.key[0] == "P13611"]
    if not p13611 or any(site.evaluation_included for site in p13611):
        raise ComparisonError("P13611 must contain only inferred display-only rows")
    return sites, sha256_file(path)


def _metric_value_equal(actual: object, expected: object) -> bool:
    if actual is None or expected is None:
        return actual is expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(
            float(actual),
            float(expected),
            rel_tol=0.0,
            abs_tol=FLOAT_TOLERANCE,
        )
    return actual == expected


def _check_esm35_metrics(
    labels: Sequence[int],
    predictions: Sequence[int],
    probabilities: Sequence[float],
    stored: Mapping[str, Any],
) -> None:
    if stored.get("schema") != ESM35_SCHEMA:
        raise ComparisonError("35M metrics schema mismatch")
    if stored.get("benchmark_id") != BENCHMARK_ID:
        raise ComparisonError("35M metrics benchmark mismatch")
    if stored.get("threshold") != 0.5:
        raise ComparisonError("35M metrics threshold mismatch")

    recomputed = binary_metrics(labels, predictions, probabilities)
    confusion = recomputed["confusion"]
    stored_confusion = stored.get("confusion")
    if not isinstance(stored_confusion, dict):
        raise ComparisonError("35M metrics confusion is missing")
    expected_groups = {
        "experimental_positive": {
            "predicted_positive": confusion["tp"],
            "predicted_control": confusion["fn"],
        },
        "unannotated_control": {
            "predicted_positive": confusion["fp"],
            "predicted_control": confusion["tn"],
        },
    }
    if stored_confusion != expected_groups:
        raise ComparisonError("stored 35M confusion disagrees with predictions")
    stored_metrics = stored.get("metrics")
    if not isinstance(stored_metrics, dict):
        raise ComparisonError("35M metrics metrics block is missing")
    for name, expected in recomputed["metrics"].items():
        if not _metric_value_equal(stored_metrics.get(name), expected):
            raise ComparisonError(
                f"stored 35M metric {name}={stored_metrics.get(name)!r} "
                f"does not equal {expected!r}"
            )
    if stored.get("null_reasons") != recomputed["null_reasons"]:
        raise ComparisonError("stored 35M null reasons disagree with predictions")


def load_esm35_votes(
    run_dir: Path,
    annotation_sites: Sequence[AnnotationSite],
) -> dict[tuple[str, int], MethodVote]:
    manifest_path = run_dir / "manifest.json"
    metrics_path = run_dir / "metrics.json"
    predictions_path = run_dir / "predictions.csv"
    require_expected_hash(
        predictions_path, EXPECTED_ESM35_PREDICTIONS_SHA256, "35M predictions"
    )
    require_expected_hash(metrics_path, EXPECTED_ESM35_METRICS_SHA256, "35M metrics")
    require_expected_hash(manifest_path, EXPECTED_ESM35_MANIFEST_SHA256, "35M manifest")

    manifest = load_json(manifest_path)
    if manifest.get("schema") != ESM35_SCHEMA or manifest.get("status") != "complete":
        raise ComparisonError("35M manifest is not a complete supported run")
    verify_artifact_records(run_dir, manifest, ("predictions.csv", "metrics.json"))
    candidate_record = manifest.get("inputs", {}).get("candidates", {})
    if candidate_record.get("sha256") != EXPECTED_CANDIDATES_SHA256:
        raise ComparisonError("35M manifest candidate hash mismatch")

    raw_rows = read_csv_exact(predictions_path, ESM35_COLUMNS)
    honest = {
        site.key: site
        for site in annotation_sites
        if site.evaluation_included
    }
    if len(raw_rows) != EXPECTED_EVALUATED_ROWS:
        raise ComparisonError(f"35M row count {len(raw_rows)} != {EXPECTED_EVALUATED_ROWS}")

    votes: dict[tuple[str, int], MethodVote] = {}
    labels: list[int] = []
    predictions: list[int] = []
    probabilities: list[float] = []
    artifact_sha = sha256_file(predictions_path)
    for row_index, raw in enumerate(raw_rows):
        try:
            position = int(raw["pos"])
            label = int(raw["label"])
            prediction = int(raw["prediction"])
            probability = float(raw["probability"])
        except ValueError as error:
            raise ComparisonError(f"invalid numeric 35M row {row_index}") from error
        key = (raw["accession"], position)
        site = honest.get(key)
        if site is None:
            raise ComparisonError(f"35M key is outside the honest population: {key}")
        if key in votes:
            raise ComparisonError(f"duplicate 35M key: {key}")
        if label != site.evaluation_label:
            raise ComparisonError(f"35M label mismatch at {key}")
        if raw["fold_id"] != f"lopo:{key[0]}":
            raise ComparisonError(f"35M fold mismatch at {key}")
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ComparisonError(f"invalid 35M probability at {key}")
        expected_prediction = int(probability >= 0.5)
        if prediction != expected_prediction:
            raise ComparisonError(f"35M threshold mismatch at {key}")
        if raw["row_id"] != f"{key[0]}:{key[1]}":
            raise ComparisonError(f"35M row_id mismatch at {key}")
        votes[key] = MethodVote(
            method_id="esm35_oof",
            key=key,
            probability=probability,
            prediction=prediction,
            source_row_id=raw["row_id"],
            source_row_index=row_index,
            source_artifact_sha256=artifact_sha,
            extra={"fold_id": raw["fold_id"]},
        )
        labels.append(label)
        predictions.append(prediction)
        probabilities.append(probability)

    if set(votes) != set(honest):
        missing = sorted(set(honest) - set(votes))
        extra = sorted(set(votes) - set(honest))
        raise ComparisonError(
            f"35M exact key-set mismatch; missing={missing[:5]} extra={extra[:5]}"
        )
    _check_esm35_metrics(labels, predictions, probabilities, load_json(metrics_path))
    return votes


def softmax_two(negative: float, positive: float) -> tuple[float, float]:
    maximum = max(negative, positive)
    exp_negative = math.exp(negative - maximum)
    exp_positive = math.exp(positive - maximum)
    total = exp_negative + exp_positive
    return exp_negative / total, exp_positive / total


def _manifest_count(
    manifest: Mapping[str, Any],
    names: Sequence[str],
) -> int | None:
    for container_name in ("counts", "inference"):
        container = manifest.get(container_name)
        if not isinstance(container, dict):
            continue
        for name in names:
            value = container.get(name)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return None


def load_esm150_votes(
    run_dir: Path,
    annotation_sites: Sequence[AnnotationSite],
) -> dict[tuple[str, int], MethodVote]:
    manifest_path = run_dir / "manifest.json"
    predictions_path = run_dir / "predictions.csv"
    manifest = load_json(manifest_path)
    if manifest.get("schema") != ESM150_SCHEMA or manifest.get("status") != "complete":
        raise ComparisonError("150M manifest is not a complete supported run")
    verify_artifact_records(run_dir, manifest, ("predictions.csv", "report.md"))

    inputs = manifest.get("inputs", {})
    candidate_record = inputs.get("candidates_lora", {})
    if candidate_record.get("sha256") != EXPECTED_CANDIDATES_LORA_SHA256:
        raise ComparisonError("150M manifest candidate-LoRA hash mismatch")
    adapter_record = inputs.get("adapter", {})
    if adapter_record.get("model_sha256") != EXPECTED_ADAPTER_SHA256:
        raise ComparisonError("150M manifest adapter hash mismatch")
    base_record = inputs.get("base_model", {})
    if base_record.get("id") != EXPECTED_BASE_MODEL_ID:
        raise ComparisonError("150M manifest base model id mismatch")
    if base_record.get("revision") != EXPECTED_BASE_MODEL_REVISION:
        raise ComparisonError("150M manifest base revision mismatch")
    if base_record.get("weights_sha256") != EXPECTED_BASE_WEIGHTS_SHA256:
        raise ComparisonError("150M manifest base weights hash mismatch")

    recorded_rows = candidate_record.get("row_count")
    if recorded_rows is not None and recorded_rows != EXPECTED_ROWS:
        raise ComparisonError("150M manifest candidate row count mismatch")
    inference_rows = _manifest_count(manifest, ("rows", "prediction_rows", "row_count"))
    if inference_rows is not None and inference_rows != EXPECTED_ROWS:
        raise ComparisonError("150M manifest inference row count mismatch")

    raw_rows = read_csv_exact(predictions_path, ESM150_COLUMNS)
    if len(raw_rows) != EXPECTED_ROWS:
        raise ComparisonError(f"150M row count {len(raw_rows)} != {EXPECTED_ROWS}")
    sites = {site.key: site for site in annotation_sites}
    votes: dict[tuple[str, int], MethodVote] = {}
    artifact_sha = sha256_file(predictions_path)
    for expected_index, raw in enumerate(raw_rows):
        try:
            row_index = int(raw["row_index"])
            position = int(raw["position"])
            label = int(raw["label"])
            sequence_length = int(raw["sequence_length"])
            logit_negative = float(raw["logit_negative"])
            logit_positive = float(raw["logit_positive"])
            prob_negative = float(raw["prob_negative"])
            prob_positive = float(raw["prob_positive"])
            prediction = int(raw["predicted_label"])
        except ValueError as error:
            raise ComparisonError(f"invalid numeric 150M row {expected_index}") from error
        key = (raw["accession"], position)
        site = sites.get(key)
        if site is None:
            raise ComparisonError(f"150M key is outside the candidate table: {key}")
        if key in votes:
            raise ComparisonError(f"duplicate 150M key: {key}")
        if row_index != expected_index:
            raise ComparisonError(f"150M row_index mismatch at {key}")
        if label != site.source_label:
            raise ComparisonError(f"150M source label mismatch at {key}")
        if sequence_length != site.seq_len:
            raise ComparisonError(f"150M sequence length mismatch at {key}")
        if raw["residue"] != "N" or raw["motif"] != site.motif:
            raise ComparisonError(f"150M residue/motif mismatch at {key}")
        if raw["is_sequon"] != "1":
            raise ComparisonError(f"150M sequon flag mismatch at {key}")
        values = (
            logit_negative,
            logit_positive,
            prob_negative,
            prob_positive,
        )
        if not all(math.isfinite(value) for value in values):
            raise ComparisonError(f"150M non-finite value at {key}")
        if not 0.0 <= prob_negative <= 1.0 or not 0.0 <= prob_positive <= 1.0:
            raise ComparisonError(f"150M probability outside [0,1] at {key}")
        if not math.isclose(
            prob_negative + prob_positive,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ComparisonError(f"150M probabilities do not sum to one at {key}")
        expected_negative, expected_positive = softmax_two(
            logit_negative, logit_positive
        )
        if not math.isclose(
            prob_negative, expected_negative, rel_tol=0.0, abs_tol=1e-12
        ) or not math.isclose(
            prob_positive, expected_positive, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ComparisonError(f"150M softmax mismatch at {key}")
        expected_prediction = int(logit_positive > logit_negative)
        if prediction != expected_prediction:
            raise ComparisonError(f"150M argmax mismatch at {key}")
        votes[key] = MethodVote(
            method_id="esm150_author_adapter",
            key=key,
            probability=prob_positive,
            prediction=prediction,
            source_row_id=str(row_index),
            source_row_index=row_index,
            source_artifact_sha256=artifact_sha,
            extra={
                "logit_negative": logit_negative,
                "logit_positive": logit_positive,
                "sequence_sha256": raw["sequence_sha256"],
            },
        )

    if set(votes) != set(sites):
        missing = sorted(set(sites) - set(votes))
        extra = sorted(set(votes) - set(sites))
        raise ComparisonError(
            f"150M exact key-set mismatch; missing={missing[:5]} extra={extra[:5]}"
        )
    return votes


def _disagreement_pattern(
    site: AnnotationSite,
    esm35_prediction: int,
    esm150_prediction: int,
) -> str:
    if not site.evaluation_included:
        return "display_only_inferred"
    if site.evaluation_label == 1:
        if esm35_prediction == 0 and esm150_prediction == 0:
            return "both_models_oppose_experimental_positive"
        if esm35_prediction == 0:
            return "esm35_opposes_experimental_positive"
        if esm150_prediction == 0:
            return "esm150_opposes_experimental_positive"
        return "all_agree"
    if site.evaluation_label == 0:
        if esm35_prediction == 1 and esm150_prediction == 1:
            return "both_models_call_unannotated_control_positive"
        if esm35_prediction == 1:
            return "esm35_calls_unannotated_control_positive"
        if esm150_prediction == 1:
            return "esm150_calls_unannotated_control_positive"
        return "all_agree"
    raise AssertionError("honest row has no evaluation label")


def build_comparison(
    sites: Sequence[AnnotationSite],
    esm35: Mapping[tuple[str, int], MethodVote],
    esm150: Mapping[tuple[str, int], MethodVote],
) -> list[ComparedSite]:
    compared: list[ComparedSite] = []
    for site in sorted(sites, key=lambda item: item.key):
        vote150 = esm150.get(site.key)
        if vote150 is None or vote150.prediction is None:
            raise ComparisonError(f"missing 150M vote for {site.key}")
        vote35 = esm35.get(site.key)
        if site.evaluation_included:
            if vote35 is None or vote35.prediction is None:
                raise ComparisonError(f"missing 35M vote for honest row {site.key}")
            pattern = _disagreement_pattern(
                site, int(vote35.prediction), int(vote150.prediction)
            )
        else:
            if vote35 is not None:
                raise ComparisonError(f"inferred row has a 35M vote: {site.key}")
            pattern = "display_only_inferred"
        compared.append(
            ComparedSite(
                site=site,
                uniprot_prediction=int(site.source_label),
                sequence_rule_prediction=1,
                esm35=vote35,
                esm150=vote150,
                disagreement_pattern=pattern,
                review_rank=None,
            )
        )
    return compared


def roc_auc(labels: Sequence[int], probabilities: Sequence[float]) -> float | None:
    positives = [score for label, score in zip(labels, probabilities) if label == 1]
    controls = [score for label, score in zip(labels, probabilities) if label == 0]
    if not positives or not controls:
        return None
    wins = 0.0
    for positive in positives:
        for control in controls:
            if positive > control:
                wins += 1.0
            elif positive == control:
                wins += 0.5
    return wins / (len(positives) * len(controls))


def binary_metrics(
    labels: Sequence[int],
    predictions: Sequence[int],
    probabilities: Sequence[float] | None,
) -> dict[str, object]:
    if len(labels) != len(predictions):
        raise ComparisonError("labels and predictions have different lengths")
    if probabilities is not None and len(labels) != len(probabilities):
        raise ComparisonError("labels and probabilities have different lengths")
    if not labels:
        raise ComparisonError("metrics require at least one row")
    if any(value not in (0, 1) for value in labels):
        raise ComparisonError("labels must be binary")
    if any(value not in (0, 1) for value in predictions):
        raise ComparisonError("predictions must be binary")
    if probabilities is not None and any(
        not math.isfinite(value) for value in probabilities
    ):
        raise ComparisonError("probabilities must be finite")

    tp = sum(label == 1 and prediction == 1 for label, prediction in zip(labels, predictions))
    fn = sum(label == 1 and prediction == 0 for label, prediction in zip(labels, predictions))
    tn = sum(label == 0 and prediction == 0 for label, prediction in zip(labels, predictions))
    fp = sum(label == 0 and prediction == 1 for label, prediction in zip(labels, predictions))
    mcc_denominator = math.sqrt(
        (tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)
    )
    mcc_defined = mcc_denominator > 0.0
    mcc_value = (
        (tp * tn - fp * fn) / mcc_denominator if mcc_defined else 0.0
    )
    positive_denominator = tp + fn
    control_denominator = tn + fp
    precision_denominator = tp + fp
    null_reasons: dict[str, str] = {}
    positive_recall = (
        tp / positive_denominator if positive_denominator else None
    )
    if positive_recall is None:
        null_reasons["positive_recall"] = "no_evaluation_positives"
    control_specificity = (
        tn / control_denominator if control_denominator else None
    )
    if control_specificity is None:
        null_reasons["control_specificity"] = "no_evaluation_controls"
    positive_precision = (
        tp / precision_denominator if precision_denominator else None
    )
    if positive_precision is None:
        null_reasons["positive_precision"] = "no_positive_predictions"
    auc = roc_auc(labels, probabilities) if probabilities is not None else None
    if probabilities is None:
        null_reasons["roc_auc"] = "method_has_no_continuous_score"
    elif auc is None:
        null_reasons["roc_auc"] = "requires_both_label_classes"
    return {
        "evaluation_rows": len(labels),
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "metrics": {
            "mcc": mcc_value,
            "positive_recall": positive_recall,
            "control_specificity": control_specificity,
            "positive_precision": positive_precision,
            "weak_label_accuracy": (tp + tn) / len(labels),
            "roc_auc": auc,
        },
        "mcc_defined": mcc_defined,
        "null_reasons": null_reasons,
    }


def _vote_probabilities(votes: Sequence[MethodVote | None]) -> list[float]:
    values: list[float] = []
    for vote in votes:
        if vote is None or vote.probability is None:
            raise ComparisonError("missing probability")
        values.append(float(vote.probability))
    return values


def compute_metrics(compared: Sequence[ComparedSite]) -> dict[str, object]:
    honest = [row for row in compared if row.site.evaluation_included]
    if len(honest) != EXPECTED_EVALUATED_ROWS:
        raise ComparisonError("metric population must contain exactly 130 rows")
    labels = [int(row.site.evaluation_label) for row in honest]
    rule_predictions = [row.sequence_rule_prediction for row in honest]
    predictions35 = [int(row.esm35.prediction) for row in honest if row.esm35]
    probabilities35 = _vote_probabilities([row.esm35 for row in honest])
    predictions150 = [int(row.esm150.prediction) for row in honest]
    probabilities150 = _vote_probabilities([row.esm150 for row in honest])
    if len(predictions35) != len(honest):
        raise ComparisonError("35M predictions are incomplete")

    method_metadata = {
        "sequon_rule": {
            "prediction_rule": "always positive; every row is an N-X-S/T sequon",
            "independent_of_benchmark": True,
            "score_kind": "fixed_binary",
        },
        "esm35_oof": {
            "prediction_rule": "stored probability >= 0.5",
            "independent_of_benchmark": True,
            "score_kind": "probability",
        },
        "esm150_author_adapter": {
            "prediction_rule": "logit_positive > logit_negative",
            "independent_of_benchmark": True,
            "score_kind": "probability",
        },
    }
    results = {
        "sequon_rule": binary_metrics(labels, rule_predictions, None),
        "esm35_oof": binary_metrics(labels, predictions35, probabilities35),
        "esm150_author_adapter": binary_metrics(
            labels, predictions150, probabilities150
        ),
    }
    methods: dict[str, object] = {}
    for method_id in (
        "sequon_rule",
        "esm35_oof",
        "esm150_author_adapter",
    ):
        payload = dict(method_metadata[method_id])
        payload.update(results[method_id])
        methods[method_id] = payload

    reference = binary_metrics(
        labels,
        [int(row.uniprot_prediction) for row in honest],
        None,
    )
    inferred = [row for row in compared if not row.site.evaluation_included]
    pattern_counts = {
        pattern: sum(row.disagreement_pattern == pattern for row in honest)
        for pattern in (*STRATA_ORDER, "all_agree")
    }
    return {
        "schema": SCHEMA,
        "benchmark": {
            "id": BENCHMARK_ID,
            "source_rows": len(compared),
            "evaluation_rows": len(honest),
            "experimental_positive": sum(labels),
            "unannotated_control": len(labels) - sum(labels),
            "inferred_display_only": len(inferred),
            "proteins": len({row.site.key[0] for row in honest}),
            "inferred_excluded_from_metrics": True,
            "controls_are_not_confirmed_negatives": True,
            "label_source": "UniProt N-linked annotation",
        },
        "methods": methods,
        "benchmark_reference": {
            "id": "uniprot_annotation",
            "role": "label_source_and_reference_ceiling",
            "independent_of_benchmark": False,
            **reference,
        },
        "display_only": {
            "inferred_positive_rows": len(inferred),
            "uniprot_annotation_positive": sum(
                row.uniprot_prediction for row in inferred
            ),
            "esm35": "not_available_by_construction",
            "esm150_predicted_positive": sum(
                int(row.esm150.prediction) for row in inferred
            ),
        },
        "disagreement_counts": pattern_counts,
        "comparability_caveat": (
            "35M scores are windowed leave-one-protein-out OOF estimates; "
            "150M scores are full-sequence author-adapter inference. A difference "
            "cannot be attributed to model size alone."
        ),
    }


def _margin(vote: MethodVote, predicted_positive: bool) -> float:
    if vote.probability is None:
        return 0.0
    probability = float(vote.probability)
    if predicted_positive:
        return 2.0 * abs(probability - 0.5)
    return 2.0 * abs(probability - 0.5)


def review_stratum(row: ComparedSite) -> str | None:
    if not row.site.evaluation_included or row.esm35 is None:
        return None
    prediction35 = int(row.esm35.prediction)
    prediction150 = int(row.esm150.prediction)
    label = int(row.site.evaluation_label)
    if label == 1:
        if prediction35 == 0 and prediction150 == 0:
            return "both_models_oppose_experimental_positive"
        if prediction35 == 0:
            return "esm35_opposes_experimental_positive"
        if prediction150 == 0:
            return "esm150_opposes_experimental_positive"
    else:
        if prediction35 == 1 and prediction150 == 1:
            return "both_models_call_unannotated_control_positive"
        if prediction35 == 1:
            return "esm35_calls_unannotated_control_positive"
        if prediction150 == 1:
            return "esm150_calls_unannotated_control_positive"
    return None


def review_confidence(row: ComparedSite) -> float:
    label = int(row.site.evaluation_label)
    margins: list[float] = []
    if row.esm35 is not None:
        prediction = int(row.esm35.prediction)
        if (label == 1 and prediction == 0) or (label == 0 and prediction == 1):
            margins.append(_margin(row.esm35, prediction == 1))
    prediction150 = int(row.esm150.prediction)
    if (label == 1 and prediction150 == 0) or (label == 0 and prediction150 == 1):
        margins.append(_margin(row.esm150, prediction150 == 1))
    return max(margins, default=0.0)


def _review_sort_key(row: ComparedSite) -> tuple[float, str, int]:
    return (-review_confidence(row), row.site.key[0], row.site.key[1])


def _selection_criteria(stratum: str) -> str:
    return (
        f"stratum={stratum}; descending max(2*abs(prob-0.5)) among "
        "models disagreeing with the UniProt label; ties by accession,pos"
    )


def _manual_review_question(site: AnnotationSite) -> str:
    if site.evaluation_label == 1:
        return (
            "Does independent literature or a curated resource support N-linked "
            "glycosylation at this site despite the model disagreement?"
        )
    return (
        "Is there a missed UniProt annotation or a plausible biological reason "
        "for the model-positive call, and does any evidence justify an "
        "annotation update?"
    )


def select_top_disagreements(
    compared: Sequence[ComparedSite],
    limit: int = REVIEW_LIMIT,
) -> list[ReviewRow]:
    honest = [row for row in compared if row.site.evaluation_included]
    strata: dict[str, list[ComparedSite]] = {name: [] for name in STRATA_ORDER}
    eligible: list[ComparedSite] = []
    for row in honest:
        stratum = review_stratum(row)
        if stratum is not None:
            strata[stratum].append(row)
            eligible.append(row)
    if len(eligible) < limit:
        raise ComparisonError(
            f"fewer than {limit} eligible honest disagreements: {len(eligible)}"
        )
    for rows in strata.values():
        rows.sort(key=_review_sort_key)

    positions = {name: 0 for name in STRATA_ORDER}
    selected: list[tuple[str, ComparedSite]] = []
    selected_ids: set[tuple[str, int]] = set()
    while len(selected) < limit:
        added = False
        for name in STRATA_ORDER:
            rows = strata[name]
            index = positions[name]
            while index < len(rows) and rows[index].site.key in selected_ids:
                index += 1
            positions[name] = index
            if index >= len(rows):
                continue
            row = rows[index]
            selected.append((name, row))
            selected_ids.add(row.site.key)
            positions[name] += 1
            added = True
            if len(selected) == limit:
                break
        if not added:
            break

    if len(selected) < limit:
        remaining = [row for row in eligible if row.site.key not in selected_ids]
        remaining.sort(key=_review_sort_key)
        for row in remaining:
            selected.append((review_stratum(row) or "remaining_disagreement", row))
            if len(selected) == limit:
                break
    if len(selected) != limit or len(selected_ids) != limit:
        raise ComparisonError("could not select ten unique disagreements")

    return [
        ReviewRow(
            rank=rank,
            stratum=stratum,
            compared=row,
            ranking_confidence=review_confidence(row),
            selection_criteria=_selection_criteria(stratum),
        )
        for rank, (stratum, row) in enumerate(selected, start=1)
    ]


def apply_review_ranks(
    compared: Sequence[ComparedSite],
    review: Sequence[ReviewRow],
) -> list[ComparedSite]:
    ranks = {row.compared.site.key: row.rank for row in review}
    return [replace(row, review_rank=ranks.get(row.site.key)) for row in compared]


def comparison_rows(compared: Sequence[ComparedSite]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in compared:
        site = row.site
        vote35 = row.esm35
        rows.append(
            {
                "row_id": f"{site.key[0]}:{site.key[1]}",
                "accession": site.key[0],
                "protein_name": site.protein_name,
                "pos": site.key[1],
                "motif": site.motif,
                "seq_len": site.seq_len,
                "uniprot_release": site.uniprot_release,
                "uniprot_evidence": site.raw_evidence,
                "n_features": site.n_features,
                "evidence_class": site.evidence_class,
                "evaluation_included": int(site.evaluation_included),
                "evaluation_label": (
                    "" if site.evaluation_label is None else site.evaluation_label
                ),
                "uniprot_prediction": row.uniprot_prediction,
                "sequence_rule_prediction": row.sequence_rule_prediction,
                "esm35_row_id": "" if vote35 is None else vote35.source_row_id,
                "esm35_fold_id": "" if vote35 is None else vote35.extra["fold_id"],
                "esm35_probability": (
                    "" if vote35 is None else repr(float(vote35.probability))
                ),
                "esm35_prediction": "" if vote35 is None else vote35.prediction,
                "esm150_row_index": row.esm150.source_row_index,
                "esm150_probability": repr(float(row.esm150.probability)),
                "esm150_prediction": row.esm150.prediction,
                "available_method_count": 3 if site.evaluation_included else 2,
                "disagreement_pattern": row.disagreement_pattern,
                "review_rank": "" if row.review_rank is None else row.review_rank,
            }
        )
    return rows


def review_rows(review: Sequence[ReviewRow]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in review:
        compared = item.compared
        site = compared.site
        rows.append(
            {
                "rank": item.rank,
                "selection_stratum": item.stratum,
                "row_id": f"{site.key[0]}:{site.key[1]}",
                "accession": site.key[0],
                "protein_name": site.protein_name,
                "pos": site.key[1],
                "motif": site.motif,
                "seq_len": site.seq_len,
                "uniprot_release": site.uniprot_release,
                "uniprot_evidence": site.raw_evidence,
                "n_features": site.n_features,
                "evidence_class": site.evidence_class,
                "evaluation_label": site.evaluation_label,
                "uniprot_prediction": compared.uniprot_prediction,
                "sequence_rule_prediction": compared.sequence_rule_prediction,
                "esm35_probability": repr(float(compared.esm35.probability)),
                "esm35_prediction": compared.esm35.prediction,
                "esm35_fold_id": compared.esm35.extra["fold_id"],
                "esm150_probability": repr(float(compared.esm150.probability)),
                "esm150_prediction": compared.esm150.prediction,
                "disagreement_pattern": compared.disagreement_pattern,
                "ranking_confidence": repr(item.ranking_confidence),
                "selection_criteria": item.selection_criteria,
                "manual_review_question": _manual_review_question(site),
                "review_status": "PENDING_MANUAL_REVIEW",
                "reviewer_note": "",
            }
        )
    return rows


def _format_metric(value: object) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def report_text(
    metrics: Mapping[str, Any],
    review: Sequence[ReviewRow],
) -> str:
    benchmark = metrics["benchmark"]
    lines = [
        "# W1 three-method comparison",
        "",
        "## Evaluation boundary",
        "",
        f"- Source candidates: {benchmark['source_rows']} rows.",
        (
            f"- Honest metrics population: {benchmark['evaluation_rows']} rows "
            f"({benchmark['experimental_positive']} experimental positives + "
            f"{benchmark['unannotated_control']} unannotated controls), "
            f"spanning {benchmark['proteins']} proteins."
        ),
        (
            f"- Display-only inferred positives: {benchmark['inferred_display_only']} "
            "rows. They remain in `comparison.csv` with a blank evaluation label "
            "and are excluded from every metric denominator."
        ),
        "- The controls are unannotated sequons, not confirmed biological negatives.",
        (
            "- UniProt N-linked annotation is the benchmark label source and "
            "reference ceiling, not a method."
        ),
        "",
        "## Methods",
        "",
        "| method | decision rule | MCC | positive recall | control specificity | "
        "positive precision | weak-label accuracy | ROC AUC |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for method_id in ("sequon_rule", "esm35_oof", "esm150_author_adapter"):
        method = metrics["methods"][method_id]
        values = method["metrics"]
        lines.append(
            "| "
            + " | ".join(
                (
                    method_id,
                    str(method["prediction_rule"]),
                    _format_metric(values["mcc"]),
                    _format_metric(values["positive_recall"]),
                    _format_metric(values["control_specificity"]),
                    _format_metric(values["positive_precision"]),
                    _format_metric(values["weak_label_accuracy"]),
                    _format_metric(values["roc_auc"]),
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            (
                "The 35M scores are windowed leave-one-protein-out OOF estimates; "
                "the 150M scores are full-sequence author-adapter inference. A "
                "difference therefore combines model size, training procedure, "
                "adapter, and input-context differences and cannot be attributed "
                "to model size alone."
            ),
            "",
            "## Disagreement strata",
            "",
        ]
    )
    for name in (*STRATA_ORDER, "all_agree"):
        lines.append(
            f"- `{name}`: {metrics['disagreement_counts'][name]} honest rows"
        )
    lines.extend(
        [
            "",
            "## Review sample",
            "",
            (
                "Selection policy: `w1-disagreement-v1`, honest 130-row pool only, "
                "round-robin across the six priority strata, then descending "
                "confidence margin within each stratum and accession,pos ties."
            ),
            "",
            "| rank | row_id | stratum | evidence | ESM-35M | ESM-150M | margin | status |",
            "|---:|---|---|---|---:|---:|---:|---|",
        ]
    )
    for item in review:
        site = item.compared.site
        lines.append(
            "| "
            + " | ".join(
                (
                    str(item.rank),
                    f"{site.key[0]}:{site.key[1]}",
                    item.stratum,
                    site.raw_evidence or "(none)",
                    _format_metric(item.compared.esm35.probability),
                    _format_metric(item.compared.esm150.probability),
                    _format_metric(item.ranking_confidence),
                    "PENDING_MANUAL_REVIEW",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Selected row IDs: "
            + ", ".join(
                f"`{item.compared.site.key[0]}:{item.compared.site.key[1]}`"
                for item in review
            )
            + ".",
            "",
            "No author-replay prediction input was read or used.",
            "",
        ]
    )
    return "\n".join(lines)


def _git_state() -> dict[str, object]:
    try:
        commit = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ComparisonError("unable to record git provenance") from error
    if len(commit) != 40:
        raise ComparisonError("git HEAD is not a 40-character commit")
    return {"git_commit": commit, "git_dirty": bool(status.strip())}


def _input_manifest(run_dir: Path, names: Sequence[str]) -> dict[str, object]:
    result: dict[str, object] = {"run_dir": {"path": display_path(run_dir)}}
    for name in names:
        result[name] = path_record(run_dir / name)
    result["manifest.json"] = path_record(run_dir / "manifest.json")
    return result


def build_manifest(
    config: ComparisonConfig,
    sites: Sequence[AnnotationSite],
    compared: Sequence[ComparedSite],
    metrics: Mapping[str, Any],
    review: Sequence[ReviewRow],
    artifact_hashes: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    selected_ids = [
        f"{item.compared.site.key[0]}:{item.compared.site.key[1]}" for item in review
    ]
    benchmark = metrics["benchmark"]
    metric_summary: dict[str, object] = {}
    for method_id, method in metrics["methods"].items():
        metric_summary[method_id] = {
            "evaluation_rows": method["evaluation_rows"],
            "mcc": method["metrics"]["mcc"],
            "mcc_defined": method["mcc_defined"],
            "roc_auc": method["metrics"]["roc_auc"],
        }
    return {
        "schema": SCHEMA,
        "status": "complete",
        "source": _git_state(),
        "inputs": {
            "candidates": {
                **path_record(config.candidates),
                "rows": len(sites),
                "proteins": len({site.key[0] for site in sites}),
                "evidence_counts": {
                    "experimental_positive": sum(
                        site.evidence_class == "experimental_positive"
                        for site in sites
                    ),
                    "inferred_positive": sum(
                        site.evidence_class == "inferred_positive" for site in sites
                    ),
                    "unannotated_control": sum(
                        site.evidence_class == "unannotated_control"
                        for site in sites
                    ),
                },
            },
            "esm35": _input_manifest(
                config.esm35_run_dir,
                ("predictions.csv", "metrics.json"),
            ),
            "esm150": _input_manifest(
                config.esm150_run_dir,
                ("predictions.csv", "report.md"),
            ),
        },
        "benchmark": {
            **benchmark,
            "p13611_only_inferred": True,
        },
        "methods": {
            "sequon_rule": {
                "prediction_rule": "always positive for the 201-sequon table",
                "source": "candidates_30.csv sequon column",
                "independent_of_benchmark": True,
            },
            "esm35_oof": {
                "prediction_rule": "stored probability >= 0.5",
                "source": path_record(config.esm35_run_dir / "predictions.csv"),
                "split": "leave_one_protein_out",
                "independent_of_benchmark": True,
            },
            "esm150_author_adapter": {
                "prediction_rule": "logit_positive > logit_negative",
                "source": path_record(config.esm150_run_dir / "predictions.csv"),
                "model": "facebook/esm2_t30_150M_UR50D + author adapter",
                "input_context": "full sequence",
                "independent_of_benchmark": True,
            },
        },
        "esm150_inference_manifest_sha256": sha256_file(
            config.esm150_run_dir / "manifest.json"
        ),
        "comparison": {
            "rows": len(compared),
            "evaluated": sum(row.site.evaluation_included for row in compared),
            "display_only": sum(not row.site.evaluation_included for row in compared),
        },
        "review": {
            "policy_version": REVIEW_POLICY_VERSION,
            "pool": "honest_130",
            "limit": REVIEW_LIMIT,
            "strata_order": list(STRATA_ORDER),
            "within_stratum_sort": [
                "ranking_confidence_desc",
                "accession_asc",
                "pos_asc",
            ],
            "fill_policy": "remaining_honest_disagreements_by_global_confidence",
            "selected_row_ids": selected_ids,
        },
        "metric_summary": metric_summary,
        "comparability_caveat": metrics["comparability_caveat"],
        "no_author_replay_prediction_input": True,
        "author_replay_prediction_input": False,
        "artifacts": artifact_hashes,
    }


def write_comparison_run(
    config: ComparisonConfig,
    sites: Sequence[AnnotationSite],
    compared: Sequence[ComparedSite],
    metrics: dict[str, object],
    review: Sequence[ReviewRow],
) -> None:
    out_dir = config.out_dir.resolve()
    if out_dir.exists():
        raise ComparisonError(f"output directory already exists: {out_dir}")
    parent = out_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".{out_dir.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        comparison = comparison_rows(compared)
        review_table = review_rows(review)
        metric_payload = dict(metrics)
        metric_payload["review_policy"] = {
            "version": REVIEW_POLICY_VERSION,
            "pool": "honest_130",
            "limit": REVIEW_LIMIT,
            "strata_order": list(STRATA_ORDER),
            "within_stratum_sort": [
                "ranking_confidence_desc",
                "accession_asc",
                "pos_asc",
            ],
            "fill_policy": "remaining_honest_disagreements_by_global_confidence",
            "selected_row_ids": [
                f"{item.compared.site.key[0]}:{item.compared.site.key[1]}"
                for item in review
            ],
        }

        write_csv(
            staging / "comparison.csv",
            COMPARISON_COLUMNS,
            comparison,
        )
        write_csv(
            staging / "review_top10.csv",
            REVIEW_COLUMNS,
            review_table,
        )
        write_text(staging / "metrics.json", json_text(metric_payload))
        write_text(staging / "report.md", report_text(metric_payload, review))

        artifact_hashes: dict[str, dict[str, object]] = {}
        for name in ARTIFACT_NAMES:
            path = staging / name
            artifact_hashes[name] = {
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        manifest = build_manifest(
            config,
            sites,
            compared,
            metric_payload,
            review,
            artifact_hashes,
        )
        write_text(staging / "manifest.json", json_text(manifest))
        os.replace(staging, out_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def parse_args(argv: Sequence[str] | None = None) -> ComparisonConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--esm35-run-dir", type=Path, default=DEFAULT_ESM35_RUN_DIR)
    parser.add_argument("--esm150-run-dir", type=Path, default=DEFAULT_ESM150_RUN_DIR)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    return ComparisonConfig(
        candidates=args.candidates,
        esm35_run_dir=args.esm35_run_dir,
        esm150_run_dir=args.esm150_run_dir,
        out_dir=args.out_dir,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        config = parse_args(argv)
        sites, _ = load_annotation_sites(config.candidates)
        votes35 = load_esm35_votes(config.esm35_run_dir, sites)
        votes150 = load_esm150_votes(config.esm150_run_dir, sites)
        compared = build_comparison(sites, votes35, votes150)
        metrics = compute_metrics(compared)
        review = select_top_disagreements(compared)
        compared = apply_review_ranks(compared, review)
        write_comparison_run(config, sites, compared, metrics, review)
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        f"PASS rows={EXPECTED_ROWS} evaluated={EXPECTED_EVALUATED_ROWS} "
        f"review={len(review)} out={config.out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
