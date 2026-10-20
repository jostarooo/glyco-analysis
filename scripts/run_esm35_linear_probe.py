"""Run the frozen ESM-2 35M linear probe on the F1 v0 candidate table.

The runner writes a complete run directory only after every artifact is
available. ``manifest.json`` is the completion marker and is written last.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = REPO_ROOT / "reports" / "candidates_30.csv"
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "raw" / "uniprot"
DEFAULT_OUT_DIR = REPO_ROOT / "reports" / "esm35_linear_probe_v0"

SCHEMA = "glyco.esm35-linear-probe/v1"
MODEL_ID = "facebook/esm2_t12_35M_UR50D"
MODEL_REVISION = "6fbf070e65b0b7291e7bbcd451118c216cff79d8"
HIDDEN_SIZE = 480
MAX_POSITION_EMBEDDINGS = 1026
MAX_WINDOW_RESIDUES = 1023
WINDOW_RADIUS = 511
SEED = 20261020
C = 1.0
THRESHOLD = 0.5
BOOTSTRAP_REPLICATES = 2000

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
WINDOW_COLUMNS = (
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
)
FOLD_COLUMNS = (
    "fold_id",
    "held_out_accession",
    "train_rows",
    "test_rows",
    "train_positive",
    "test_positive",
    "train_negative",
    "test_negative",
)
PREDICTION_COLUMNS = (
    "row_id",
    "accession",
    "pos",
    "label",
    "fold_id",
    "logit",
    "probability",
    "prediction",
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


class InputError(ValueError):
    """The input table or sequence cache violates the declared contract."""


@dataclass(frozen=True)
class ProbeConfig:
    candidates_path: Path
    cache_dir: Path
    out_dir: Path
    device: str
    batch_size: int
    allow_download: bool


@dataclass(frozen=True)
class Candidate:
    row_id: str
    accession: str
    position: int
    label: bool
    seq_len: int
    sequence: str


@dataclass(frozen=True)
class WindowedCandidate:
    candidate: Candidate
    window_start: int
    window_end: int
    target_offset: int
    window: str
    window_sha256: str


@dataclass(frozen=True)
class EmbeddingJob:
    job_id: str
    accession: str
    window_start: int
    window_end: int
    window: str
    targets: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Fold:
    fold_id: str
    held_out: str
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]


@dataclass(frozen=True)
class Prediction:
    row_id: str
    accession: str
    position: int
    label: bool
    fold_id: str
    logit: float
    probability: float
    prediction: bool


@dataclass(frozen=True)
class InputData:
    candidates: tuple[Candidate, ...]
    uniprot_release: str
    candidate_sha256: str
    uniprot_list_sha256: str
    sequence_cache_sha256: str


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest().upper()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(text.encode("utf-8"))
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: object) -> None:
    atomic_write_text(path, json_text(value))


def atomic_write_csv(
    path: Path, columns: Sequence[str], rows: Sequence[Sequence[object]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
    os.replace(temporary, path)


def atomic_write_npy(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        np.save(handle, values, allow_pickle=False)
    os.replace(temporary, path)


def read_candidates(candidates_path: Path, cache_dir: Path) -> InputData:
    if not candidates_path.is_file():
        raise FileNotFoundError(f"candidate table not found: {candidates_path}")
    if not cache_dir.is_dir():
        raise FileNotFoundError(f"UniProt cache directory not found: {cache_dir}")

    with candidates_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CANDIDATE_COLUMNS:
            raise InputError(
                f"candidate columns must be {CANDIDATE_COLUMNS}, got {reader.fieldnames}"
            )
        raw_rows = list(reader)
    if not raw_rows:
        raise InputError("candidate table is empty")

    accessions = sorted({row["accession"] for row in raw_rows})
    records: dict[str, dict] = {}
    cache_hash = hashlib.sha256()
    for accession in accessions:
        path = cache_dir / f"{accession}.json"
        if not path.is_file():
            raise FileNotFoundError(f"cached UniProt record not found: {path}")
        body = path.read_bytes()
        records[accession] = json.loads(body.decode("utf-8"))
        cache_hash.update(accession.encode("ascii"))
        cache_hash.update(b"\0")
        cache_hash.update(bytes.fromhex(sha256_bytes(body)))

    list_path = cache_dir / "_list.json"
    if not list_path.is_file():
        raise FileNotFoundError(f"UniProt list cache not found: {list_path}")
    list_sha256 = file_sha256(list_path)

    candidates = []
    seen: set[tuple[str, int]] = set()
    release = ""
    for raw in raw_rows:
        accession = raw["accession"]
        try:
            position = int(raw["pos"])
            seq_len = int(raw["seq_len"])
        except ValueError as error:
            raise InputError(f"{accession} has a non-integer pos or seq_len") from error
        key = (accession, position)
        if key in seen:
            raise InputError(f"duplicate candidate row: {accession}#{position}")
        seen.add(key)
        if raw["label"] not in {"0", "1"}:
            raise InputError(f"{accession}#{position} has invalid label {raw['label']!r}")
        if raw["sequon"] != "1":
            raise InputError(f"{accession}#{position} is not marked as a sequon")
        if raw["uniprot_release"] != raw_rows[0]["uniprot_release"]:
            raise InputError("candidate rows contain multiple UniProt releases")
        release = raw["uniprot_release"]
        if not release:
            raise InputError("candidate table has an empty UniProt release")

        record = records[accession]
        sequence = record["sequence"]["value"]
        if seq_len != len(sequence):
            raise InputError(
                f"{accession} declares seq_len {seq_len}, cache has {len(sequence)}"
            )
        if not 1 <= position <= seq_len:
            raise InputError(f"{accession}#{position} is outside the sequence")
        residue = sequence[position - 1]
        if residue != "N" or raw["residue"] != residue:
            raise InputError(
                f"{accession}#{position} residue {residue!r} disagrees with {raw['residue']!r}"
            )
        motif = sequence[position - 1 : position + 2]
        if (
            len(motif) != 3
            or SEQUON.fullmatch(motif) is None
            or raw["motif"] != motif
        ):
            raise InputError(
                f"{accession}#{position} has invalid sequon {raw['motif']!r}, expected {motif!r}"
            )
        label = raw["label"] == "1"
        if label != (raw["linkage"] == "N-linked"):
            raise InputError(f"{accession}#{position} label and linkage disagree")

        candidates.append(
            Candidate(
                row_id=f"{accession}:{position}",
                accession=accession,
                position=position,
                label=label,
                seq_len=seq_len,
                sequence=sequence,
            )
        )

    candidates.sort(key=lambda item: (item.accession, item.position))
    return InputData(
        candidates=tuple(candidates),
        uniprot_release=release,
        candidate_sha256=file_sha256(candidates_path),
        uniprot_list_sha256=list_sha256,
        sequence_cache_sha256=cache_hash.hexdigest().upper(),
    )


def build_window(candidate: Candidate) -> WindowedCandidate:
    if candidate.seq_len <= MAX_WINDOW_RESIDUES:
        start = 1
        end = candidate.seq_len
    else:
        start = min(
            max(1, candidate.position - WINDOW_RADIUS),
            candidate.seq_len - MAX_WINDOW_RESIDUES + 1,
        )
        end = start + MAX_WINDOW_RESIDUES - 1
    target_offset = candidate.position - start
    window = candidate.sequence[start - 1 : end]
    if not (
        1 <= start <= candidate.position <= end <= candidate.seq_len
        and len(window) <= MAX_WINDOW_RESIDUES
        and window[target_offset] == candidate.sequence[candidate.position - 1] == "N"
    ):
        raise AssertionError(f"window invariant failed for {candidate.row_id}")
    return WindowedCandidate(
        candidate=candidate,
        window_start=start,
        window_end=end,
        target_offset=target_offset,
        window=window,
        window_sha256=sha256_bytes(window.encode("ascii")),
    )


def build_windows(candidates: Sequence[Candidate]) -> list[WindowedCandidate]:
    return [build_window(candidate) for candidate in candidates]


def build_embedding_jobs(windows: Sequence[WindowedCandidate]) -> list[EmbeddingJob]:
    grouped: dict[tuple[str, int, int], list[tuple[str, int]]] = {}
    window_by_key: dict[tuple[str, int, int], str] = {}
    for windowed in windows:
        candidate = windowed.candidate
        key = (candidate.accession, windowed.window_start, windowed.window_end)
        grouped.setdefault(key, []).append((candidate.row_id, 1 + windowed.target_offset))
        window_by_key[key] = windowed.window

    jobs = []
    for key in sorted(grouped):
        accession, start, end = key
        jobs.append(
            EmbeddingJob(
                job_id=f"{accession}:{start}-{end}",
                accession=accession,
                window_start=start,
                window_end=end,
                window=window_by_key[key],
                targets=tuple(grouped[key]),
            )
        )
    return jobs


def resolve_device(requested: str):
    import torch

    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(requested)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    return device


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


def load_encoder(config: ProbeConfig):
    import torch
    from transformers import AutoModel, AutoTokenizer

    local_files_only = not config.allow_download
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        local_files_only=local_files_only,
    )
    model = AutoModel.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        local_files_only=local_files_only,
    )
    device = resolve_device(config.device)
    model.to(device=device, dtype=torch.float32)
    model.eval()
    model.requires_grad_(False)
    if model.config.hidden_size != HIDDEN_SIZE:
        raise RuntimeError(f"expected hidden size {HIDDEN_SIZE}, got {model.config.hidden_size}")
    if model.config.max_position_embeddings != MAX_POSITION_EMBEDDINGS:
        raise RuntimeError(
            "unexpected max_position_embeddings: "
            f"{model.config.max_position_embeddings}"
        )
    return tokenizer, model, device


def embed_jobs(
    jobs: Sequence[EmbeddingJob],
    tokenizer,
    model,
    device,
    batch_size: int,
) -> dict[str, np.ndarray]:
    import torch

    ordered = sorted(
        enumerate(jobs), key=lambda item: (len(item[1].window), item[1].job_id)
    )
    results: list[np.ndarray | None] = [None] * len(jobs)

    def encode_batch(batch: Sequence[tuple[int, EmbeddingJob]]):
        encoded = tokenizer(
            [job.window for _, job in batch],
            padding=True,
            return_tensors="pt",
            truncation=False,
        )
        input_ids = encoded["input_ids"]
        if input_ids.shape[1] > MAX_POSITION_EMBEDDINGS:
            raise RuntimeError(
                f"token length {input_ids.shape[1]} exceeds {MAX_POSITION_EMBEDDINGS}"
            )
        for batch_index, (_, job) in enumerate(batch):
            for row_id, token_index in job.targets:
                token = tokenizer.convert_ids_to_tokens(
                    int(input_ids[batch_index, token_index])
                )
                residue = job.window[token_index - 1]
                if token != residue:
                    raise RuntimeError(
                        f"{row_id} token mismatch at {job.job_id}: "
                        f"token {token!r}, residue {residue!r}"
                    )

        model_inputs = {
            "input_ids": input_ids.to(device),
            "attention_mask": encoded["attention_mask"].to(device),
        }
        try:
            with torch.inference_mode():
                hidden = model(**model_inputs).last_hidden_state
        except RuntimeError as error:
            if "out of memory" not in str(error).lower() or len(batch) == 1:
                raise
            if device.type == "cuda":
                torch.cuda.empty_cache()
            middle = len(batch) // 2
            return encode_batch(batch[:middle]) + encode_batch(batch[middle:])

        output = []
        for batch_index, (_, job) in enumerate(batch):
            vectors = []
            for _, token_index in job.targets:
                vector = hidden[batch_index, token_index].detach().float().cpu().numpy()
                if not np.isfinite(vector).all():
                    raise RuntimeError(f"non-finite embedding for {job.job_id}")
                vectors.append(vector)
            output.append((job.job_id, np.stack(vectors).astype(np.float32, copy=False)))
        return output

    batches = [
        ordered[index : index + batch_size] for index in range(0, len(ordered), batch_size)
    ]
    position_by_job = {job.job_id: index for index, job in enumerate(jobs)}
    for batch in batches:
        for job_id, features in encode_batch(batch):
            results[position_by_job[job_id]] = features
    if any(value is None for value in results):
        raise RuntimeError("not every embedding job produced output")
    return {job.job_id: results[index] for index, job in enumerate(jobs)}


def assemble_row_matrix(
    windows: Sequence[WindowedCandidate],
    jobs: Sequence[EmbeddingJob],
    job_embeddings: dict[str, np.ndarray],
) -> np.ndarray:
    target_indices = {
        job.job_id: {row_id: index for index, (row_id, _) in enumerate(job.targets)}
        for job in jobs
    }
    rows = []
    for windowed in windows:
        candidate = windowed.candidate
        job_id = (
            f"{candidate.accession}:{windowed.window_start}-{windowed.window_end}"
        )
        rows.append(job_embeddings[job_id][target_indices[job_id][candidate.row_id]])
    features = np.stack(rows).astype(np.float32, copy=False)
    if features.shape != (len(windows), HIDDEN_SIZE):
        raise RuntimeError(f"unexpected feature shape {features.shape}")
    if not np.isfinite(features).all():
        raise RuntimeError("feature matrix contains non-finite values")
    return features


def leave_one_protein_out(candidates: Sequence[Candidate]) -> list[Fold]:
    accessions = sorted({candidate.accession for candidate in candidates})
    folds = []
    for held_out in accessions:
        train = tuple(
            index
            for index, candidate in enumerate(candidates)
            if candidate.accession != held_out
        )
        test = tuple(
            index
            for index, candidate in enumerate(candidates)
            if candidate.accession == held_out
        )
        if not train or not test:
            raise RuntimeError(f"degenerate leave-one-protein-out fold for {held_out}")
        folds.append(
            Fold(
                fold_id=f"lopo:{held_out}",
                held_out=held_out,
                train_indices=train,
                test_indices=test,
            )
        )
    return folds


def fit_and_predict(
    features: np.ndarray,
    candidates: Sequence[Candidate],
    folds: Sequence[Fold],
) -> list[Prediction]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    labels = np.asarray([candidate.label for candidate in candidates], dtype=np.int64)
    logits = np.full(len(candidates), np.nan, dtype=np.float64)
    probabilities = np.full(len(candidates), np.nan, dtype=np.float64)
    predictions = np.zeros(len(candidates), dtype=bool)
    assigned = np.zeros(len(candidates), dtype=np.int64)

    for fold in folds:
        train_indices = np.asarray(fold.train_indices, dtype=np.int64)
        test_indices = np.asarray(fold.test_indices, dtype=np.int64)
        train_labels = labels[train_indices]
        if np.unique(train_labels).size != 2:
            raise RuntimeError(f"{fold.fold_id} training data contains one class")
        scaler = StandardScaler()
        train_features = scaler.fit_transform(features[train_indices])
        test_features = scaler.transform(features[test_indices])
        classifier = LogisticRegression(
            C=C,
            penalty="l2",
            solver="liblinear",
            max_iter=5000,
            random_state=SEED,
            class_weight=None,
        )
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=FutureWarning)
            classifier.fit(train_features, train_labels)
        if int(np.max(classifier.n_iter_)) >= 5000:
            raise RuntimeError(f"{fold.fold_id} logistic regression did not converge")
        fold_logits = classifier.decision_function(test_features)
        fold_probabilities = 1.0 / (1.0 + np.exp(-fold_logits))
        fold_predictions = fold_probabilities >= THRESHOLD
        logits[test_indices] = fold_logits
        probabilities[test_indices] = fold_probabilities
        predictions[test_indices] = fold_predictions
        assigned[test_indices] += 1

    if not np.all(assigned == 1):
        raise RuntimeError("leave-one-protein-out did not test each row exactly once")
    if not np.isfinite(logits).all() or not np.isfinite(probabilities).all():
        raise RuntimeError("prediction output contains non-finite values")

    return [
        Prediction(
            row_id=candidate.row_id,
            accession=candidate.accession,
            position=candidate.position,
            label=candidate.label,
            fold_id=f"lopo:{candidate.accession}",
            logit=float(logits[index]),
            probability=float(probabilities[index]),
            prediction=bool(predictions[index]),
        )
        for index, candidate in enumerate(candidates)
    ]


def point_metrics(labels: np.ndarray, predictions: np.ndarray, probabilities: np.ndarray):
    labels = labels.astype(bool, copy=False)
    predictions = predictions.astype(bool, copy=False)
    true_positive = int(np.sum(labels & predictions))
    true_negative = int(np.sum(~labels & ~predictions))
    false_positive = int(np.sum(~labels & predictions))
    false_negative = int(np.sum(labels & ~predictions))

    null_reasons: dict[str, str] = {}
    mcc_denominator = math.sqrt(
        (true_positive + false_positive)
        * (true_positive + false_negative)
        * (true_negative + false_positive)
        * (true_negative + false_negative)
    )
    mcc = (
        (true_positive * true_negative - false_positive * false_negative)
        / mcc_denominator
        if mcc_denominator
        else None
    )
    if mcc is None:
        null_reasons["mcc"] = "confusion matrix has no square root support"
    sensitivity = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else None
    )
    if sensitivity is None:
        null_reasons["sensitivity"] = "no positive labels"
    specificity = (
        true_negative / (true_negative + false_positive)
        if true_negative + false_positive
        else None
    )
    if specificity is None:
        null_reasons["specificity"] = "no negative labels"
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else None
    )
    if precision is None:
        null_reasons["precision"] = "no predicted positives"
    accuracy = (
        (true_positive + true_negative) / len(labels)
        if len(labels)
        else None
    )
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
    predictions: Sequence[Prediction],
    *,
    replicates: int,
    seed: int,
) -> dict:
    accessions = sorted({prediction.accession for prediction in predictions})
    indices_by_accession = {
        accession: np.asarray(
            [
                index
                for index, prediction in enumerate(predictions)
                if prediction.accession == accession
            ],
            dtype=np.int64,
        )
        for accession in accessions
    }
    labels = np.asarray([prediction.label for prediction in predictions], dtype=bool)
    predicted = np.asarray(
        [prediction.prediction for prediction in predictions], dtype=bool
    )
    rng = np.random.default_rng(seed)
    values = {"mcc": [], "sensitivity": [], "specificity": []}

    for _ in range(replicates):
        sampled = rng.choice(accessions, size=len(accessions), replace=True)
        indices = np.concatenate([indices_by_accession[accession] for accession in sampled])
        metrics = point_metrics(labels[indices], predicted[indices], labels[indices])[
            "metrics"
        ]
        if all(metrics[name] is not None for name in values):
            for name in values:
                values[name].append(metrics[name])

    valid = len(values["mcc"])
    undefined = replicates - valid
    intervals = {
        name: (
            [
                float(np.percentile(samples, 2.5)),
                float(np.percentile(samples, 97.5)),
            ]
            if samples
            else [None, None]
        )
        for name, samples in values.items()
    }
    return {
        "unit": "protein",
        "replicates": replicates,
        "seed": seed,
        "valid_replicates": valid,
        "undefined_replicates": undefined,
        "ci95": intervals,
    }


def metrics_document(predictions: Sequence[Prediction]) -> dict:
    labels = np.asarray([prediction.label for prediction in predictions], dtype=bool)
    predicted = np.asarray(
        [prediction.prediction for prediction in predictions], dtype=bool
    )
    probabilities = np.asarray(
        [prediction.probability for prediction in predictions], dtype=np.float64
    )
    point = point_metrics(labels, predicted, probabilities)
    return {
        "schema": SCHEMA,
        "threshold": THRESHOLD,
        "confusion": point["confusion"],
        "metrics": point["metrics"],
        "null_reasons": point["null_reasons"],
        "bootstrap": bootstrap_by_protein(
            predictions, replicates=BOOTSTRAP_REPLICATES, seed=SEED
        ),
    }


def format_metric(value) -> str:
    return "null" if value is None else f"{value:.6f}"


def format_interval(values: Sequence[float | None]) -> str:
    if len(values) != 2 or any(value is None for value in values):
        return "null"
    return f"[{values[0]:.6f}, {values[1]:.6f}]"


def metrics_markdown(metrics: dict, proteins: int) -> str:
    point = metrics["metrics"]
    confusion = metrics["confusion"]
    bootstrap = metrics["bootstrap"]
    lines = [
        "<!-- BEGIN GENERATED METRICS -->",
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
        "<!-- END GENERATED METRICS -->",
    ]
    return "\n".join(lines) + "\n"


def report_text(
    *,
    metrics: dict,
    manifest_base: dict,
    proteins: int,
) -> str:
    model = manifest_base["model"]
    inputs = manifest_base["inputs"]
    source = manifest_base["source"]
    settings = manifest_base["settings"]
    counts = manifest_base["counts"]
    environment = manifest_base["environment"]
    return (
        "# ESM-2 35M frozen linear probe\n\n"
        "This report applies only to the F1 v0 candidate table. Label 0 means "
        "\"not annotated with a verified UniProt N-linked site\" and does not mean "
        "\"verified negative\".\n\n"
        "External context only: the paper's 0.781 is from a different dataset and "
        "protocol. It is not this run's result and is not used in the generated "
        "metrics block.\n\n"
        "## Run contract\n\n"
        f"- Model: `{model['id']}` at `{model['revision']}`\n"
        f"- Candidate SHA256: `{inputs['candidates']['sha256']}`\n"
        f"- UniProt release: `{inputs['uniprot_release']}`\n"
        f"- Split: `{settings['split']}`\n"
        f"- Representation: `{settings['representation']}`\n"
        f"- Rows / proteins / unique windows: {counts['rows']} / "
        f"{counts['proteins']} / {counts['unique_windows']}\n"
        f"- Classifier: `{settings['classifier']}` with C={settings['C']}, "
        f"class_weight={settings['class_weight']}, solver={settings['solver']}\n"
        f"- Threshold: {settings['threshold']}\n"
        f"- Base commit at generation: `{source['git_commit']}` "
        f"(dirty={str(source['git_dirty']).lower()})\n"
        f"- Device and dtype: `{settings['device']}` / `{settings['dtype']}`\n\n"
        "## Reproduce\n\n"
        "```powershell\n"
        ".venv\\Scripts\\python.exe scripts\\run_esm35_linear_probe.py "
        "--cache-dir <uniprot-cache> --out-dir reports\\esm35_linear_probe_v0\n"
        ".venv\\Scripts\\python.exe scripts\\check_esm35_linear_probe.py "
        "--run-dir reports\\esm35_linear_probe_v0 --cache-dir <uniprot-cache>\n"
        "```\n\n"
        "## Environment\n\n"
        f"- Python {environment['python']}\n"
        f"- torch {environment['torch']}\n"
        f"- transformers {environment['transformers']}\n"
        f"- scikit-learn {environment['scikit_learn']}\n"
        f"- NumPy {environment['numpy']}\n\n"
        "## Result\n\n"
        f"{metrics_markdown(metrics, proteins)}"
    )


def model_fingerprints(allow_download: bool) -> dict:
    from transformers.utils import cached_file

    fingerprints = {}
    for name in (
        "config.json",
        "model.safetensors",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "vocab.txt",
    ):
        path = Path(
            cached_file(
                MODEL_ID,
                name,
                revision=MODEL_REVISION,
                local_files_only=not allow_download,
            )
        )
        fingerprints[name] = {
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
        }
    return fingerprints


def git_state() -> tuple[str, bool]:
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
        return commit, bool(status.strip())
    except (OSError, subprocess.CalledProcessError):
        return "unknown", True


def environment_versions() -> dict:
    import sklearn
    import torch
    import transformers

    return {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "scikit_learn": sklearn.__version__,
        "numpy": np.__version__,
    }


def relative_input_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def write_run(
    config: ProbeConfig,
    inputs: InputData,
    candidates: Sequence[Candidate],
    windows: Sequence[WindowedCandidate],
    folds: Sequence[Fold],
    jobs: Sequence[EmbeddingJob],
    features: np.ndarray,
    predictions: Sequence[Prediction],
    metrics: dict,
    *,
    device: str,
) -> Path:
    config.out_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths = {
        name: config.out_dir / name for name in ARTIFACT_NAMES
    }

    fold_by_accession = {fold.held_out: fold for fold in folds}
    atomic_write_csv(
        artifact_paths["windows.csv"],
        WINDOW_COLUMNS,
        (
            (
                windowed.candidate.row_id,
                windowed.candidate.accession,
                windowed.candidate.position,
                int(windowed.candidate.label),
                windowed.candidate.seq_len,
                windowed.window_start,
                windowed.window_end,
                len(windowed.window),
                windowed.target_offset,
                windowed.candidate.sequence[windowed.candidate.position - 1],
                windowed.window_sha256,
                fold_by_accession[windowed.candidate.accession].fold_id,
            )
            for windowed in windows
        ),
    )
    atomic_write_csv(
        artifact_paths["folds.csv"],
        FOLD_COLUMNS,
        (
            (
                fold.fold_id,
                fold.held_out,
                len(fold.train_indices),
                len(fold.test_indices),
                sum(candidates[index].label for index in fold.train_indices),
                sum(candidates[index].label for index in fold.test_indices),
                sum(not candidates[index].label for index in fold.train_indices),
                sum(not candidates[index].label for index in fold.test_indices),
            )
            for fold in folds
        ),
    )
    atomic_write_npy(artifact_paths["embeddings.npy"], features)
    atomic_write_csv(
        artifact_paths["predictions.csv"],
        PREDICTION_COLUMNS,
        (
            (
                prediction.row_id,
                prediction.accession,
                prediction.position,
                int(prediction.label),
                prediction.fold_id,
                repr(prediction.logit),
                repr(prediction.probability),
                int(prediction.prediction),
            )
            for prediction in predictions
        ),
    )
    atomic_write_json(artifact_paths["metrics.json"], metrics)

    commit, dirty = git_state()
    proteins = len({candidate.accession for candidate in candidates})
    manifest_base = {
        "schema": SCHEMA,
        "status": "complete",
        "inputs": {
            "candidates": {
                "path": relative_input_path(config.candidates_path),
                "sha256": inputs.candidate_sha256,
            },
            "uniprot_release": inputs.uniprot_release,
            "uniprot_list_sha256": inputs.uniprot_list_sha256,
            "sequence_cache_sha256": inputs.sequence_cache_sha256,
        },
        "source": {"git_commit": commit, "git_dirty": dirty},
        "model": {
            "id": MODEL_ID,
            "revision": MODEL_REVISION,
            "hidden_size": HIDDEN_SIZE,
            "layers": 12,
            "max_position_embeddings": MAX_POSITION_EMBEDDINGS,
            "files": model_fingerprints(config.allow_download),
        },
        "settings": {
            "window_radius": WINDOW_RADIUS,
            "max_window_residues": MAX_WINDOW_RESIDUES,
            "representation": "last_hidden_state_at_target_token",
            "split": "leave_one_protein_out",
            "classifier": "LogisticRegression",
            "C": C,
            "class_weight": "none",
            "solver": "liblinear",
            "max_iter": 5000,
            "threshold": THRESHOLD,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "seed": SEED,
            "device": device,
            "dtype": "float32",
        },
        "environment": environment_versions(),
        "counts": {
            "proteins": proteins,
            "rows": len(candidates),
            "positive": sum(candidate.label for candidate in candidates),
            "negative": sum(not candidate.label for candidate in candidates),
            "unique_windows": len(jobs),
            "folds": len(folds),
        },
    }

    atomic_write_text(
        artifact_paths["report.md"],
        report_text(metrics=metrics, manifest_base=manifest_base, proteins=proteins),
    )
    manifest_base["artifacts"] = {
        name: {
            "sha256": file_sha256(artifact_paths[name]),
            "bytes": artifact_paths[name].stat().st_size,
        }
        for name in ARTIFACT_NAMES
    }
    atomic_write_json(config.out_dir / "manifest.json", manifest_base)
    return config.out_dir


def parse_args(argv: Sequence[str] | None = None) -> ProbeConfig:
    parser = argparse.ArgumentParser(
        description="Run the frozen ESM-2 35M linear probe on F1 v0"
    )
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Allow Hugging Face model download; default is local files only",
    )
    args = parser.parse_args(argv)
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    return ProbeConfig(
        candidates_path=args.candidates.resolve(),
        cache_dir=args.cache_dir.resolve(),
        out_dir=args.out_dir.resolve(),
        device=args.device,
        batch_size=args.batch_size,
        allow_download=args.allow_download,
    )


def main(argv: Sequence[str] | None = None) -> int:
    config = parse_args(argv)
    try:
        inputs = read_candidates(config.candidates_path, config.cache_dir)
    except (FileNotFoundError, InputError, json.JSONDecodeError) as error:
        print(f"input error: {error}", file=sys.stderr)
        return 2

    candidates = inputs.candidates
    if len(candidates) != 201:
        print(f"input error: expected 201 rows, got {len(candidates)}", file=sys.stderr)
        return 2
    if len({candidate.accession for candidate in candidates}) != 29:
        print("input error: expected 29 proteins", file=sys.stderr)
        return 2

    windows = build_windows(candidates)
    jobs = build_embedding_jobs(windows)
    if len(jobs) != 82:
        print(f"input error: expected 82 unique windows, got {len(jobs)}", file=sys.stderr)
        return 2

    configure_torch()
    try:
        tokenizer, model, device = load_encoder(config)
        job_embeddings = embed_jobs(
            jobs, tokenizer, model, device, batch_size=config.batch_size
        )
        features = assemble_row_matrix(windows, jobs, job_embeddings)
        folds = leave_one_protein_out(candidates)
        predictions = fit_and_predict(features, candidates, folds)
        metrics = metrics_document(predictions)
        output_dir = write_run(
            config,
            inputs,
            candidates,
            windows,
            folds,
            jobs,
            features,
            predictions,
            metrics,
            device=device.type,
        )
    except Exception as error:
        print(f"run error: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    point = metrics["metrics"]
    interval = metrics["bootstrap"]["ci95"]["mcc"]
    print(
        "rows={rows} proteins={proteins} windows={windows} "
        "MCC={mcc:.6f} sensitivity={sensitivity:.6f} specificity={specificity:.6f}".format(
            rows=len(candidates),
            proteins=len({candidate.accession for candidate in candidates}),
            windows=len(jobs),
            mcc=point["mcc"],
            sensitivity=point["sensitivity"],
            specificity=point["specificity"],
        )
    )
    print(
        "MCC 95% protein-resampling interval="
        + format_interval(interval)
        + f"; output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
