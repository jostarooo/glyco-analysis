from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "glyco.w1-esm150-candidates/v1"
EXPECTED_CANDIDATES_SHA256 = (
    "DBD51D28ABC0B0C74E78496E0A8F54CEBAA1C29F274B6E6B2716E39631A09FAB"
)
EXPECTED_CANDIDATE_COLUMNS = ("label", "id", "pos", "sequence")
EXPECTED_ADAPTER_SHA256 = (
    "A4A5B486862724F459F60E8343AC135C340305D5A0F2E936EB5AD1DFD34788D4"
)
EXPECTED_ADAPTER_TENSORS = 376
EXPECTED_BASE_MODEL_ID = "facebook/esm2_t30_150M_UR50D"
EXPECTED_BASE_MODEL_REVISION = "a695f6045e2e32885fa60af20c13cb35398ce30c"
EXPECTED_BASE_WEIGHTS_SHA256 = (
    "C3F1DA8AEA53BDDD32C246C86168C23B9FD72341FB9DB9A94436F855F5053566"
)
EXPECTED_ROW_COUNT = 201
EXPECTED_PROTEIN_COUNT = 29
EXPECTED_UNIQUE_SEQUENCE_COUNT = 29
EXPECTED_LABEL_COUNTS = {"0": 48, "1": 153}
PROBABILITY_SUM_TOLERANCE = 1e-12
PROBABILITY_VALUE_TOLERANCE = 1e-15
PREDICTION_COLUMNS = (
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
PAYLOAD_ARTIFACTS = ("predictions.csv", "report.md")


class CandidateInferenceError(RuntimeError):
    pass


def _load_repro_helpers() -> Any:
    helper_path = Path(__file__).resolve().with_name("run_esm150_lora_repro.py")
    module_name = "_glyco_esm150_candidate_inference_helpers"
    spec = importlib.util.spec_from_file_location(module_name, helper_path)
    if spec is None or spec.loader is None:
        raise CandidateInferenceError(f"Cannot load helper module: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


helpers = _load_repro_helpers()


@dataclass(frozen=True)
class CandidateInferenceConfig:
    candidates: Path
    adapter_dir: Path
    base_model_id: str
    base_model_revision: str
    compat_path: Path
    device: str
    attention_backend: str
    out_dir: Path
    offline: bool


@dataclass(frozen=True)
class CandidateInputSummary:
    path: Path
    sha256: str
    row_count: int
    protein_count: int
    unique_sequence_count: int
    keys_sha256: str
    label_counts: dict[str, int]
    model_inputs: dict[str, str]


@dataclass(frozen=True)
class CandidateInferenceRow:
    row_index: int
    accession: str
    position: int
    label: int
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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateInferenceError(message)


def _load_candidate_rows(path: Path) -> list[Any]:
    try:
        return helpers.load_test_rows(path)
    except helpers.ReproError as error:
        raise CandidateInferenceError(str(error)) from error


def _key_digest(rows: Sequence[Any]) -> str:
    ordered_keys = [[row.protein_id, row.position] for row in rows]
    canonical = json.dumps(ordered_keys, separators=(",", ":"), ensure_ascii=False)
    return helpers.sha256_text(canonical)


def validate_candidates(path: Path) -> CandidateInputSummary:
    path = path.resolve()
    _require(path.is_file(), f"Candidate CSV not found: {path}")
    sha256 = helpers.sha256_file(path)
    _require(
        sha256 == EXPECTED_CANDIDATES_SHA256,
        f"Unexpected candidate CSV SHA256: {sha256}; "
        f"expected {EXPECTED_CANDIDATES_SHA256}",
    )

    rows = _load_candidate_rows(path)
    _require(
        len(rows) == EXPECTED_ROW_COUNT,
        f"Candidate CSV has {len(rows)} rows; expected {EXPECTED_ROW_COUNT}",
    )

    keys: set[tuple[str, int]] = set()
    accession_sequences: dict[str, str] = {}
    label_counts = {"0": 0, "1": 0}
    for row in rows:
        _require(bool(row.protein_id), f"Empty accession at CSV row {row.row_index}")
        key = (row.protein_id, row.position)
        _require(key not in keys, f"Duplicate candidate key: {key}")
        keys.add(key)
        label_counts[str(row.label)] += 1

        previous_sequence = accession_sequences.get(row.protein_id)
        if previous_sequence is not None:
            _require(
                previous_sequence == row.sequence,
                f"Accession {row.protein_id} maps to multiple sequences",
            )
        else:
            accession_sequences[row.protein_id] = row.sequence

        residue, motif, is_sequon = helpers.residue_and_motif(
            row.sequence,
            row.position,
        )
        _require(
            residue == "N",
            f"Target residue is not N at CSV row {row.row_index}: {residue}",
        )
        _require(
            is_sequon == 1,
            f"Invalid N-X-S/T motif at CSV row {row.row_index}: {motif}",
        )

    _require(
        len(accession_sequences) == EXPECTED_PROTEIN_COUNT,
        f"Candidate CSV has {len(accession_sequences)} accessions; "
        f"expected {EXPECTED_PROTEIN_COUNT}",
    )
    unique_sequence_count = len(set(accession_sequences.values()))
    _require(
        unique_sequence_count == EXPECTED_UNIQUE_SEQUENCE_COUNT,
        f"Candidate CSV has {unique_sequence_count} unique sequences; "
        f"expected {EXPECTED_UNIQUE_SEQUENCE_COUNT}",
    )
    _require(
        label_counts == EXPECTED_LABEL_COUNTS,
        f"Unexpected candidate label counts: {label_counts}; "
        f"expected {EXPECTED_LABEL_COUNTS}",
    )

    return CandidateInputSummary(
        path=path,
        sha256=sha256,
        row_count=len(rows),
        protein_count=len(accession_sequences),
        unique_sequence_count=unique_sequence_count,
        keys_sha256=_key_digest(rows),
        label_counts=label_counts,
        model_inputs=accession_sequences,
    )


def _validate_pinned_config(config: CandidateInferenceConfig) -> None:
    _require(
        config.base_model_id == EXPECTED_BASE_MODEL_ID,
        f"Unexpected base model ID: {config.base_model_id}",
    )
    _require(
        config.base_model_revision == EXPECTED_BASE_MODEL_REVISION,
        f"Unexpected base model revision: {config.base_model_revision}",
    )
    _require(
        config.device == "cuda" or config.device.startswith("cuda:"),
        "This W1 candidate inference is pinned to a CUDA device",
    )
    if config.attention_backend == "sdpa":
        _require(
            config.device.startswith("cuda"),
            "SDPA efficient attention requires a CUDA device",
        )


def _repro_run_config(config: CandidateInferenceConfig) -> Any:
    return helpers.RunConfig(
        test_csv=config.candidates,
        adapter_dir=config.adapter_dir,
        base_model_id=config.base_model_id,
        base_model_revision=config.base_model_revision,
        out_dir=config.out_dir,
        compat_path=config.compat_path,
        device=config.device,
        batch_size=1,
        attention_backend=config.attention_backend,
        offline=config.offline,
    )


def _adapter_metadata(adapter_dir: Path) -> dict[str, object]:
    adapter_file = adapter_dir / "adapter_model.safetensors"
    adapter_config = adapter_dir / "adapter_config.json"
    _require(adapter_file.is_file(), f"Adapter weights not found: {adapter_file}")
    _require(adapter_config.is_file(), f"Adapter config not found: {adapter_config}")
    adapter_sha256 = helpers.sha256_file(adapter_file)
    _require(
        adapter_sha256 == EXPECTED_ADAPTER_SHA256,
        f"Unexpected adapter SHA256: {adapter_sha256}; "
        f"expected {EXPECTED_ADAPTER_SHA256}",
    )
    tensor_count = helpers.adapter_tensor_count(adapter_file)
    _require(
        tensor_count == EXPECTED_ADAPTER_TENSORS,
        f"Unexpected adapter tensor count: {tensor_count}; "
        f"expected {EXPECTED_ADAPTER_TENSORS}",
    )
    return {
        "path": str(adapter_dir),
        "model_sha256": adapter_sha256,
        "config_sha256": helpers.sha256_file(adapter_config),
        "tensor_count": tensor_count,
    }


def _find_base_weights(snapshot: Path) -> Path:
    for name in ("model.safetensors", "pytorch_model.bin"):
        candidate = snapshot / name
        if candidate.is_file():
            return candidate
    raise CandidateInferenceError(f"No base-model weights found in snapshot: {snapshot}")


def _base_model_metadata(config: CandidateInferenceConfig) -> dict[str, object]:
    snapshot = helpers.resolve_model_snapshot(_repro_run_config(config))
    weights_path = _find_base_weights(snapshot)
    weights_sha256 = helpers.sha256_file(weights_path)
    _require(
        weights_sha256 == EXPECTED_BASE_WEIGHTS_SHA256,
        f"Unexpected base-model weights SHA256: {weights_sha256}; "
        f"expected {EXPECTED_BASE_WEIGHTS_SHA256}",
    )
    return {
        "id": config.base_model_id,
        "revision": config.base_model_revision,
        "snapshot": str(snapshot),
        "weights_file": weights_path.name,
        "weights_sha256": weights_sha256,
    }


def _validate_prediction_values(row: CandidateInferenceRow) -> None:
    values = (
        row.logit_negative,
        row.logit_positive,
        row.prob_negative,
        row.prob_positive,
    )
    _require(
        all(math.isfinite(value) for value in values),
        f"Non-finite prediction value at row_index {row.row_index}",
    )
    _require(
        0.0 <= row.prob_negative <= 1.0 and 0.0 <= row.prob_positive <= 1.0,
        f"Probability outside [0, 1] at row_index {row.row_index}",
    )
    _require(
        abs((row.prob_negative + row.prob_positive) - 1.0)
        <= PROBABILITY_SUM_TOLERANCE,
        f"Probabilities do not sum to 1 at row_index {row.row_index}",
    )

    expected_negative, expected_positive = helpers.softmax_two(
        row.logit_negative,
        row.logit_positive,
    )
    _require(
        math.isclose(
            row.prob_negative,
            expected_negative,
            rel_tol=0.0,
            abs_tol=PROBABILITY_VALUE_TOLERANCE,
        )
        and math.isclose(
            row.prob_positive,
            expected_positive,
            rel_tol=0.0,
            abs_tol=PROBABILITY_VALUE_TOLERANCE,
        ),
        f"Probability invariant failed at row_index {row.row_index}",
    )

    expected_label = helpers.binary_argmax(
        row.logit_negative,
        row.logit_positive,
    )
    _require(
        row.predicted_label == expected_label,
        f"Predicted label does not match argmax at row_index {row.row_index}",
    )


def validate_prediction_rows(
    predictions: Sequence[CandidateInferenceRow],
    source_rows: Sequence[Any],
    summary: CandidateInputSummary,
) -> None:
    _require(
        len(predictions) == summary.row_count,
        f"Prediction count {len(predictions)} does not match "
        f"candidate row count {summary.row_count}",
    )
    _require(
        [row.row_index for row in predictions] == list(range(summary.row_count)),
        "Prediction row_index values are not the original 0-based order",
    )

    predicted_keys = [(row.accession, row.position) for row in predictions]
    source_keys = [(row.protein_id, row.position) for row in source_rows]
    _require(
        predicted_keys == source_keys,
        "Prediction keys do not exactly preserve candidate key order",
    )
    _require(
        len(set(predicted_keys)) == len(predicted_keys),
        "Prediction keys are not unique",
    )

    for prediction, source in zip(predictions, source_rows):
        sequence = summary.model_inputs[source.protein_id]
        _require(
            prediction.accession == source.protein_id
            and prediction.position == source.position,
            f"Prediction key mismatch at row_index {prediction.row_index}",
        )
        _require(
            prediction.label == source.label,
            f"Source label mismatch at row_index {prediction.row_index}",
        )
        _require(
            prediction.sequence_sha256 == helpers.sha256_text(sequence),
            f"Sequence hash mismatch at row_index {prediction.row_index}",
        )
        _require(
            prediction.sequence_length == len(sequence),
            f"Sequence length mismatch at row_index {prediction.row_index}",
        )
        _require(
            prediction.token_length == len(sequence) + 2,
            f"Token length indicates truncation or tokenizer drift at "
            f"row_index {prediction.row_index}",
        )
        _require(
            1 <= source.position < prediction.token_length - 1,
            f"Target token position is invalid at row_index {prediction.row_index}",
        )

        residue, motif, is_sequon = helpers.residue_and_motif(
            sequence,
            source.position,
        )
        _require(
            prediction.residue == residue
            and prediction.motif == motif
            and prediction.is_sequon == is_sequon,
            f"Residue or motif mismatch at row_index {prediction.row_index}",
        )
        _require(
            prediction.residue == "N" and prediction.is_sequon == 1,
            f"Non-sequon target at row_index {prediction.row_index}",
        )
        _validate_prediction_values(prediction)


def infer_candidates(
    config: CandidateInferenceConfig,
    summary: CandidateInputSummary,
) -> tuple[list[CandidateInferenceRow], dict[str, object], list[str]]:
    _validate_pinned_config(config)
    current_summary = validate_candidates(config.candidates)
    _require(current_summary == summary, "Candidate CSV changed after validation")
    source_rows = _load_candidate_rows(config.candidates)
    sequence_jobs = helpers.group_rows_by_sequence(source_rows)
    _require(
        len(sequence_jobs) == summary.unique_sequence_count,
        "Sequence grouping does not match the validated unique-sequence count",
    )

    adapter_metadata = _adapter_metadata(config.adapter_dir)
    base_model_metadata = _base_model_metadata(config)
    model, tokenizer, environment, load_warnings = helpers.load_model(
        _repro_run_config(config)
    )
    import torch

    device_record = dict(environment.get("device", {}))
    device_record["actual"] = str(getattr(model, "device", config.device))
    for count_name in (
        "sdpa_module_count",
        "sdpa_eligible_module_count",
        "sdpa_expected_module_count",
    ):
        device_record.setdefault(count_name, 0)
    environment["device"] = device_record
    environment["adapter"] = adapter_metadata
    environment["base_model"] = base_model_metadata

    position_model = model.base_model.model
    predictions: list[CandidateInferenceRow] = []
    completed_jobs = 0
    with torch.inference_mode():
        for job in sequence_jobs:
            encoded = tokenizer(job.sequence, return_tensors="pt")
            input_ids = encoded["input_ids"].to(config.device)
            attention_mask = encoded["attention_mask"].to(config.device)
            _require(
                int(input_ids.shape[0]) == 1,
                "Tokenizer produced a batch other than 1",
            )
            token_length = int(input_ids.shape[1])
            _require(
                token_length == len(job.sequence) + 2,
                f"Full sequence was not encoded exactly once for accession "
                f"{job.rows[0].protein_id}: token_length={token_length}, "
                f"sequence_length={len(job.sequence)}",
            )

            hidden = position_model.esm(
                input_ids=input_ids,
                attention_mask=attention_mask,
                return_dict=True,
            ).last_hidden_state
            for row in job.rows:
                _require(
                    1 <= row.position < token_length - 1,
                    f"Token position {row.position} does not map to a residue "
                    f"for CSV row {row.row_index}",
                )
                position_tensor = torch.tensor(
                    [row.position],
                    dtype=torch.long,
                    device=input_ids.device,
                )
                logits = position_model.classifier(hidden, position_tensor)[0]
                logit_negative = float(logits[0].item())
                logit_positive = float(logits[1].item())
                _require(
                    math.isfinite(logit_negative)
                    and math.isfinite(logit_positive),
                    f"Non-finite logit at CSV row {row.row_index}",
                )
                prob_negative, prob_positive = helpers.softmax_two(
                    logit_negative,
                    logit_positive,
                )
                residue, motif, is_sequon = helpers.residue_and_motif(
                    row.sequence,
                    row.position,
                )
                prediction = CandidateInferenceRow(
                    row_index=row.row_index,
                    accession=row.protein_id,
                    position=row.position,
                    label=row.label,
                    sequence_sha256=helpers.sha256_text(row.sequence),
                    sequence_length=len(row.sequence),
                    token_length=token_length,
                    residue=residue,
                    motif=motif,
                    is_sequon=is_sequon,
                    logit_negative=logit_negative,
                    logit_positive=logit_positive,
                    prob_negative=prob_negative,
                    prob_positive=prob_positive,
                    predicted_label=helpers.binary_argmax(
                        logit_negative,
                        logit_positive,
                    ),
                )
                _validate_prediction_values(prediction)
                predictions.append(prediction)

            completed_jobs += 1
            if completed_jobs % 5 == 0 or completed_jobs == len(sequence_jobs):
                print(
                    f"processed {completed_jobs}/{len(sequence_jobs)} unique sequences",
                    file=sys.stderr,
                    flush=True,
                )

    validate_prediction_rows(predictions, source_rows, summary)
    return predictions, environment, load_warnings


def _write_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temporary, path)


def _write_json(path: Path, value: object) -> None:
    _write_text(
        path,
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
    )


def _write_csv(
    path: Path,
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
    os.replace(temporary, path)


def _artifact_records(
    out_dir: Path,
    names: Sequence[str] = PAYLOAD_ARTIFACTS,
) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for name in names:
        path = out_dir / name
        _require(path.is_file(), f"Artifact not found: {path}")
        records[name] = {
            "sha256": helpers.sha256_file(path),
            "bytes": path.stat().st_size,
        }
    return records


def verify_artifact_records(
    out_dir: Path,
    artifacts: Mapping[str, Mapping[str, object]],
) -> int:
    verified = 0
    for name, expected in artifacts.items():
        _require(
            name in PAYLOAD_ARTIFACTS,
            f"Unexpected manifest artifact name: {name}",
        )
        path = out_dir / name
        _require(path.is_file(), f"Artifact not found: {path}")
        actual_sha256 = helpers.sha256_file(path)
        actual_bytes = path.stat().st_size
        _require(
            actual_sha256 == expected.get("sha256"),
            f"Artifact hash mismatch for {name}: {actual_sha256}",
        )
        _require(
            actual_bytes == expected.get("bytes"),
            f"Artifact byte-size mismatch for {name}: {actual_bytes}",
        )
        verified += 1
    return verified


def _validate_serialized_predictions(
    path: Path,
    expected_rows: Sequence[CandidateInferenceRow],
) -> None:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _require(
            tuple(reader.fieldnames or ()) == PREDICTION_COLUMNS,
            f"Unexpected prediction CSV header: {reader.fieldnames}; "
            f"expected {list(PREDICTION_COLUMNS)}",
        )
        raw_rows = list(reader)

    _require(
        len(raw_rows) == len(expected_rows),
        f"Prediction CSV has {len(raw_rows)} rows; expected {len(expected_rows)}",
    )
    parsed_rows: list[CandidateInferenceRow] = []
    for raw in raw_rows:
        try:
            row = CandidateInferenceRow(
                row_index=int(raw["row_index"]),
                accession=raw["accession"],
                position=int(raw["position"]),
                label=int(raw["label"]),
                sequence_sha256=raw["sequence_sha256"],
                sequence_length=int(raw["sequence_length"]),
                token_length=int(raw["token_length"]),
                residue=raw["residue"],
                motif=raw["motif"],
                is_sequon=int(raw["is_sequon"]),
                logit_negative=float(raw["logit_negative"]),
                logit_positive=float(raw["logit_positive"]),
                prob_negative=float(raw["prob_negative"]),
                prob_positive=float(raw["prob_positive"]),
                predicted_label=int(raw["predicted_label"]),
            )
        except (TypeError, ValueError) as error:
            raise CandidateInferenceError(
                "Prediction CSV contains a non-numeric field"
            ) from error
        _validate_prediction_values(row)
        parsed_rows.append(row)

    _require(
        parsed_rows == list(expected_rows),
        "Serialized predictions do not match the validated in-memory rows",
    )


def _source_state(repo_root: Path) -> tuple[str, bool]:
    commit_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if commit_result.returncode != 0:
        raise CandidateInferenceError(
            f"git rev-parse HEAD failed: {commit_result.stderr.strip()}"
        )
    status_result = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if status_result.returncode != 0:
        raise CandidateInferenceError(
            f"git status failed: {status_result.stderr.strip()}"
        )
    return commit_result.stdout.strip(), bool(status_result.stdout.strip())


def _device_manifest(config: CandidateInferenceConfig, environment: Mapping[str, Any]) -> dict[str, object]:
    device = dict(environment.get("device", {}))
    device.setdefault("requested", config.device)
    device.setdefault("actual", config.device)
    for count_name in (
        "sdpa_module_count",
        "sdpa_eligible_module_count",
        "sdpa_expected_module_count",
    ):
        device.setdefault(count_name, 0)
    return device


def _report_text(
    summary: CandidateInputSummary,
    adapter: Mapping[str, object],
    base_model: Mapping[str, object],
    config: CandidateInferenceConfig,
) -> str:
    lines = [
        "# W1 ESM-2 150M 候选位点推理",
        "",
        "## 结论",
        "",
        "本产物使用固定的作者 PEFT 参数高效微调适配器，对 W1 候选表的 201 行逐行推理。"
        "模型读取完整蛋白序列，在目标残基输出两个分数（`logit`），并按 "
        "`argmax(logits)` 得到预测标签。",
        "",
        "复制过来的 `label` 列只用于追溯，不进入模型输入。本次推理不计算基准评测"
        "指标，也不比较推断证据与实验证据的表现。",
        "",
        "## 输入",
        "",
        f"- 候选表：`{summary.path}`",
        f"- 候选表 SHA256：`{summary.sha256}`",
        f"- 行数：`{summary.row_count}`",
        f"- 蛋白数：`{summary.protein_count}`",
        f"- 唯一序列数：`{summary.unique_sequence_count}`",
        f"- 标签计数：`1={summary.label_counts['1']}`, "
        f"`0={summary.label_counts['0']}`",
        f"- 有序键 SHA256：`{summary.keys_sha256}`",
        "",
        "## 固定模型",
        "",
        f"- 适配器 SHA256：`{adapter['model_sha256']}`",
        f"- 适配器张量数：`{adapter['tensor_count']}`",
        f"- 基座模型：`{base_model['id']}`",
        f"- 基座版本（`revision`）：`{base_model['revision']}`",
        f"- 基座权重 SHA256：`{base_model['weights_sha256']}`",
        "",
        "## 推理设置",
        "",
        "- 精度：FP32",
        "- 批大小：1",
        "- 序列覆盖：完整序列",
        "- 截断：无",
        "- 滑窗：无",
        f"- 注意力后端：`{config.attention_backend}`",
        "- 判定规则：当且仅当 `logit_positive > logit_negative` 时判为阳性",
        "- 编码器前向次数：29，每条唯一序列执行一次",
        "",
        "## 完成标记",
        "",
        "`predictions.csv` 与本报告都被写入 `manifest.json` 的哈希记录。"
        "`manifest.json` 最后写入，并把本次运行标记为完成。",
        "",
    ]
    return "\n".join(lines)


def write_inference_run(
    config: CandidateInferenceConfig,
    summary: CandidateInputSummary,
    rows: Sequence[CandidateInferenceRow],
    environment: dict[str, object],
    load_warnings: Sequence[str],
) -> None:
    _require(
        not config.out_dir.exists(),
        f"Output directory already exists: {config.out_dir}",
    )
    current_summary = validate_candidates(config.candidates)
    _require(current_summary == summary, "Candidate CSV changed before output")
    source_rows = _load_candidate_rows(config.candidates)
    validate_prediction_rows(rows, source_rows, summary)

    adapter = environment.get("adapter")
    if not isinstance(adapter, dict):
        adapter = _adapter_metadata(config.adapter_dir)
    base_model = environment.get("base_model")
    if not isinstance(base_model, dict):
        base_model = _base_model_metadata(config)
    versions = environment.get("versions")
    _require(isinstance(versions, dict) and versions, "Missing dependency versions")
    device = _device_manifest(config, environment)
    report = _report_text(summary, adapter, base_model, config)

    repo_root = Path(__file__).resolve().parents[1]
    git_commit, git_dirty = _source_state(repo_root)
    config.out_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{config.out_dir.name}.tmp-",
            dir=config.out_dir.parent,
        )
    )
    try:
        prediction_path = temporary_dir / "predictions.csv"
        _write_csv(
            prediction_path,
            PREDICTION_COLUMNS,
            [
                [getattr(row, column) for column in PREDICTION_COLUMNS]
                for row in rows
            ],
        )
        _write_text(temporary_dir / "report.md", report)
        _validate_serialized_predictions(prediction_path, rows)
        artifacts = _artifact_records(temporary_dir)
        _require(
            verify_artifact_records(temporary_dir, artifacts) == len(PAYLOAD_ARTIFACTS),
            "Not all payload artifacts were verified",
        )

        manifest = {
            "schema": SCHEMA,
            "status": "complete",
            "source": {
                "git_commit": git_commit,
                "git_dirty": git_dirty,
                "git_commit_role": "pre_artifact_code_baseline",
            },
            "inputs": {
                "candidates_lora": {
                    "path": str(summary.path),
                    "sha256": summary.sha256,
                    "row_count": summary.row_count,
                    "protein_count": summary.protein_count,
                    "unique_sequence_count": summary.unique_sequence_count,
                    "keys_sha256": summary.keys_sha256,
                    "label_counts": summary.label_counts,
                },
                "adapter": adapter,
                "base_model": base_model,
            },
            "compatibility": {
                "path": str(config.compat_path),
                "pythonpath": os.environ.get("PYTHONPATH", ""),
                "versions": versions,
            },
            "device": device,
            "load_warnings": list(load_warnings),
            "inference": {
                "dtype": "float32",
                "batch_size": 1,
                "attention_backend": config.attention_backend,
                "decision_rule": "argmax(logits)",
                "positive_rule": "logit_positive > logit_negative",
                "encoding_strategy": "once_per_unique_sequence",
                "full_sequence": True,
                "truncation": False,
                "windowing": False,
                "row_count": summary.row_count,
                "protein_count": summary.protein_count,
                "unique_sequence_count": summary.unique_sequence_count,
                "encoder_forward_count": summary.unique_sequence_count,
            },
            "artifacts": artifacts,
        }
        _require(
            not config.out_dir.exists(),
            f"Output directory appeared during the run: {config.out_dir}",
        )
        _write_json(temporary_dir / "manifest.json", manifest)
        _require(
            not config.out_dir.exists(),
            f"Output directory appeared during the run: {config.out_dir}",
        )
        os.rename(temporary_dir, config.out_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise


def parse_args(argv: Sequence[str] | None = None) -> CandidateInferenceConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--adapter-dir", required=True, type=Path)
    parser.add_argument("--base-model-id", default=EXPECTED_BASE_MODEL_ID)
    parser.add_argument("--base-model-revision", default=EXPECTED_BASE_MODEL_REVISION)
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
    parser.add_argument(
        "--attention-backend",
        choices=("eager", "sdpa"),
        default="eager",
    )
    parser.add_argument("--allow-download", action="store_true")
    args = parser.parse_args(argv)

    if args.base_model_id != EXPECTED_BASE_MODEL_ID:
        raise CandidateInferenceError(
            f"Unexpected base model ID: {args.base_model_id}"
        )
    if args.base_model_revision != EXPECTED_BASE_MODEL_REVISION:
        raise CandidateInferenceError(
            f"Unexpected base model revision: {args.base_model_revision}"
        )
    if args.attention_backend == "sdpa" and not args.device.startswith("cuda"):
        raise CandidateInferenceError("SDPA efficient attention requires a CUDA device")

    return CandidateInferenceConfig(
        candidates=args.candidates.resolve(),
        adapter_dir=args.adapter_dir.resolve(),
        base_model_id=args.base_model_id,
        base_model_revision=args.base_model_revision,
        compat_path=args.compat_path.resolve(),
        device=args.device,
        attention_backend=args.attention_backend,
        out_dir=args.out_dir.resolve(),
        offline=not args.allow_download,
    )


def main(argv: Sequence[str] | None = None) -> int:
    config = parse_args(argv)
    if config.out_dir.exists():
        raise CandidateInferenceError(
            f"Output directory already exists: {config.out_dir}"
        )
    summary = validate_candidates(config.candidates)
    rows, environment, load_warnings = infer_candidates(config, summary)
    write_inference_run(
        config,
        summary,
        rows,
        environment,
        load_warnings,
    )
    print(
        json.dumps(
            {
                "out_dir": str(config.out_dir),
                "schema": SCHEMA,
                "status": "complete",
                "row_count": summary.row_count,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
