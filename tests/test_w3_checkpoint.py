from __future__ import annotations

import contextlib
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
SCRIPT = ROOT / "scripts" / "build_w3_checkpoint.py"
SPEC = importlib.util.spec_from_file_location("build_w3_checkpoint", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checkpoint = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checkpoint
SPEC.loader.exec_module(checkpoint)


class CheckpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in checkpoint.SOURCE_PATHS.values():
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
        with self.assertRaisesRegex(checkpoint.CheckpointValidationError, pattern):
            checkpoint.generate_checkpoint(self.root)

    def test_real_generation_has_all_required_sections(self) -> None:
        result = checkpoint.generate_checkpoint(self.root)
        self.assertEqual(2, len(result.f2))
        self.assertEqual(3, len(result.f3.models))
        self.assertEqual(50, result.f3.task_count)
        self.assertEqual(70, result.f3.tool_count)
        self.assertEqual(6, result.system.candidate_count)
        self.assertTrue(result.system.all_labels_match)
        self.assertEqual(0.0, result.system.max_probability_delta)
        self.assertGreater(result.validation.tests_run, 0)
        self.assertEqual(result.validation.tests_run - result.validation.skipped, result.validation.passed)

        payload = json.loads((self.root / "reports" / "w3_day5" / "checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual("PASS", payload["status"])
        self.assertEqual("w3-day5-checkpoint-v1", payload["schema_version"])
        self.assertFalse(payload["f3"]["upstream_gpt4o_equivalent"])
        self.assertEqual("workbuddy-ai/kimi-k3", payload["f3"]["judge_model"])
        self.assertNotIn("combined_accuracy", json.dumps(payload, ensure_ascii=False))
        self.assertEqual("GlycanML Table 3", payload["policy"]["f2_reference"])

    def test_f1_mcc_must_match_confusion_matrix(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            data["mcc"] += 0.001
            data["mcc_delta_from_reference"] = data["mcc"] - data["reference_mcc"]

        self.mutate_json(checkpoint.SOURCE_PATHS[checkpoint.SourceRole.F1_METRICS], mutate)
        self.assert_invalid("does not match confusion matrix")

    def test_sources_are_hashed_and_sorted(self) -> None:
        checkpoint.generate_checkpoint(self.root)
        payload = json.loads((self.root / "reports" / "w3_day5" / "checkpoint.json").read_text(encoding="utf-8"))
        sources = payload["sources"]
        self.assertEqual(len(checkpoint.SOURCE_PATHS), len(sources))
        self.assertEqual([role.value for role in checkpoint.SOURCE_PATHS], [item["role"] for item in sources])
        for source in sources:
            raw = (self.root / source["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source["sha256"])
            self.assertEqual(len(raw), source["byte_count"])

    def test_f2_statistics_are_recomputed_from_seeds(self) -> None:
        source = self.load_json(checkpoint.SOURCE_PATHS[checkpoint.SourceRole.F2_RECOMPUTE])
        for task_name, metric in (("immunogenicity", "auprc"), ("glycosylation", "macro_f1")):
            task = source["tasks"][task_name]
            values = [record["test"][metric] for record in task["per_seed"]]
            self.assertAlmostEqual(statistics.fmean(values), task["aggregate"][f"test_{metric}"]["mean"], places=15)
            self.assertAlmostEqual(statistics.stdev(values), task["aggregate"][f"test_{metric}"]["std"], places=15)

    def test_f3_does_not_gain_a_numeric_delta(self) -> None:
        checkpoint.generate_checkpoint(self.root)
        payload = json.loads((self.root / "reports" / "w3_day5" / "checkpoint.json").read_text(encoding="utf-8"))
        self.assertNotIn("combined_accuracy", payload["f3"])
        for model in payload["f3"]["models"]:
            self.assertIn("trajectory", model)
            self.assertIn("answer_grade", model)
            self.assertNotIn("delta", model)

    def test_system_requires_full_sequence_without_truncation(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            data["model"]["truncation"] = True

        self.mutate_json(checkpoint.SOURCE_PATHS[checkpoint.SourceRole.SYSTEM_E2E], mutate)
        self.assert_invalid("expected full sequence with no truncation")

    def test_f3_rejects_upstream_equivalence_claim(self) -> None:
        def mutate(data: dict[str, object]) -> None:
            data["upstream_gpt4o_equivalent"] = True

        self.mutate_json(checkpoint.SOURCE_PATHS[checkpoint.SourceRole.F3_THREE_MODEL], mutate)
        self.assert_invalid("upstream_gpt4o_equivalent")

    def test_missing_validation_log_is_structural_error(self) -> None:
        self.path(checkpoint.SOURCE_PATHS[checkpoint.SourceRole.VALIDATION]).unlink()
        self.assert_invalid("unreadable source")

    def test_check_is_read_only(self) -> None:
        checkpoint.generate_checkpoint(self.root)
        out = self.root / "reports" / "w3_day5"
        before = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in checkpoint.OUTPUT_NAMES}
        checkpoint.check_checkpoint(self.root)
        after = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in checkpoint.OUTPUT_NAMES}
        self.assertEqual(before, after)

    def test_two_generations_are_byte_identical_and_preserve_mtime(self) -> None:
        checkpoint.generate_checkpoint(self.root)
        out = self.root / "reports" / "w3_day5"
        first = {name: (out / name).read_bytes() for name in checkpoint.OUTPUT_NAMES}
        mtimes = {name: (out / name).stat().st_mtime_ns for name in checkpoint.OUTPUT_NAMES}
        time.sleep(0.02)
        checkpoint.generate_checkpoint(self.root)
        second = {name: (out / name).read_bytes() for name in checkpoint.OUTPUT_NAMES}
        self.assertEqual(first, second)
        self.assertEqual(mtimes, {name: (out / name).stat().st_mtime_ns for name in checkpoint.OUTPUT_NAMES})

    def test_cli_exit_codes_distinguish_structure_and_stale_output(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(0, checkpoint.main(["--repo-root", str(self.root)]))
            self.assertEqual(0, checkpoint.main(["--repo-root", str(self.root), "--check"]))
        output = self.root / "reports" / "w3_day5" / "checkpoint.json"
        output.write_bytes(output.read_bytes() + b"\n")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, checkpoint.main(["--repo-root", str(self.root), "--check"]))
        self.path(checkpoint.SOURCE_PATHS[checkpoint.SourceRole.VALIDATION]).unlink()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, checkpoint.main(["--repo-root", str(self.root)]))


if __name__ == "__main__":
    unittest.main()
