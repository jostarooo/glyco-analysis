from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import doc2agent_three_model_report as three_model  # noqa: E402


MODEL_KEYS = ("alpha", "beta", "gamma")
PROMPT_HASHES = {
    "system": hashlib.sha256(b"system").hexdigest(),
    "user_template": hashlib.sha256(b"user").hexdigest(),
    "tool_catalog": hashlib.sha256(b"tools").hexdigest(),
}
RUBRIC_SHA = hashlib.sha256(b"rubric").hexdigest()
PROMPT_TEMPLATE_SHA = hashlib.sha256(b"prompt-template").hexdigest()
TASKS_FILE_SHA = hashlib.sha256(b"tasks-file").hexdigest()
JUDGE_CONFIG = {
    "model": "judge-test",
    "endpoint": "http://127.0.0.1:9999/v1/chat/completions",
    "api_key_env": "TEST_KEY",
    "temperature": 0.0,
    "max_tokens": 128,
    "request_timeout_seconds": 30.0,
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_task(task_id: int, *, question: str | None = None) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "question": question or f"Question {task_id}",
        "expected_tools": ["tool_a"],
        "tool_calls": [
            {
                "tool": "tool_a",
                "arguments": {},
                "status": "ok",
                "error": "",
                "result": {"value": "evidence"},
            }
        ],
        "final_answer": f"Answer {task_id}",
        "errors": [],
        "elapsed_seconds": 1.0,
        "exact_sequence": True,
        "all_expected_called": True,
        "any_expected_called": True,
        "expected_steps": 1,
        "called_steps": 1,
        "call_successes": 1,
        "model_calls": 1,
        "model_responses": [{"round": 1, "finish_reason": "stop"}],
        "token_usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
            "responses_with_usage": 1,
        },
    }


