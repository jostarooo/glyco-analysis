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
    if "https://" in html or "http://" in html:
        failures.append("absolute URL found in self-contained deck")

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
            "delivery",
            "boundaries",
            "next",
        }
        if set(story) != expected_keys:
            failures.append("story top-level shape changed")
        if len(story.get("weeks", [])) != 8:
            failures.append("story must contain eight slides")
        expected_ids = ["cover", "w1", "w2", "tracks", "f2", "f3", "delivery", "boundaries"]
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
        print(f"PASS Edge file:// mount and eight-slide routing: {index.as_uri()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
