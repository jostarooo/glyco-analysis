from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_w3_delivery.py"
SPEC = importlib.util.spec_from_file_location("build_w3_delivery", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
delivery = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = delivery
SPEC.loader.exec_module(delivery)


class DeliveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.out = self.root / "package"
        for item in delivery.PACKAGE_FILES:
            target = self.root / item.source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / item.source).read_bytes())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_real_package_has_expected_files_and_checksums(self) -> None:
        count = delivery.build_delivery(self.root, self.out)
        self.assertEqual(len(delivery.PACKAGE_FILES) + 3, count)
        for item in delivery.PACKAGE_FILES:
            self.assertEqual((self.root / item.source).read_bytes(), (self.out / item.destination).read_bytes())
        evidence_manifest = self.out / delivery.EVIDENCE_DIR / "SHA256SUMS.txt"
        root_manifest = self.out / "SHA256SUMS.txt"
        self.assertTrue(evidence_manifest.is_file())
        self.assertTrue(root_manifest.is_file())
        self.assertIn("SHA256SUMS.txt", root_manifest.read_text(encoding="utf-8"))
        self.assertIn("2026-11-08_W3_checkpoint.json", root_manifest.read_text(encoding="utf-8"))

    def test_check_rejects_stale_output(self) -> None:
        delivery.build_delivery(self.root, self.out)
        target = self.out / delivery.PACKAGE_FILES[0].destination
        target.write_bytes(target.read_bytes() + b"\n")
        with self.assertRaisesRegex(delivery.DeliveryCheckError, "stale"):
            delivery.check_delivery(self.root, self.out)

    def test_two_builds_preserve_bytes_and_mtime(self) -> None:
        delivery.build_delivery(self.root, self.out)
        before = {
            path.relative_to(self.out).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.out.rglob("*")
            if path.is_file()
        }
        time.sleep(0.02)
        delivery.build_delivery(self.root, self.out)
        after = {
            path.relative_to(self.out).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.out.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_missing_source_is_structural_error(self) -> None:
        (self.root / delivery.PACKAGE_FILES[0].source).unlink()
        with self.assertRaisesRegex(delivery.DeliveryError, "unreadable source"):
            delivery.build_delivery(self.root, self.out)

    def test_cli_exit_codes(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(0, delivery.main(["--repo-root", str(self.root), "--out-dir", str(self.out)]))
            self.assertEqual(0, delivery.main(["--repo-root", str(self.root), "--out-dir", str(self.out), "--check"]))
        (self.out / "SHA256SUMS.txt").write_bytes(b"stale\n")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, delivery.main(["--repo-root", str(self.root), "--out-dir", str(self.out), "--check"]))
        (self.root / delivery.PACKAGE_FILES[0].source).unlink()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, delivery.main(["--repo-root", str(self.root), "--out-dir", str(self.out)]))


if __name__ == "__main__":
    unittest.main()
