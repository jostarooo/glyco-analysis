from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = REPO_ROOT / "system" / "static" / "index.html"


class SystemUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = INDEX_HTML.read_text(encoding="utf-8")

    def test_ui_is_self_contained(self) -> None:
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)
        self.assertNotIn("@import", self.html)
        self.assertEqual(self.html.count("<script"), 1)
        self.assertEqual(self.html.count("<style"), 1)

    def test_ui_uses_the_real_system_contract(self) -> None:
        for path in (
            "/api/auth/session",
            "/api/auth/login",
            "/api/auth/logout",
            "/api/runtime",
            "/api/predictions",
        ):
            self.assertIn(path, self.html)
        self.assertIn('credentials: "same-origin"', self.html)
        self.assertIn("X-CSRF-Token", self.html)

    def test_ui_does_not_embed_prediction_results(self) -> None:
        self.assertNotIn("0.999", self.html)
        self.assertNotIn("predicted_label\": 1", self.html)
        self.assertIn("result.candidates.map(normalizeCandidate)", self.html)

    def test_research_and_evidence_boundaries_are_visible(self) -> None:
        for phrase in ("研究原型", "不是临床诊断", "概率不是实验验证"):
            self.assertIn(phrase, self.html)


if __name__ == "__main__":
    unittest.main()
