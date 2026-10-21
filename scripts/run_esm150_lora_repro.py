from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


REFERENCE_MCC = 0.848
EXPECTED_PEFT_VERSION = "0.14.0"
EXPECTED_TRANSFORMERS_VERSION = "4.50.3"
EXPECTED_TOKENIZERS_VERSION = "0.21.1"
EXPECTED_HUB_VERSION = "0.26.3"
EXPECTED_TEST_SHA256 = (
    "D2533271159123EE1C8D537CBE7BDA115AB0E0A29D98A8DF7B7B4ACC69217D20"
)
EXPECTED_ADAPTER_SHA256 = (
    "A4A5B486862724F459F60E8343AC135C340305D5A0F2E936EB5AD1DFD34788D4"
)
EXPECTED_ADAPTER_TENSORS = 376
EXPECTED_COLUMNS = ("label", "id", "pos", "sequence")
PREDICTION_COLUMNS = (
    "row_index",
    "label",
    "protein_id",
    "position",
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


class ReproError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunConfig:
    test_csv: Path
    adapter_dir: Path
    base_model_id: str
    base_model_revision: str
    out_dir: Path
    compat_path: Path
    device: str
    batch_size: int
    offline: bool


@dataclass(frozen=True)
class TestRow:
    row_index: int
    label: int
    protein_id: str
    position: int
    sequence: str


@dataclass(frozen=True)
class Prediction:
    row_index: int
    label: int
    protein_id: str
    position: int
    sequence_sha256: str
    sequence_length: int
    token_length: int
    residue: str
    motif: str
    is_sequon: int
    logit_negative: float
    logit_positive: float
    prob_negative: float
    prob_positive: float
    predicted_label: int


@dataclass(frozen=True)
class LogitsOutput:
    logits: Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def atomic_write_csv(
    path: Path,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)
    os.replace(temporary, path)


def run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise ReproError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def code_state(repo_root: Path) -> tuple[str, bool]:
    commit = run_git(repo_root, "rev-parse", "HEAD")
    status = run_git(repo_root, "status", "--porcelain=v1")
    return commit, bool(status)


def load_test_rows(path: Path) -> list[TestRow]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
            raise ReproError(
                f"Unexpected CSV header: {reader.fieldnames}; expected {list(EXPECTED_COLUMNS)}"
            )
        rows: list[TestRow] = []
        for row_index, raw in enumerate(reader):
            try:
                label = int(raw["label"])
                position = int(raw["pos"])
            except (TypeError, ValueError) as error:
                raise ReproError(f"Invalid label or pos at CSV data row {row_index}") from error
            if label not in (0, 1):
                raise ReproError(f"Label must be 0 or 1 at CSV data row {row_index}")
            sequence = raw["sequence"]
            if not sequence:
                raise ReproError(f"Empty sequence at CSV data row {row_index}")
            if not 1 <= position <= len(sequence):
                raise ReproError(
                    f"Position {position} outside sequence at CSV data row {row_index}"
                )
            rows.append(
                TestRow(
                    row_index=row_index,
                    label=label,
                    protein_id=raw["id"],
                    position=position,
                    sequence=sequence,
                )
            )
    if not rows:
        raise ReproError("Test CSV contains no data rows")
    return rows


def residue_and_motif(sequence: str, position: int) -> tuple[str, str, int]:
    start = position - 1
    motif = sequence[start : start + 3]
    residue = sequence[start]
    is_sequon = int(
        len(motif) == 3
        and motif[0] == "N"
        and motif[1] != "P"
        and motif[2] in {"S", "T"}
    )
    return residue, motif, is_sequon


def softmax_two(logit_negative: float, logit_positive: float) -> tuple[float, float]:
    maximum = max(logit_negative, logit_positive)
    exp_negative = math.exp(logit_negative - maximum)
    exp_positive = math.exp(logit_positive - maximum)
    denominator = exp_negative + exp_positive
    return exp_negative / denominator, exp_positive / denominator


def binary_argmax(logit_negative: float, logit_positive: float) -> int:
    return int(logit_positive > logit_negative)


def confusion_and_metrics(
    labels: Sequence[int],
    predictions: Sequence[int],
) -> dict[str, Any]:
    if len(labels) != len(predictions):
        raise ReproError("Labels and predictions have different lengths")
    if not labels:
        raise ReproError("Metrics require at least one row")
    tp = fp = tn = fn = 0
    for label, prediction in zip(labels, predictions):
        if label == 1 and prediction == 1:
            tp += 1
        elif label == 0 and prediction == 1:
            fp += 1
        elif label == 0 and prediction == 0:
            tn += 1
        elif label == 1 and prediction == 0:
            fn += 1
        else:
            raise ReproError("Labels and predictions must be binary")

    denominator = math.sqrt(
        float((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    )
    mcc = ((tp * tn) - (fp * fn)) / denominator if denominator else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    accuracy = (tp + tn) / len(labels)
    return {
        "mcc": mcc,
        "reference_mcc": REFERENCE_MCC,
        "mcc_delta_from_reference": mcc - REFERENCE_MCC,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "confusion": {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
        },
        "row_count": len(labels),
    }


def select_audit_indices(rows: Sequence[TestRow], limit: int = 16) -> list[int]:
    shortest = min(rows, key=lambda row: (len(row.sequence), row.row_index))
    longest = max(rows, key=lambda row: (len(row.sequence), -row.row_index))
    non_sequon = [
        row.row_index for row in rows if residue_and_motif(row.sequence, row.position)[2] == 0
    ]
    positives = [row.row_index for row in rows if row.label == 1]
    negatives = [row.row_index for row in rows if row.label == 0]
    selected = [
        0,
        len(rows) - 1,
        shortest.row_index,
        longest.row_index,
        *non_sequon[:4],
        *positives[:2],
        *negatives[:2],
    ]
    ordered = sorted({index for index in selected if 0 <= index < len(rows)})
    cursor = 0
    while len(ordered) < min(limit, len(rows)):
        candidate = round(cursor * (len(rows) - 1) / max(limit - 1, 1))
        if candidate not in ordered:
            ordered.append(candidate)
            ordered.sort()
        cursor += 1
    return ordered[:limit]


def activate_compatibility_path(compat_path: Path) -> None:
    resolved = compat_path.resolve()
    if not resolved.is_dir():
        raise ReproError(f"Compatibility path does not exist: {resolved}")
    sys.path.insert(0, str(resolved))


def load_model(
    config: RunConfig,
) -> tuple[Any, Any, dict[str, Any], list[str]]:
    activate_compatibility_path(config.compat_path)

    import huggingface_hub
    import peft
    import tokenizers
    import torch
    import transformers
    from peft import PeftModel
    from torch import nn
    from transformers import AutoTokenizer, EsmForSequenceClassification

    versions = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "peft": peft.__version__,
        "tokenizers": tokenizers.__version__,
        "huggingface_hub": huggingface_hub.__version__,
    }
    expected = {
        "transformers": EXPECTED_TRANSFORMERS_VERSION,
        "peft": EXPECTED_PEFT_VERSION,
        "tokenizers": EXPECTED_TOKENIZERS_VERSION,
        "huggingface_hub": EXPECTED_HUB_VERSION,
    }
    mismatches = {
        name: {"actual": versions[name], "expected": version}
        for name, version in expected.items()
        if versions[name] != version
    }
    if mismatches:
        raise ReproError(f"Compatibility version mismatch: {mismatches}")

    class EsmClassificationHead(nn.Module):
        def __init__(self, model_config: Any) -> None:
            super().__init__()
            self.dense = nn.Linear(model_config.hidden_size, model_config.hidden_size)
            self.dropout = nn.Dropout(model_config.hidden_dropout_prob)
            self.out_proj = nn.Linear(model_config.hidden_size, model_config.num_labels)

        def forward(self, features: Any, pos: Any, **_: Any) -> Any:
            batch_indices = torch.arange(features.shape[0], device=features.device)
            selected = features[batch_indices, pos]
            selected = self.dropout(selected)
            selected = self.dense(selected)
            selected = torch.tanh(selected)
            selected = self.dropout(selected)
            return self.out_proj(selected)

    class PositionEsmForSequenceClassification(EsmForSequenceClassification):
        def __init__(self, model_config: Any) -> None:
            super().__init__(model_config)
            self.classifier = EsmClassificationHead(model_config)

        def forward(
            self,
            input_ids: Any,
            attention_mask: Any,
            pos: Any,
            **_,
        ) -> Any:
            hidden = self.esm(
                input_ids=input_ids,
                attention_mask=attention_mask,
                return_dict=True,
            ).last_hidden_state
            logits = self.classifier(hidden, pos)
            return LogitsOutput(logits)

    if config.device.startswith("cuda") and not torch.cuda.is_available():
        raise ReproError("CUDA was requested but is unavailable")
    torch.manual_seed(42)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(42)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True

    load_warnings: list[str] = []
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        tokenizer = AutoTokenizer.from_pretrained(
            config.base_model_id,
            revision=config.base_model_revision,
            trust_remote_code=True,
            local_files_only=config.offline,
        )
        load_kwargs: dict[str, Any] = {
            "revision": config.base_model_revision,
            "num_labels": 2,
            "torch_dtype": torch.float32,
            "local_files_only": config.offline,
        }
        if config.device.startswith("cuda"):
            load_kwargs["device_map"] = config.device
        base_model = PositionEsmForSequenceClassification.from_pretrained(
            config.base_model_id,
            **load_kwargs,
        )
        model = PeftModel.from_pretrained(base_model, config.adapter_dir)
        if not config.device.startswith("cuda"):
            model.to(config.device)
        model.eval()
        load_warnings = [str(item.message) for item in captured]

    device_info: dict[str, Any] = {"requested": config.device}
    if config.device.startswith("cuda"):
        index = torch.device(config.device).index or 0
        properties = torch.cuda.get_device_properties(index)
        device_info.update(
            {
                "name": torch.cuda.get_device_name(index),
                "capability": list(torch.cuda.get_device_capability(index)),
                "total_memory_bytes": properties.total_memory,
            }
        )
    device_info["attention_implementation"] = getattr(
        model.config, "_attn_implementation", "unknown"
    )
    return model, tokenizer, {"versions": versions, "device": device_info}, load_warnings


def resolve_model_snapshot(config: RunConfig) -> Path:
    activate_compatibility_path(config.compat_path)
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            repo_id=config.base_model_id,
            revision=config.base_model_revision,
            local_files_only=config.offline,
        )
    )


