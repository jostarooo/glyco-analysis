from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_esm35_linear_probe.py"
SPEC = importlib.util.spec_from_file_location("run_esm35_linear_probe", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def candidate(
    position: int,
    sequence: str,
    accession: str = "P00001",
    *,
    label: bool = True,
    evidence: tuple[str, ...] = ("ECO:0000269",),
) -> object:
    evidence_class = probe.classify_evidence(
        label,
        evidence,
        f"{accession}:{position}",
    )
    return probe.Candidate(
        row_id=f"{accession}:{position}",
        accession=accession,
        position=position,
        label=label,
        seq_len=len(sequence),
        sequence=sequence,
        evidence=evidence,
        evidence_class=evidence_class,
    )


class WindowTests(unittest.TestCase):
    def test_short_sequence_uses_full_window(self):
        sequence = "M" * 20 + "NLS" + "A" * 20
        window = probe.build_window(candidate(21, sequence))
        self.assertEqual((window.window_start, window.window_end), (1, len(sequence)))
        self.assertEqual(window.window, sequence)
        self.assertEqual(window.target_offset, 20)
        self.assertEqual(window.window[window.target_offset], "N")

    def test_long_sequence_centres_target_without_truncation(self):
        residues = list("A" * 4563)
        residues[1999] = "N"
        window = probe.build_window(candidate(2000, "".join(residues)))
        self.assertEqual(len(window.window), 1023)
        self.assertEqual((window.window_start, window.window_end), (1489, 2511))
        self.assertEqual(window.target_offset, 511)
        self.assertEqual(window.window[window.target_offset], "N")

    def test_terminal_target_remains_inside_window(self):
        residues = list("A" * 4563)
        residues[-1] = "N"
        window = probe.build_window(candidate(4563, "".join(residues)))
        self.assertEqual((window.window_start, window.window_end), (3541, 4563))
        self.assertEqual(window.target_offset, 1022)
        self.assertEqual(window.window[window.target_offset], "N")

    def test_identical_windows_share_one_embedding_job(self):
        sequence = "M" * 20 + "NLS" + "A" * 20
        first = probe.build_window(candidate(21, sequence))
        second = probe.build_window(candidate(21, sequence))
        jobs = probe.build_embedding_jobs([first, second])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(jobs[0].targets), 2)


class SplitTests(unittest.TestCase):
    def test_leave_one_protein_out_is_disjoint_and_complete(self):
        sequence = "M" * 20 + "NLS" + "A" * 20
        candidates = [
            candidate(21, sequence, "P00001"),
            candidate(21, sequence, "P00002"),
            candidate(21, sequence, "P00002"),
            candidate(21, sequence, "P00003"),
        ]
        folds = probe.leave_one_protein_out(candidates)
        self.assertEqual([fold.held_out for fold in folds], ["P00001", "P00002", "P00003"])
        tested = []
        for fold in folds:
            self.assertTrue(fold.train_indices)
            self.assertTrue(fold.test_indices)
            self.assertFalse(
                any(
                    candidates[index].accession == fold.held_out
                    for index in fold.train_indices
                )
            )
            tested.extend(fold.test_indices)
        self.assertEqual(sorted(tested), list(range(len(candidates))))


