from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = load_script(
    "run_esm150_candidate_inference_test",
    "scripts/run_esm150_candidate_inference.py",
)


def candidate_sequence(index: int) -> str:
    return "M" + "NST" * 8 + "G" + "A" * index


def make_candidate_rows() -> list[dict[str, object]]:
    accessions = [f"P{index:05d}" for index in range(29)]
    occurrences = {accession: 0 for accession in accessions}
    rows: list[dict[str, object]] = []
    for index in range(201):
        accession = accessions[index % len(accessions)]
        occurrence = occurrences[accession]
        occurrences[accession] += 1
        rows.append(
            {
                "label": 1 if index < 153 else 0,
                "id": accession,
                "pos": 2 + 3 * occurrence,
                "sequence": candidate_sequence(int(accession[1:])),
            }
        )
    return rows


def write_candidate_fixture(
    path: Path,
    rows: list[dict[str, object]],
    header: tuple[str, ...] = runner.EXPECTED_CANDIDATE_COLUMNS,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=header,
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def validate_fixture(path: Path):
    with mock.patch.object(
        runner,
        "EXPECTED_CANDIDATES_SHA256",
        runner.helpers.sha256_file(path),
    ):
        return runner.validate_candidates(path)


def make_predictions(source_rows: list[dict[str, object]]):
    predictions = []
    for index, source in enumerate(source_rows):
        sequence = str(source["sequence"])
        position = int(source["pos"])
        residue, motif, is_sequon = runner.helpers.residue_and_motif(
            sequence,
            position,
        )
        logit_negative = -0.75 + (index % 5) * 0.05
        logit_positive = 0.60 - (index % 7) * 0.04
        prob_negative, prob_positive = runner.helpers.softmax_two(
            logit_negative,
            logit_positive,
        )
        predictions.append(
            runner.CandidateInferenceRow(
                row_index=index,
                accession=str(source["id"]),
                position=position,
                label=int(source["label"]),
                sequence_sha256=runner.helpers.sha256_text(sequence),
                sequence_length=len(sequence),
                token_length=len(sequence) + 2,
                residue=residue,
                motif=motif,
                is_sequon=is_sequon,
                logit_negative=logit_negative,
                logit_positive=logit_positive,
                prob_negative=prob_negative,
                prob_positive=prob_positive,
                predicted_label=runner.helpers.binary_argmax(
                    logit_negative,
                    logit_positive,
                ),
            )
        )
    return predictions


def make_config(candidates: Path, out_dir: Path):
    return runner.CandidateInferenceConfig(
        candidates=candidates,
        adapter_dir=out_dir.parent / "adapter",
        base_model_id=runner.EXPECTED_BASE_MODEL_ID,
        base_model_revision=runner.EXPECTED_BASE_MODEL_REVISION,
        compat_path=out_dir.parent / "compat",
        device="cuda",
        attention_backend="sdpa",
        out_dir=out_dir,
        offline=True,
    )


class CandidateInputTests(unittest.TestCase):
    def test_valid_fixture_records_all_provenance_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidates.csv"
            write_candidate_fixture(path, make_candidate_rows())
            summary = validate_fixture(path)

        self.assertEqual(summary.row_count, 201)
        self.assertEqual(summary.protein_count, 29)
        self.assertEqual(summary.unique_sequence_count, 29)
        self.assertEqual(summary.label_counts, {"0": 48, "1": 153})
        self.assertEqual(len(summary.model_inputs), 29)
        self.assertEqual(len(summary.keys_sha256), 64)

    def test_rejects_wrong_row_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidates.csv"
            write_candidate_fixture(path, make_candidate_rows()[:-1])
            with self.assertRaisesRegex(
                runner.CandidateInferenceError,
                "200 rows; expected 201",
            ):
                validate_fixture(path)

    def test_rejects_wrong_header(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidates.csv"
            rows = make_candidate_rows()[:1]
            write_candidate_fixture(
                path,
                rows,
                ("label", "id", "pos", "sequence", "extra"),
            )
            with self.assertRaisesRegex(
                runner.CandidateInferenceError,
                "header",
            ):
                validate_fixture(path)

    def test_rejects_duplicate_candidate_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidates.csv"
            rows = make_candidate_rows()
            rows[-1]["id"] = rows[0]["id"]
            rows[-1]["pos"] = rows[0]["pos"]
            write_candidate_fixture(path, rows)
            with self.assertRaisesRegex(
                runner.CandidateInferenceError,
                "Duplicate candidate key",
            ):
                validate_fixture(path)

    def test_rejects_inconsistent_accession_sequences(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidates.csv"
            rows = make_candidate_rows()
            rows[1]["id"] = rows[0]["id"]
            rows[1]["pos"] = 23
            rows[1]["sequence"] = candidate_sequence(28)
            write_candidate_fixture(path, rows)
            with self.assertRaisesRegex(
                runner.CandidateInferenceError,
                "multiple sequences",
            ):
                validate_fixture(path)


class PredictionInvariantTests(unittest.TestCase):
    def base_row(self):
        prob_negative, prob_positive = runner.helpers.softmax_two(0.0, 0.0)
        return runner.CandidateInferenceRow(
            row_index=0,
            accession="P00000",
            position=2,
            label=1,
            sequence_sha256=runner.helpers.sha256_text("MNST"),
            sequence_length=4,
            token_length=6,
            residue="N",
            motif="NST",
            is_sequon=1,
            logit_negative=0.0,
            logit_positive=0.0,
            prob_negative=prob_negative,
            prob_positive=prob_positive,
            predicted_label=0,
        )

    def test_exact_argmax_tie_selects_negative_class(self):
        row = self.base_row()
        self.assertEqual(runner.helpers.binary_argmax(0.0, 0.0), 0)
        runner._validate_prediction_values(row)

    def test_probability_sum_and_argmax_invariants_are_enforced(self):
        row = self.base_row()
        with self.assertRaisesRegex(
            runner.CandidateInferenceError,
            "do not sum to 1",
        ):
            runner._validate_prediction_values(
                replace(row, prob_negative=0.6, prob_positive=0.6)
            )
        with self.assertRaisesRegex(
            runner.CandidateInferenceError,
            "Predicted label does not match argmax",
        ):
            runner._validate_prediction_values(
                replace(row, predicted_label=1)
            )


class OutputArtifactTests(unittest.TestCase):
    def test_write_is_manifest_last_and_records_exact_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            candidates = work / "candidates.csv"
            out_dir = work / "run"
            source_rows = make_candidate_rows()
            write_candidate_fixture(candidates, source_rows)
            with mock.patch.object(
                runner,
                "EXPECTED_CANDIDATES_SHA256",
                runner.helpers.sha256_file(candidates),
            ):
                summary = runner.validate_candidates(candidates)
                predictions = make_predictions(source_rows)
                config = make_config(candidates, out_dir)
                environment = {
                    "versions": {
                        "python": "3.12.14",
                        "torch": "2.9.1+cu128",
                        "transformers": "4.50.3",
                        "peft": "0.14.0",
                        "tokenizers": "0.21.1",
                        "huggingface_hub": "0.26.3",
                    },
                    "device": {
                        "requested": "cuda",
                        "actual": "cuda:0",
                        "name": "Fake GPU",
                        "sdpa_module_count": 30,
                        "sdpa_eligible_module_count": 30,
                        "sdpa_expected_module_count": 30,
                    },
                }
                adapter = {
                    "path": str(work / "adapter"),
                    "model_sha256": runner.EXPECTED_ADAPTER_SHA256,
                    "config_sha256": "B" * 64,
                    "tensor_count": 376,
                }
                base_model = {
                    "id": runner.EXPECTED_BASE_MODEL_ID,
                    "revision": runner.EXPECTED_BASE_MODEL_REVISION,
                    "snapshot": str(work / "snapshot"),
                    "weights_file": "model.safetensors",
                    "weights_sha256": runner.EXPECTED_BASE_WEIGHTS_SHA256,
                }
                events: list[str] = []
                original_write_csv = runner._write_csv
                original_write_text = runner._write_text

                def record_csv(path, columns, rows):
                    events.append(path.name)
                    return original_write_csv(path, columns, rows)

                def record_text(path, text):
                    events.append(path.name)
                    return original_write_text(path, text)

                with (
                    mock.patch.object(
                        runner,
                        "_adapter_metadata",
                        return_value=adapter,
                    ),
                    mock.patch.object(
                        runner,
                        "_base_model_metadata",
                        return_value=base_model,
                    ),
                    mock.patch.object(
                        runner,
                        "_source_state",
                        return_value=("A" * 40, False),
                    ),
                    mock.patch.object(
                        runner,
                        "_write_csv",
                        side_effect=record_csv,
                    ),
                    mock.patch.object(
                        runner,
                        "_write_text",
                        side_effect=record_text,
                    ),
                ):
                    runner.write_inference_run(
                        config,
                        summary,
                        predictions,
                        environment,
                        [],
                    )

                self.assertEqual(
                    events,
                    ["predictions.csv", "report.md", "manifest.json"],
                )
                with (out_dir / "predictions.csv").open(
                    "r",
                    encoding="utf-8",
                    newline="",
                ) as handle:
                    reader = csv.DictReader(handle)
                    self.assertEqual(
                        tuple(reader.fieldnames or ()),
                        runner.PREDICTION_COLUMNS,
                    )
                    written_rows = list(reader)
                self.assertEqual(len(written_rows), 201)
                self.assertEqual(
                    [int(row["row_index"]) for row in written_rows],
                    list(range(201)),
                )

                manifest_text = (out_dir / "manifest.json").read_text(
                    encoding="utf-8"
                )
                manifest = json.loads(manifest_text)
                self.assertEqual(
                    manifest["schema"],
                    "glyco.w1-esm150-candidates/v1",
                )
                self.assertEqual(manifest["status"], "complete")
                self.assertEqual(manifest["source"]["git_commit"], "A" * 40)
                self.assertFalse(manifest["source"]["git_dirty"])
                self.assertEqual(
                    manifest["inputs"]["candidates_lora"]["row_count"],
                    201,
                )
                self.assertEqual(
                    manifest["inputs"]["candidates_lora"]["protein_count"],
                    29,
                )
                self.assertEqual(
                    manifest["inputs"]["candidates_lora"]["unique_sequence_count"],
                    29,
                )
                self.assertEqual(
                    manifest["inputs"]["candidates_lora"]["label_counts"],
                    {"0": 48, "1": 153},
                )
                self.assertEqual(
                    manifest["inputs"]["adapter"]["tensor_count"],
                    376,
                )
                self.assertEqual(
                    manifest["inputs"]["base_model"]["revision"],
                    runner.EXPECTED_BASE_MODEL_REVISION,
                )
                self.assertEqual(manifest["device"]["sdpa_module_count"], 30)
                self.assertEqual(
                    manifest["inference"]["encoder_forward_count"],
                    29,
                )
                self.assertFalse(manifest["inference"]["truncation"])
                self.assertFalse(manifest["inference"]["windowing"])
                self.assertNotIn("created_at", manifest_text)
                self.assertNotIn("elapsed", manifest_text.lower())
                self.assertEqual(
                    set(manifest["artifacts"]),
                    {"predictions.csv", "report.md"},
                )
                for name, artifact in manifest["artifacts"].items():
                    path = out_dir / name
                    self.assertEqual(
                        artifact["sha256"],
                        runner.helpers.sha256_file(path),
                    )
                    self.assertEqual(artifact["bytes"], path.stat().st_size)

                report = (out_dir / "report.md").read_text(encoding="utf-8")
                self.assertIn("只用于追溯", report)
                self.assertNotIn("MCC", report)
                self.assertNotIn("ROC AUC", report)
                self.assertFalse(
                    any(
                        path.name.startswith(".run.tmp-")
                        for path in work.iterdir()
                    )
                )

                with self.assertRaisesRegex(
                    runner.CandidateInferenceError,
                    "already exists",
                ):
                    runner.write_inference_run(
                        config,
                        summary,
                        predictions,
                        environment,
                        [],
                    )


class HashAndHelperTests(unittest.TestCase):
    def test_dynamic_helper_set_and_sha256_behavior(self):
        required_helpers = (
            "RunConfig",
            "load_test_rows",
            "group_rows_by_sequence",
            "residue_and_motif",
            "softmax_two",
            "binary_argmax",
            "resolve_model_snapshot",
            "adapter_tensor_count",
            "load_model",
            "sha256_file",
            "sha256_text",
        )
        for name in required_helpers:
            with self.subTest(name=name):
                self.assertTrue(hasattr(runner.helpers, name))

        self.assertEqual(
            runner.helpers.sha256_text("abc"),
            hashlib.sha256(b"abc").hexdigest().upper(),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "payload.txt"
            path.write_bytes(b"payload\n")
            self.assertEqual(
                runner.helpers.sha256_file(path),
                hashlib.sha256(b"payload\n").hexdigest().upper(),
            )

    def test_artifact_hash_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            out_dir = Path(temporary)
            path = out_dir / "predictions.csv"
            path.write_text("original\n", encoding="utf-8")
            artifacts = runner._artifact_records(out_dir, ("predictions.csv",))
            self.assertEqual(runner.verify_artifact_records(out_dir, artifacts), 1)

            path.write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(
                runner.CandidateInferenceError,
                "[Hh]ash mismatch",
            ):
                runner.verify_artifact_records(out_dir, artifacts)


if __name__ == "__main__":
    unittest.main()
