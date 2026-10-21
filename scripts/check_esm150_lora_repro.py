from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


REFERENCE_MCC = 0.848
EXPECTED_TEST_SHA256 = (
    "D2533271159123EE1C8D537CBE7BDA115AB0E0A29D98A8DF7B7B4ACC69217D20"
)
EXPECTED_ADAPTER_SHA256 = (
    "A4A5B486862724F459F60E8343AC135C340305D5A0F2E936EB5AD1DFD34788D4"
)
EXPECTED_ADAPTER_TENSORS = 376
EXPECTED_BASE_WEIGHTS_SHA256 = (
    "C3F1DA8AEA53BDDD32C246C86168C23B9FD72341FB9DB9A94436F855F5053566"
)
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


class CheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckConfig:
    run_dir: Path
    test_csv: Path
    adapter_dir: Path
    base_model_id: str
    base_model_revision: str
    compat_path: Path
    device: str
    recheck_inference: bool
    offline: bool
    logit_tolerance: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def approximately_equal(actual: float, expected: float, tolerance: float) -> bool:
    return math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance)


def softmax_pair(negative: float, positive: float) -> tuple[float, float]:
    top = max(negative, positive)
    exp_negative = math.exp(negative - top)
    exp_positive = math.exp(positive - top)
    total = exp_negative + exp_positive
    return exp_negative / total, exp_positive / total


def binary_argmax(negative: float, positive: float) -> int:
    return int(positive > negative)


def metrics_from_predictions(
    labels: Sequence[int],
    predictions: Sequence[int],
) -> dict[str, Any]:
    if len(labels) != len(predictions):
        raise CheckError("Labels and predictions have different lengths")
    if not labels:
        raise CheckError("Metrics require at least one row")
    if any(label not in (0, 1) for label in labels):
        raise CheckError("Labels must be binary")
    if any(prediction not in (0, 1) for prediction in predictions):
        raise CheckError("Predictions must be binary")
    tp = sum(label == 1 and prediction == 1 for label, prediction in zip(labels, predictions))
    fp = sum(label == 0 and prediction == 1 for label, prediction in zip(labels, predictions))
    tn = sum(label == 0 and prediction == 0 for label, prediction in zip(labels, predictions))
    fn = sum(label == 1 and prediction == 0 for label, prediction in zip(labels, predictions))
    product = (tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)
    mcc = ((tp * tn) - (fp * fn)) / math.sqrt(product) if product else 0.0
    return {
        "mcc": mcc,
        "reference_mcc": REFERENCE_MCC,
        "mcc_delta_from_reference": mcc - REFERENCE_MCC,
        "accuracy": (tp + tn) / len(labels),
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "specificity": tn / (tn + fp) if tn + fp else 0.0,
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "row_count": len(labels),
    }


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckError(f"Cannot read JSON {path}: {error}") from error


