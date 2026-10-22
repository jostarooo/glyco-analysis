"""Independently verify the W1 three-method comparison artifacts.

The checker is read-only. It reconstructs candidate joins, method votes,
metrics, review selection, artifact hashes, and provenance without importing
the comparison runner.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = REPO_ROOT / "reports" / "candidates_30.csv"
DEFAULT_CANDIDATES_LORA = REPO_ROOT / "reports" / "candidates_30_lora.csv"
DEFAULT_ESM35_RUN_DIR = REPO_ROOT / "reports" / "esm35_linear_probe_v0"
DEFAULT_ESM150_RUN_DIR = REPO_ROOT / "reports" / "esm150_w1_candidates_v0"
DEFAULT_ADAPTER_DIR = (
    Path("D:/wbworkspace/LoRA-N-Gly/checkpoints/N-linked/ESM-150M/checkpoint")
)
DEFAULT_COMPAT_PATH = Path("D:/uv/pylibs/lora-n-gly-peft014")

SCHEMA = "glyco.w1-three-method/v1"
ESM35_SCHEMA = "glyco.esm35-linear-probe/v2"
ESM150_SCHEMA = "glyco.w1-esm150-candidates/v1"
BENCHMARK_ID = "experimental_positive_vs_unannotated_control"

EXPECTED_CANDIDATES_SHA256 = (
    "A584C3814226B7287807676F65D5CFFE2F5D47A53BC00476A4B9945CB0719F1C"
)
EXPECTED_CANDIDATES_LORA_SHA256 = (
    "DBD51D28ABC0B0C74E78496E0A8F54CEBAA1C29F274B6E6B2716E39631A09FAB"
)
EXPECTED_ADAPTER_SHA256 = (
    "A4A5B486862724F459F60E8343AC135C340305D5A0F2E936EB5AD1DFD34788D4"
)
EXPECTED_BASE_MODEL_ID = "facebook/esm2_t30_150M_UR50D"
EXPECTED_BASE_MODEL_REVISION = "a695f6045e2e32885fa60af20c13cb35398ce30c"
EXPECTED_BASE_WEIGHTS_SHA256 = (
    "C3F1DA8AEA53BDDD32C246C86168C23B9FD72341FB9DB9A94436F855F5053566"
)
EXPECTED_AUTHOR_REPLAY_PREDICTIONS_SHA256 = (
    "372112E11FE8BFB785508BFC3CAE932DA6622566C6E1DD5D035B88C6DBC7622E"
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
LORA_COLUMNS = ("label", "id", "pos", "sequence")
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


class CheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckConfig:
    comparison_dir: Path
    candidates: Path
    candidates_lora: Path
    esm35_run_dir: Path
    esm150_run_dir: Path
    adapter_dir: Path
    compat_path: Path
    logit_tolerance: float


@dataclass(frozen=True)
class Site:
    row_index: int
    accession: str
    position: int
    protein_name: str
    seq_len: int
    motif: str
    n_features: int
    label: int
    evidence: tuple[str, ...]
    raw_evidence: str
    evidence_class: str
    included: bool
    evaluation_label: int | None
    release: str

    @property
    def key(self) -> tuple[str, int]:
        return (self.accession, self.position)


@dataclass(frozen=True)
class LoraRow:
    row_index: int
    label: int
    accession: str
    position: int
    sequence: str

    @property
    def key(self) -> tuple[str, int]:
        return (self.accession, self.position)


@dataclass(frozen=True)
class Vote:
    prediction: int
    probability: float | None
    row_id: str
    row_index: int
    fold_id: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest().upper()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CheckError(f"JSON file not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CheckError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise CheckError(f"JSON object required: {path}")
    return value


def read_csv_exact(path: Path, columns: Sequence[str]) -> list[dict[str, str]]:
    if not path.is_file():
        raise CheckError(f"CSV file not found: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != tuple(columns):
            raise CheckError(
                f"CSV header mismatch for {path}: {tuple(reader.fieldnames or ())!r}"
            )
        return list(reader)


def _assert_expected_hash(path: Path, expected: str, label: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise CheckError(f"{label} SHA256 mismatch: {actual} != {expected}")


def verify_manifest_and_hashes(
    run_dir: Path,
    expected_schema: str,
    expected_artifacts: Sequence[str] | None = None,
) -> dict[str, Any]:
    manifest = load_json(run_dir / "manifest.json")
    if manifest.get("schema") != expected_schema:
        raise CheckError(
            f"manifest schema mismatch: {manifest.get('schema')!r} != {expected_schema!r}"
        )
    if manifest.get("status") != "complete":
        raise CheckError(f"manifest is not marked complete: {run_dir}")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise CheckError(f"manifest artifacts must be an object: {run_dir}")
    names = tuple(expected_artifacts or tuple(sorted(artifacts)))
    for name in names:
        record = artifacts.get(name)
        if not isinstance(record, dict):
            raise CheckError(f"missing artifact record: {run_dir / name}")
        path = run_dir / name
        if not path.is_file():
            raise CheckError(f"missing artifact: {path}")
        if record.get("bytes") != path.stat().st_size:
            raise CheckError(f"artifact byte count mismatch: {name}")
        expected_sha = record.get("sha256")
        actual_sha = sha256_file(path)
        if expected_sha != actual_sha:
            raise CheckError(f"artifact hash mismatch: {name}")
    return manifest


def classify_evidence(label: int, codes: Sequence[str], row_id: str) -> str:
    evidence = frozenset(codes)
    if label == 1:
        if EXPERIMENTAL_CODE in evidence:
            return "experimental_positive"
        if evidence == {INFERRED_CODE}:
            return "inferred_positive"
        raise CheckError(f"{row_id} has unsupported positive evidence")
    if evidence:
        raise CheckError(f"{row_id} control has evidence")
    return "unannotated_control"


def load_candidates(path: Path) -> list[Site]:
    _assert_expected_hash(path, EXPECTED_CANDIDATES_SHA256, "candidate table")
    rows = read_csv_exact(path, CANDIDATE_COLUMNS)
    if len(rows) != EXPECTED_ROWS:
        raise CheckError(f"candidate row count mismatch: {len(rows)}")
    sites: list[Site] = []
    seen: set[tuple[str, int]] = set()
    release: str | None = None
    for row_index, raw in enumerate(rows):
        try:
            position = int(raw["pos"])
            seq_len = int(raw["seq_len"])
            n_features = int(raw["n_features"])
            label = int(raw["label"])
        except ValueError as error:
            raise CheckError(f"invalid numeric candidate row {row_index}") from error
        key = (raw["accession"], position)
        row_id = f"{key[0]}:{key[1]}"
        if key in seen:
            raise CheckError(f"duplicate candidate key: {row_id}")
        seen.add(key)
        if label not in (0, 1):
            raise CheckError(f"invalid label: {row_id}")
        if raw["residue"] != "N" or raw["sequon"] != "1":
            raise CheckError(f"non-sequon row: {row_id}")
        if SEQUON.fullmatch(raw["motif"]) is None:
            raise CheckError(f"invalid motif: {row_id}")
        if not 1 <= position <= seq_len:
            raise CheckError(f"position outside sequence: {row_id}")
        if label != int(raw["linkage"] == "N-linked"):
            raise CheckError(f"label/linkage mismatch: {row_id}")
        if release is None:
            release = raw["uniprot_release"]
        elif release != raw["uniprot_release"]:
            raise CheckError("multiple UniProt releases")
        codes = tuple(
            sorted(
                {
                    part.strip()
                    for part in raw["evidence"].split(";")
                    if part.strip()
                }
            )
        )
        if any(ECO_CODE.fullmatch(code) is None for code in codes):
            raise CheckError(f"invalid ECO code: {row_id}")
        evidence_class = classify_evidence(label, codes, row_id)
        included = evidence_class in {
            "experimental_positive",
            "unannotated_control",
        }
        sites.append(
            Site(
                row_index=row_index,
                accession=key[0],
                position=position,
                protein_name=raw["protein_name"],
                seq_len=seq_len,
                motif=raw["motif"],
                n_features=n_features,
                label=label,
                evidence=codes,
                raw_evidence=raw["evidence"],
                evidence_class=evidence_class,
                included=included,
                evaluation_label=label if included else None,
                release=raw["uniprot_release"],
            )
        )

    counts = {
        name: sum(site.evidence_class == name for site in sites)
        for name in (
            "experimental_positive",
            "inferred_positive",
            "unannotated_control",
        )
    }
    if counts != {
        "experimental_positive": EXPECTED_EXPERIMENTAL,
        "inferred_positive": EXPECTED_INFERRED,
        "unannotated_control": EXPECTED_CONTROLS,
    }:
        raise CheckError(f"evidence counts mismatch: {counts}")
    evaluated = [site for site in sites if site.included]
    if len(evaluated) != EXPECTED_EVALUATED_ROWS:
        raise CheckError(f"evaluated row count mismatch: {len(evaluated)}")
    if len({site.accession for site in sites}) != EXPECTED_PROTEINS:
        raise CheckError("protein count mismatch")
    if len({site.accession for site in evaluated}) != EXPECTED_EVALUATED_PROTEINS:
        raise CheckError("evaluated protein count mismatch")
    p13611 = [site for site in sites if site.accession == "P13611"]
    if not p13611 or any(site.included for site in p13611):
        raise CheckError("P13611 is not exclusively inferred")
    return sites


def load_candidates_lora(path: Path, sites: Sequence[Site]) -> list[LoraRow]:
    _assert_expected_hash(path, EXPECTED_CANDIDATES_LORA_SHA256, "candidate LoRA table")
    rows = read_csv_exact(path, LORA_COLUMNS)
    if len(rows) != len(sites):
        raise CheckError("candidate LoRA row count mismatch")
    lora: list[LoraRow] = []
    for row_index, raw in enumerate(rows):
        try:
            label = int(raw["label"])
            position = int(raw["pos"])
        except ValueError as error:
            raise CheckError(f"invalid LoRA row {row_index}") from error
        lora.append(
            LoraRow(
                row_index=row_index,
                label=label,
                accession=raw["id"],
                position=position,
                sequence=raw["sequence"],
            )
        )
    ordered_source = [(site.accession, site.position) for site in sites]
    ordered_lora = [row.key for row in lora]
    if ordered_lora != ordered_source:
        raise CheckError("candidate LoRA key order differs from the source table")
    by_key = {site.key: site for site in sites}
    sequences: dict[str, str] = {}
    for row in lora:
        site = by_key.get(row.key)
        if site is None:
            raise CheckError(f"LoRA row is outside source table: {row.key}")
        if row.label != site.label:
            raise CheckError(f"LoRA label mismatch: {row.key}")
        previous = sequences.setdefault(row.accession, row.sequence)
        if previous != row.sequence:
            raise CheckError(f"accession maps to multiple sequences: {row.accession}")
        if len(row.sequence) != site.seq_len:
            raise CheckError(f"LoRA sequence length mismatch: {row.key}")
        if not 1 <= row.position <= len(row.sequence):
            raise CheckError(f"LoRA position outside sequence: {row.key}")
        residue = row.sequence[row.position - 1]
        motif = row.sequence[row.position - 1 : row.position + 2]
        if residue != "N" or motif != site.motif or SEQUON.fullmatch(motif) is None:
            raise CheckError(f"LoRA target residue/motif mismatch: {row.key}")
    if len(set(sequences.values())) != EXPECTED_PROTEINS:
        raise CheckError("unique sequence count mismatch")
    return lora


def _softmax_two(negative: float, positive: float) -> tuple[float, float]:
    maximum = max(negative, positive)
    first = math.exp(negative - maximum)
    second = math.exp(positive - maximum)
    total = first + second
    return first / total, second / total


def _as_prediction(raw: str, row_id: str) -> int:
    if raw not in {"0", "1"}:
        raise CheckError(f"invalid binary prediction: {row_id}")
    return int(raw)


def load_esm35(
    run_dir: Path,
    sites: Sequence[Site],
) -> tuple[dict[tuple[str, int], Vote], dict[str, Any]]:
    manifest = verify_manifest_and_hashes(
        run_dir,
        ESM35_SCHEMA,
        ("predictions.csv", "metrics.json"),
    )
    candidate_record = manifest.get("inputs", {}).get("candidates", {})
    if candidate_record.get("sha256") != EXPECTED_CANDIDATES_SHA256:
        raise CheckError("35M manifest candidate hash mismatch")
    rows = read_csv_exact(run_dir / "predictions.csv", ESM35_COLUMNS)
    honest = {site.key: site for site in sites if site.included}
    if len(rows) != EXPECTED_EVALUATED_ROWS:
        raise CheckError("35M does not contain exactly 130 rows")
    votes: dict[tuple[str, int], Vote] = {}
    labels: list[int] = []
    predictions: list[int] = []
    probabilities: list[float] = []
    for row_index, raw in enumerate(rows):
        try:
            position = int(raw["pos"])
            label = int(raw["label"])
            probability = float(raw["probability"])
        except ValueError as error:
            raise CheckError(f"invalid numeric 35M row {row_index}") from error
        key = (raw["accession"], position)
        row_id = f"{key[0]}:{key[1]}"
        site = honest.get(key)
        if site is None:
            raise CheckError(f"35M key outside honest population: {row_id}")
        if key in votes:
            raise CheckError(f"duplicate 35M key: {row_id}")
        if label != site.evaluation_label:
            raise CheckError(f"35M label mismatch: {row_id}")
        if raw["row_id"] != row_id:
            raise CheckError(f"35M row_id mismatch: {row_id}")
        if raw["fold_id"] != f"lopo:{key[0]}":
            raise CheckError(f"35M fold mismatch: {row_id}")
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise CheckError(f"35M probability invalid: {row_id}")
        prediction = _as_prediction(raw["prediction"], row_id)
        if prediction != int(probability >= 0.5):
            raise CheckError(f"35M threshold mismatch: {row_id}")
        votes[key] = Vote(
            prediction=prediction,
            probability=probability,
            row_id=row_id,
            row_index=row_index,
            fold_id=raw["fold_id"],
        )
        labels.append(label)
        predictions.append(prediction)
        probabilities.append(probability)
    if set(votes) != set(honest):
        missing = sorted(set(honest) - set(votes))
        extra = sorted(set(votes) - set(honest))
        raise CheckError(
            f"35M exact key-set mismatch; missing={missing[:5]} extra={extra[:5]}"
        )
    verify_35m_metrics(load_json(run_dir / "metrics.json"), labels, predictions, probabilities)
    return votes, manifest


def load_esm150(
    run_dir: Path,
    sites: Sequence[Site],
    lora: Sequence[LoraRow],
    candidates_lora: Path,
    logit_tolerance: float,
) -> tuple[dict[tuple[str, int], Vote], dict[str, Any]]:
    manifest = verify_manifest_and_hashes(
        run_dir,
        ESM150_SCHEMA,
        ("predictions.csv", "report.md"),
    )
    inputs = manifest.get("inputs", {})
    candidate_record = inputs.get("candidates_lora", {})
    if candidate_record.get("sha256") != sha256_file(candidates_lora):
        raise CheckError("150M manifest candidate-LoRA hash mismatch")
    if candidate_record.get("row_count") != EXPECTED_ROWS:
        raise CheckError("150M manifest candidate row count mismatch")
    adapter_record = inputs.get("adapter", {})
    if adapter_record.get("model_sha256") != EXPECTED_ADAPTER_SHA256:
        raise CheckError("150M manifest adapter hash mismatch")
    if adapter_record.get("tensor_count") != 376:
        raise CheckError("150M manifest adapter tensor count mismatch")
    base = inputs.get("base_model", {})
    if base.get("id") != EXPECTED_BASE_MODEL_ID:
        raise CheckError("150M manifest base model id mismatch")
    if base.get("revision") != EXPECTED_BASE_MODEL_REVISION:
        raise CheckError("150M manifest base model revision mismatch")
    if base.get("weights_sha256") != EXPECTED_BASE_WEIGHTS_SHA256:
        raise CheckError("150M manifest base model weights hash mismatch")

    rows = read_csv_exact(run_dir / "predictions.csv", ESM150_COLUMNS)
    if len(rows) != EXPECTED_ROWS:
        raise CheckError("150M does not contain exactly 201 rows")
    sites_by_key = {site.key: site for site in sites}
    lora_by_key = {row.key: row for row in lora}
    votes: dict[tuple[str, int], Vote] = {}
    for expected_index, raw in enumerate(rows):
        try:
            row_index = int(raw["row_index"])
            position = int(raw["position"])
            label = int(raw["label"])
            sequence_length = int(raw["sequence_length"])
            token_length = int(raw["token_length"])
            logit_negative = float(raw["logit_negative"])
            logit_positive = float(raw["logit_positive"])
            prob_negative = float(raw["prob_negative"])
            prob_positive = float(raw["prob_positive"])
            prediction = int(raw["predicted_label"])
        except ValueError as error:
            raise CheckError(f"invalid numeric 150M row {expected_index}") from error
        key = (raw["accession"], position)
        row_id = f"{key[0]}:{key[1]}"
        site = sites_by_key.get(key)
        lora_row = lora_by_key.get(key)
        if site is None or lora_row is None:
            raise CheckError(f"150M key outside source population: {row_id}")
        if key in votes:
            raise CheckError(f"duplicate 150M key: {row_id}")
        if row_index != expected_index:
            raise CheckError(f"150M row_index mismatch: {row_id}")
        if lora_row.row_index != expected_index:
            raise CheckError(f"150M output order differs from LoRA input: {row_id}")
        if label != site.label:
            raise CheckError(f"150M source label mismatch: {row_id}")
        if sequence_length != site.seq_len or len(lora_row.sequence) != sequence_length:
            raise CheckError(f"150M sequence length mismatch: {row_id}")
        if token_length != sequence_length + 2:
            raise CheckError(f"150M token length mismatch: {row_id}")
        if raw["sequence_sha256"] != sha256_text(lora_row.sequence):
            raise CheckError(f"150M sequence hash mismatch: {row_id}")
        if raw["residue"] != "N" or raw["motif"] != site.motif:
            raise CheckError(f"150M residue/motif mismatch: {row_id}")
        if raw["is_sequon"] != "1":
            raise CheckError(f"150M sequon mismatch: {row_id}")
        values = (
            logit_negative,
            logit_positive,
            prob_negative,
            prob_positive,
        )
        if not all(math.isfinite(value) for value in values):
            raise CheckError(f"150M non-finite value: {row_id}")
        if not 0.0 <= prob_negative <= 1.0 or not 0.0 <= prob_positive <= 1.0:
            raise CheckError(f"150M probability outside [0,1]: {row_id}")
        if not math.isclose(
            prob_negative + prob_positive,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise CheckError(f"150M probabilities do not sum to one: {row_id}")
        soft_negative, soft_positive = _softmax_two(logit_negative, logit_positive)
        if not math.isclose(
            prob_negative,
            soft_negative,
            rel_tol=0.0,
            abs_tol=max(1e-12, logit_tolerance),
        ) or not math.isclose(
            prob_positive,
            soft_positive,
            rel_tol=0.0,
            abs_tol=max(1e-12, logit_tolerance),
        ):
            raise CheckError(f"150M softmax mismatch: {row_id}")
        expected_prediction = int(logit_positive > logit_negative)
        if prediction != expected_prediction:
            raise CheckError(f"150M argmax mismatch: {row_id}")
        votes[key] = Vote(
            prediction=prediction,
            probability=prob_positive,
            row_id=str(row_index),
            row_index=row_index,
        )
    if set(votes) != set(sites_by_key):
        raise CheckError("150M exact key-set mismatch")
    return votes, manifest


def confusion_values(
    labels: Sequence[int],
    predictions: Sequence[int],
) -> tuple[int, int, int, int]:
    if len(labels) != len(predictions) or not labels:
        raise CheckError("confusion inputs are empty or unequal")
    tp = sum(label == 1 and prediction == 1 for label, prediction in zip(labels, predictions))
    fn = sum(label == 1 and prediction == 0 for label, prediction in zip(labels, predictions))
    tn = sum(label == 0 and prediction == 0 for label, prediction in zip(labels, predictions))
    fp = sum(label == 0 and prediction == 1 for label, prediction in zip(labels, predictions))
    return tp, fn, tn, fp


def roc_auc(labels: Sequence[int], probabilities: Sequence[float]) -> float | None:
    if len(labels) != len(probabilities):
        raise CheckError("ROC AUC inputs have different lengths")
    positives = [score for label, score in zip(labels, probabilities) if label == 1]
    controls = [score for label, score in zip(labels, probabilities) if label == 0]
    if not positives or not controls:
        return None
    score = 0.0
    for positive in positives:
        for control in controls:
            score += 1.0 if positive > control else 0.5 if positive == control else 0.0
    return score / (len(positives) * len(controls))


def binary_metrics(
    labels: Sequence[int],
    predictions: Sequence[int],
    probabilities: Sequence[float] | None,
) -> dict[str, object]:
    if len(labels) != len(predictions):
        raise CheckError("labels and predictions have different lengths")
    if probabilities is not None and len(labels) != len(probabilities):
        raise CheckError("labels and probabilities have different lengths")
    if any(label not in (0, 1) for label in labels):
        raise CheckError("labels must be binary")
    if any(prediction not in (0, 1) for prediction in predictions):
        raise CheckError("predictions must be binary")
    tp, fn, tn, fp = confusion_values(labels, predictions)
    denominator = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    defined = denominator > 0.0
    mcc = (tp * tn - fp * fn) / denominator if defined else 0.0
    null_reasons: dict[str, str] = {}
    positive_recall = tp / (tp + fn) if tp + fn else None
    control_specificity = tn / (tn + fp) if tn + fp else None
    positive_precision = tp / (tp + fp) if tp + fp else None
    if positive_recall is None:
        null_reasons["positive_recall"] = "no_evaluation_positives"
    if control_specificity is None:
        null_reasons["control_specificity"] = "no_evaluation_controls"
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
            "mcc": mcc,
            "positive_recall": positive_recall,
            "control_specificity": control_specificity,
            "positive_precision": positive_precision,
            "weak_label_accuracy": (tp + tn) / len(labels),
            "roc_auc": auc,
        },
        "mcc_defined": defined,
        "null_reasons": null_reasons,
    }


def verify_35m_metrics(
    stored: Mapping[str, Any],
    labels: Sequence[int],
    predictions: Sequence[int],
    probabilities: Sequence[float],
) -> None:
    if stored.get("schema") != ESM35_SCHEMA:
        raise CheckError("35M metrics schema mismatch")
    if stored.get("benchmark_id") != BENCHMARK_ID:
        raise CheckError("35M metrics benchmark mismatch")
    if stored.get("threshold") != 0.5:
        raise CheckError("35M metrics threshold mismatch")
    recomputed = binary_metrics(labels, predictions, probabilities)
    tp, fn, tn, fp = confusion_values(labels, predictions)
    expected_confusion = {
        "experimental_positive": {
            "predicted_positive": tp,
            "predicted_control": fn,
        },
        "unannotated_control": {
            "predicted_positive": fp,
            "predicted_control": tn,
        },
    }
    if stored.get("confusion") != expected_confusion:
        raise CheckError("stored 35M confusion does not match rows")
    stored_metrics = stored.get("metrics", {})
    for name, value in recomputed["metrics"].items():
        actual = stored_metrics.get(name)
        if value is None or actual is None:
            if value is not actual:
                raise CheckError(f"stored 35M metric {name} mismatch")
        elif not math.isclose(
            float(actual),
            float(value),
            rel_tol=0.0,
            abs_tol=FLOAT_TOLERANCE,
        ):
            raise CheckError(f"stored 35M metric {name} mismatch")
    if stored.get("null_reasons") != recomputed["null_reasons"]:
        raise CheckError("stored 35M null reasons mismatch")


def disagreement_pattern(site: Site, vote35: Vote, vote150: Vote) -> str:
    if not site.included:
        return "display_only_inferred"
    if site.evaluation_label == 1:
        if vote35.prediction == 0 and vote150.prediction == 0:
            return "both_models_oppose_experimental_positive"
        if vote35.prediction == 0:
            return "esm35_opposes_experimental_positive"
        if vote150.prediction == 0:
            return "esm150_opposes_experimental_positive"
    else:
        if vote35.prediction == 1 and vote150.prediction == 1:
            return "both_models_call_unannotated_control_positive"
        if vote35.prediction == 1:
            return "esm35_calls_unannotated_control_positive"
        if vote150.prediction == 1:
            return "esm150_calls_unannotated_control_positive"
    return "all_agree"


def expected_comparison_row(
    site: Site,
    vote35: Vote | None,
    vote150: Vote,
) -> dict[str, str]:
    if site.included:
        if vote35 is None:
            raise CheckError(f"missing honest 35M vote: {site.key}")
        pattern = disagreement_pattern(site, vote35, vote150)
        available = "3"
        evaluation_label = str(site.evaluation_label)
        vote35_fields = {
            "esm35_row_id": vote35.row_id,
            "esm35_fold_id": str(vote35.fold_id),
            "esm35_probability": repr(float(vote35.probability)),
            "esm35_prediction": str(vote35.prediction),
        }
    else:
        if vote35 is not None:
            raise CheckError(f"inferred row unexpectedly has 35M vote: {site.key}")
        pattern = "display_only_inferred"
        available = "2"
        evaluation_label = ""
        vote35_fields = {
            "esm35_row_id": "",
            "esm35_fold_id": "",
            "esm35_probability": "",
            "esm35_prediction": "",
        }
    return {
        "row_id": f"{site.accession}:{site.position}",
        "accession": site.accession,
        "protein_name": site.protein_name,
        "pos": str(site.position),
        "motif": site.motif,
        "seq_len": str(site.seq_len),
        "uniprot_release": site.release,
        "uniprot_evidence": site.raw_evidence,
        "n_features": str(site.n_features),
        "evidence_class": site.evidence_class,
        "evaluation_included": str(int(site.included)),
        "evaluation_label": evaluation_label,
        "uniprot_prediction": str(site.label),
        "sequence_rule_prediction": "1",
        **vote35_fields,
        "esm150_row_index": str(vote150.row_index),
        "esm150_probability": repr(float(vote150.probability)),
        "esm150_prediction": str(vote150.prediction),
        "available_method_count": available,
        "disagreement_pattern": pattern,
        "review_rank": "",
    }


def select_review_keys(rows: Sequence[Mapping[str, str]]) -> list[tuple[str, str]]:
    honest = [row for row in rows if row["evaluation_included"] == "1"]
    if len(honest) != EXPECTED_EVALUATED_ROWS:
        raise CheckError("review pool is not exactly 130 rows")
    strata: dict[str, list[dict[str, str]]] = {name: [] for name in STRATA_ORDER}
    eligible: list[dict[str, str]] = []
    for row in honest:
        pattern = row["disagreement_pattern"]
        if pattern not in strata:
            continue
        strata[pattern].append(dict(row))
        eligible.append(dict(row))
    if len(eligible) < REVIEW_LIMIT:
        raise CheckError(f"fewer than {REVIEW_LIMIT} honest disagreements")

    def confidence(row: Mapping[str, str]) -> float:
        label = int(row["evaluation_label"])
        pred35 = int(row["esm35_prediction"])
        pred150 = int(row["esm150_prediction"])
        margins: list[float] = []
        if (label == 1 and pred35 == 0) or (label == 0 and pred35 == 1):
            margins.append(2.0 * abs(float(row["esm35_probability"]) - 0.5))
        if (label == 1 and pred150 == 0) or (label == 0 and pred150 == 1):
            margins.append(2.0 * abs(float(row["esm150_probability"]) - 0.5))
        return max(margins, default=0.0)

    def sort_key(row: Mapping[str, str]) -> tuple[float, str, int]:
        return (-confidence(row), row["accession"], int(row["pos"]))

    for values in strata.values():
        values.sort(key=sort_key)
    selected: list[tuple[str, dict[str, str]]] = []
    selected_ids: set[str] = set()
    positions = {name: 0 for name in STRATA_ORDER}
    while len(selected) < REVIEW_LIMIT:
        added = False
        for name in STRATA_ORDER:
            values = strata[name]
            index = positions[name]
            while index < len(values) and values[index]["row_id"] in selected_ids:
                index += 1
            positions[name] = index
            if index >= len(values):
                continue
            row = values[index]
            selected.append((name, row))
            selected_ids.add(row["row_id"])
            positions[name] += 1
            added = True
            if len(selected) == REVIEW_LIMIT:
                break
        if not added:
            break
    if len(selected) < REVIEW_LIMIT:
        remaining = [row for row in eligible if row["row_id"] not in selected_ids]
        remaining.sort(key=sort_key)
        selected.extend(
            (row["disagreement_pattern"], row)
            for row in remaining[: REVIEW_LIMIT - len(selected)]
        )
    if len(selected) != REVIEW_LIMIT:
        raise CheckError("review selection did not produce ten unique rows")
    return [(name, row["row_id"]) for name, row in selected]


def _manual_review_question(row: Mapping[str, str]) -> str:
    if row["evaluation_label"] == "1":
        return (
            "Does independent literature or a curated resource support N-linked "
            "glycosylation at this site despite the model disagreement?"
        )
    return (
        "Is there a missed UniProt annotation or a plausible biological reason "
        "for the model-positive call, and does any evidence justify an "
        "annotation update?"
    )


def expected_review_row(
    rank: int,
    stratum: str,
    row: Mapping[str, str],
) -> dict[str, str]:
    label = int(row["evaluation_label"])
    pred35 = int(row["esm35_prediction"])
    pred150 = int(row["esm150_prediction"])
    margins: list[float] = []
    if (label == 1 and pred35 == 0) or (label == 0 and pred35 == 1):
        margins.append(2.0 * abs(float(row["esm35_probability"]) - 0.5))
    if (label == 1 and pred150 == 0) or (label == 0 and pred150 == 1):
        margins.append(2.0 * abs(float(row["esm150_probability"]) - 0.5))
    confidence = max(margins, default=0.0)
    return {
        "rank": str(rank),
        "selection_stratum": stratum,
        "row_id": row["row_id"],
        "accession": row["accession"],
        "protein_name": row["protein_name"],
        "pos": row["pos"],
        "motif": row["motif"],
        "seq_len": row["seq_len"],
        "uniprot_release": row["uniprot_release"],
        "uniprot_evidence": row["uniprot_evidence"],
        "n_features": row["n_features"],
        "evidence_class": row["evidence_class"],
        "evaluation_label": row["evaluation_label"],
        "uniprot_prediction": row["uniprot_prediction"],
        "sequence_rule_prediction": row["sequence_rule_prediction"],
        "esm35_probability": row["esm35_probability"],
        "esm35_prediction": row["esm35_prediction"],
        "esm35_fold_id": row["esm35_fold_id"],
        "esm150_probability": row["esm150_probability"],
        "esm150_prediction": row["esm150_prediction"],
        "disagreement_pattern": row["disagreement_pattern"],
        "ranking_confidence": repr(confidence),
        "selection_criteria": (
            f"stratum={stratum}; descending max(2*abs(prob-0.5)) among "
            "models disagreeing with the UniProt label; ties by accession,pos"
        ),
        "manual_review_question": _manual_review_question(row),
        "review_status": "PENDING_MANUAL_REVIEW",
        "reviewer_note": "",
    }


def recompute_metrics(rows: Sequence[Mapping[str, str]]) -> dict[str, object]:
    honest = [row for row in rows if row["evaluation_included"] == "1"]
    labels = [int(row["evaluation_label"]) for row in honest]
    predictions35 = [int(row["esm35_prediction"]) for row in honest]
    probabilities35 = [float(row["esm35_probability"]) for row in honest]
    predictions150 = [int(row["esm150_prediction"]) for row in honest]
    probabilities150 = [float(row["esm150_probability"]) for row in honest]
    rule_predictions = [int(row["sequence_rule_prediction"]) for row in honest]
    methods = {
        "sequon_rule": {
            "prediction_rule": "always positive; every row is an N-X-S/T sequon",
            "independent_of_benchmark": True,
            "score_kind": "fixed_binary",
            **binary_metrics(labels, rule_predictions, None),
        },
        "esm35_oof": {
            "prediction_rule": "stored probability >= 0.5",
            "independent_of_benchmark": True,
            "score_kind": "probability",
            **binary_metrics(labels, predictions35, probabilities35),
        },
        "esm150_author_adapter": {
            "prediction_rule": "logit_positive > logit_negative",
            "independent_of_benchmark": True,
            "score_kind": "probability",
            **binary_metrics(labels, predictions150, probabilities150),
        },
    }
    reference = binary_metrics(
        labels,
        [int(row["uniprot_prediction"]) for row in honest],
        None,
    )
    display = [row for row in rows if row["evaluation_included"] == "0"]
    patterns = {
        name: sum(row["disagreement_pattern"] == name for row in honest)
        for name in (*STRATA_ORDER, "all_agree")
    }
    return {
        "schema": SCHEMA,
        "benchmark": {
            "id": BENCHMARK_ID,
            "source_rows": len(rows),
            "evaluation_rows": len(honest),
            "experimental_positive": sum(labels),
            "unannotated_control": len(labels) - sum(labels),
            "inferred_display_only": len(display),
            "proteins": len({row["accession"] for row in honest}),
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
            "inferred_positive_rows": len(display),
            "uniprot_annotation_positive": sum(
                int(row["uniprot_prediction"]) for row in display
            ),
            "esm35": "not_available_by_construction",
            "esm150_predicted_positive": sum(
                int(row["esm150_prediction"]) for row in display
            ),
        },
        "disagreement_counts": patterns,
        "comparability_caveat": (
            "35M scores are windowed leave-one-protein-out OOF estimates; "
            "150M scores are full-sequence author-adapter inference. A difference "
            "cannot be attributed to model size alone."
        ),
    }


def _compare_json(actual: object, expected: object, path: str = "$") -> None:
    if isinstance(actual, dict) and isinstance(expected, dict):
        if set(actual) != set(expected):
            raise CheckError(
                f"JSON key mismatch at {path}: {sorted(actual)} != {sorted(expected)}"
            )
        for key in expected:
            _compare_json(actual[key], expected[key], f"{path}.{key}")
        return
    if isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            raise CheckError(f"JSON list length mismatch at {path}")
        for index, (left, right) in enumerate(zip(actual, expected)):
            _compare_json(left, right, f"{path}[{index}]")
        return
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        if isinstance(actual, bool) or isinstance(expected, bool):
            if actual != expected:
                raise CheckError(f"JSON value mismatch at {path}")
        elif not math.isclose(
            float(actual),
            float(expected),
            rel_tol=0.0,
            abs_tol=FLOAT_TOLERANCE,
        ):
            raise CheckError(
                f"JSON number mismatch at {path}: {actual!r} != {expected!r}"
            )
        return
    if actual != expected:
        raise CheckError(f"JSON value mismatch at {path}: {actual!r} != {expected!r}")


def _walk_mappings(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mappings(child)


def assert_no_author_replay_prediction_input(manifest: Mapping[str, Any]) -> None:
    if manifest.get("no_author_replay_prediction_input") is not True:
        raise CheckError("manifest does not explicitly exclude author-replay prediction input")
    if manifest.get("author_replay_prediction_input") is not False:
        raise CheckError("manifest author_replay_prediction_input must be false")
    forbidden_suffix = "reports/esm150_lora_repro_v0/predictions.csv"
    for mapping in _walk_mappings(manifest):
        role = mapping.get("role")
        if role != "prediction_input":
            continue
        path_value = mapping.get("path")
        digest = mapping.get("sha256")
        if isinstance(path_value, str) and forbidden_suffix in path_value.replace("\\", "/"):
            raise CheckError("author-replay predictions are registered as prediction input")
        if digest == EXPECTED_AUTHOR_REPLAY_PREDICTIONS_SHA256:
            raise CheckError("author-replay prediction hash is registered as input")


def verify_comparison(
    comparison_dir: Path,
    sites: Sequence[Site],
    votes35: Mapping[tuple[str, int], Vote],
    votes150: Mapping[tuple[str, int], Vote],
    esm35_manifest: Mapping[str, Any],
    esm150_manifest: Mapping[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any], dict[str, Any]]:
    manifest = verify_manifest_and_hashes(
        comparison_dir,
        SCHEMA,
        ARTIFACT_NAMES,
    )
    assert_no_author_replay_prediction_input(manifest)
    expected_files = set(ARTIFACT_NAMES) | {"manifest.json"}
    actual_files = {path.name for path in comparison_dir.iterdir() if path.is_file()}
    if actual_files != expected_files:
        raise CheckError(f"unexpected comparison artifact set: {sorted(actual_files)}")

    comparison = read_csv_exact(comparison_dir / "comparison.csv", COMPARISON_COLUMNS)
    if len(comparison) != EXPECTED_ROWS:
        raise CheckError("comparison does not contain exactly 201 rows")
    ordered_sites = sorted(sites, key=lambda site: site.key)
    keys = [(row["accession"], int(row["pos"])) for row in comparison]
    if keys != [site.key for site in ordered_sites]:
        raise CheckError("comparison is not sorted by the complete candidate key set")
    for row, site in zip(comparison, ordered_sites):
        expected = expected_comparison_row(
            site,
            votes35.get(site.key),
            votes150[site.key],
        )
        differences = [
            name
            for name in COMPARISON_COLUMNS
            if name != "review_rank" and row.get(name) != expected[name]
        ]
        if differences:
            raise CheckError(
                f"comparison row mismatch at {site.key}: {differences[:8]}"
            )
    included = [row for row in comparison if row["evaluation_included"] == "1"]
    excluded = [row for row in comparison if row["evaluation_included"] == "0"]
    if len(included) != 130 or len(excluded) != 71:
        raise CheckError("comparison 130/71 split mismatch")
    if sum(row["evaluation_label"] == "1" for row in included) != 82:
        raise CheckError("comparison experimental-positive count mismatch")
    if sum(row["evaluation_label"] == "0" for row in included) != 48:
        raise CheckError("comparison control count mismatch")
    if any(row["evaluation_label"] != "" for row in excluded):
        raise CheckError("inferred row has an evaluation label")
    if any(row["evidence_class"] != "inferred_positive" for row in excluded):
        raise CheckError("display-only row is not inferred")

    metrics = load_json(comparison_dir / "metrics.json")
    expected_metrics = recompute_metrics(comparison)
    selected = select_review_keys(comparison)
    policy = {
        "version": "w1-disagreement-v1",
        "pool": "honest_130",
        "limit": REVIEW_LIMIT,
        "strata_order": list(STRATA_ORDER),
        "within_stratum_sort": [
            "ranking_confidence_desc",
            "accession_asc",
            "pos_asc",
        ],
        "fill_policy": "remaining_honest_disagreements_by_global_confidence",
        "selected_row_ids": [row_id for _, row_id in selected],
    }
    expected_metrics["review_policy"] = policy
    _compare_json(metrics, expected_metrics, "$.metrics")

    review = read_csv_exact(comparison_dir / "review_top10.csv", REVIEW_COLUMNS)
    if len(review) != REVIEW_LIMIT:
        raise CheckError("review_top10.csv does not contain exactly ten rows")
    by_id = {row["row_id"]: row for row in comparison}
    ranks: dict[str, str] = {}
    for rank, ((stratum, row_id), actual) in enumerate(zip(selected, review), start=1):
        source = by_id[row_id]
        expected = expected_review_row(rank, stratum, source)
        if actual != expected:
            differences = [
                name for name in REVIEW_COLUMNS if actual.get(name) != expected[name]
            ]
            raise CheckError(
                f"review row mismatch at rank {rank}: {differences[:8]}"
            )
        ranks[row_id] = str(rank)
    if len(ranks) != REVIEW_LIMIT:
        raise CheckError("review row IDs are not unique")
    for row in comparison:
        expected_rank = ranks.get(row["row_id"], "")
        if row["review_rank"] != expected_rank:
            raise CheckError(f"comparison review_rank mismatch: {row['row_id']}")

    manifest_review = manifest.get("review", {})
    expected_manifest_review = {
        "policy_version": policy["version"],
        "pool": policy["pool"],
        "limit": policy["limit"],
        "strata_order": policy["strata_order"],
        "within_stratum_sort": policy["within_stratum_sort"],
        "fill_policy": policy["fill_policy"],
        "selected_row_ids": policy["selected_row_ids"],
    }
    if manifest_review != expected_manifest_review:
        raise CheckError("manifest review policy/selection mismatch")

    if manifest.get("esm150_inference_manifest_sha256") is None:
        raise CheckError("manifest missing 150M inference-manifest hash")
    methods = manifest.get("methods", {})
    if set(methods) != {"sequon_rule", "esm35_oof", "esm150_author_adapter"}:
        raise CheckError("manifest method IDs mismatch")
    if methods["sequon_rule"].get("independent_of_benchmark") is not True:
        raise CheckError("sequon rule independence flag mismatch")
    if methods["esm35_oof"].get("independent_of_benchmark") is not True:
        raise CheckError("35M independence flag mismatch")
    if methods["esm150_author_adapter"].get("independent_of_benchmark") is not True:
        raise CheckError("150M independence flag mismatch")
    if manifest.get("benchmark") != {
        **expected_metrics["benchmark"],
        "p13611_only_inferred": True,
    }:
        raise CheckError("manifest benchmark contract mismatch")
    if manifest.get("comparison") != {
        "rows": 201,
        "evaluated": 130,
        "display_only": 71,
    }:
        raise CheckError("manifest comparison counts mismatch")
    metric_summary = {}
    for method_id, method in expected_metrics["methods"].items():
        metric_summary[method_id] = {
            "evaluation_rows": method["evaluation_rows"],
            "mcc": method["metrics"]["mcc"],
            "mcc_defined": method["mcc_defined"],
            "roc_auc": method["metrics"]["roc_auc"],
        }
    _compare_json(manifest.get("metric_summary"), metric_summary, "$.metric_summary")

    for timestamp_key in ("created_at", "generated_at", "timestamp", "elapsed_seconds"):
        if timestamp_key in manifest:
            raise CheckError(f"manifest contains non-deterministic field: {timestamp_key}")
    source = manifest.get("source", {})
    if not isinstance(source.get("git_commit"), str) or len(source["git_commit"]) != 40:
        raise CheckError("manifest git commit is invalid")
    if not isinstance(source.get("git_dirty"), bool):
        raise CheckError("manifest git dirty flag is invalid")

    report = (comparison_dir / "report.md").read_text(encoding="utf-8")
    required_report_text = (
        "unannotated sequons, not confirmed biological negatives",
        "not a method",
        "cannot be attributed to model size alone",
        "PENDING_MANUAL_REVIEW",
        "No author-replay prediction input was read or used.",
    )
    for text in required_report_text:
        if text not in report:
            raise CheckError(f"report is missing required text: {text}")
    for _, row_id in selected:
        if row_id not in report:
            raise CheckError(f"report omits selected row: {row_id}")

    return comparison, metrics, manifest


def verify_input_provenance(
    manifest: Mapping[str, Any],
    config: CheckConfig,
    esm35_manifest: Mapping[str, Any],
    esm150_manifest: Mapping[str, Any],
) -> None:
    inputs = manifest.get("inputs", {})
    if inputs.get("candidates", {}).get("sha256") != sha256_file(config.candidates):
        raise CheckError("comparison manifest candidate hash mismatch")
    if inputs.get("esm35", {}).get("predictions.csv", {}).get("sha256") != sha256_file(
        config.esm35_run_dir / "predictions.csv"
    ):
        raise CheckError("comparison manifest 35M prediction hash mismatch")
    if inputs.get("esm35", {}).get("metrics.json", {}).get("sha256") != sha256_file(
        config.esm35_run_dir / "metrics.json"
    ):
        raise CheckError("comparison manifest 35M metrics hash mismatch")
    if inputs.get("esm35", {}).get("manifest.json", {}).get("sha256") != sha256_file(
        config.esm35_run_dir / "manifest.json"
    ):
        raise CheckError("comparison manifest 35M manifest hash mismatch")
    if inputs.get("esm150", {}).get("manifest.json", {}).get("sha256") != sha256_file(
        config.esm150_run_dir / "manifest.json"
    ):
        raise CheckError("comparison manifest 150M manifest hash mismatch")
    if inputs.get("esm150", {}).get("predictions.csv", {}).get("sha256") != sha256_file(
        config.esm150_run_dir / "predictions.csv"
    ):
        raise CheckError("comparison manifest 150M prediction hash mismatch")
    if inputs.get("esm150", {}).get("report.md", {}).get("sha256") != sha256_file(
        config.esm150_run_dir / "report.md"
    ):
        raise CheckError("comparison manifest 150M report hash mismatch")
    if manifest.get("esm150_inference_manifest_sha256") != sha256_file(
        config.esm150_run_dir / "manifest.json"
    ):
        raise CheckError("comparison manifest 150M inference-manifest hash mismatch")
    if esm35_manifest.get("schema") != ESM35_SCHEMA:
        raise CheckError("unexpected 35M manifest")
    if esm150_manifest.get("schema") != ESM150_SCHEMA:
        raise CheckError("unexpected 150M manifest")
    adapter_weights = config.adapter_dir / "adapter_model.safetensors"
    adapter_config = config.adapter_dir / "adapter_config.json"
    if not adapter_weights.is_file() or not adapter_config.is_file():
        raise CheckError("adapter directory is incomplete")
    if sha256_file(adapter_weights) != EXPECTED_ADAPTER_SHA256:
        raise CheckError("adapter weight hash mismatch")
    if not config.compat_path.is_dir():
        raise CheckError("compatibility path does not exist")


def parse_args(argv: Sequence[str] | None = None) -> CheckConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-dir", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--candidates-lora", type=Path, default=DEFAULT_CANDIDATES_LORA)
    parser.add_argument("--esm35-run-dir", type=Path, default=DEFAULT_ESM35_RUN_DIR)
    parser.add_argument("--esm150-run-dir", type=Path, default=DEFAULT_ESM150_RUN_DIR)
    parser.add_argument("--adapter-dir", type=Path, default=DEFAULT_ADAPTER_DIR)
    parser.add_argument("--compat-path", type=Path, default=DEFAULT_COMPAT_PATH)
    parser.add_argument("--logit-tolerance", type=float, default=1e-12)
    args = parser.parse_args(argv)
    return CheckConfig(
        comparison_dir=args.comparison_dir,
        candidates=args.candidates,
        candidates_lora=args.candidates_lora,
        esm35_run_dir=args.esm35_run_dir,
        esm150_run_dir=args.esm150_run_dir,
        adapter_dir=args.adapter_dir,
        compat_path=args.compat_path,
        logit_tolerance=args.logit_tolerance,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        config = parse_args(argv)
        sites = load_candidates(config.candidates)
        lora = load_candidates_lora(config.candidates_lora, sites)
        votes35, esm35_manifest = load_esm35(config.esm35_run_dir, sites)
        votes150, esm150_manifest = load_esm150(
            config.esm150_run_dir,
            sites,
            lora,
            config.candidates_lora,
            config.logit_tolerance,
        )
        _, metrics, manifest = verify_comparison(
            config.comparison_dir,
            sites,
            votes35,
            votes150,
            esm35_manifest,
            esm150_manifest,
        )
        verify_input_provenance(
            manifest,
            config,
            esm35_manifest,
            esm150_manifest,
        )
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "comparison_rows": 201,
                "evaluated_rows": 130,
                "inferred_display_only": 71,
                "review_rows": 10,
                "metric_methods": sorted(metrics["methods"]),
                "inference_recheck": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
