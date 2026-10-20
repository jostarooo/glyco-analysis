from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_esm35_linear_probe.py"
SPEC = importlib.util.spec_from_file_location("run_esm35_linear_probe", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def candidate(position: int, sequence: str, accession: str = "P00001") -> object:
    return probe.Candidate(
        row_id=f"{accession}:{position}",
        accession=accession,
        position=position,
        label=True,
        seq_len=len(sequence),
        sequence=sequence,
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
                "true_negative": 1,
                "false_positive": 1,
                "false_negative": 1,
                "true_positive": 1,
            },
        )
        self.assertEqual(result["metrics"]["mcc"], 0.0)
        self.assertEqual(result["metrics"]["sensitivity"], 0.5)
        self.assertEqual(result["metrics"]["specificity"], 0.5)
        self.assertEqual(result["metrics"]["precision"], 0.5)
        self.assertEqual(result["metrics"]["accuracy"], 0.5)
        self.assertEqual(result["metrics"]["roc_auc"], 0.75)

    def test_metrics_block_never_contains_external_paper_number(self):
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
                    "sensitivity": [1.0, 1.0],
                    "specificity": [1.0, 1.0],
                },
            },
        }
        rendered = probe.metrics_markdown(metrics, 1)
        self.assertNotIn("0.781", rendered)


if __name__ == "__main__":
    unittest.main()
