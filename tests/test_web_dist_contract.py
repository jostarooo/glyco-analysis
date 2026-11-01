from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_web_dist import check_html, is_external_asset  # noqa: E402


class WebDistContractTests(unittest.TestCase):
    def test_accepts_a_self_contained_page(self) -> None:
        html = """
        <!doctype html>
        <html>
          <head>
            <style>body { color: black; }</style>
            <script type="module">document.body.dataset.ready = "true";</script>
          </head>
          <body><div id="root"></div></body>
        </html>
        """
        self.assertEqual(check_html(html), [])

    def test_rejects_external_module_and_stylesheet(self) -> None:
        html = """
        <!doctype html>
        <html>
          <head>
            <link rel="stylesheet" href="./assets/index.css">
            <script type="module" src="./assets/index.js"></script>
          </head>
          <body><div id="root"></div></body>
        </html>
        """
        failures = check_html(html)
        self.assertTrue(any("./assets/index.css" in item for item in failures))
        self.assertTrue(any("./assets/index.js" in item for item in failures))
        self.assertIn("missing inline module script", failures)
        self.assertIn("missing inline stylesheet", failures)

    def test_allows_embedded_and_anchor_references(self) -> None:
        self.assertFalse(is_external_asset("data:image/png;base64,abc"))
        self.assertFalse(is_external_asset("#/metrics"))
        self.assertTrue(is_external_asset("./assets/index.js"))
        self.assertTrue(is_external_asset("https://example.com/app.js"))


if __name__ == "__main__":
    unittest.main()
