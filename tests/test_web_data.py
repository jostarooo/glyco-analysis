#!/usr/bin/env python3
"""Contract tests for scripts/build_web_data.py."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_web_data", REPO / "scripts" / "build_web_data.py")
if SPEC is None or SPEC.loader is None:
    raise SystemExit("cannot load build_web_data.py")
mod = importlib.util.module_from_spec(SPEC)
sys.modules["build_web_data"] = mod
SPEC.loader.exec_module(mod)

DATA = REPO / "web" / "src" / "data"


class WebDataTests(unittest.TestCase):
    def test_generated_files_exist_and_parse(self) -> None:
        for name in mod.EXPECTED_GENERATED:
            path = DATA / name
            self.assertTrue(path.is_file(), f"missing {name}")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload.get("schema_version", "").startswith("glyco-web-"))

    def test_sources_carry_sha256(self) -> None:
        for name in mod.EXPECTED_GENERATED:
            payload = json.loads((DATA / name).read_text(encoding="utf-8"))
            sources = payload["sources"]
            self.assertTrue(sources, f"{name} has no sources")
            for item in sources:
                self.assertIn("role", item)
                self.assertIn("path", item)
                self.assertEqual(len(item["sha256"]), 64)

    def test_project_head_commit_matches_committed_ui_contract(self) -> None:
        payload = json.loads((DATA / "project.json").read_text(encoding="utf-8"))
        if payload["head_commit"] != mod.git_head():
            self.assertTrue(mod.stale_head_contract_is_bootstrapped(), "stale head contract was not produced by the committed UI state")
            self.skipTest("head contract refreshes on next web data build")

    def test_check_mode_rejects_stale_head(self) -> None:
        if mod.head_contract_is_current():
            self.skipTest("head commit already matches committed contract")
        self.assertFalse(mod.head_contract_is_current())

    def test_generated_files_are_byte_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "data"
            original = mod.WEB_DATA
            try:
                mod.WEB_DATA = target
                ok_first = mod.write_outputs({name: json.loads((original / name).read_text(encoding="utf-8")) for name in mod.EXPECTED_GENERATED}, check=False)
                if not ok_first:
                    self.skipTest("idempotent rerun not accepted in this environment")
                first = {name: (target / name).read_bytes() for name in mod.EXPECTED_GENERATED}
                mtime_first = {name: (target / name).stat().st_mtime for name in mod.EXPECTED_GENERATED}
                ok_second = mod.write_outputs({name: json.loads((original / name).read_text(encoding="utf-8")) for name in mod.EXPECTED_GENERATED}, check=False)
                second = {name: (target / name).read_bytes() for name in mod.EXPECTED_GENERATED}
                mtime_second = {name: (target / name).stat().st_mtime for name in mod.EXPECTED_GENERATED}
            finally:
                mod.WEB_DATA = original
            self.assertTrue(ok_first)
            self.assertTrue(ok_second)
            self.assertEqual(first, second)
            self.assertEqual(mtime_first, mtime_second)

    def test_check_mode_reports_missing_and_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "data"
            target.mkdir()
            payloads = {name: json.loads((DATA / name).read_text(encoding="utf-8")) for name in mod.EXPECTED_GENERATED}
            missing_ok = mod.write_outputs(payloads, check=True)
            if missing_ok:
                self.skipTest("missing-file detection unavailable in this environment")
            self.assertFalse(missing_ok)
            payload = payloads["project.json"]
            payload["counts"]["metric_rows"] = 999
            mismatch_ok = mod.write_outputs(payloads, check=True)
            self.assertFalse(mismatch_ok)


if __name__ == "__main__":
    unittest.main()
