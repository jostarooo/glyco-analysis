from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_agent_session_archive as archive  # noqa: E402


STABLE_ID = "codex:01a00000-0000-7000-8000-000000000001"
VOLATILE_ID = "codex:01a00000-0000-7000-8000-000000000002"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _base_plan(stable_path: Path) -> dict[str, Any]:
    del stable_path
    return {
        "schema_version": 1,
        "sessions": [
            {
                "id": STABLE_ID,
                "label": "稳定子会话",
                "verify_source_file": True,
                "volatile_reason": "",
            },
            {
                "id": VOLATILE_ID,
                "label": "增长中的主会话",
                "verify_source_file": False,
                "volatile_reason": "主会话仍在增长",
            },
        ],
        "records": [
            {
                "date": "2026-11-01",
                "file": "01-test-record.md",
                "title": "测试工程记录",
                "summary": "本记录验证真实证据、脱敏和离线检查。",
                "summary_evidence": ["E-USER", "E-RESULT"],
                "sections": [
                    {
                        "heading": "任务与执行",
                        "paragraphs": [
                            {
                                "text": "用户要求检查会话归档。",
                                "evidence": ["E-USER"],
                            },
                            {
                                "text": "工具实际返回成功结果。",
                                "evidence": ["E-TOOL"],
                            },
                        ],
                    }
                ],
                "boundaries": [
                    {
                        "text": "一次成功输出只证明该次命令成功。",
                        "evidence": ["E-RESULT"],
                    }
                ],
                "ai_use": [
                    {
                        "text": "本记录来自 AI 会话的结构化证据，不包含隐藏推理。",
                        "evidence": ["E-USER", "E-RESULT"],
                    }
                ],
                "evidence": [
                    {
                        "id": "E-USER",
                        "type": "message",
                        "session": VOLATILE_ID,
                        "ordinal": 1,
                        "label": "用户任务",
                    },
                    {
                        "id": "E-TOOL",
                        "type": "tool",
                        "session": STABLE_ID,
                        "ordinal": 2,
                        "call_index": 0,
                        "event_index": 0,
                        "label": "工具结果",
                    },
                    {
                        "id": "E-RESULT",
                        "type": "message",
                        "session": STABLE_ID,
                        "ordinal": 3,
                        "label": "助手结论",
                    },
                ],
            }
        ],
    }