class MetricTests(unittest.TestCase):
    def test_confusion_and_auc_arithmetic(self):
        labels = np.array([1, 1, 0, 0], dtype=bool)
        predictions = np.array([1, 0, 0, 1], dtype=bool)
        probabilities = np.array([0.9, 0.4, 0.2, 0.6], dtype=float)
        result = probe.point_metrics(labels, predictions, probabilities)
        self.assertEqual(
            result["confusion"],
            {
                "experimental_positive": {
                    "predicted_positive": 1,
                    "predicted_control": 1,
                },
                "unannotated_control": {
                    "predicted_positive": 1,
                    "predicted_control": 1,
                },
            },
        )
        self.assertEqual(result["metrics"]["mcc"], 0.0)
        self.assertEqual(result["metrics"]["positive_recall"], 0.5)
        self.assertEqual(result["metrics"]["control_specificity"], 0.5)
        self.assertEqual(result["metrics"]["positive_precision"], 0.5)
        self.assertEqual(result["metrics"]["weak_label_accuracy"], 0.5)
        self.assertEqual(result["metrics"]["roc_auc"], 0.75)

    def test_metrics_block_uses_weak_label_names_and_values(self):
        labels = np.array([1, 0], dtype=bool)
        predictions = np.array([1, 0], dtype=bool)
        probabilities = np.array([0.9, 0.1], dtype=float)
        point = probe.point_metrics(labels, predictions, probabilities)
        metrics = {
            "metrics": point["metrics"],
            "confusion": point["confusion"],
            "bootstrap": {
                "replicates": 10,
                "valid_replicates": 10,
                "undefined_replicates": 0,
                "ci95": {
                    "mcc": [1.0, 1.0],
                    "positive_recall": [1.0, 1.0],
                    "control_specificity": [1.0, 1.0],
                },
            },
        }
        rendered = probe.metrics_markdown(metrics, 1)
        self.assertIn("未标注对照", rendered)
        self.assertIn("| MCC | 1.000000 |", rendered)
        self.assertNotIn("灵敏度", rendered)


class EvidenceTests(unittest.TestCase):
    def test_evidence_parser_sorts_values_and_rejects_unknown_codes(self):
        self.assertEqual(
            probe.parse_evidence("ECO:0007744;ECO:0000269;ECO:0000269", "P1:1"),
            ("ECO:0000269", "ECO:0007744"),
        )
        with self.assertRaises(probe.InputError):
            probe.parse_evidence("GO:0000001", "P1:1")

    def test_probe_selection_excludes_only_inferred_positives(self):
        sequence = "M" * 20 + "NLS" + "A" * 20
        experimental = candidate(21, sequence, "P00001")
        inferred = candidate(
            21,
            sequence,
            "P00002",
            evidence=("ECO:0000255",),
        )
        control = candidate(
            21,
            sequence,
            "P00003",
            label=False,
            evidence=(),
        )
        selected, inferred_accessions = probe.select_probe_candidates(
            [experimental, inferred, control]
        )
        self.assertEqual(
            [item.accession for item in selected],
            ["P00001", "P00003"],
        )
        self.assertEqual(inferred_accessions, ("P00002",))

    def test_classifier_rejects_positive_rows_without_evidence(self):
        with self.assertRaises(probe.InputError):
            probe.classify_evidence(True, (), "P00001:21")


class InputBoundaryTests(unittest.TestCase):
    def test_unsafe_accession_is_rejected_before_cache_lookup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidates = root / "candidates.csv"
            with candidates.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(probe.CANDIDATE_COLUMNS)
                writer.writerow(
                    (
                        "../escape",
                        "protein",
                        10,
                        1,
                        "N",
                        "NLS",
                        "1",
                        "1",
                        "N-linked",
                        0,
                        "ECO:0000269",
                        "2026_03",
                        "2026-10-20",
                    )
                )
            with self.assertRaisesRegex(probe.InputError, "unsafe accession"):
                probe.read_candidates(candidates, root)

    def test_malformed_cache_record_raises_input_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidates = root / "candidates.csv"
            with candidates.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(probe.CANDIDATE_COLUMNS)
                writer.writerow(
                    (
                        "P00001",
                        "protein",
                        10,
                        1,
                        "N",
                        "NLS",
                        "1",
                        "1",
                        "N-linked",
                        0,
                        "ECO:0000269",
                        "2026_03",
                        "2026-10-20",
                    )
                )
            (root / "P00001.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(probe.InputError, "has no sequence"):
                probe.read_candidates(candidates, root)

    def test_invalidation_removes_only_the_completion_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            out_dir = Path(temporary)
            manifest = out_dir / "manifest.json"
            artifact = out_dir / "metrics.json"
            manifest.write_text(json.dumps({"status": "complete"}), encoding="utf-8")
            artifact.write_text("{}", encoding="utf-8")
            probe.invalidate_run(out_dir)
            self.assertFalse(manifest.exists())
            self.assertTrue(artifact.exists())


if __name__ == "__main__":
    unittest.main()
