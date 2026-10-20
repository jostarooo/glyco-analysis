"""Independently verify an ESM-2 35M linear-probe run.

This checker imports no code from the runner. It rebuilds the input labels,
windows, folds, classifier fits, metrics, and report block from the raw inputs
and committed artifacts.

Exit codes: 0 PASS, 1 FAIL, 2 missing or unreadable required input.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import warnings
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "glyco.esm35-linear-probe/v1"
MODEL_ID = "facebook/esm2_t12_35M_UR50D"
MODEL_REVISION = "6fbf070e65b0b7291e7bbcd451118c216cff79d8"
HIDDEN_SIZE = 480
MAX_POSITION_EMBEDDINGS = 1026
MAX_WINDOW_RESIDUES = 1023
WINDOW_RADIUS = 511
SEED = 20261020
BOOTSTRAP_REPLICATES = 2000
THRESHOLD = 0.5
MAX_EXAMPLES = 5

ARTIFACT_COLUMNS = {
    "windows.csv": (
        "row_id",
        "accession",
        "pos",
        "label",
        "seq_len",
        "window_start",
        "window_end",
        "window_len",
        "target_offset",
        "residue",
        "window_sha256",
        "fold_id",
    ),
    "folds.csv": (
        "fold_id",
        "held_out_accession",
        "train_rows",
        "test_rows",
        "train_positive",
        "test_positive",
        "train_negative",
        "test_negative",
    ),
    "predictions.csv": (
        "row_id",
        "accession",
        "pos",
        "label",
        "fold_id",
        "logit",
        "probability",
        "prediction",
    ),
}
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
ARTIFACT_NAMES = (
    "windows.csv",
    "folds.csv",
    "embeddings.npy",
    "predictions.csv",
    "metrics.json",
    "report.md",
)
SEQUON = re.compile(r"N[^P][ST]\Z")
METRICS_BEGIN = "<!-- BEGIN GENERATED METRICS -->"
METRICS_END = "<!-- END GENERATED METRICS -->"


@dataclass(frozen=True)
class Candidate:
    row_id: str
    accession: str
    position: int
    label: bool
    seq_len: int
    sequence: str


@dataclass(frozen=True)
class Fold:
    fold_id: str
    held_out: str
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: Counter[str] = Counter()
        self.examples: dict[str, list[str]] = {}

    def check(self, condition: bool, section: str, detail: str) -> bool:
        if condition:
            self.passed += 1
            return True
        self.failures[section] += 1
        bucket = self.examples.setdefault(section, [])
        if len(bucket) < MAX_EXAMPLES:
            bucket.append(detail)
        return False

    def report(self) -> int:
        print(f"passed assertions: {self.passed}")
        if not self.failures:
            print("PASS")
            return 0
        print(f"FAIL: {sum(self.failures.values())} mismatches")
        for section, count in self.failures.most_common():
            print(f"  [{section}] {count}")
            for detail in self.examples[section]:
                print(f"      {detail}")
        return 1


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest().upper()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_csv(path: Path, expected_columns: Sequence[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != tuple(expected_columns):
            raise ValueError(
                f"{path.name} columns {reader.fieldnames} != {tuple(expected_columns)}"
            )
        return list(reader)


def label_from_record(record: dict, position: int) -> bool:
    for feature in record.get("features") or []:
        if feature.get("type") != "Glycosylation":
            continue
        start = ((feature.get("location") or {}).get("start") or {}).get("value")
        description = str(feature.get("description") or "")
        if start == position and description.startswith("N-linked"):
            return True
    return False


def read_inputs(
    candidates_path: Path,
    cache_dir: Path,
    check: Checker,
) -> tuple[list[Candidate], dict[str, dict], str]:
    raw_rows = read_csv(candidates_path, CANDIDATE_COLUMNS)
    accessions = sorted({row["accession"] for row in raw_rows})
    records = {}
    for accession in accessions:
        path = cache_dir / f"{accession}.json"
        records[accession] = json.loads(path.read_text(encoding="utf-8"))

    list_payload = json.loads((cache_dir / "_list.json").read_text(encoding="utf-8"))
    release = list_payload["release"]
    candidates = []
    seen = set()
    for row in raw_rows:
        accession = row["accession"]
        position = int(row["pos"])
        sequence = records[accession]["sequence"]["value"]
        residue = sequence[position - 1] if 0 < position <= len(sequence) else "?"
        motif = sequence[position - 1 : position + 2]
        derived_label = label_from_record(records[accession], position)
        check.check(
            (accession, position) not in seen,
            "input uniqueness",
            f"duplicate {accession}#{position}",
        )
        seen.add((accession, position))
        check.check(
            row["label"] in {"0", "1"} and (row["label"] == "1") == derived_label,
            "label from raw cache",
            f"{accession}#{position} csv={row['label']} cache={int(derived_label)}",
        )
        check.check(
            row["uniprot_release"] == release,
            "release",
            f"{accession}#{position} csv={row['uniprot_release']} list={release}",
        )
        check.check(
            int(row["seq_len"]) == len(sequence),
            "sequence length",
            f"{accession} csv={row['seq_len']} cache={len(sequence)}",
        )
        check.check(
            residue == "N" and row["residue"] == "N",
            "target residue",
            f"{accession}#{position} residue={residue!r}",
        )
        check.check(
            len(motif) == 3 and SEQUON.fullmatch(motif) is not None,
            "sequon",
            f"{accession}#{position} motif={motif!r}",
        )
        check.check(
            row["motif"] == motif and row["sequon"] == "1",
            "sequon table",
            f"{accession}#{position} motif={row['motif']!r} sequon={row['sequon']!r}",
        )
        candidates.append(
            Candidate(
                row_id=f"{accession}:{position}",
                accession=accession,
                position=position,
                label=row["label"] == "1",
                seq_len=len(sequence),
                sequence=sequence,
            )
        )

    candidates.sort(key=lambda item: (item.accession, item.position))
    order = [(item.accession, item.position) for item in candidates]
    check.check(order == sorted(order), "row order", "inputs are not sorted")
    return candidates, records, release


def expected_window(candidate: Candidate) -> dict[str, object]:
    if candidate.seq_len <= MAX_WINDOW_RESIDUES:
        start = 1
        end = candidate.seq_len
    else:
        start = min(
            max(1, candidate.position - WINDOW_RADIUS),
            candidate.seq_len - MAX_WINDOW_RESIDUES + 1,
        )
        end = start + MAX_WINDOW_RESIDUES - 1
    offset = candidate.position - start
    window = candidate.sequence[start - 1 : end]
    return {
        "row_id": candidate.row_id,
        "accession": candidate.accession,
        "pos": candidate.position,
        "label": int(candidate.label),
        "seq_len": candidate.seq_len,
        "window_start": start,
        "window_end": end,
        "window_len": len(window),
        "target_offset": offset,
        "residue": window[offset],
        "window_sha256": sha256_bytes(window.encode("ascii")),
        "fold_id": f"lopo:{candidate.accession}",
        "window": window,
    }


def expected_folds(candidates: Sequence[Candidate]) -> list[Fold]:
    folds = []
    for accession in sorted({candidate.accession for candidate in candidates}):
        train = tuple(
            index
            for index, candidate in enumerate(candidates)
            if candidate.accession != accession
        )
        test = tuple(
            index
            for index, candidate in enumerate(candidates)
            if candidate.accession == accession
        )
        folds.append(
            Fold(
                fold_id=f"lopo:{accession}",
                held_out=accession,
                train_indices=train,
                test_indices=test,
            )
        )
    return folds


def point_metrics(labels: np.ndarray, predictions: np.ndarray, probabilities: np.ndarray):
    labels = labels.astype(bool, copy=False)
    predictions = predictions.astype(bool, copy=False)
    true_positive = int(np.sum(labels & predictions))
    true_negative = int(np.sum(~labels & ~predictions))
    false_positive = int(np.sum(~labels & predictions))
    false_negative = int(np.sum(labels & ~predictions))
    null_reasons = {}
    denominator = math.sqrt(
        (true_positive + false_positive)
        * (true_positive + false_negative)
        * (true_negative + false_positive)
        * (true_negative + false_negative)
    )
    mcc = (
        (true_positive * true_negative - false_positive * false_negative) / denominator
        if denominator
        else None
    )
    sensitivity = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else None
    )
    specificity = (
        true_negative / (true_negative + false_positive)
        if true_negative + false_positive
        else None
    )
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else None
    )
    accuracy = (
        (true_positive + true_negative) / len(labels) if len(labels) else None
    )
    if mcc is None:
        null_reasons["mcc"] = "confusion matrix has no square root support"
    if sensitivity is None:
        null_reasons["sensitivity"] = "no positive labels"
    if specificity is None:
        null_reasons["specificity"] = "no negative labels"
    if precision is None:
        null_reasons["precision"] = "no predicted positives"
    if accuracy is None:
        null_reasons["accuracy"] = "no rows"
    if np.unique(labels).size == 2:
        from sklearn.metrics import roc_auc_score

        roc_auc = float(roc_auc_score(labels, probabilities))
    else:
        roc_auc = None
        null_reasons["roc_auc"] = "ROC AUC requires both classes"
    return {
        "confusion": {
            "true_negative": true_negative,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "true_positive": true_positive,
        },
        "metrics": {
            "mcc": None if mcc is None else float(mcc),
            "sensitivity": sensitivity,
            "specificity": specificity,
            "precision": precision,
            "accuracy": accuracy,
            "roc_auc": roc_auc,
        },
        "null_reasons": null_reasons,
    }


def bootstrap_by_protein(
    labels: np.ndarray,
    predictions: np.ndarray,
    probabilities: np.ndarray,
    accessions: Sequence[str],
    replicates: int,
    seed: int,
) -> dict:
    names = sorted(set(accessions))
    indices_by_name = {
        name: np.asarray(
            [index for index, accession in enumerate(accessions) if accession == name],
            dtype=np.int64,
        )
        for name in names
    }
    rng = np.random.default_rng(seed)
    collected = {"mcc": [], "sensitivity": [], "specificity": []}
    for _ in range(replicates):
        sampled = rng.choice(names, size=len(names), replace=True)
        indices = np.concatenate([indices_by_name[name] for name in sampled])
        values = point_metrics(
            labels[indices], predictions[indices], probabilities[indices]
        )["metrics"]
        if all(values[name] is not None for name in collected):
            for name in collected:
                collected[name].append(values[name])
    valid = len(collected["mcc"])
    return {
        "unit": "protein",
        "replicates": replicates,
        "seed": seed,
        "valid_replicates": valid,
        "undefined_replicates": replicates - valid,
        "ci95": {
            name: (
                [
                    float(np.percentile(values, 2.5)),
                    float(np.percentile(values, 97.5)),
                ]
                if values
                else [None, None]
            )
            for name, values in collected.items()
        },
    }


def format_metric(value) -> str:
    return "null" if value is None else f"{value:.6f}"


def format_interval(values: Sequence[float | None]) -> str:
    if len(values) != 2 or any(value is None for value in values):
        return "null"
    return f"[{values[0]:.6f}, {values[1]:.6f}]"


def metrics_block(metrics: dict, proteins: int) -> str:
    point = metrics["metrics"]
    confusion = metrics["confusion"]
    bootstrap = metrics["bootstrap"]
    lines = [
        METRICS_BEGIN,
        "| metric | value |",
        "|---|---:|",
        f"| MCC | {format_metric(point['mcc'])} |",
        f"| sensitivity | {format_metric(point['sensitivity'])} |",
        f"| specificity | {format_metric(point['specificity'])} |",
        f"| precision | {format_metric(point['precision'])} |",
        f"| accuracy | {format_metric(point['accuracy'])} |",
        f"| ROC AUC | {format_metric(point['roc_auc'])} |",
        f"| confusion | TN={confusion['true_negative']} FP={confusion['false_positive']} FN={confusion['false_negative']} TP={confusion['true_positive']} |",
        "",
        (
            f"{bootstrap['replicates']} protein-bootstrap replicates over "
            f"{proteins} proteins. This is a {proteins}-protein resampling interval, "
            "not a generalisation guarantee."
        ),
        f"Valid replicates: {bootstrap['valid_replicates']}; undefined: {bootstrap['undefined_replicates']}.",
        "",
        "| interval | 95% |",
        "|---|---:|",
        f"| MCC | {format_interval(bootstrap['ci95']['mcc'])} |",
        f"| sensitivity | {format_interval(bootstrap['ci95']['sensitivity'])} |",
        f"| specificity | {format_interval(bootstrap['ci95']['specificity'])} |",
        METRICS_END,
    ]
    return "\n".join(lines)


def close_float(actual, expected, tolerance: float = 1e-12) -> bool:
    if actual is None or expected is None:
        return actual is expected
    return math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=tolerance)


def compare_metric_value(
    check: Checker,
    section: str,
    actual,
    expected,
    tolerance: float = 1e-12,
) -> None:
    check.check(
        close_float(actual, expected, tolerance),
        section,
        f"actual={actual!r} expected={expected!r}",
    )


def configure_torch() -> None:
    import torch

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    if hasattr(torch.backends.cuda, "enable_flash_sdp"):
        torch.backends.cuda.enable_flash_sdp(False)
        torch.backends.cuda.enable_mem_efficient_sdp(False)
        torch.backends.cuda.enable_math_sdp(True)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")


def tokenizer_alignment(
    tokenizer,
    windows: Sequence[dict[str, object]],
    check: Checker,
) -> dict[tuple[str, int, int], dict[str, object]]:
    jobs: dict[tuple[str, int, int], dict[str, object]] = {}
    for window in windows:
        key = (
            str(window["accession"]),
            int(window["window_start"]),
            int(window["window_end"]),
        )
        jobs.setdefault(
            key,
            {
                "window": window["window"],
                "targets": [],
            },
        )["targets"].append(
            (
                str(window["row_id"]),
                int(window["target_offset"]),
                str(window["residue"]),
            )
        )

    for key, job in jobs.items():
        encoded = tokenizer(
            job["window"], return_tensors="pt", truncation=False, padding=False
        )
        input_ids = encoded["input_ids"][0]
        check.check(
            len(input_ids) <= MAX_POSITION_EMBEDDINGS,
            "token length",
            f"{key} tokens={len(input_ids)}",
        )
        for row_id, offset, target_residue in job["targets"]:
            token_index = 1 + offset
            token = tokenizer.convert_ids_to_tokens(int(input_ids[token_index]))
            residue = job["window"][offset]
            check.check(
                token == residue == target_residue,
                "token alignment",
                f"{row_id} token={token!r} window_residue={residue!r}",
            )
    return jobs


def reembed_and_compare(
    tokenizer,
    jobs: dict[tuple[str, int, int], dict[str, object]],
    candidates: Sequence[Candidate],
    windows: Sequence[dict[str, object]],
    features: np.ndarray,
    device_name: str,
    check: Checker,
) -> None:
    import torch
    from transformers import AutoModel

    if device_name == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(device_name)
    model = AutoModel.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        local_files_only=True,
    )
    model.to(device=device, dtype=torch.float32)
    model.eval()
    model.requires_grad_(False)

    ordered = sorted(jobs.items(), key=lambda item: (len(item[1]["window"]), item[0]))
    vectors: dict[tuple[str, int, int], dict[str, np.ndarray]] = {}
    for start in range(0, len(ordered), 4):
        batch = ordered[start : start + 4]
        encoded = tokenizer(
            [job["window"] for _, job in batch],
            padding=True,
            return_tensors="pt",
            truncation=False,
        )
        with torch.inference_mode():
            hidden = model(
                input_ids=encoded["input_ids"].to(device),
                attention_mask=encoded["attention_mask"].to(device),
            ).last_hidden_state
        for batch_index, (key, job) in enumerate(batch):
            vectors[key] = {}
            for row_id, offset, _ in job["targets"]:
                vectors[key][row_id] = (
                    hidden[batch_index, 1 + offset].float().cpu().numpy()
                )

    for index, (candidate, window) in enumerate(zip(candidates, windows)):
        key = (
            candidate.accession,
            int(window["window_start"]),
            int(window["window_end"]),
        )
        actual = features[index]
        expected = vectors[key][candidate.row_id]
        difference = float(np.max(np.abs(actual - expected)))
        scale = float(np.max(np.abs(expected))) or 1.0
        check.check(
            difference <= 5e-4 + 5e-4 * scale,
            "re-embedding",
            f"{candidate.row_id} max_abs_diff={difference:.9g}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ESM-2 35M probe artifacts")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "esm35_linear_probe_v0",
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=REPO_ROOT / "reports" / "candidates_30.csv",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=REPO_ROOT / "data" / "raw" / "uniprot",
    )
    parser.add_argument("--reembed", action="store_true")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    manifest_path = run_dir / "manifest.json"
    required = [manifest_path] + [run_dir / name for name in ARTIFACT_NAMES]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print(f"missing required input: {missing[0]}", file=sys.stderr)
        return 2
    if not args.candidates.is_file():
        print(f"missing required input: {args.candidates}", file=sys.stderr)
        return 2
    if not args.cache_dir.is_dir():
        print(f"missing required input: {args.cache_dir}", file=sys.stderr)
        return 2

    check = Checker()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        candidates, records, release = read_inputs(
            args.candidates.resolve(), args.cache_dir.resolve(), check
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"unreadable required input: {error}", file=sys.stderr)
        return 2

    check.check(manifest.get("schema") == SCHEMA, "manifest schema", str(manifest.get("schema")))
    check.check(
        manifest.get("status") == "complete",
        "manifest status",
        str(manifest.get("status")),
    )
    check.check(
        "generated_at" not in manifest and "timestamp" not in manifest,
        "manifest determinism",
        "manifest contains a wall-clock field",
    )
    check.check(len(candidates) == 201, "input rows", str(len(candidates)))
    check.check(
        len({candidate.accession for candidate in candidates}) == 29,
        "input proteins",
        str(len({candidate.accession for candidate in candidates})),
    )
    check.check(
        sum(candidate.label for candidate in candidates) == 153,
        "positive labels",
        str(sum(candidate.label for candidate in candidates)),
    )
    check.check(
        sum(not candidate.label for candidate in candidates) == 48,
        "negative labels",
        str(sum(not candidate.label for candidate in candidates)),
    )

    artifact_records = manifest.get("artifacts") or {}
    check.check(
        tuple(sorted(artifact_records)) == tuple(sorted(ARTIFACT_NAMES)),
        "artifact set",
        f"actual={tuple(sorted(artifact_records))}",
    )
    for name in ARTIFACT_NAMES:
        path = run_dir / name
        record = artifact_records.get(name) or {}
        check.check(
            path.stat().st_size == record.get("bytes"),
            f"artifact bytes {name}",
            f"actual={path.stat().st_size} manifest={record.get('bytes')}",
        )
        check.check(
            file_sha256(path) == record.get("sha256"),
            f"artifact sha256 {name}",
            f"actual={file_sha256(path)} manifest={record.get('sha256')}",
        )

    inputs = manifest.get("inputs") or {}
    check.check(
        inputs.get("candidates", {}).get("sha256") == file_sha256(args.candidates),
        "candidate hash",
        "manifest candidate hash differs from input",
    )
    check.check(
        inputs.get("uniprot_release") == release,
        "manifest release",
        f"manifest={inputs.get('uniprot_release')} cache={release}",
    )
    check.check(
        inputs.get("uniprot_list_sha256")
        == file_sha256(args.cache_dir / "_list.json"),
        "UniProt list hash",
        "manifest list hash differs from cache",
    )
    cache_hash = hashlib.sha256()
    for accession in sorted(records):
        path = args.cache_dir / f"{accession}.json"
        cache_hash.update(accession.encode("ascii"))
        cache_hash.update(b"\0")
        cache_hash.update(bytes.fromhex(file_sha256(path)))
    check.check(
        inputs.get("sequence_cache_sha256") == cache_hash.hexdigest().upper(),
        "sequence cache hash",
        "manifest sequence-cache hash differs from cache",
    )

    model = manifest.get("model") or {}
    settings = manifest.get("settings") or {}
    counts = manifest.get("counts") or {}
    check.check(model.get("id") == MODEL_ID, "manifest model", str(model.get("id")))
    check.check(
        model.get("revision") == MODEL_REVISION,
        "manifest revision",
        str(model.get("revision")),
    )
    check.check(
        model.get("hidden_size") == HIDDEN_SIZE,
        "manifest hidden size",
        str(model.get("hidden_size")),
    )
    check.check(
        settings.get("split") == "leave_one_protein_out",
        "manifest split",
        str(settings.get("split")),
    )
    check.check(
        settings.get("class_weight") == "none"
        and settings.get("solver") == "liblinear"
        and settings.get("C") == 1.0,
        "manifest classifier",
        str(settings),
    )
    check.check(settings.get("threshold") == THRESHOLD, "manifest threshold", str(settings))
    check.check(
        settings.get("bootstrap_replicates") == BOOTSTRAP_REPLICATES,
        "manifest bootstrap",
        str(settings.get("bootstrap_replicates")),
    )
    check.check(counts.get("rows") == 201, "manifest rows", str(counts.get("rows")))
    check.check(
        counts.get("proteins") == 29,
        "manifest proteins",
        str(counts.get("proteins")),
    )
    check.check(
        counts.get("unique_windows") == 82,
        "manifest windows",
        str(counts.get("unique_windows")),
    )

    window_rows = read_csv(run_dir / "windows.csv", ARTIFACT_COLUMNS["windows.csv"])
    expected_windows = [expected_window(candidate) for candidate in candidates]
    check.check(len(window_rows) == 201, "window rows", str(len(window_rows)))
    unique_windows = set()
    for raw, expected in zip(window_rows, expected_windows):
        for field in ARTIFACT_COLUMNS["windows.csv"]:
            check.check(
                raw[field] == str(expected[field]),
                f"window field {field}",
                f"{expected['row_id']} actual={raw[field]!r} expected={expected[field]!r}",
            )
        unique_windows.add(
            (expected["accession"], expected["window_start"], expected["window_end"])
        )
    check.check(len(unique_windows) == 82, "unique windows", str(len(unique_windows)))

    folds = expected_folds(candidates)
    fold_rows = read_csv(run_dir / "folds.csv", ARTIFACT_COLUMNS["folds.csv"])
    check.check(len(fold_rows) == 29, "fold rows", str(len(fold_rows)))
    tested: list[int] = []
    labels = np.asarray([candidate.label for candidate in candidates], dtype=bool)
    for raw, fold in zip(fold_rows, folds):
        check.check(raw["fold_id"] == fold.fold_id, "fold id", raw["fold_id"])
        check.check(
            raw["held_out_accession"] == fold.held_out,
            "fold accession",
            raw["held_out_accession"],
        )
        check.check(
            not any(
                candidates[index].accession == fold.held_out
                for index in fold.train_indices
            ),
            "LOPO disjointness",
            fold.fold_id,
        )
        expected_counts = (
            len(fold.train_indices),
            len(fold.test_indices),
            int(labels[list(fold.train_indices)].sum()),
            int(labels[list(fold.test_indices)].sum()),
            int((~labels[list(fold.train_indices)]).sum()),
            int((~labels[list(fold.test_indices)]).sum()),
        )
        actual_counts = tuple(
            int(raw[name])
            for name in (
                "train_rows",
                "test_rows",
                "train_positive",
                "test_positive",
                "train_negative",
                "test_negative",
            )
        )
        check.check(
            actual_counts == expected_counts,
            "fold counts",
            f"{fold.fold_id} actual={actual_counts} expected={expected_counts}",
        )
        tested.extend(fold.test_indices)
    check.check(sorted(tested) == list(range(len(candidates))), "LOPO completeness", "")

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        local_files_only=True,
    )
    jobs = tokenizer_alignment(tokenizer, expected_windows, check)

    features = np.load(run_dir / "embeddings.npy", allow_pickle=False)
    check.check(
        features.shape == (201, HIDDEN_SIZE),
        "embedding shape",
        str(features.shape),
    )
    check.check(
        features.dtype == np.float32,
        "embedding dtype",
        str(features.dtype),
    )
    check.check(features.flags.c_contiguous, "embedding order", "not C-contiguous")
    check.check(np.isfinite(features).all(), "embedding finiteness", "non-finite value")

    prediction_rows = read_csv(
        run_dir / "predictions.csv", ARTIFACT_COLUMNS["predictions.csv"]
    )
    check.check(len(prediction_rows) == 201, "prediction rows", str(len(prediction_rows)))
    actual_probabilities = []
    actual_predictions = []
    for raw, candidate, window in zip(prediction_rows, candidates, expected_windows):
        check.check(
            raw["row_id"] == candidate.row_id
            and raw["accession"] == candidate.accession
            and raw["pos"] == str(candidate.position)
            and raw["label"] == str(int(candidate.label))
            and raw["fold_id"] == window["fold_id"],
            "prediction identity",
            raw["row_id"],
        )
        probability = float(raw["probability"])
        actual_probabilities.append(probability)
        actual_predictions.append(raw["prediction"] == "1")

    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    max_logit_difference = 0.0
    max_probability_difference = 0.0
    prediction_mismatches = 0
    for fold in folds:
        train_indices = np.asarray(fold.train_indices, dtype=np.int64)
        test_indices = np.asarray(fold.test_indices, dtype=np.int64)
        scaler = StandardScaler()
        train_features = scaler.fit_transform(features[train_indices])
        test_features = scaler.transform(features[test_indices])
        classifier = LogisticRegression(
            C=1.0,
            penalty="l2",
            solver="liblinear",
            max_iter=5000,
            random_state=SEED,
            class_weight=None,
        )
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=FutureWarning)
            classifier.fit(train_features, labels[train_indices])
        logits = classifier.decision_function(test_features)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        predictions = probabilities >= THRESHOLD
        for offset, index in enumerate(test_indices):
            raw = prediction_rows[index]
            max_logit_difference = max(
                max_logit_difference, abs(float(raw["logit"]) - float(logits[offset]))
            )
            max_probability_difference = max(
                max_probability_difference,
                abs(float(raw["probability"]) - float(probabilities[offset])),
            )
            prediction_mismatches += int(
                (raw["prediction"] == "1") != bool(predictions[offset])
            )
    check.check(
        max_logit_difference <= 1e-12,
        "retrained logits",
        f"max difference={max_logit_difference:.9g}",
    )
    check.check(
        max_probability_difference <= 1e-12,
        "retrained probabilities",
        f"max difference={max_probability_difference:.9g}",
    )
    check.check(
        prediction_mismatches == 0,
        "retrained predictions",
        f"{prediction_mismatches} mismatches",
    )

    stored_metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    probabilities_array = np.asarray(actual_probabilities, dtype=np.float64)
    predictions_array = np.asarray(actual_predictions, dtype=bool)
    recomputed = point_metrics(labels, predictions_array, probabilities_array)
    for key, value in recomputed["confusion"].items():
        check.check(
            stored_metrics.get("confusion", {}).get(key) == value,
            "confusion",
            f"{key} actual={stored_metrics.get('confusion', {}).get(key)} expected={value}",
        )
    for key, value in recomputed["metrics"].items():
        compare_metric_value(
            check,
            f"metric {key}",
            stored_metrics.get("metrics", {}).get(key),
            value,
        )
    check.check(
        stored_metrics.get("null_reasons") == recomputed["null_reasons"],
        "null reasons",
        f"actual={stored_metrics.get('null_reasons')} expected={recomputed['null_reasons']}",
    )
    accessions = [candidate.accession for candidate in candidates]
    bootstrap = bootstrap_by_protein(
        labels,
        predictions_array,
        probabilities_array,
        accessions,
        BOOTSTRAP_REPLICATES,
        SEED,
    )
    stored_bootstrap = stored_metrics.get("bootstrap") or {}
    for key in ("unit", "replicates", "seed", "valid_replicates", "undefined_replicates"):
        check.check(
            stored_bootstrap.get(key) == bootstrap[key],
            f"bootstrap {key}",
            f"actual={stored_bootstrap.get(key)} expected={bootstrap[key]}",
        )
    for metric in ("mcc", "sensitivity", "specificity"):
        for index, label in enumerate(("lower", "upper")):
            compare_metric_value(
                check,
                f"bootstrap {metric} {label}",
                stored_bootstrap.get("ci95", {}).get(metric, [None, None])[index],
                bootstrap["ci95"][metric][index],
            )

    report_bytes = (run_dir / "report.md").read_bytes()
    report = report_bytes.decode("utf-8")
    check.check(b"\r\n" not in report_bytes, "report LF", "report contains CRLF")
    check.check(
        report.count(METRICS_BEGIN) == 1 and report.count(METRICS_END) == 1,
        "report markers",
        "generated metric markers are not unique",
    )
    start = report.find(METRICS_BEGIN)
    end = report.find(METRICS_END)
    expected_block = metrics_block(stored_metrics, 29)
    check.check(
        start >= 0
        and end >= 0
        and report[start : end + len(METRICS_END)] == expected_block,
        "report metrics block",
        "generated block differs from recomputed values",
    )
    check.check(
        "not annotated" in report and "verified negative" in report,
        "report label semantics",
        "label-0 caveat is missing",
    )
    check.check(
        "0.781" in report and "different dataset" in report,
        "report external reference",
        "paper reference is not labelled as external",
    )

    if args.reembed:
        configure_torch()
        reembed_and_compare(
            tokenizer,
            jobs,
            candidates,
            expected_windows,
            features,
            args.device,
            check,
        )

    print(
        f"rows={len(candidates)} proteins={len(set(accessions))} "
        f"windows={len(unique_windows)} release={release}"
    )
    return check.report()


if __name__ == "__main__":
    raise SystemExit(main())
