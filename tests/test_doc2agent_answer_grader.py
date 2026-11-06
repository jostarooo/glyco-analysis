from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import grade_doc2agent_answers as grader  # noqa: E402
    import compare_doc2agent_answer_grades as comparison  # noqa: E402
except ModuleNotFoundError:
    grader = None  # type: ignore[assignment]
    comparison = None  # type: ignore[assignment]


def task_row(task_id: int, *, question: str | None = None) -> dict[str, Any]:
    return {
        "question": question or f"Question {task_id}",
        "expected_trajectory": "tool_a",
        "expected_answer": f"Expected answer {task_id}",
        "site": "test",
        "task_type": "test",
    }


def write_tasks(path: Path, count: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(task_row(task_id), ensure_ascii=False) + "\n"
            for task_id in range(1, count + 1)
        ),
        encoding="utf-8",
    )


def run_row(
    task_id: int,
    *,
    question: str | None = None,
    expected_tools: list[str] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    final_answer: str | None = "Answer",
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "question": question or f"Question {task_id}",
        "expected_tools": expected_tools or ["tool_a"],
        "tool_calls": tool_calls or [],
        "final_answer": final_answer if final_answer is not None else "",
        "errors": errors or [],
    }


def write_run_dir(run_dir: Path, rows: list[dict[str, Any]]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        (run_dir / f"task_{int(row['task_id']):02d}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    (run_dir / "summary.json").write_text(
        json.dumps({"model": "test-model", "tasks_run": len(rows)}) + "\n",
        encoding="utf-8",
    )


def ok_tool(name: str = "tool_a", result: Any = None) -> dict[str, Any]:
    return {
        "tool": name,
        "arguments": {},
        "status": "ok",
        "error": "",
        "result": {"value": "evidence"} if result is None else result,
    }


def failed_tool(name: str = "tool_a", status: str = "error") -> dict[str, Any]:
    return {
        "tool": name,
        "arguments": {},
        "status": status,
        "error": "tool failed",
    }


def fake_judge(
    payload: dict[str, Any] | None = None,
    *,
    raw_response: str | None = None,
    request_error: str | None = None,
    calls: list[str] | None = None,
) -> Callable[[str, Any], Any]:
    def judge(prompt: str, config: Any) -> Any:
        if calls is not None:
            calls.append(prompt)
        return grader.JudgeResponse(
            raw_response=raw_response
            if raw_response is not None
            else json.dumps(payload or {}, ensure_ascii=False),
            request_error=request_error,
        )

    return judge


def success_payload(evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "decision": "SUCCESS",
        "reason": "The answer matches the expected result.",
        "critical_issues": [],
        "scientific_accuracy": "accurate",
        "api_usage_assessment": "The trace supports the answer.",
        "evidence_ids": evidence_ids,
    }


def grade_one(
    base: Path,
    *,
    run: dict[str, Any],
    judge: Callable[[str, Any], Any],
    tasks_count: int = 1,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    tasks_path = base / "tasks.jsonl"
    run_dir = base / "run"
    out_dir = base / "grades"
    write_tasks(tasks_path, tasks_count)
    write_run_dir(run_dir, [run])
    summary = grader.run_grading(
        tasks_path=tasks_path,
        run_dir=run_dir,
        out_dir=out_dir,
        task_ids={int(run["task_id"])},
        judge_fn=judge,
    )
    grade = json.loads(
        (out_dir / f"task_{int(run['task_id']):02d}.json").read_text(
            encoding="utf-8"
        )
    )
    return summary, grade, [str(run_dir), str(out_dir), str(tasks_path)]


class GraderStatusTest(unittest.TestCase):
    def test_missing_answer_does_not_call_judge(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as temp:
            _, grade, _ = grade_one(
                Path(temp),
                run=run_row(1, final_answer=""),
                judge=fake_judge(success_payload([]), calls=calls),
            )
        self.assertEqual(grade["status"], "missing_answer")
        self.assertEqual(calls, [])

    def test_failed_and_unknown_tools_are_not_silently_correct(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, grade, _ = grade_one(
                Path(temp),
                run=run_row(
                    1,
                    tool_calls=[
                        failed_tool(),
                        failed_tool("missing_tool", status="unknown_tool"),
                    ],
                ),
                judge=fake_judge(success_payload(["tool_1", "tool_2"])),
            )
        self.assertEqual(grade["status"], "manual_review")
        self.assertIn(
            "success_without_successful_tool_evidence", grade["reason_codes"]
        )

    def test_success_with_successful_tool_evidence_is_correct(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, grade, _ = grade_one(
                Path(temp),
                run=run_row(1, tool_calls=[ok_tool()]),
                judge=fake_judge(success_payload(["tool_1"])),
            )
        self.assertEqual(grade["status"], "correct")
        self.assertEqual(grade["evidence_audit"]["successful_tool_calls"], 1)
        self.assertEqual(
            set(grade["source_hashes"]),
            {
                "tasks_file_sha256",
                "authoritative_task_sha256",
                "run_task_sha256",
                "run_summary_sha256",
            },
        )
        self.assertEqual(len(grade["prompt_sha256"]), 64)
        self.assertEqual(
            grade["judge_model_config"]["model"],
            "opencode-zen/deepseek-v4.1-flash-free",
        )

    def test_success_without_successful_evidence_is_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, grade, _ = grade_one(
                Path(temp),
                run=run_row(1),
                judge=fake_judge(success_payload([])),
            )
        self.assertEqual(grade["status"], "manual_review")
        self.assertIn(
            "success_without_successful_tool_evidence", grade["reason_codes"]
        )

    def test_success_with_only_truncated_evidence_is_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, grade, _ = grade_one(
                Path(temp),
                run=run_row(
                    1,
                    tool_calls=[
                        ok_tool(result={"truncated": True, "preview": "partial"})
                    ],
                ),
                judge=fake_judge(success_payload(["tool_1"])),
            )
        self.assertEqual(grade["status"], "manual_review")
        self.assertIn(
            "success_with_only_truncated_tool_evidence", grade["reason_codes"]
        )

    def test_failure_is_incorrect(self) -> None:
        payload = success_payload(["tool_1"])
        payload["decision"] = "FAILURE"
        with tempfile.TemporaryDirectory() as temp:
            _, grade, _ = grade_one(
                Path(temp),
                run=run_row(1, tool_calls=[ok_tool()]),
                judge=fake_judge(payload),
            )
        self.assertEqual(grade["status"], "incorrect")

    def test_inconclusive_is_manual_review(self) -> None:
        payload = success_payload(["tool_1"])
        payload["decision"] = "INCONCLUSIVE"
        with tempfile.TemporaryDirectory() as temp:
            _, grade, _ = grade_one(
                Path(temp),
                run=run_row(1, tool_calls=[ok_tool()]),
                judge=fake_judge(payload),
            )
        self.assertEqual(grade["status"], "manual_review")

    def test_malformed_judge_is_judge_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, grade, _ = grade_one(
                Path(temp),
                run=run_row(1, tool_calls=[ok_tool()]),
                judge=fake_judge(raw_response="{not valid json"),
            )
        self.assertEqual(grade["status"], "judge_unavailable")

    def test_judge_request_error_is_judge_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, grade, _ = grade_one(
                Path(temp),
                run=run_row(1, tool_calls=[ok_tool()]),
                judge=fake_judge(request_error="network_error:timeout"),
            )
        self.assertEqual(grade["status"], "judge_unavailable")
        self.assertEqual(grade["parsed_judge"], None)

    def test_invalid_evidence_reference_is_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, grade, _ = grade_one(
                Path(temp),
                run=run_row(1, tool_calls=[ok_tool()]),
                judge=fake_judge(success_payload(["tool_99"])),
            )
        self.assertEqual(grade["status"], "manual_review")
        self.assertTrue(
            any(code.startswith("invalid_evidence_reference:") for code in grade["reason_codes"])
        )

    def test_upstream_question_or_tools_mismatch_is_invalid_trace(self) -> None:
        cases = (
            {"question": "Different question", "expected_tools": ["tool_a"]},
            {"question": "Question 1", "expected_tools": ["tool_b"]},
        )
        for changes in cases:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as temp:
                calls: list[str] = []
                _, grade, _ = grade_one(
                    Path(temp),
                    run=run_row(1, **changes),
                    judge=fake_judge(success_payload(["tool_1"]), calls=calls),
                )
                self.assertEqual(grade["status"], "invalid_trace")
                self.assertEqual(calls, [])

    def test_structured_expected_answer_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            tasks_path = base / "tasks.jsonl"
            tasks_path.write_text(
                json.dumps(
                    {
                        "question": "Question 1",
                        "expected_trajectory": "tool_a",
                        "expected_answer": {"status_code": "HTTP 200"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            run_dir = base / "run"
            write_run_dir(run_dir, [run_row(1, tool_calls=[ok_tool()])])
            summary = grader.run_grading(
                tasks_path=tasks_path,
                run_dir=run_dir,
                out_dir=base / "grades",
                task_ids={1},
                judge_fn=fake_judge(success_payload(["tool_1"])),
            )
            grade = json.loads(
                (base / "grades" / "task_01.json").read_text(encoding="utf-8")
            )
        self.assertEqual(summary["graded_correct"], 1)
        self.assertEqual(grade["status"], "correct")


class GraderCacheAndCheckTest(unittest.TestCase):
    def test_cache_hit_keeps_bytes_and_mtime_without_calling_judge(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            tasks_path = base / "tasks.jsonl"
            run_dir = base / "run"
            out_dir = base / "grades"
            write_tasks(tasks_path)
            write_run_dir(run_dir, [run_row(1, tool_calls=[ok_tool()])])
            kwargs = {
                "tasks_path": tasks_path,
                "run_dir": run_dir,
                "out_dir": out_dir,
                "task_ids": {1},
                "judge_fn": fake_judge(success_payload(["tool_1"]), calls=calls),
            }
            grader.run_grading(**kwargs)
            grade_path = out_dir / "task_01.json"
            before_bytes = grade_path.read_bytes()
            before_mtime = grade_path.stat().st_mtime_ns
            time.sleep(0.02)
            grader.run_grading(**kwargs)
            after_bytes = grade_path.read_bytes()
            after_mtime = grade_path.stat().st_mtime_ns
        self.assertEqual(len(calls), 1)
        self.assertEqual(before_bytes, after_bytes)
        self.assertEqual(before_mtime, after_mtime)

    def test_check_fails_when_one_of_50_tasks_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            tasks_path, run_dir, out_dir = build_complete_grades(base, count=50)
            (out_dir / "task_50.json").unlink()
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = grader.main(
                    [
                        "--check",
                        "--tasks",
                        str(tasks_path),
                        "--run-dir",
                        str(run_dir),
                        "--out-dir",
                        str(out_dir),
                    ]
                )
        self.assertEqual(exit_code, 1)

    def test_check_fails_when_summary_was_edited(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            tasks_path, run_dir, out_dir = build_complete_grades(base, count=50)
            summary_path = out_dir / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["status_counts"]["correct"] += 1
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = grader.main(
                    [
                        "--check",
                        "--tasks",
                        str(tasks_path),
                        "--run-dir",
                        str(run_dir),
                        "--out-dir",
                        str(out_dir),
                    ]
                )
        self.assertEqual(exit_code, 1)

    def test_check_fails_when_raw_judge_response_was_edited(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            tasks_path, run_dir, out_dir = build_complete_grades(base, count=50)
            grade_path = out_dir / "task_01.json"
            grade = json.loads(grade_path.read_text(encoding="utf-8"))
            grade["raw_response"] = grade["raw_response"].replace(
                "The answer matches", "The answer contradicts"
            )
            grade_path.write_text(
                json.dumps(grade, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = grader.main(
                    [
                        "--check",
                        "--tasks",
                        str(tasks_path),
                        "--run-dir",
                        str(run_dir),
                        "--out-dir",
                        str(out_dir),
                    ]
                )
        self.assertEqual(exit_code, 1)


def build_complete_grades(
    base: Path, *, count: int
) -> tuple[Path, Path, Path]:
    tasks_path = base / "tasks.jsonl"
    run_dir = base / "run"
    out_dir = base / "grades"
    write_tasks(tasks_path, count)
    write_run_dir(
        run_dir,
        [
            run_row(task_id, tool_calls=[ok_tool()])
            for task_id in range(1, count + 1)
        ],
    )
    grader.run_grading(
        tasks_path=tasks_path,
        run_dir=run_dir,
        out_dir=out_dir,
        judge_fn=fake_judge(success_payload(["tool_1"])),
    )
    return tasks_path, run_dir, out_dir


class ComparisonTest(unittest.TestCase):
    def test_comparison_requires_same_judge_and_marks_local_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            _, _, local_dir = build_complete_grades(base / "local", count=50)
            _, _, external_dir = build_complete_grades(base / "external", count=50)
            report = comparison.build_comparison(local_dir, external_dir)
            json_out = base / "comparison.json"
            markdown_out = base / "comparison.md"
            comparison.write_reports(report, json_out, markdown_out)
            self.assertEqual(
                report["comparison_scope"], "local_evidence_grading"
            )
            self.assertFalse(report["upstream_gpt4o_equivalent"])
            self.assertEqual(report["validation"]["tasks_compared"], 50)
            self.assertTrue(json_out.is_file())
            self.assertIn(
                "not equivalent to the upstream GPT-4o grader",
                markdown_out.read_text(encoding="utf-8"),
            )

            summary_path = external_dir / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["judge_model_config"]["model"] = "different-judge"
            for grade_path in sorted(external_dir.glob("task_*.json")):
                grade = json.loads(grade_path.read_text(encoding="utf-8"))
                grade["judge_model_config"] = summary["judge_model_config"]
                grade_path.write_text(
                    json.dumps(
                        grade, ensure_ascii=False, indent=2, sort_keys=True
                    )
                    + "\n",
                    encoding="utf-8",
                )
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError, "Judge config differs between grade directories"
            ):
                comparison.build_comparison(local_dir, external_dir)


if __name__ == "__main__":
    unittest.main()