def _build_fixture(root: Path) -> tuple[Path, Path, Path, Path]:
    stable_path = root / "stable-session.jsonl"
    stable_path.write_bytes(b'{"stable":true}\n')
    database = root / "sessions.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            project TEXT,
            agent TEXT,
            started_at TEXT,
            ended_at TEXT,
            message_count INTEGER,
            file_path TEXT,
            file_size INTEGER,
            file_hash TEXT,
            secret_leak_count INTEGER,
            transcript_fidelity TEXT,
            is_truncated INTEGER
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL
        );
        CREATE TABLE tool_calls (
            id INTEGER PRIMARY KEY,
            message_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            input_json TEXT,
            call_index INTEGER NOT NULL
        );
        CREATE TABLE tool_result_events (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            tool_call_message_ordinal INTEGER NOT NULL,
            call_index INTEGER NOT NULL,
            event_index INTEGER NOT NULL,
            status TEXT NOT NULL,
            content TEXT NOT NULL
        );
        CREATE TABLE secret_findings (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL
        );
        """
    )
    stable_bytes = stable_path.read_bytes()
    connection.execute(
        """
        INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            STABLE_ID,
            "glyco_analysis",
            "codex",
            "2026-11-01T00:00:00Z",
            "2026-11-01T00:10:00Z",
            3,
            str(stable_path),
            len(stable_bytes),
            _sha(stable_bytes),
            0,
            "",
            0,
        ),
    )
    connection.execute(
        """
        INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            VOLATILE_ID,
            "glyco_analysis",
            "codex",
            "2026-11-01T00:00:00Z",
            "2026-11-01T00:20:00Z",
            1,
            str(root / "volatile.jsonl"),
            10,
            _sha(b"volatile"),
            0,
            "",
            0,
        ),
    )
    connection.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
        (1, STABLE_ID, 1, "user", "检查这个项目"),
    )
    connection.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
        (2, STABLE_ID, 2, "assistant", "运行检查命令"),
    )
    connection.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
        (3, STABLE_ID, 3, "assistant", "完成检查：PASS"),
    )
    connection.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
        (4, VOLATILE_ID, 1, "user", "请完成今天的任务"),
    )
    connection.execute(
        "INSERT INTO tool_calls VALUES (?, ?, ?, ?, ?, ?)",
        (1, 2, STABLE_ID, "exec_command", '{"cmd":"check"}', 0),
    )
    connection.execute(
        "INSERT INTO tool_result_events VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, STABLE_ID, 2, 0, 0, "ok", "EXIT=0\nPASS"),
    )
    connection.commit()
    connection.close()

    plan_path = root / "archive-plan.json"
    _write_json(plan_path, _base_plan(stable_path))
    return database, plan_path, root / "out", stable_path


def _build_and_write(
    database: Path,
    plan_path: Path,
    out_dir: Path,
) -> archive.BuildResult:
    result = archive.build_archive(database, plan_path, out_dir)
    for relative, content in result.outputs.items():
        archive.write_if_changed(out_dir / relative, content)
    return result


class AgentSessionArchiveTest(unittest.TestCase):
    def test_happy_path_builds_evidence_links_and_source_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database, plan_path, out_dir, _ = _build_fixture(Path(temp))
            result = _build_and_write(database, plan_path, out_dir)
            document = (
                out_dir / "2026-11-01" / "01-test-record.md"
            ).read_text(encoding="utf-8")
            sources = (out_dir / "SOURCES.sha256").read_text(encoding="utf-8")

        self.assertEqual(3, len(result.evidence))
        self.assertIn("[E-USER]", document)
        self.assertIn("原始证据 SHA256", document)
        self.assertIn("参数：\ncheck", document)
        self.assertNotIn("sandbox_permissions", document)
        self.assertIn(f"source-file/{STABLE_ID}", sources)
        self.assertNotIn(f"source-file/{VOLATILE_ID}", sources)

    def test_second_build_is_byte_and_mtime_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database, plan_path, out_dir, _ = _build_fixture(Path(temp))
            _build_and_write(database, plan_path, out_dir)
            before = {
                path.relative_to(out_dir).as_posix(): (
                    path.read_bytes(),
                    path.stat().st_mtime_ns,
                )
                for path in out_dir.rglob("*")
                if path.is_file()
            }
            _build_and_write(database, plan_path, out_dir)
            after = {
                path.relative_to(out_dir).as_posix(): (
                    path.read_bytes(),
                    path.stat().st_mtime_ns,
                )
                for path in out_dir.rglob("*")
                if path.is_file()
            }

        self.assertEqual(before, after)

    def test_check_detects_hand_edited_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database, plan_path, out_dir, _ = _build_fixture(Path(temp))
            result = _build_and_write(database, plan_path, out_dir)
            document = out_dir / "2026-11-01" / "01-test-record.md"
            document.write_text(
                document.read_text(encoding="utf-8") + "\n手改\n",
                encoding="utf-8",
            )
            errors = archive.verify_outputs(out_dir, result)

        self.assertTrue(
            any("已过期或被手改" in error for error in errors),
            errors,
        )

    def test_high_confidence_token_is_rejected(self) -> None:
        fake = "ghp_" + "a" * 30
        self.assertIn("GitHub token", archive.find_sensitive_text(fake))

    def test_non_whitelisted_session_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, plan_path, _, _ = _build_fixture(Path(temp))
            plan = _read_json(plan_path)
            plan["records"][0]["evidence"][0]["session"] = (
                "codex:01a00000-0000-7000-8000-000000000099"
            )
            with self.assertRaisesRegex(archive.ArchiveError, "未声明会话"):
                archive.parse_plan(plan)

    def test_missing_message_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database, plan_path, out_dir, _ = _build_fixture(Path(temp))
            plan = _read_json(plan_path)
            plan["records"][0]["evidence"][0]["ordinal"] = 99
            _write_json(plan_path, plan)
            with self.assertRaisesRegex(archive.ArchiveError, "缺少消息证据"):
                archive.build_archive(database, plan_path, out_dir)

    def test_missing_tool_result_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database, plan_path, out_dir, _ = _build_fixture(Path(temp))
            plan = _read_json(plan_path)
            plan["records"][0]["evidence"][1]["event_index"] = 9
            _write_json(plan_path, plan)
            with self.assertRaisesRegex(archive.ArchiveError, "缺少工具结果"):
                archive.build_archive(database, plan_path, out_dir)

    def test_unknown_narrative_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, plan_path, _, _ = _build_fixture(Path(temp))
            plan = _read_json(plan_path)
            plan["records"][0]["sections"][0]["paragraphs"][0]["evidence"] = [
                "E-MISSING"
            ]
            with self.assertRaisesRegex(archive.ArchiveError, "不存在的证据"):
                archive.parse_plan(plan)

    def test_duplicate_evidence_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, plan_path, _, _ = _build_fixture(Path(temp))
            plan = _read_json(plan_path)
            duplicate = copy.deepcopy(plan["records"][0]["evidence"][0])
            plan["records"][0]["evidence"].append(duplicate)
            with self.assertRaisesRegex(archive.ArchiveError, "重复证据 ID"):
                archive.parse_plan(plan)

    def test_stable_source_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database, plan_path, out_dir, stable_path = _build_fixture(
                Path(temp)
            )
            stable_path.write_bytes(b'{"stable":truf}\n')
            with self.assertRaisesRegex(archive.ArchiveError, "SHA256 与数据库不一致"):
                archive.build_archive(database, plan_path, out_dir)

    def test_volatile_session_must_explain_why_file_hash_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, plan_path, _, _ = _build_fixture(Path(temp))
            plan = _read_json(plan_path)
            plan["sessions"][1]["volatile_reason"] = ""
            with self.assertRaisesRegex(archive.ArchiveError, "volatile_reason"):
                archive.parse_plan(plan)

    def test_review_guide_is_present_and_linked(self) -> None:
        archive_root = ROOT / "agent-sessions"
        guide = archive_root / "REVIEW_GUIDE.md"
        self.assertTrue(guide.is_file())
        self.assertIn("不能证明", guide.read_text(encoding="utf-8"))
        for name in ("INDEX.md", "README.md"):
            text = (archive_root / name).read_text(encoding="utf-8")
            self.assertIn("[REVIEW_GUIDE.md](REVIEW_GUIDE.md)", text)

    def test_redaction_handles_realistic_secret_fields(self) -> None:
        secret = "s" * 12
        cases = [
            'password="' + secret + '"',
            "密码 `" + secret + "`。",
            "GITHUB_TOKEN=" + secret,
            "https://example.test/path?token=" + secret,
            "Authorization: Bearer " + "b" * 24,
            r"C:\Users\example\project\file.txt",
        ]
        for value in cases:
            with self.subTest(value=value):
                output, counts = archive.redact_text(value)
                self.assertTrue(counts)
                self.assertEqual([], archive.find_sensitive_text(output))

    def test_truncation_is_stable_and_marked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database, plan_path, out_dir, _ = _build_fixture(Path(temp))
            plan = _read_json(plan_path)
            plan["records"][0]["evidence"][2]["excerpt_chars"] = 120
            _write_json(plan_path, plan)
            connection = sqlite3.connect(database)
            connection.execute(
                "UPDATE messages SET content = ? WHERE id = 3",
                ("长内容" * 200,),
            )
            connection.commit()
            connection.close()
            first = archive.build_archive(database, plan_path, out_dir)
            second = archive.build_archive(database, plan_path, out_dir)

        first_excerpt = first.evidence["E-RESULT"].excerpt
        second_excerpt = second.evidence["E-RESULT"].excerpt
        self.assertEqual(first_excerpt, second_excerpt)
        self.assertIn("证据摘录已按固定长度截断", first_excerpt)


if __name__ == "__main__":
    unittest.main()
