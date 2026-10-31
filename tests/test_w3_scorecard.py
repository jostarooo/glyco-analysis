from __future__ import annotations

import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import statistics
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_w3_scorecard.py"
SPEC = importlib.util.spec_from_file_location("build_w3_scorecard", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
scorecard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scorecard
SPEC.loader.exec_module(scorecard)


class ScorecardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in scorecard.SOURCE_PATHS.values():
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def path(self, relative: str) -> Path:
        return self.root / relative

    def load_json(self, relative: str) -> dict[str, object]:
        return json.loads(self.path(relative).read_text(encoding="utf-8-sig"))

    def write_json(self, relative: str, data: dict[str, object]) -> None:
        self.path(relative).write_text(
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def mutate_json(self, relative: str, mutator) -> None:
        data = self.load_json(relative)
        mutator(data)
        self.write_json(relative, data)

    def assert_invalid(self, pattern: str) -> None:
        with self.assertRaisesRegex(scorecard.ScorecardValidationError, pattern):
            scorecard.generate_scorecard(self.root)

    def test_real_generation_has_eight_rows_and_50_task_split(self) -> None:
        card = scorecard.generate_scorecard(self.root)
        self.assertEqual(8, len(card.metrics))
        self.assertEqual(
            [
                "f1.esm150_lora.mcc",
                "f2.immunogenicity.auprc",
                "f2.glycosylation.macro_f1",
                "f3.qwen3_4b.exact_sequence",
                "f3.qwen3_4b.all_expected_called",
                "f3.qwen3_4b.any_expected_called",
                "f3.qwen3_4b.tasks_with_final_answer",
                "f3.qwen3_4b.tool_call_successes",
            ],
            [row.metric_id for row in card.metrics],
        )
        self.assertEqual(
            {"current_tools_direct": 43, "needs_replacement_tool": 5, "service_failure": 2},
            {category.value: count for category, count in card.feasibility.counts},
        )
        self.assertEqual(50, card.feasibility.total_tasks)
        self.assertEqual(8, len(card.sources.pins))
        for pin in card.sources.pins:
            self.assertEqual(
                hashlib.sha256((self.root / pin.path).read_bytes()).hexdigest(),
                pin.sha256,
            )
            self.assertGreater(pin.byte_count, 0)
        for name in scorecard.OUTPUT_NAMES:
            self.assertTrue((self.root / "reports" / "w3_day2" / name).is_file())

    def test_f1_confusion_sum_must_match_row_count(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            data["confusion"]["tp"] += 1

        self.mutate_json(scorecard.SOURCE_PATHS[scorecard.SourceRole.F1], mutate)
        self.assert_invalid("confusion sum must equal snapshot 2554")

    def test_f1_mcc_must_be_recomputed_from_confusion_matrix(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            data["mcc"] += 0.001

        self.mutate_json(scorecard.SOURCE_PATHS[scorecard.SourceRole.F1], mutate)
        self.assert_invalid("mcc: recomputed")

    def test_f1_delta_direction_is_checked(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            data["mcc_delta_from_reference"] *= -1

        self.mutate_json(scorecard.SOURCE_PATHS[scorecard.SourceRole.F1], mutate)
        self.assert_invalid("must equal mcc - reference_mcc")

    def test_f2_free_class_count_is_fixed(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            data["tasks"]["glycosylation"]["label_counts"]["2"] = 77

        self.mutate_json(scorecard.SOURCE_PATHS[scorecard.SourceRole.F2], mutate)
        self.assert_invalid("glycosylation.label_counts")

    def test_f2_single_seed_change_cannot_keep_stale_aggregate(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            data["tasks"]["immunogenicity"]["per_seed"][0]["test"]["auprc"] += 0.001

        self.mutate_json(scorecard.SOURCE_PATHS[scorecard.SourceRole.F2], mutate)
        self.assert_invalid("does not match three seeds")

    def test_f2_requires_all_three_seeds(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            data["tasks"]["immunogenicity"]["per_seed"].pop()

        self.mutate_json(scorecard.SOURCE_PATHS[scorecard.SourceRole.F2], mutate)
        self.assert_invalid("expected 3 seeds")

    def test_f2_std_is_recomputed_with_statistics_stdev(self) -> None:
        source = self.load_json(scorecard.SOURCE_PATHS[scorecard.SourceRole.F2])
        task = source["tasks"]["glycosylation"]
        seeds = [record["test"]["macro_f1"] for record in task["per_seed"]]
        expected = statistics.stdev(seeds)
        self.assertEqual(expected, task["aggregate"]["test_macro_f1"]["std"])
        self.assertLess(abs(expected - 0.0038891301525018625), 1e-15)

    def test_f3_counts_cannot_exceed_task_total(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            data["exact_sequence"] = 51

        self.mutate_json(scorecard.SOURCE_PATHS[scorecard.SourceRole.F3], mutate)
        self.assert_invalid("sequence counts are not monotonic")

    def test_f3_rows_never_emit_numeric_delta(self) -> None:
        scorecard.generate_scorecard(self.root)
        out = self.root / "reports" / "w3_day2"
        payload = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
        f3_rows = [row for row in payload["metrics"] if row["track"] == "F3"]
        self.assertEqual(5, len(f3_rows))
        for row in f3_rows:
            self.assertEqual("not_comparable", row["comparison"]["kind"])
            self.assertNotIn("delta_local_minus_reference", row["comparison"])
            self.assertNotIn("delta", json.dumps(row["local"], ensure_ascii=False))
        with (out / "scorecard.csv").open(encoding="utf-8", newline="") as stream:
            csv_rows = [row for row in csv.DictReader(stream) if row["track"] == "F3"]
        self.assertTrue(all(not row["delta_local_minus_reference"] for row in csv_rows))
        markdown = (out / "scorecard.md").read_text(encoding="utf-8")
        self.assertEqual(5, markdown.count("| not_comparable |"))

    def test_task_id_swap_across_categories_is_rejected(self) -> None:
        relative = scorecard.SOURCE_PATHS[scorecard.SourceRole.CSV]
        rows = list(csv.DictReader(io.StringIO(self.path(relative).read_text(encoding="utf-8-sig"))))
        direct = next(row for row in rows if row["revised_category"] == "current_tools_direct")
        replacement = next(row for row in rows if row["revised_category"] == "needs_replacement_tool")
        direct["task_id"], replacement["task_id"] = replacement["task_id"], direct["task_id"]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        self.path(relative).write_text(buffer.getvalue(), encoding="utf-8")
        self.assert_invalid("task ids differ from 5,21,28,48,50")

    def test_w3_historical_counts_must_equal_w2(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            data["w2_task_reclassification"]["original_counts"]["current_tools_direct"] = 19
            data["w2_task_reclassification"]["original_counts"]["needs_replacement_tool"] = 26

        self.mutate_json(scorecard.SOURCE_PATHS[scorecard.SourceRole.W3], mutate)
        self.assert_invalid("historical counts differ from W2 summary")

    def test_reference_catalog_must_match_markdown_anchor(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            data["references"][1]["value"] = 0.781

        self.mutate_json(scorecard.SOURCE_PATHS[scorecard.SourceRole.CATALOG], mutate)
        self.assert_invalid("catalog differs from Markdown anchor")

    def test_missing_source_is_a_structural_error(self) -> None:
        self.path(scorecard.SOURCE_PATHS[scorecard.SourceRole.F3]).unlink()
        self.assert_invalid("unreadable source")

    def test_bad_json_is_a_structural_error(self) -> None:
        self.path(scorecard.SOURCE_PATHS[scorecard.SourceRole.F1]).write_text("{", encoding="utf-8")
        self.assert_invalid("invalid JSON")

    def test_bad_csv_is_a_structural_error(self) -> None:
        self.path(scorecard.SOURCE_PATHS[scorecard.SourceRole.CSV]).write_text(
            'task_id,original_category,revised_category,blocking_tools,decision_reason,evidence\n"unterminated',
            encoding="utf-8",
        )
        self.assert_invalid("invalid CSV")

    def test_cli_exit_codes_distinguish_structure_and_stale_output(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(0, scorecard.main(["--repo-root", str(self.root)]))
            self.assertEqual(0, scorecard.main(["--repo-root", str(self.root), "--check"]))
        output = self.root / "reports" / "w3_day2" / "scorecard.json"
        output.write_bytes(output.read_bytes() + b"\n")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, scorecard.main(["--repo-root", str(self.root), "--check"]))
        self.path(scorecard.SOURCE_PATHS[scorecard.SourceRole.F1]).unlink()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, scorecard.main(["--repo-root", str(self.root)]))

    def test_check_is_read_only(self) -> None:
        scorecard.generate_scorecard(self.root)
        out = self.root / "reports" / "w3_day2"
        before = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in scorecard.OUTPUT_NAMES}
        scorecard.check_scorecard(self.root)
        after = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in scorecard.OUTPUT_NAMES}
        self.assertEqual(before, after)

    def test_two_generations_are_byte_identical_and_preserve_mtime(self) -> None:
        scorecard.generate_scorecard(self.root)
        out = self.root / "reports" / "w3_day2"
        first = {name: (out / name).read_bytes() for name in scorecard.OUTPUT_NAMES}
        mtimes = {name: (out / name).stat().st_mtime_ns for name in scorecard.OUTPUT_NAMES}
        time.sleep(0.02)
        scorecard.generate_scorecard(self.root)
        second = {name: (out / name).read_bytes() for name in scorecard.OUTPUT_NAMES}
        self.assertEqual(first, second)
        self.assertEqual(mtimes, {name: (out / name).stat().st_mtime_ns for name in scorecard.OUTPUT_NAMES})

    def test_json_csv_and_markdown_agree_on_ids_values_and_status(self) -> None:
        scorecard.generate_scorecard(self.root)
        out = self.root / "reports" / "w3_day2"
        payload = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
        with (out / "scorecard.csv").open(encoding="utf-8", newline="") as stream:
            csv_rows = {row["metric_id"]: row for row in csv.DictReader(stream)}
        markdown = (out / "scorecard.md").read_text(encoding="utf-8")
        self.assertEqual(8, len(payload["metrics"]))
        self.assertEqual(8, len(csv_rows))
        for metric in payload["metrics"]:
            metric_id = metric["metric_id"]
            self.assertIn(metric_id, csv_rows)
            self.assertIn(f"`{metric_id}`", markdown)
            csv_row = csv_rows[metric_id]
            self.assertEqual(str(metric["local"]["value"]), csv_row["local_value"])
            self.assertEqual(metric["comparison"]["kind"], csv_row["comparison_kind"])
            self.assertEqual(metric["local"]["source"], csv_row["source_role"])
            self.assertTrue(csv_row["source_sha256"])
            self.assertIn(f"| {metric['comparison']['kind']} |", markdown)
            if metric["local"]["denominator"] is not None:
                self.assertEqual(str(metric["local"]["denominator"]), csv_row["local_denominator"])


if __name__ == "__main__":
    unittest.main()
