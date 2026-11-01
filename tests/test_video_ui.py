from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_video_ui as builder  # noqa: E402


HEAD = "a" * 40


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs}
        if tag == "script" and values.get("src"):
            self.references.append(values["src"] or "")
        elif tag == "link" and values.get("href"):
            rel = (values.get("rel") or "").lower()
            if rel in {"stylesheet", "modulepreload", "preload", "icon"}:
                self.references.append(values["href"] or "")
        elif tag in {"img", "source", "audio", "video", "iframe"} and values.get("src"):
            self.references.append(values["src"] or "")


class VideoStoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.story = builder.build_story(ROOT, head=HEAD)
        cls.story_bytes, cls.html_bytes = builder.render_bundle(ROOT, cls.story)

    def test_top_level_shape_is_exact(self) -> None:
        self.assertEqual(
            list(self.story),
            ["schema_version", "meta", "weeks", "tracks", "delivery", "boundaries", "next"],
        )

    def test_eight_slide_projection(self) -> None:
        self.assertEqual(len(self.story["weeks"]), 8)
        self.assertEqual(
            [slide["id"] for slide in self.story["weeks"]],
            ["cover", "w1", "w2", "tracks", "f2", "f3", "delivery", "boundaries"],
        )
        self.assertEqual(self.story["meta"]["slide_count"], 8)
        self.assertEqual(self.story["meta"]["head_commit"], HEAD)

    def test_every_source_hash_matches_disk(self) -> None:
        self.assertGreaterEqual(len(self.story["meta"]["sources"]), 8)
        for source in self.story["meta"]["sources"]:
            path = ROOT / source["path"]
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source["sha256"])
            self.assertEqual(len(raw), source["bytes"])

    def test_source_values_are_extracted_not_retyped(self) -> None:
        w1 = json.loads((ROOT / "reports/w1_three_method_v0/manifest.json").read_text(encoding="utf-8"))
        f2 = json.loads((ROOT / "reports/w2_day1/glycanml_rgcn_recompute.json").read_text(encoding="utf-8"))
        f3 = json.loads((ROOT / "reports/w2_day2/f3_qwen3_4b_50/summary.json").read_text(encoding="utf-8"))
        tools = json.loads((ROOT / "reports/w2_day1/doc2agent_tools_summary.json").read_text(encoding="utf-8"))
        scorecard = json.loads((ROOT / "reports/w2_day4/scorecard.json").read_text(encoding="utf-8"))

        w1_slide = self.story["weeks"][1]
        self.assertEqual(w1_slide["benchmark"]["evaluation_rows"], w1["benchmark"]["evaluation_rows"])
        self.assertEqual(w1_slide["benchmark"]["experimental_positive"], w1["benchmark"]["experimental_positive"])
        self.assertEqual(w1_slide["benchmark"]["unannotated_control"], w1["benchmark"]["unannotated_control"])
        self.assertEqual(w1_slide["benchmark"]["inferred_display_only"], w1["benchmark"]["inferred_display_only"])
        self.assertEqual(
            w1_slide["review_counts"]["reviewed_total"],
            sum(w1["manual_review"]["status_counts"].values()),
        )

        f2_track = next(item for item in self.story["tracks"] if item["code"] == "F2")
        immuno = f2_track["tasks"]["immunogenicity"]
        glyco = f2_track["tasks"]["glycosylation"]
        self.assertEqual(
            immuno["mean"],
            f2["tasks"]["immunogenicity"]["aggregate"]["test_auprc"]["mean"],
        )
        self.assertEqual(
            immuno["std"],
            f2["tasks"]["immunogenicity"]["aggregate"]["test_auprc"]["std"],
        )
        self.assertEqual(
            glyco["mean"],
            f2["tasks"]["glycosylation"]["aggregate"]["test_macro_f1"]["mean"],
        )
        self.assertEqual(
            glyco["std"],
            f2["tasks"]["glycosylation"]["aggregate"]["test_macro_f1"]["std"],
        )

        f3_track = next(item for item in self.story["tracks"] if item["code"] == "F3")
        for key in (
            "tasks_run",
            "exact_sequence",
            "all_expected_called",
            "any_expected_called",
            "tasks_with_final_answer",
            "tool_call_successes",
            "tool_calls",
        ):
            self.assertEqual(f3_track["trajectory"][key], f3[key])
        self.assertEqual(f3_track["tools"]["total"], tools["total_tools"])
        self.assertEqual(f3_track["tools"]["direct_ok"], tools["directly_ok"])
        self.assertEqual(f3_track["tools"]["service_alive"], tools["service_alive"])
        self.assertEqual(
            f3_track["feasibility"]["direct"],
            scorecard["feasibility"]["counts"]["current_tools_direct"],
        )
        self.assertEqual(
            f3_track["feasibility"]["replacement"],
            scorecard["feasibility"]["counts"]["needs_replacement_tool"],
        )
        self.assertEqual(
            f3_track["feasibility"]["service_failure"],
            scorecard["feasibility"]["counts"]["service_failure"],
        )

    def test_rendered_html_has_no_external_assets(self) -> None:
        html = self.html_bytes.decode("utf-8")
        parser = AssetParser()
        parser.feed(html)
        self.assertEqual(parser.references, [])
        self.assertNotIn("@import", html)
        self.assertNotIn("url(http", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("fetch(", html)
        self.assertIn('id="deck"', html)
        self.assertIn('id="story-data"', html)

    def test_generation_is_byte_deterministic(self) -> None:
        story = builder.build_story(ROOT, head=HEAD)
        story_bytes, html_bytes = builder.render_bundle(ROOT, story)
        self.assertEqual(story_bytes, self.story_bytes)
        self.assertEqual(html_bytes, self.html_bytes)
        again = builder.render_bundle(ROOT, builder.build_story(ROOT, head=HEAD))
        self.assertEqual(again, (story_bytes, html_bytes))

    def test_check_rejects_tamper_and_missing_outputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyco-video-test-") as temp:
            artifact_root = Path(temp) / "video-ui"
            builder.write_bundle(artifact_root, self.story_bytes, self.html_bytes)
            self.assertEqual(
                builder.verify_bundle(artifact_root, self.story_bytes, self.html_bytes),
                [],
            )
            index = artifact_root / builder.INDEX_REL
            index.write_bytes(index.read_bytes() + b"\n<!-- tampered -->\n")
            failures = builder.verify_bundle(artifact_root, self.story_bytes, self.html_bytes)
            self.assertTrue(any("index.html: differs" in failure for failure in failures))

            index.unlink()
            failures = builder.verify_bundle(artifact_root, self.story_bytes, self.html_bytes)
            self.assertTrue(any("index.html: missing" in failure for failure in failures))

    def test_keyboard_control_contract(self) -> None:
        script = (ROOT / "video-ui/src/deck.js").read_text(encoding="utf-8")
        for token in (
            "ArrowRight",
            "PageDown",
            "ArrowLeft",
            "PageUp",
            "Home",
            "End",
            'key.toLowerCase() === "n"',
            'key.toLowerCase() === "f"',
            "/^[1-8]$/",
        ):
            self.assertIn(token, script)

    def test_boundary_language_is_present(self) -> None:
        text = "\n".join(boundary["text"] for boundary in self.story["boundaries"])
        self.assertIn("Table 3", text)
        self.assertIn("TorchDrug", text)
        self.assertIn("轨迹", text)
        self.assertIn("答案正确率", text)
        self.assertIn("未标注", text)
        self.assertIn("TLS", text)

    def test_scientific_values_are_not_copied_into_renderer_sources(self) -> None:
        renderer = (ROOT / "video-ui/src/deck.js").read_text(encoding="utf-8")
        template = (ROOT / "video-ui/src/template.html").read_text(encoding="utf-8")
        joined = renderer + "\n" + template
        forbidden = [
            "0.7748635136784087",
            "0.009111853148723878",
            "0.9377928560029268",
            "0.0038891301525018625",
            "0.8483488428592927",
            "人工复核 10 个",
            "50 题按当前工具",
        ]
        for value in forbidden:
            self.assertNotIn(value, joined)


if __name__ == "__main__":
    unittest.main()