def load_csv(path: Path, expected_columns: Sequence[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != tuple(expected_columns):
            raise CheckError(
                f"Unexpected header in {path}: {reader.fieldnames}; "
                f"expected {list(expected_columns)}"
            )
        return list(reader)


def expected_motif(sequence: str, position: int) -> tuple[str, str, int]:
    start = position - 1
    motif = sequence[start : start + 3]
    is_sequon = int(
        len(motif) == 3
        and motif[0] == "N"
        and motif[1] != "P"
        and motif[2] in {"S", "T"}
    )
    return sequence[start], motif, is_sequon


def verify_artifact_hashes(run_dir: Path, manifest: dict[str, Any]) -> int:
    assertions = 0
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise CheckError("manifest.artifacts must be an object")
    expected_names = {
        "predictions.csv",
        "audit_sample.csv",
        "metrics.json",
        "report.md",
    }
    if set(artifacts) != expected_names:
        raise CheckError(
            f"Artifact set mismatch: {sorted(artifacts)} != {sorted(expected_names)}"
        )
    for name, expected_hash in artifacts.items():
        path = run_dir / name
        if not path.is_file():
            raise CheckError(f"Missing artifact: {path}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise CheckError(
                f"Artifact hash mismatch for {name}: {actual_hash} != {expected_hash}"
            )
        assertions += 1
    return assertions


def verify_predictions(
    run_dir: Path,
    test_rows: Sequence[dict[str, str]],
) -> tuple[list[dict[str, str]], int]:
    prediction_rows = load_csv(run_dir / "predictions.csv", PREDICTION_COLUMNS)
    if len(prediction_rows) != len(test_rows):
        raise CheckError(
            f"Prediction row count mismatch: {len(prediction_rows)} != {len(test_rows)}"
        )
    assertions = 1
    for row_index, (actual, source) in enumerate(zip(prediction_rows, test_rows)):
        sequence = source["sequence"]
        position = int(source["pos"])
        residue, motif, is_sequon = expected_motif(sequence, position)
        expected_values = {
            "row_index": str(row_index),
            "label": source["label"],
            "protein_id": source["id"],
            "position": source["pos"],
            "sequence_sha256": sha256_text(sequence),
            "sequence_length": str(len(sequence)),
            "residue": residue,
            "motif": motif,
            "is_sequon": str(is_sequon),
        }
        for field, expected in expected_values.items():
            if actual[field] != expected:
                raise CheckError(
                    f"Row {row_index} field {field}: {actual[field]!r} != {expected!r}"
                )
            assertions += 1

        logit_negative = float(actual["logit_negative"])
        logit_positive = float(actual["logit_positive"])
        if not math.isfinite(logit_negative) or not math.isfinite(logit_positive):
            raise CheckError(f"Non-finite logit at row {row_index}")
        expected_negative, expected_positive = softmax_pair(logit_negative, logit_positive)
        actual_negative = float(actual["prob_negative"])
        actual_positive = float(actual["prob_positive"])
        if not approximately_equal(actual_negative, expected_negative, 1e-12):
            raise CheckError(
                f"Negative probability mismatch at row {row_index}: "
                f"{actual_negative} != {expected_negative}"
            )
        if not approximately_equal(actual_positive, expected_positive, 1e-12):
            raise CheckError(
                f"Positive probability mismatch at row {row_index}: "
                f"{actual_positive} != {expected_positive}"
            )
        expected_label = binary_argmax(logit_negative, logit_positive)
        actual_label = int(actual["predicted_label"])
        if actual_label != expected_label:
            raise CheckError(
                f"Argmax mismatch at row {row_index}: {actual_label} != {expected_label}"
            )
        assertions += 4
    return prediction_rows, assertions


def verify_metrics(
    run_dir: Path,
    manifest: dict[str, Any],
    prediction_rows: Sequence[dict[str, str]],
) -> int:
    metrics = load_json(run_dir / "metrics.json")
    recomputed = metrics_from_predictions(
        [int(row["label"]) for row in prediction_rows],
        [int(row["predicted_label"]) for row in prediction_rows],
    )
    recomputed.update(
        {
            "decision_rule": "argmax(logits)",
            "non_sequon_rows": sum(
                int(row["is_sequon"]) == 0 for row in prediction_rows
            ),
            "protein_count": len({row["protein_id"] for row in prediction_rows}),
            "longest_sequence_length": max(
                int(row["sequence_length"]) for row in prediction_rows
            ),
        }
    )
    if metrics != recomputed:
        raise CheckError("metrics.json does not match independently recomputed metrics")
    if manifest.get("metrics") != recomputed:
        raise CheckError("Manifest metrics do not match independently recomputed metrics")

    return len(recomputed) + 2


def verify_manifest(
    config: CheckConfig,
    manifest: dict[str, Any],
    test_rows: Sequence[dict[str, str]],
) -> int:
    assertions = 0
    if manifest.get("schema_version") != 1:
        raise CheckError("Unsupported manifest schema")
    if manifest.get("status") != "complete":
        raise CheckError("Manifest is not marked complete")
    source = manifest.get("source", {})
    commit = source.get("git_commit")
    if not isinstance(commit, str) or len(commit) != 40:
        raise CheckError(f"Invalid source commit: {commit!r}")
    if source.get("git_dirty") is not False:
        raise CheckError("Source baseline was dirty; rerun from a clean code commit")
    assertions += 3

    test_sha = sha256_file(config.test_csv)
    adapter_sha = sha256_file(config.adapter_dir / "adapter_model.safetensors")
    if test_sha != EXPECTED_TEST_SHA256:
        raise CheckError(f"Test CSV hash mismatch: {test_sha}")
    if adapter_sha != EXPECTED_ADAPTER_SHA256:
        raise CheckError(f"Adapter hash mismatch: {adapter_sha}")
    inputs = manifest.get("inputs", {})
    if inputs.get("test_csv", {}).get("sha256") != test_sha:
        raise CheckError("Manifest test CSV hash mismatch")
    if inputs.get("test_csv", {}).get("row_count") != len(test_rows):
        raise CheckError("Manifest test row count mismatch")
    if inputs.get("adapter", {}).get("model_sha256") != adapter_sha:
        raise CheckError("Manifest adapter hash mismatch")
    if inputs.get("adapter", {}).get("tensor_count") != EXPECTED_ADAPTER_TENSORS:
        raise CheckError("Manifest adapter tensor count mismatch")
    base = inputs.get("base_model", {})
    if base.get("id") != config.base_model_id:
        raise CheckError("Manifest base model id mismatch")
    if base.get("revision") != config.base_model_revision:
        raise CheckError("Manifest base model revision mismatch")
    if base.get("weights_sha256") != EXPECTED_BASE_WEIGHTS_SHA256:
        raise CheckError("Manifest base model weights hash mismatch")
    expected_label_counts = {
        "0": sum(row["label"] == "0" for row in test_rows),
        "1": sum(row["label"] == "1" for row in test_rows),
    }
    if inputs.get("test_csv", {}).get("label_counts") != expected_label_counts:
        raise CheckError("Manifest label counts mismatch")
    if inputs.get("test_csv", {}).get("protein_count") != len(
        {row["id"] for row in test_rows}
    ):
        raise CheckError("Manifest test protein count mismatch")
    assertions += 11

    versions = manifest.get("environment", {}).get("versions", {})
    expected_versions = {
        "transformers": "4.50.3",
        "peft": "0.14.0",
        "tokenizers": "0.21.1",
        "huggingface_hub": "0.26.3",
    }
    for name, expected in expected_versions.items():
        if versions.get(name) != expected:
            raise CheckError(
                f"Manifest dependency mismatch for {name}: "
                f"{versions.get(name)!r} != {expected!r}"
            )
        assertions += 1

    inference = manifest.get("inference", {})
    required_inference = {
        "dtype": "float32",
        "batch_size": 1,
        "decision_rule": "argmax(logits)",
        "encoding_strategy": "once_per_unique_sequence",
        "full_sequence": True,
        "truncation": False,
        "windowing": False,
        "row_count": len(test_rows),
        "unique_sequence_count": len({row["sequence"] for row in test_rows}),
        "encoder_forward_count": len({row["sequence"] for row in test_rows}),
    }
    for key, expected in required_inference.items():
        if inference.get(key) != expected:
            raise CheckError(
                f"Inference contract mismatch for {key}: "
                f"{inference.get(key)!r} != {expected!r}"
            )
        assertions += 1
    return assertions


def load_recheck_matches(
    config: CheckConfig,
    run_dir: Path,
    test_rows: Sequence[dict[str, str]],
    prediction_rows: Sequence[dict[str, str]],
) -> tuple[list[dict[str, Any]], int]:
    if not config.recheck_inference:
        return [], 0

    compat = config.compat_path.resolve()
    if not compat.is_dir():
        raise CheckError(f"Compatibility path does not exist: {compat}")
    sys.path.insert(0, str(compat))
    import peft
    import torch
    import transformers
    from peft import PeftModel
    from transformers import AutoTokenizer

    if peft.__version__ != "0.14.0" or transformers.__version__ != "4.50.3":
        raise CheckError(
            f"Recheck dependency mismatch: peft={peft.__version__}, "
            f"transformers={transformers.__version__}"
        )

    upstream_repo = config.adapter_dir.parents[3]
    if not (upstream_repo / "model" / "esm_model.py").is_file():
        raise CheckError(f"Cannot find upstream model module under {upstream_repo}")
    sys.path.insert(0, str(upstream_repo))
    from model.esm_model import EsmModelClassification

    from huggingface_hub import snapshot_download

    sample_rows = load_csv(run_dir / "audit_sample.csv", ("row_index",))
    sample_indices = [int(row["row_index"]) for row in sample_rows]
    if len(sample_indices) != 16 or len(set(sample_indices)) != 16:
        raise CheckError("Audit sample must contain 16 unique rows")
    if any(index < 0 or index >= len(test_rows) for index in sample_indices):
        raise CheckError("Audit sample index outside test CSV")
    selected_labels = {int(test_rows[index]["label"]) for index in sample_indices}
    if selected_labels != {0, 1}:
        raise CheckError("Audit sample must contain both labels")
    if not any(
        expected_motif(test_rows[index]["sequence"], int(test_rows[index]["pos"]))[2] == 0
        for index in sample_indices
    ):
        raise CheckError("Audit sample must contain a non-sequon row")

    snapshot = Path(
        snapshot_download(
            repo_id=config.base_model_id,
            revision=config.base_model_revision,
            local_files_only=config.offline,
        )
    )
    tokenizer = AutoTokenizer.from_pretrained(
        snapshot,
        trust_remote_code=True,
        local_files_only=True,
    )
    kwargs: dict[str, Any] = {
        "num_labels": 2,
        "torch_dtype": torch.float32,
        "local_files_only": True,
    }
    if config.device.startswith("cuda"):
        kwargs["device_map"] = config.device
    model = EsmModelClassification.from_pretrained(snapshot, **kwargs)
    model = PeftModel.from_pretrained(model, config.adapter_dir)
    if not config.device.startswith("cuda"):
        model.to(config.device)
    model.eval()

    recomputed: list[dict[str, Any]] = []
    with torch.inference_mode():
        for index in sample_indices:
            source = test_rows[index]
            encoded = tokenizer(source["sequence"], return_tensors="pt")
            encoded = {key: value.to(config.device) for key, value in encoded.items()}
            logits = model(
                input_ids=encoded["input_ids"],
                attention_mask=encoded["attention_mask"],
                pos=torch.tensor(
                    [int(source["pos"])],
                    dtype=torch.long,
                    device=config.device,
                ),
            ).logits[0]
            recomputed.append(
                {
                    "row_index": index,
                    "logit_negative": float(logits[0].item()),
                    "logit_positive": float(logits[1].item()),
                }
            )

    assertions = 0
    prediction_by_index = {
        int(row["row_index"]): row for row in prediction_rows
    }
    for recomputed_row in recomputed:
        index = recomputed_row["row_index"]
        saved = prediction_by_index.get(index)
        if saved is None:
            raise CheckError(f"Missing saved prediction for rechecked row {index}")
        for field in ("logit_negative", "logit_positive"):
            if not approximately_equal(
                recomputed_row[field],
                float(saved[field]),
                config.logit_tolerance,
            ):
                raise CheckError(
                    f"Recheck mismatch row {index} {field}: "
                    f"{recomputed_row[field]} != {saved[field]}"
                )
            assertions += 1
    return recomputed, assertions


def parse_args(argv: Sequence[str] | None = None) -> CheckConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--test-csv", required=True, type=Path)
    parser.add_argument("--adapter-dir", required=True, type=Path)
    parser.add_argument(
        "--base-model-id",
        default="facebook/esm2_t30_150M_UR50D",
    )
    parser.add_argument(
        "--base-model-revision",
        default="a695f6045e2e32885fa60af20c13cb35398ce30c",
    )
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
    parser.add_argument("--recheck-inference", action="store_true")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--logit-tolerance", type=float, default=2e-4)
    args = parser.parse_args(argv)
    return CheckConfig(
        run_dir=args.run_dir.resolve(),
        test_csv=args.test_csv.resolve(),
        adapter_dir=args.adapter_dir.resolve(),
        base_model_id=args.base_model_id,
        base_model_revision=args.base_model_revision,
        compat_path=args.compat_path.resolve(),
        device=args.device,
        recheck_inference=args.recheck_inference,
        offline=not args.allow_download,
        logit_tolerance=args.logit_tolerance,
    )


def main(argv: Sequence[str] | None = None) -> int:
    config = parse_args(argv)
    try:
        test_rows = load_csv(config.test_csv, EXPECTED_COLUMNS)
        manifest = load_json(config.run_dir / "manifest.json")
        assertions = verify_manifest(config, manifest, test_rows)
        assertions += verify_artifact_hashes(config.run_dir, manifest)
        prediction_rows, prediction_assertions = verify_predictions(
            config.run_dir,
            test_rows,
        )
        assertions += prediction_assertions
        assertions += verify_metrics(config.run_dir, manifest, prediction_rows)
        rechecked, recheck_assertions = load_recheck_matches(
            config,
            config.run_dir,
            test_rows,
            prediction_rows,
        )
        assertions += recheck_assertions
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    result = {
        "status": "PASS",
        "assertions": assertions,
        "rows": len(prediction_rows),
        "rechecked_rows": len(rechecked),
        "mcc": manifest["metrics"]["mcc"],
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
