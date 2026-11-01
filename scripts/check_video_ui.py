#!/usr/bin/env python3
"""Check the recording-only deck statically and through Edge file://."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_video_ui as builder  # noqa: E402


DEFAULT_INDEX = ROOT / "video-ui" / "dist" / "index.html"
DEFAULT_EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


class DeckParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self.in_story = False
        self.story_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs}
        if tag == "script":
            source = values.get("src")
            if source:
                self.references.append(source)
            if values.get("id") == "story-data":
                self.in_story = True
        elif tag == "link" and values.get("href"):
            rel = (values.get("rel") or "").lower()
            if rel in {"stylesheet", "modulepreload", "preload", "icon"}:
                self.references.append(values["href"] or "")
        elif tag in {"img", "source", "audio", "video", "iframe"} and values.get("src"):
            self.references.append(values["src"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.in_story:
            self.in_story = False

    def handle_data(self, data: str) -> None:
        if self.in_story:
            self.story_chunks.append(data)


def is_external(reference: str) -> bool:
    value = reference.strip().lower()
    return not (
        not value
        or value.startswith("#")
        or value.startswith("data:")
        or value.startswith("javascript:")
    )


def static_check(index: Path) -> tuple[list[str], dict | None]:
    failures: list[str] = []
    if not index.is_file():
        return [f"missing index: {index}"], None

    expected_story = builder.build_story(ROOT)
    story_bytes, html_bytes = builder.render_bundle(ROOT, expected_story)
    failures.extend(
        builder.verify_bundle(ROOT / "video-ui", story_bytes, html_bytes)
    )

    html = index.read_text(encoding="utf-8")
    parser = DeckParser()
    parser.feed(html)
    external = sorted({ref for ref in parser.references if is_external(ref)})
    if external:
        failures.append("external references: " + ", ".join(external))
    if 'id="deck"' not in html:
        failures.append('missing id="deck"')
    if "data-deck-mounted=\"false\"" not in html:
        failures.append("missing static deck mount marker")
    if "__STORY_JSON__" in html or "__DECK_CSS__" in html or "__DECK_JS__" in html:
        failures.append("unrendered template marker remains")
    if "fetch(" in html or "XMLHttpRequest" in html:
        failures.append("network API found in self-contained deck")
    if "url(http" in html:
        failures.append("remote CSS asset found in self-contained deck")

    story = None
    try:
        story = json.loads("".join(parser.story_chunks))
    except json.JSONDecodeError as exc:
        failures.append(f"story JSON does not parse: {exc}")

    if story is not None:
        expected_keys = {
            "schema_version",
            "meta",
            "weeks",
            "tracks",
            "demos",
            "delivery",
            "boundaries",
            "next",
        }
        if set(story) != expected_keys:
            failures.append("story top-level shape changed")
        if len(story.get("weeks", [])) != 9:
            failures.append("story must contain nine slides")
        expected_ids = [
            "cover",
            "w1",
            "f1demo",
            "w2",
            "tracks",
            "f2",
            "f3",
            "delivery",
            "boundaries",
        ]
        actual_ids = [slide.get("id") for slide in story.get("weeks", [])]
        if actual_ids != expected_ids:
            failures.append(f"slide ids differ: {actual_ids}")
        if len(story.get("meta", {}).get("head_commit", "")) != 40:
            failures.append("story head_commit is not a full git SHA")
    return failures, story


def dump_dom(
    index: Path,
    edge: Path,
    suffix: str = "",
    window_size: tuple[int, int] = (1920, 1080),
) -> str:
    with tempfile.TemporaryDirectory(prefix="glyco-recording-") as profile:
        command = [
            str(edge),
            "--headless",
            "--disable-gpu",
            "--no-first-run",
            f"--window-size={window_size[0]},{window_size[1]}",
            f"--user-data-dir={profile}",
            "--virtual-time-budget=2500",
            "--dump-dom",
            index.resolve().as_uri() + suffix,
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=45,
        )
    if completed.returncode != 0:
        details = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Edge exited with {completed.returncode}: {details[-1000:]}")
    return completed.stdout.decode("utf-8", errors="replace")


def browser_check(index: Path, edge: Path, story: dict) -> list[str]:
    failures: list[str] = []
    if not edge.is_file():
        return [f"Edge executable not found: {edge}"]

    expected = [(slide["slide"], slide["id"]) for slide in story["weeks"]]
    viewports = ((1920, 1080), (1366, 768))
    for width, height in viewports:
        for number, slide_id in expected:
            dom = dump_dom(index, edge, f"?slide={number}", (width, height))
            if 'data-deck-mounted="true"' not in dom:
                failures.append(f"slide {number} at {width}x{height}: deck did not mount")
                continue
            if f'data-active-slide="{number}"' not in dom:
                failures.append(f"slide {number} at {width}x{height}: active slide marker missing")
            if f'data-slide-id="{slide_id}"' not in dom:
                failures.append(
                    f"slide {number} at {width}x{height}: expected id {slide_id!r} absent"
                )
            if story["meta"]["head_commit"] not in dom:
                failures.append(f"slide {number} at {width}x{height}: full head commit absent")
            if 'data-layout-ok="true"' not in dom:
                failures.append(f"slide {number} at {width}x{height}: viewport overflow detected")

    notes_dom = dump_dom(index, edge, "?slide=3&notes=1")
    if 'data-notes-visible="true"' not in notes_dom:
        failures.append("notes=1 did not open speaker notes")
    if 'aria-hidden="false"' not in notes_dom:
        failures.append("speaker notes aria-hidden did not update")
    return failures


def interactive_check(index: Path, edge: Path) -> list[str]:
    failures: list[str] = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ["Playwright is not installed in the active Python environment"]

    uri = index.resolve().as_uri()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(edge),
            headless=True,
        )
        try:
            for width, height in ((1920, 1080), (1366, 768)):
                page = browser.new_page(viewport={"width": width, "height": height})

                def goto_slide(number: int, label: str) -> bool:
                    page.goto(f"{uri}?slide={number}", wait_until="load")
                    page.wait_for_selector('#deck[data-deck-mounted="true"]')
                    layout_ok = page.locator("#deck").get_attribute("data-layout-ok")
                    if layout_ok != "true":
                        failures.append(f"{label} at {width}x{height}: layout overflow")
                        return False
                    body_text = page.locator("body").inner_text()
                    for malformed in ("[object Object]", "undefined"):
                        if malformed in body_text:
                            failures.append(
                                f"{label} at {width}x{height}: malformed text {malformed!r}"
                            )
                    return True

                if goto_slide(3, "F1 demo"):
                    initial_row = page.locator("[data-f1-row]").get_attribute("data-f1-row")
                    preset_count = page.locator('[data-demo="f1-preset"]').count()
                    if preset_count < 2:
                        failures.append(
                            f"F1 at {width}x{height}: expected at least two presets"
                        )
                    else:
                        if page.locator(".f1-matrix-row").count() != 4:
                            failures.append(
                                f"F1 at {width}x{height}: expected four matrix rows"
                            )
                        page.locator('[data-demo="f1-preset"]').nth(1).click()
                        changed_row = page.locator("[data-f1-row]").get_attribute(
                            "data-f1-row"
                        )
                        if changed_row == initial_row:
                            failures.append(
                                f"F1 at {width}x{height}: preset did not change candidate"
                            )
                        if page.locator(".f1-matrix-row.active").count() != 1:
                            failures.append(
                                f"F1 at {width}x{height}: active matrix row is ambiguous"
                            )

                    page.fill('[data-demo="f1-rule-input"]', "NST")
                    page.click('[data-demo="f1-rule-run"]')
                    page.wait_for_selector(".rule-result")
                    positive_count = page.locator(".rule-result").get_attribute(
                        "data-rule-match-count"
                    )
                    if positive_count != "1":
                        failures.append(
                            f"F1 at {width}x{height}: NST produced {positive_count} matches"
                        )
                    if "NST" not in page.locator(".rule-result").inner_text():
                        failures.append(
                            f"F1 at {width}x{height}: NST match text absent"
                        )

                    page.fill('[data-demo="f1-rule-input"]', "NPS")
                    page.click('[data-demo="f1-rule-run"]')
                    page.wait_for_selector(".rule-result")
                    negative_count = page.locator(".rule-result").get_attribute(
                        "data-rule-match-count"
                    )
                    if negative_count != "0":
                        failures.append(
                            f"F1 at {width}x{height}: NPS should be rejected"
                        )

                if goto_slide(6, "F2 demo"):
                    initial_task = page.locator(".f2-demo-slide").get_attribute(
                        "data-f2-task"
                    )
                    task_buttons = page.locator('[data-demo="f2-task"]')
                    if task_buttons.count() < 2:
                        failures.append(
                            f"F2 at {width}x{height}: task selector missing"
                        )
                    else:
                        task_buttons.nth(1).click()
                        changed_task = page.locator(".f2-demo-slide").get_attribute(
                            "data-f2-task"
                        )
                        if changed_task == initial_task:
                            failures.append(
                                f"F2 at {width}x{height}: task did not switch"
                            )
                    page.click('[data-demo="f2-seed"][data-seed="2"]')
                    if not page.locator('.f2-seed-detail[data-f2-seed="2"]').count():
                        failures.append(
                            f"F2 at {width}x{height}: seed 2 detail missing"
                        )
                    if page.locator(".seed-comparison-row").count() != 3:
                        failures.append(
                            f"F2 at {width}x{height}: expected three seed bars"
                        )
                    if page.locator(".seed-comparison-row.active").count() != 1:
                        failures.append(
                            f"F2 at {width}x{height}: active seed bar is ambiguous"
                        )
                    f2_text = page.locator(".f2-demo-slide").inner_text()
                    for malformed in ("[object Object]", "undefined"):
                        if malformed in f2_text:
                            failures.append(
                                f"F2 at {width}x{height}: malformed text {malformed!r}"
                            )
                    if page.locator("#deck").get_attribute("data-layout-ok") != "true":
                        failures.append(
                            f"F2 at {width}x{height}: layout overflow after interaction"
                        )

                if goto_slide(7, "F3 demo"):
                    page.select_option('[data-demo="f3-task"]', "3")
                    before = page.locator(".trace-step-list").get_attribute(
                        "data-visible-steps"
                    )
                    page.click('[data-demo="f3-next-step"]')
                    after = page.locator(".trace-step-list").get_attribute(
                        "data-visible-steps"
                    )
                    if int(after or "0") <= int(before or "0"):
                        failures.append(
                            f"F3 at {width}x{height}: next step did not reveal a call"
                        )
                    page.click('[data-demo="f3-all-steps"]')
                    if not page.locator(".final-answer").count():
                        failures.append(
                            f"F3 at {width}x{height}: final answer did not appear"
                        )
                    page.click('[data-demo="f3-filter"][data-filter="failure"]')
                    active_filter = page.locator(
                        '[data-demo="f3-filter"][data-filter="failure"]'
                    ).get_attribute("class")
                    if "active" not in (active_filter or ""):
                        failures.append(
                            f"F3 at {width}x{height}: failure filter did not activate"
                        )
                    if page.locator("#deck").get_attribute("data-layout-ok") != "true":
                        failures.append(
                            f"F3 at {width}x{height}: layout overflow after interaction"
                        )

                page.close()
        finally:
            browser.close()
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--edge", type=Path, default=DEFAULT_EDGE)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args(argv)

    index = args.index.resolve()
    failures, story = static_check(index)
    if failures:
        print(f"FAIL recording deck: {index}")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"PASS static self-contained contract: {index}")
    print(f"- bytes: {index.stat().st_size}")
    print(f"- slides: {len(story['weeks'])}")
    print(f"- head: {story['meta']['head_commit']}")

    if args.browser:
        try:
            failures = browser_check(index, args.edge.resolve(), story)
        except Exception as exc:
            print(f"FAIL Edge file:// check: {exc}")
            return 1
        if failures:
            print(f"FAIL Edge file:// check: {index.as_uri()}")
            for failure in failures:
                print(f"- {failure}")
            return 1
        print(f"PASS Edge file:// mount and nine-slide routing: {index.as_uri()}")
        try:
            failures = interactive_check(index, args.edge.resolve())
        except Exception as exc:
            print(f"FAIL interactive file:// check: {exc}")
            return 1
        if failures:
            print(f"FAIL interactive file:// check: {index.as_uri()}")
            for failure in failures:
                print(f"- {failure}")
            return 1
        print("PASS interactive F1/F2/F3 controls at 1920x1080 and 1366x768")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
