from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import compare_doc2agent_runs as comparison  # noqa: E402


def write_run(
    run_dir: Path,
    *,
    task_id: int,
    question: str,
    expected_tools: list[str],
    exact_sequence: bool,
    all_expected_called: bool,
    any_expected_called: bool,
    called_tools: list[str],
    successes: int,
    final_answer: str,
    model_calls: int = 0,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    tool_calls = [
        {"tool": tool, "status": "ok" if index < successes else "error"}
        for index, tool in enumerate(called_tools)
    ]
    payload = {
        "task_id": task_id,
        "question": question,
        "expected_tools": expected_tools,
        "tool_calls": tool_calls,
        "final_answer": final_answer,
        "errors": [],
        "elapsed_seconds": 1.0,
        "exact_sequence": exact_sequence,
        "all_expected_called": all_expected_called,
        "any_expected_called": any_expected_called,
        "expected_steps": len(expected_tools),
        "called_steps": len(called_tools),
        "call_successes": successes,
        "model_responses": [{"round": index} for index in range(model_calls)],
    }
    (run_dir / f"task_{task_id:02d}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def all_keys(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_keys(child)


class ComparisonTest(unittest.TestCase):
    def test_matching_runs_produce_json_and_markdown_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            local_dir = base / "local"
            external_dir = base / "external"
            write_run(
                local_dir,
                task_id=1,
                question="Question one",
                expected_tools=["a"],
                exact_sequence=True,
                all_expected_called=True,
                any_expected_called=True,
                called_tools=["a"],
                successes=1,
                final_answer="answer",
            )
            write_run(
                local_dir,
                task_id=2,
                question="Question two",
                expected_tools=["b"],
                exact_sequence=False,
                all_expected_called=False,
                any_expected_called=False,
                called_tools=[],
                successes=0,
                final_answer="",
            )
            write_run(
                external_dir,
                task_id=1,
                question="Question one",
                expected_tools=["a"],
                exact_sequence=False,
                all_expected_called=True,
                any_expected_called=True,
                called_tools=["x", "a"],
                successes=1,
                final_answer="",
                model_calls=2,
            )
            write_run(
                external_dir,
                task_id=2,
                question="Question two",
                expected_tools=["b"],
                exact_sequence=False,
                all_expected_called=True,
                any_expected_called=True,
                called_tools=["b"],
                successes=1,
                final_answer="answer",
                model_calls=1,
            )
            (local_dir / "summary.json").write_text(
                json.dumps({"model": "qwen3:4b"}), encoding="utf-8"
            )
            (external_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "model": "workbuddy-ai/glm-5.3",
                        "provider": "local_magpie",
                        "endpoint": "http://127.0.0.1:3425/v1/chat/completions",
                    }
                ),
                encoding="utf-8",
            )

            report = comparison.build_comparison(local_dir, external_dir)
            json_path = base / "report.json"
            markdown_path = base / "report.md"
            comparison.write_reports(report, json_path, markdown_path)

            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown_path.is_file())
            self.assertEqual(report["validation"]["tasks_validated"], 2)
            self.assertEqual(report["aggregate"]["delta"]["exact_sequence"], -1)
            self.assertEqual(
                report["aggregate"]["delta"]["all_expected_called"], 1
            )
            self.assertEqual(report["models"]["local"], "qwen3:4b")
            self.assertEqual(
                report["models"]["external"], "workbuddy-ai/glm-5.3"
            )
            self.assertEqual(report["tasks"][0]["delta"]["tool_calls"], 1)
            self.assertNotIn("model_calls", report["aggregate"]["delta"])
            self.assertNotIn("model_calls", report["tasks"][0]["delta"])
            self.assertIn("## Per task", markdown_path.read_text(encoding="utf-8"))
            self.assertIn(
                "External model: `workbuddy-ai/glm-5.3`",
                markdown_path.read_text(encoding="utf-8"),
            )

    def test_comparison_rejects_mismatched_task_data(self) -> None:
        cases = (
            ("task_ids", None, "Task ids differ"),
            ("question", "Changed question", "Question differs"),
        )
        for case, changed_question, expected_error in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                local_dir = base / "local"
                external_dir = base / "external"
                write_run(
                    local_dir,
                    task_id=1,
                    question="Question one",
                    expected_tools=["a"],
                    exact_sequence=True,
                    all_expected_called=True,
                    any_expected_called=True,
                    called_tools=["a"],
                    successes=1,
                    final_answer="answer",
                )
                if case == "task_ids":
                    write_run(
                        external_dir,
                        task_id=2,
                        question="Question two",
                        expected_tools=["a"],
                        exact_sequence=True,
                        all_expected_called=True,
                        any_expected_called=True,
                        called_tools=["a"],
                        successes=1,
                        final_answer="answer",
                    )
                elif changed_question is not None:
                    write_run(
                        external_dir,
                        task_id=1,
                        question=changed_question,
                        expected_tools=["a"],
                        exact_sequence=True,
                        all_expected_called=True,
                        any_expected_called=True,
                        called_tools=["a"],
                        successes=1,
                        final_answer="answer",
                    )
                with self.assertRaisesRegex(ValueError, expected_error):
                    comparison.build_comparison(local_dir, external_dir)

    def test_comparison_rejects_mismatched_expected_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            local_dir = base / "local"
            external_dir = base / "external"
            write_run(
                local_dir,
                task_id=1,
                question="Question one",
                expected_tools=["a"],
                exact_sequence=True,
                all_expected_called=True,
                any_expected_called=True,
                called_tools=["a"],
                successes=1,
                final_answer="answer",
            )
            write_run(
                external_dir,
                task_id=1,
                question="Question one",
                expected_tools=["b"],
                exact_sequence=False,
                all_expected_called=False,
                any_expected_called=False,
                called_tools=["b"],
                successes=1,
                final_answer="answer",
            )
            with self.assertRaisesRegex(ValueError, "Expected tools differ"):
                comparison.build_comparison(local_dir, external_dir)

    def test_report_does_not_invent_accuracy_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            local_dir = base / "local"
            external_dir = base / "external"
            for run_dir in (local_dir, external_dir):
                write_run(
                    run_dir,
                    task_id=1,
                    question="Question one",
                    expected_tools=["a"],
                    exact_sequence=True,
                    all_expected_called=True,
                    any_expected_called=True,
                    called_tools=["a"],
                    successes=1,
                    final_answer="answer",
                )

            report = comparison.build_comparison(local_dir, external_dir)
            markdown = comparison.render_markdown(report)

        self.assertEqual(report["metrics_scope"], "trajectory_only")
        self.assertEqual(report["answer_correctness"], "not_evaluated")
        self.assertEqual(
            report["grader"], "not_run_upstream_requires_gpt4o_api_key"
        )
        for key in all_keys(report):
            lowered = key.lower()
            self.assertNotIn("accuracy", lowered)
            self.assertTrue(
                lowered == "answer_correctness" or "correctness" not in lowered
            )
        self.assertNotIn("accuracy", markdown.lower())
        self.assertNotIn("correctness", markdown.lower())


if __name__ == "__main__":
    unittest.main()