def adapter_tensor_count(adapter_path: Path) -> int:
    from safetensors import safe_open

    with safe_open(str(adapter_path), framework="pt") as handle:
        return len(list(handle.keys()))


def artifact_hashes(out_dir: Path) -> dict[str, str]:
    names = (
        "predictions.csv",
        "audit_sample.csv",
        "metrics.json",
        "report.md",
    )
    return {name: sha256_file(out_dir / name) for name in names}


def report_text(
    metrics: dict[str, Any],
    rows: Sequence[TestRow],
    load_warnings: Sequence[str],
) -> str:
    confusion = metrics["confusion"]
    non_sequon = sum(
        residue_and_motif(row.sequence, row.position)[2] == 0 for row in rows
    )
    lines = [
        "# ESM-2 150M LoRA author-checkpoint reproduction",
        "",
        "## Scope",
        "",
        "The run evaluates every row of the author's `test.csv` in original order. "
        "No non-canonical or non-sequon rows are removed. The model uses the full "
        "protein sequence, the author's PEFT adapter, two logits, and `argmax`.",
        "",
        "## Result",
        "",
        f"- MCC: `{metrics['mcc']:.12f}`",
        f"- Reference MCC: `{REFERENCE_MCC:.3f}`",
        f"- Difference from reference: `{metrics['mcc_delta_from_reference']:+.12f}`",
        f"- Accuracy: `{metrics['accuracy']:.12f}`",
        f"- Precision: `{metrics['precision']:.12f}`",
        f"- Recall: `{metrics['recall']:.12f}`",
        f"- Specificity: `{metrics['specificity']:.12f}`",
        f"- TP / FP / TN / FN: `{confusion['tp']}` / `{confusion['fp']}` / "
        f"`{confusion['tn']}` / `{confusion['fn']}`",
        "",
        "## Data audit",
        "",
        f"- Rows: `{len(rows)}`",
        f"- Positives / negatives: `{sum(row.label == 1 for row in rows)}` / "
        f"`{sum(row.label == 0 for row in rows)}`",
        f"- Non-sequon rows retained: `{non_sequon}`",
        f"- Longest sequence: `{max(len(row.sequence) for row in rows)}` residues",
        "",
        "## Compatibility note",
        "",
        "The author adapter was saved with an older PEFT layout. The reproduction "
        f"uses the author-pinned stack `peft {EXPECTED_PEFT_VERSION}` and "
        f"`transformers {EXPECTED_TRANSFORMERS_VERSION}` through an isolated overlay.",
        "",
    ]
    if load_warnings:
        lines.extend(["Captured load warnings:", ""])
        lines.extend(f"- `{warning}`" for warning in load_warnings)
        lines.append("")
    lines.extend(
        [
            "The difference is reported as measured. Any attribution must be supported "
            "by the manifest, row predictions, and checker result.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> RunConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-csv", required=True, type=Path)
    parser.add_argument("--adapter-dir", required=True, type=Path)
    parser.add_argument("--base-model-id", default="facebook/esm2_t30_150M_UR50D")
    parser.add_argument("--base-model-revision", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--compat-path",
        type=Path,
        default=Path(
            os.environ.get(
                "LORA_N_GLY_COMPAT_PATH",
                r"D:\uv\pylibs\lora-n-gly-peft014",
            )
        ),
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--allow-download", action="store_true")
    args = parser.parse_args(argv)
    if args.batch_size != 1:
        raise ReproError("The author benchmark used per-device evaluation batch size 1")
    return RunConfig(
        test_csv=args.test_csv.resolve(),
        adapter_dir=args.adapter_dir.resolve(),
        base_model_id=args.base_model_id,
        base_model_revision=args.base_model_revision,
        out_dir=args.out_dir.resolve(),
        compat_path=args.compat_path.resolve(),
        device=args.device,
        batch_size=args.batch_size,
        offline=not args.allow_download,
    )


def main(argv: Sequence[str] | None = None) -> int:
    config = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    if config.out_dir.exists():
        raise ReproError(f"Output directory already exists: {config.out_dir}")
    if not config.test_csv.is_file():
        raise ReproError(f"Test CSV not found: {config.test_csv}")
    adapter_file = config.adapter_dir / "adapter_model.safetensors"
    adapter_config = config.adapter_dir / "adapter_config.json"
    if not adapter_file.is_file() or not adapter_config.is_file():
        raise ReproError(f"Incomplete adapter directory: {config.adapter_dir}")

    test_sha256 = sha256_file(config.test_csv)
    adapter_sha256 = sha256_file(adapter_file)
    if test_sha256 != EXPECTED_TEST_SHA256:
        raise ReproError(
            f"Unexpected test CSV SHA256: {test_sha256}; expected {EXPECTED_TEST_SHA256}"
        )
    if adapter_sha256 != EXPECTED_ADAPTER_SHA256:
        raise ReproError(
            f"Unexpected adapter SHA256: {adapter_sha256}; "
            f"expected {EXPECTED_ADAPTER_SHA256}"
        )
    tensor_count = adapter_tensor_count(adapter_file)
    if tensor_count != EXPECTED_ADAPTER_TENSORS:
        raise ReproError(
            f"Unexpected adapter tensor count: {tensor_count}; "
            f"expected {EXPECTED_ADAPTER_TENSORS}"
        )

    rows = load_test_rows(config.test_csv)
    git_commit, git_dirty = code_state(repo_root)
    model_snapshot = resolve_model_snapshot(config)
    model_file = model_snapshot / "model.safetensors"
    if not model_file.is_file():
        model_file = model_snapshot / "pytorch_model.bin"
    if not model_file.is_file():
        raise ReproError(f"No model weights found in snapshot {model_snapshot}")

    model, tokenizer, environment, load_warnings = load_model(config)
    import torch

    started = time.perf_counter()
    predictions: list[Prediction] = []
    sequence_cache: dict[str, dict[str, Any]] = {}
    for completed, row in enumerate(rows, start=1):
        encoded = sequence_cache.get(row.sequence)
        if encoded is None:
            encoded = tokenizer(row.sequence, return_tensors="pt")
            sequence_cache[row.sequence] = encoded
        input_ids = encoded["input_ids"].to(config.device)
        attention_mask = encoded["attention_mask"].to(config.device)
        token_length = int(input_ids.shape[1])
        if row.position + 1 >= token_length:
            raise ReproError(
                f"Token position {row.position} does not map to a residue for CSV row "
                f"{row.row_index}; token length is {token_length}"
            )
        with torch.inference_mode():
            logits = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                pos=torch.tensor([row.position], dtype=torch.long, device=config.device),
            ).logits[0]
        logit_negative = float(logits[0].item())
        logit_positive = float(logits[1].item())
        if not math.isfinite(logit_negative) or not math.isfinite(logit_positive):
            raise ReproError(f"Non-finite logit at CSV row {row.row_index}")
        prob_negative, prob_positive = softmax_two(logit_negative, logit_positive)
        residue, motif, is_sequon = residue_and_motif(row.sequence, row.position)
        predictions.append(
            Prediction(
                row_index=row.row_index,
                label=row.label,
                protein_id=row.protein_id,
                position=row.position,
                sequence_sha256=sha256_text(row.sequence),
                sequence_length=len(row.sequence),
                token_length=token_length,
                residue=residue,
                motif=motif,
                is_sequon=is_sequon,
                logit_negative=logit_negative,
                logit_positive=logit_positive,
                prob_negative=prob_negative,
                prob_positive=prob_positive,
                predicted_label=binary_argmax(logit_negative, logit_positive),
            )
        )
        if completed % 100 == 0 or completed == len(rows):
            print(f"processed {completed}/{len(rows)} rows", file=sys.stderr, flush=True)
    elapsed = time.perf_counter() - started

    metrics = confusion_and_metrics(
        [prediction.label for prediction in predictions],
        [prediction.predicted_label for prediction in predictions],
    )
    metrics.update(
        {
            "decision_rule": "argmax(logits)",
            "non_sequon_rows": sum(1 for prediction in predictions if not prediction.is_sequon),
            "protein_count": len({prediction.protein_id for prediction in predictions}),
            "longest_sequence_length": max(
                prediction.sequence_length for prediction in predictions
            ),
        }
    )
    audit_indices = select_audit_indices(rows)
    audit_set = set(audit_indices)

    temporary_dir = config.out_dir.with_name(f".{config.out_dir.name}.tmp-{os.getpid()}")
    if temporary_dir.exists():
        shutil.rmtree(temporary_dir)
    temporary_dir.mkdir(parents=True)
    try:
        atomic_write_csv(
            temporary_dir / "predictions.csv",
            PREDICTION_COLUMNS,
            (
                [asdict(prediction)[column] for column in PREDICTION_COLUMNS]
                for prediction in predictions
            ),
        )
        atomic_write_csv(
            temporary_dir / "audit_sample.csv",
            ("row_index",),
            ([index] for index in audit_indices),
        )
        atomic_write_json(temporary_dir / "metrics.json", metrics)
        atomic_write_text(
            temporary_dir / "report.md",
            report_text(metrics, rows, load_warnings),
        )

        created_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "schema_version": 1,
            "status": "complete",
            "created_at_utc": created_at,
            "command": [sys.executable, *sys.argv],
            "source": {
                "git_commit": git_commit,
                "git_dirty": git_dirty,
                "git_commit_role": "pre_artifact_code_baseline",
            },
            "inputs": {
                "test_csv": {
                    "path": str(config.test_csv),
                    "sha256": test_sha256,
                    "row_count": len(rows),
                    "label_counts": {
                        "0": sum(row.label == 0 for row in rows),
                        "1": sum(row.label == 1 for row in rows),
                    },
                    "protein_count": len({row.protein_id for row in rows}),
                },
                "adapter": {
                    "path": str(config.adapter_dir),
                    "model_sha256": adapter_sha256,
                    "config_sha256": sha256_file(adapter_config),
                    "tensor_count": tensor_count,
                },
                "base_model": {
                    "id": config.base_model_id,
                    "revision": config.base_model_revision,
                    "snapshot": str(model_snapshot),
                    "weights_file": model_file.name,
                    "weights_sha256": sha256_file(model_file),
                },
            },
            "environment": environment,
            "load_warnings": load_warnings,
            "inference": {
                "dtype": "float32",
                "batch_size": config.batch_size,
                "decision_rule": "argmax(logits)",
                "full_sequence": True,
                "truncation": False,
                "windowing": False,
                "elapsed_seconds": elapsed,
                "audit_sample_indices": audit_indices,
                "audit_sample_coverage": {
                    "contains_non_sequon": any(
                        not residue_and_motif(rows[index].sequence, rows[index].position)[2]
                        for index in audit_set
                    ),
                    "contains_longest": max(
                        range(len(rows)), key=lambda index: len(rows[index].sequence)
                    )
                    in audit_set,
                    "contains_both_labels": len({rows[index].label for index in audit_set})
                    == 2,
                },
            },
            "metrics": metrics,
            "artifacts": artifact_hashes(temporary_dir),
        }
        atomic_write_json(temporary_dir / "manifest.json", manifest)
        os.replace(temporary_dir, config.out_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise

    print(
        json.dumps(
            {
                "mcc": metrics["mcc"],
                "reference_mcc": REFERENCE_MCC,
                "delta": metrics["mcc_delta_from_reference"],
                "out_dir": str(config.out_dir),
                "elapsed_seconds": elapsed,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
