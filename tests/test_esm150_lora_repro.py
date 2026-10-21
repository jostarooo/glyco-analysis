from __future__ import annotations

import copy
import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = load_script("run_esm150_lora_repro_test", "scripts/run_esm150_lora_repro.py")
checker = load_script("check_esm150_lora_repro_test", "scripts/check_esm150_lora_repro.py")


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class RowContractTests(unittest.TestCase):
    def test_author_row_order_and_non_sequon_rows_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.csv"
            write_csv(
                path,
                runner.EXPECTED_COLUMNS,
                [
                    {
                        "label": 1,
                        "id": "P1",
                        "pos": 2,
                        "sequence": "MNST",
                    },
                    {
                        "label": 0,
                        "id": "P2",
                        "pos": 1,
                        "sequence": "AAAA",
                    },
                ],
            )
            rows = runner.load_test_rows(path)

        self.assertEqual([row.row_index for row in rows], [0, 1])
        self.assertEqual([row.protein_id for row in rows], ["P1", "P2"])
        self.assertEqual([row.position for row in rows], [2, 1])
        self.assertEqual(
            [runner.residue_and_motif(row.sequence, row.position) for row in rows],
            [("N", "NST", 1), ("A", "AAA", 0)],
        )

    def test_invalid_position_fails_at_the_input_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.csv"
            write_csv(
                path,
                runner.EXPECTED_COLUMNS,
                [
                    {
                        "label": 1,
                        "id": "P1",
                        "pos": 5,
                        "sequence": "MNST",
                    }
                ],
            )
            with self.assertRaisesRegex(runner.ReproError, "outside sequence"):
                runner.load_test_rows(path)

    def test_sequence_grouping_preserves_rows_and_first_seen_order(self):
        rows = [
            runner.TestRow(0, 1, "P1", 2, "MNST"),
            runner.TestRow(1, 0, "P2", 1, "AAAA"),
            runner.TestRow(2, 1, "P3", 2, "MNST"),
        ]

        jobs = runner.group_rows_by_sequence(rows)

        self.assertEqual([job.sequence for job in jobs], ["MNST", "AAAA"])
        self.assertEqual([row.row_index for row in jobs[0].rows], [0, 2])
        self.assertEqual([row.row_index for row in jobs[1].rows], [1])


class DecisionRuleTests(unittest.TestCase):
    def test_softmax_is_stable_and_normalized(self):
        for module, function_name in (
            (runner, "softmax_two"),
            (checker, "softmax_pair"),
        ):
            with self.subTest(module=module.__name__):
                function = getattr(module, function_name)
                negative, positive = function(-800.0, 800.0)
                self.assertEqual((negative, positive), (0.0, 1.0))
                self.assertAlmostEqual(sum(function(-1.0, 1.0)), 1.0)

    def test_binary_argmax_uses_the_first_class_on_an_exact_tie(self):
        for module in (runner, checker):
            with self.subTest(module=module.__name__):
                self.assertEqual(module.binary_argmax(0.0, 0.0), 0)
                self.assertEqual(module.binary_argmax(-0.1, 0.1), 1)


class MetricTests(unittest.TestCase):
    def test_runner_metrics_use_zero_for_undefined_mcc(self):
        single_class = runner.confusion_and_metrics([1, 1], [1, 1])
        self.assertEqual(single_class["mcc"], 0.0)
        self.assertEqual(single_class["confusion"]["tp"], 2)
        self.assertEqual(single_class["confusion"]["tn"], 0)

        no_errors = runner.confusion_and_metrics([1, 1, 0, 0], [1, 1, 0, 0])
        self.assertEqual(no_errors["mcc"], 1.0)

    def test_runner_metrics_reject_bad_binary_inputs(self):
        with self.assertRaisesRegex(runner.ReproError, "different lengths"):
            runner.confusion_and_metrics([1, 0], [1])
        with self.assertRaisesRegex(runner.ReproError, "binary"):
            runner.confusion_and_metrics([1, 2], [1, 0])

    def test_checker_metrics_reject_bad_binary_inputs(self):
        self.assertEqual(checker.metrics_from_predictions([1, 1], [1, 1])["mcc"], 0.0)
        with self.assertRaisesRegex(checker.CheckError, "different lengths"):
            checker.metrics_from_predictions([1, 0], [1])
        with self.assertRaisesRegex(checker.CheckError, "at least one row"):
            checker.metrics_from_predictions([], [])
        with self.assertRaisesRegex(checker.CheckError, "binary"):
            checker.metrics_from_predictions([1, 0], [1, 2])


