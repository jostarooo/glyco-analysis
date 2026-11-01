"""Move accidental W3 labels from 2026-10-30 to 2026-11-01 back into W2.

The project uses W2 Day 1 to mean 2026-10-28. Earlier work accidentally named
the next three workdays W3. This command renames those paths and updates exact
references. Run without arguments to check, or pass --write to migrate.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PATH_RENAMES = {
    "docs/W3_D1_tool_blocker_triage.txt": "docs/W2_D3_tool_blocker_triage.txt",
    "scripts/build_w3_scorecard.py": "scripts/build_w2_scorecard.py",
    "tests/test_w3_scorecard.py": "tests/test_w2_scorecard.py",
    "reports/w3_day1": "reports/w2_day3",
    "reports/w3_day2": "reports/w2_day4",
    "reports/w3_day3": "reports/w2_day5",
}

TEXT_REPLACEMENTS = {
    b"docs/W3_D1_tool_blocker_triage.txt": b"docs/W2_D3_tool_blocker_triage.txt",
    b"scripts/build_w3_scorecard.py": b"scripts/build_w2_scorecard.py",
    b"tests/test_w3_scorecard.py": b"tests/test_w2_scorecard.py",
    b"reports/w3_day1": b"reports/w2_day3",
    b"reports/w3_day2": b"reports/w2_day4",
    b"reports/w3_day3": b"reports/w2_day5",
    b"W3 Day 1": b"W2 Day 3",
    b"W3 Day 2": b"W2 Day 4",
    b"W3 Day 3": b"W2 Day 5",
    b"W3 Day1": b"W2 Day3",
    b"W3 Day2": b"W2 Day4",
    b"W3 Day3": b"W2 Day5",
    b"W3_D1_tool_blocker_triage": b"W2_D3_tool_blocker_triage",
    b"build_w3_scorecard": b"build_w2_scorecard",
    b"test_w3_scorecard": b"test_w2_scorecard",
    b"w3_day1": b"w2_day3",
    b"w3_day2": b"w2_day4",
    b"w3_day3": b"w2_day5",
    b"w3_classes": b"recheck_classes",
    b"w3-scorecard-references": b"w2-day4-scorecard-references",
    b"w3-scorecard": b"w2-day4-scorecard",
    b"w3_recheck_summary": b"recheck_summary",
}


def _tracked_files() -> list[str]:
    raw = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"])
    return [item.decode("utf-8") for item in raw.split(b"\0") if item]


def _new_path(path: Path) -> Path:
    relative = path.relative_to(ROOT).as_posix()
    for old, new in sorted(PATH_RENAMES.items(), key=lambda item: -len(item[0])):
        if relative == old or relative.startswith(old + "/"):
            return ROOT / (new + relative[len(old) :])
    return path


def _legacy_paths() -> list[Path]:
    found: list[Path] = []
    for old in PATH_RENAMES:
        path = ROOT / old
        if path.exists():
            found.append(path)
    return found


def _legacy_text_files(tracked: list[str]) -> list[tuple[Path, bytes]]:
    found: list[tuple[Path, bytes]] = []
    for item in tracked:
        source = _new_path(ROOT / item)
        if source == Path(__file__).resolve():
            continue
        if not source.is_file() or source.stat().st_size > 5 * 1024 * 1024:
            continue
        data = source.read_bytes()
        if any(old in data for old in TEXT_REPLACEMENTS):
            found.append((source, data))
    return found


def _migrate_paths() -> None:
    for old, new in sorted(
        PATH_RENAMES.items(), key=lambda item: (-item[0].count("/"), -len(item[0]))
    ):
        source = ROOT / old
        target = ROOT / new
        if not source.exists():
            continue
        if target.exists():
            raise RuntimeError(f"refusing to overwrite existing target: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)


def _migrate_text(tracked: list[str]) -> int:
    changed = 0
    for source, data in _legacy_text_files(tracked):
        updated = data
        for old, new in TEXT_REPLACEMENTS.items():
            updated = updated.replace(old, new)
        if updated != data:
            source.write_bytes(updated)
            changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    tracked = _tracked_files()
    if not args.write:
        paths = _legacy_paths()
        files = _legacy_text_files(tracked)
        if paths or files:
            for path in paths:
                print(f"LEGACY PATH: {path.relative_to(ROOT).as_posix()}")
            for path, _ in files:
                print(f"LEGACY TEXT: {path.relative_to(ROOT).as_posix()}")
            return 1
        print("PASS: no accidental W3 labels remain for W2 work")
        return 0

    _migrate_paths()
    changed = _migrate_text(tracked)
    print(f"PASS: renamed {len(PATH_RENAMES)} legacy path groups; updated {changed} text files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