def _grade_tasks(
    *,
    run_dir: Path,
    run_summary_sha: str,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for task_id in range(1, 51):
        run_task_path = run_dir / f"task_{task_id:02d}.json"
        tasks.append(
            {
                "task_id": task_id,
                "status": "correct",
                "reason_codes": ["judge_success"],
                "rubric_sha256": RUBRIC_SHA,
                "rubric_version": "rubric-v1",
                "prompt_template_sha256": PROMPT_TEMPLATE_SHA,
                "judge_model_config": JUDGE_CONFIG,
                "evidence_audit": {"has_final_answer": True},
                "source_hashes": {
                    "authoritative_task_sha256": hashlib.sha256(
                        f"task-{task_id}".encode("utf-8")
                    ).hexdigest(),
                    "run_summary_sha256": run_summary_sha,
                    "run_task_sha256": _sha(run_task_path),
                    "tasks_file_sha256": TASKS_FILE_SHA,
                },
            }
        )
    return tasks


def _model_fixture(
    base: Path,
    *,
    key: str,
    use_sidecar: bool,
) -> dict[str, Any]:
    run_dir = base / f"{key}-run"
    grade_dir = base / f"{key}-grade"
    run_dir.mkdir(parents=True)
    grade_dir.mkdir(parents=True)
    for task_id in range(1, 51):
        _write_json(
            run_dir / f"task_{task_id:02d}.json",
            _run_task(task_id),
        )
    summary = {
        "schema_version": 1,
        "provider": "test-provider",
        "model": f"model-{key}",
        "tasks_run": 50,
        "max_rounds": 4,
        "tools_available": 70,
        "exact_sequence": 50,
        "all_expected_called": 50,
        "any_expected_called": 50,
        "tasks_with_tool_call": 50,
        "tasks_with_final_answer": 50,
        "tool_call_successes": 50,
        "tool_calls": 50,
        "model_calls": 50,
        "finish_reasons": {"stop": 50},
        "token_usage": {
            "prompt_tokens": 50,
            "completion_tokens": 50,
            "total_tokens": 100,
            "responses_with_usage": 50,
        },
        "elapsed_seconds": 5.0,
    }
    if not use_sidecar:
        summary["prompt_hashes"] = PROMPT_HASHES
    _write_json(run_dir / "summary.json", summary)
    run_summary_sha = _sha(run_dir / "summary.json")

    for task in _grade_tasks(
        run_dir=run_dir,
        run_summary_sha=run_summary_sha,
    ):
        _write_json(grade_dir / f"task_{task['task_id']:02d}.json", task)
    grade_summary = {
        "schema_version": 1,
        "run_id": f"{key}-50",
        "task_count": 50,
        "task_ids": list(range(1, 51)),
        "status_counts": {
            "correct": 50,
            "incorrect": 0,
            "manual_review": 0,
            "missing_answer": 0,
            "invalid_trace": 0,
            "judge_unavailable": 0,
        },
        "graded_correct": 50,
        "graded_incorrect": 0,
        "graded_accuracy": {
            "numerator": 50,
            "denominator": 50,
            "value": 1.0,
        },
        "graded_coverage": {
            "numerator": 50,
            "denominator": 50,
            "value": 1.0,
        },
        "correct_over_task_count": {
            "numerator": 50,
            "denominator": 50,
            "value": 1.0,
        },
        "answer_available_rate": {
            "numerator": 50,
            "denominator": 50,
            "value": 1.0,
        },
        "rubric_sha256": RUBRIC_SHA,
        "rubric_version": "rubric-v1",
        "prompt_template_sha256": PROMPT_TEMPLATE_SHA,
        "judge_model_config": JUDGE_CONFIG,
        "source": {
            "run_summary_sha256": run_summary_sha,
            "tasks_file_sha256": TASKS_FILE_SHA,
        },
    }
    _write_json(grade_dir / "summary.json", grade_summary)

    entry: dict[str, Any] = {
        "key": key,
        "label": key.title(),
        "provider": "test-provider",
        "model": f"model-{key}",
        "run_dir": str(run_dir),
        "grade_dir": str(grade_dir),
    }
    if use_sidecar:
        sidecar = base / f"{key}-provenance.json"
        _write_json(
            sidecar,
            {
                "schema_version": 1,
                "run_id": f"{key}-50",
                "verification_method": (
                    "historical_code_provenance_not_runtime_recorded"
                ),
                "runtime_recorded": False,
                "prompt_hashes": PROMPT_HASHES,
                "historical_facts": {"fixture": True},
            },
        )
        entry["provenance_sidecar"] = str(sidecar)
    return entry


def build_fixture(base: Path) -> tuple[Path, Path, Path]:
    entries = [
        _model_fixture(base, key=key, use_sidecar=index == 0)
        for index, key in enumerate(MODEL_KEYS)
    ]
    manifest = base / "manifest.json"
    _write_json(
        manifest,
        {
            "schema_version": 1,
            "reference_model": MODEL_KEYS[0],
            "models": entries,
        },
    )
    return manifest, base / "report.json", base / "report.md"


def _refresh_grade_run_hash(grade_dir: Path, run_summary: Path) -> None:
    sha = _sha(run_summary)
    summary_path = grade_dir / "summary.json"
    summary = _read_json(summary_path)
    summary["source"]["run_summary_sha256"] = sha
    _write_json(summary_path, summary)
    for task_id in range(1, 51):
        path = grade_dir / f"task_{task_id:02d}.json"
        task = _read_json(path)
        task["source_hashes"]["run_summary_sha256"] = sha
        _write_json(path, task)


class ThreeModelReportTest(unittest.TestCase):
    def test_happy_path_builds_separate_metric_domains_and_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest, json_out, md_out = build_fixture(Path(temp))
            report = three_model.build_report(manifest)
            with contextlib.redirect_stdout(io.StringIO()):
                three_model.main(
                    [
                        "--manifest",
                        str(manifest),
                        "--json-out",
                        str(json_out),
                        "--md-out",
                        str(md_out),
                    ]
                )
            markdown = md_out.read_text(encoding="utf-8")

        self.assertEqual(report["scope"], "f3_three_model")
        self.assertEqual(report["reference_model"], MODEL_KEYS[0])
        self.assertFalse(report["upstream_gpt4o_equivalent"])
        self.assertEqual(len(report["models"]), 3)
        self.assertEqual(len(report["tasks"]), 50)
        self.assertEqual(report["models"][0]["trajectory"]["exact_sequence"], 50)
        self.assertEqual(
            report["models"][0]["answer_grade"]["graded_correct"], 50
        )
        self.assertEqual(
            report["models"][1]["delta_vs_reference"]["trajectory"][
                "exact_sequence"
            ],
            0,
        )
        self.assertEqual(
            report["tasks"][0]["by_model"][MODEL_KEYS[1]][
                "delta_vs_reference"
            ]["reference_model"],
            MODEL_KEYS[0],
        )
        self.assertIn(
            "provenance_sidecar",
            report["models"][0]["sources"],
        )
        self.assertEqual(
            report["models"][0]["prompt_provenance"]["runtime_recorded"],
            False,
        )
        self.assertIn("工具轨迹指标与答案评分指标分开报告", markdown)
        self.assertNotIn("combined accuracy:", markdown.lower())

    def test_manifest_requires_three_unique_models_and_existing_reference(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest, _, _ = build_fixture(Path(temp))
            original = _read_json(manifest)
            cases = (
                (
                    "count",
                    {"models": original["models"][:2]},
                    "exactly 3 models",
                ),
                (
                    "duplicate",
                    {
                        "models": [
                            original["models"][0],
                            dict(
                                original["models"][1],
                                key=original["models"][0]["key"],
                            ),
                            original["models"][2],
                        ]
                    },
                    "duplicate model key",
                ),
                (
                    "reference",
                    {"reference_model": "missing"},
                    "not present in models",
                ),
            )
            for name, changes, message in cases:
                with self.subTest(name=name):
                    value = dict(original)
                    value.update(changes)
                    _write_json(manifest, value)
                    with self.assertRaisesRegex(
                        three_model.ReportError, message
                    ):
                        three_model.build_report(manifest)

    def test_task_question_or_expected_tools_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest, _, _ = build_fixture(Path(temp))
            data = _read_json(manifest)
            run_dir = Path(data["models"][1]["run_dir"])
            grade_dir = Path(data["models"][1]["grade_dir"])
            task_path = run_dir / "task_01.json"
            original = _read_json(task_path)
            cases = (
                ("question", "Changed question", "question differs"),
                ("tools", ["tool_b"], "expected_tools differ"),
            )
            for name, value, message in cases:
                with self.subTest(name=name):
                    task = dict(original)
                    task["question" if name == "question" else "expected_tools"] = (
                        value
                    )
                    _write_json(task_path, task)
                    grade_task_path = grade_dir / "task_01.json"
                    grade_task = _read_json(grade_task_path)
                    grade_task["source_hashes"]["run_task_sha256"] = _sha(
                        task_path
                    )
                    _write_json(grade_task_path, grade_task)
                    with self.assertRaisesRegex(
                        three_model.ReportError, message
                    ):
                        three_model.build_report(manifest)

    def test_missing_task_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest, _, _ = build_fixture(Path(temp))
            data = _read_json(manifest)
            run_dir = Path(data["models"][1]["run_dir"])
            (run_dir / "task_50.json").unlink()
            with self.assertRaisesRegex(
                three_model.ReportError, "exactly task_01\\.\\.task_50"
            ):
                three_model.build_report(manifest)

    def test_run_setting_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest, _, _ = build_fixture(Path(temp))
            data = _read_json(manifest)
            run_dir = Path(data["models"][1]["run_dir"])
            grade_dir = Path(data["models"][1]["grade_dir"])
            run_summary_path = run_dir / "summary.json"
            original = _read_json(run_summary_path)
            for field in ("max_rounds", "tools_available"):
                with self.subTest(field=field):
                    summary = dict(original)
                    summary[field] = int(original[field]) + 1
                    _write_json(run_summary_path, summary)
                    _refresh_grade_run_hash(grade_dir, run_summary_path)
                    with self.assertRaisesRegex(
                        three_model.ReportError, f"{field} differs"
                    ):
                        three_model.build_report(manifest)
                    _write_json(run_summary_path, original)
                    _refresh_grade_run_hash(grade_dir, run_summary_path)

    def test_mixed_judge_or_rubric_contract_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest, _, _ = build_fixture(Path(temp))
            data = _read_json(manifest)
            grade_dir = Path(data["models"][1]["grade_dir"])
            original_summary = _read_json(grade_dir / "summary.json")
            cases = (
                ("judge", "judge_model_config", {**JUDGE_CONFIG, "model": "other"}),
                ("rubric", "rubric_sha256", hashlib.sha256(b"other").hexdigest()),
            )
            for name, field, value in cases:
                with self.subTest(name=name):
                    summary = dict(original_summary)
                    summary[field] = value
                    _write_json(grade_dir / "summary.json", summary)
                    for task_id in range(1, 51):
                        path = grade_dir / f"task_{task_id:02d}.json"
                        task = _read_json(path)
                        task[field] = value
                        _write_json(path, task)
                    with self.assertRaisesRegex(
                        three_model.ReportError, f"grade {field} differs"
                    ):
                        three_model.build_report(manifest)
                    _write_json(grade_dir / "summary.json", original_summary)
                    for task_id in range(1, 51):
                        path = grade_dir / f"task_{task_id:02d}.json"
                        task = _read_json(path)
                        task[field] = original_summary[field]
                        _write_json(path, task)

    def test_missing_prompt_provenance_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest, _, _ = build_fixture(Path(temp))
            data = _read_json(manifest)
            data["models"][0].pop("provenance_sidecar")
            _write_json(manifest, data)
            with self.assertRaisesRegex(
                three_model.ReportError, "prompt provenance missing"
            ):
                three_model.build_report(manifest)

    def test_grade_summary_mismatch_and_run_hash_drift_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest, _, _ = build_fixture(Path(temp))
            data = _read_json(manifest)
            grade_dir = Path(data["models"][1]["grade_dir"])
            original = _read_json(grade_dir / "summary.json")

            changed = dict(original)
            changed["status_counts"] = dict(original["status_counts"])
            changed["status_counts"]["correct"] = 49
            _write_json(grade_dir / "summary.json", changed)
            with self.assertRaisesRegex(
                three_model.ReportError, "status_counts"
            ):
                three_model.build_report(manifest)

            changed = dict(original)
            changed["source"] = dict(original["source"])
            changed["source"]["run_summary_sha256"] = "0" * 64
            _write_json(grade_dir / "summary.json", changed)
            with self.assertRaisesRegex(
                three_model.ReportError, "run_summary_sha256"
            ):
                three_model.build_report(manifest)

            changed = dict(original)
            changed["graded_coverage"] = {
                "numerator": 49,
                "denominator": 50,
                "value": 0.98,
            }
            _write_json(grade_dir / "summary.json", changed)
            with self.assertRaisesRegex(
                three_model.ReportError, "graded_coverage"
            ):
                three_model.build_report(manifest)

    def test_second_write_is_byte_and_mtime_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest, json_out, md_out = build_fixture(Path(temp))
            args = [
                "--manifest",
                str(manifest),
                "--json-out",
                str(json_out),
                "--md-out",
                str(md_out),
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(three_model.main(args), 0)
            before = {
                path: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in (json_out, md_out)
            }
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(three_model.main(args), 0)
            after = {
                path: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in (json_out, md_out)
            }
        self.assertEqual(before, after)

    def test_check_catches_edited_output_or_changed_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest, json_out, md_out = build_fixture(Path(temp))
            base_args = [
                "--manifest",
                str(manifest),
                "--json-out",
                str(json_out),
                "--md-out",
                str(md_out),
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(three_model.main(base_args), 0)
                self.assertEqual(
                    three_model.main([*base_args, "--check"]),
                    0,
                )

            original_json = json_out.read_text(encoding="utf-8")
            json_out.write_text(original_json + " ", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    three_model.main([*base_args, "--check"]),
                    1,
                )
            json_out.write_text(original_json, encoding="utf-8")

            json_out.unlink()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    three_model.main([*base_args, "--check"]),
                    1,
                )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(three_model.main(base_args), 0)

            data = _read_json(manifest)
            run_dir = Path(data["models"][1]["run_dir"])
            task_path = run_dir / "task_01.json"
            task = _read_json(task_path)
            task["question"] = "Changed source question"
            _write_json(task_path, task)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    three_model.main([*base_args, "--check"]),
                    1,
                )


if __name__ == "__main__":
    unittest.main()