class AuditSampleTests(unittest.TestCase):
    def test_sample_covers_boundaries_labels_and_non_sequons(self):
        rows = []
        for index in range(20):
            sequence = "A" * (10 + index)
            rows.append(
                runner.TestRow(
                    row_index=index,
                    label=index % 2,
                    protein_id=f"P{index:02d}",
                    position=1,
                    sequence=sequence,
                )
            )

        selected = runner.select_audit_indices(rows)
        selected_rows = [rows[index] for index in selected]

        self.assertEqual(len(selected), 16)
        self.assertEqual(len(set(selected)), 16)
        self.assertIn(0, selected)
        self.assertIn(19, selected)
        self.assertEqual({row.label for row in selected_rows}, {0, 1})
        self.assertTrue(
            any(
                runner.residue_and_motif(row.sequence, row.position)[2] == 0
                for row in selected_rows
            )
        )


class ArtifactHashTests(unittest.TestCase):
    def test_artifact_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            names = ("predictions.csv", "audit_sample.csv", "metrics.json", "report.md")
            artifacts = {}
            for name in names:
                path = run_dir / name
                path.write_text(f"content for {name}\n", encoding="utf-8")
                artifacts[name] = checker.sha256_file(path)

            manifest = {"artifacts": artifacts}
            self.assertEqual(checker.verify_artifact_hashes(run_dir, manifest), 4)

            with (run_dir / "report.md").open("a", encoding="utf-8") as handle:
                handle.write("tampered\n")
            with self.assertRaisesRegex(checker.CheckError, "hash mismatch"):
                checker.verify_artifact_hashes(run_dir, manifest)


class PredictionCheckerTests(unittest.TestCase):
    def prediction_row(self) -> dict[str, object]:
        negative, positive = checker.softmax_pair(-0.5, 0.5)
        return {
            "row_index": 0,
            "label": 1,
            "protein_id": "P1",
            "position": 2,
            "sequence_sha256": checker.sha256_text("MNST"),
            "sequence_length": 4,
            "token_length": 6,
            "residue": "N",
            "motif": "NST",
            "is_sequon": 1,
            "logit_negative": -0.5,
            "logit_positive": 0.5,
            "prob_negative": repr(negative),
            "prob_positive": repr(positive),
            "predicted_label": 1,
        }

    def test_corrupted_prediction_is_detected(self):
        source = [
            {
                "label": "1",
                "id": "P1",
                "pos": "2",
                "sequence": "MNST",
            }
        ]
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            row = self.prediction_row()
            write_csv(
                run_dir / "predictions.csv",
                checker.PREDICTION_COLUMNS,
                [row],
            )
            prediction_rows, _ = checker.verify_predictions(run_dir, source)
            self.assertEqual(prediction_rows[0]["predicted_label"], "1")

            row["predicted_label"] = 0
            write_csv(
                run_dir / "predictions.csv",
                checker.PREDICTION_COLUMNS,
                [row],
            )
            with self.assertRaisesRegex(checker.CheckError, "Argmax mismatch"):
                checker.verify_predictions(run_dir, source)


class MetricArtifactTests(unittest.TestCase):
    def test_metric_and_manifest_corruption_are_detected(self):
        prediction_rows = [
            {
                "label": "1",
                "predicted_label": "1",
                "is_sequon": "1",
                "protein_id": "P1",
                "sequence_length": "100",
            },
            {
                "label": "0",
                "predicted_label": "0",
                "is_sequon": "0",
                "protein_id": "P2",
                "sequence_length": "200",
            },
        ]
        metrics = checker.metrics_from_predictions([1, 0], [1, 0])
        metrics.update(
            {
                "decision_rule": "argmax(logits)",
                "non_sequon_rows": 1,
                "protein_count": 2,
                "longest_sequence_length": 200,
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            metrics_path = run_dir / "metrics.json"
            metrics_path.write_text(
                json.dumps(metrics, ensure_ascii=False),
                encoding="utf-8",
            )
            manifest = {"metrics": copy.deepcopy(metrics)}
            self.assertGreater(
                checker.verify_metrics(run_dir, manifest, prediction_rows),
                0,
            )

            corrupted_metrics = dict(metrics)
            corrupted_metrics["row_count"] = 3
            metrics_path.write_text(
                json.dumps(corrupted_metrics, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(checker.CheckError, "metrics.json"):
                checker.verify_metrics(run_dir, manifest, prediction_rows)

            metrics_path.write_text(
                json.dumps(metrics, ensure_ascii=False),
                encoding="utf-8",
            )
            manifest["metrics"]["row_count"] = 3
            with self.assertRaisesRegex(checker.CheckError, "Manifest metrics"):
                checker.verify_metrics(run_dir, manifest, prediction_rows)


if __name__ == "__main__":
    unittest.main()
