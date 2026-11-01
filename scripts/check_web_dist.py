#!/usr/bin/env python3
"""Verify that the production interface can run directly from file://."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "web" / "dist" / "index.html"
DEFAULT_EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self.has_inline_module = False
        self.has_inline_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs}
        if tag == "script":
            source = values.get("src")
            if source:
                self.references.append(source)
            if (values.get("type") or "").lower() == "module" and not source:
                self.has_inline_module = True
        elif tag == "link":
            rel = (values.get("rel") or "").lower()
            if rel in {"stylesheet", "modulepreload", "preload"} and values.get("href"):
                self.references.append(values["href"] or "")
        elif tag in {"img", "source", "audio", "video", "iframe"} and values.get("src"):
            self.references.append(values["src"] or "")
        elif tag == "style":
            self.has_inline_style = True


def is_external_asset(reference: str) -> bool:
    value = reference.strip().lower()
    return not (
        not value
        or value.startswith("#")
        or value.startswith("data:")
        or value.startswith("javascript:")
        or value.startswith("mailto:")
    )


def check_html(html: str) -> list[str]:
    parser = AssetParser()
    parser.feed(html)
    failures: list[str] = []
    external = sorted({ref for ref in parser.references if is_external_asset(ref)})
    if external:
        failures.append("external asset references: " + ", ".join(external))
    if not parser.has_inline_module:
        failures.append("missing inline module script")
    if not parser.has_inline_style:
        failures.append("missing inline stylesheet")
    if 'id="root"' not in html:
        failures.append('missing id="root" mount point')
    return failures


def dump_dom(index: Path, edge: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="glyco-web-file-") as profile:
        command = [
            str(edge),
            "--headless",
            "--disable-gpu",
            "--no-first-run",
            f"--user-data-dir={profile}",
            "--virtual-time-budget=3000",
            "--dump-dom",
            index.resolve().as_uri(),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--edge", type=Path, default=DEFAULT_EDGE)
    parser.add_argument(
        "--browser",
        action="store_true",
        help="also load the artifact through Edge using file://",
    )
    args = parser.parse_args()

    index = args.index.resolve()
    if not index.is_file():
        print(f"FAIL missing production build: {index}")
        return 1

    html = index.read_text(encoding="utf-8")
    failures = check_html(html)
    if failures:
        print(f"FAIL {index}")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"PASS static single-file contract: {index}")
    print(f"- bytes: {index.stat().st_size}")

    if args.browser:
        if not args.edge.is_file():
            print(f"FAIL Edge executable not found: {args.edge}")
            return 1
        dom = dump_dom(index, args.edge)
        if 'class="app-shell"' not in dom:
            print(f"FAIL Edge did not mount the app from {index.as_uri()}")
            return 1
        print(f"PASS Edge file:// mount: {index.as_uri()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
