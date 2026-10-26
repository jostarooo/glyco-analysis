"""Build and verify the W1 delivery tree from repository artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DELIVERY_ROOT = Path(r"D:\毕设交付\W1_完整交付_v1")
OFFICIAL_WEEK = Path(r"D:\毕设交付\W01_2026-10-27")

REPORT_COPIES = {
    "reports/weekly/W01_2026-10-27_progress.md": (
        "02-进度报告/W01_2026-10-27_progress.md"
    ),
    "reports/esm150_lora_repro_v0/report.md": (
        "03-附件材料/ESM150_LoRA 复算/report.md"
    ),
    "reports/esm150_w1_candidates_v0/report.md": (
        "03-附件材料/三方法对拍/ESM150候选推理/report.md"
    ),
    "reports/w1_three_method_v0/report.md": "03-附件材料/三方法对拍/report.md",
    "reports/mcc_repro.md": "06-核心数据/mcc_repro.md",
    "reports/esm150_lora_recheck_2026-10-26.md": (
        "06-核心数据/esm150_lora_recheck_2026-10-26.md"
    ),
}

GITHUB_RECORD_DIR = "reports"
GITHUB_RECORD_GLOB = "github_publish_*.md"
GITHUB_RECORD_DESTINATION = "04-GitHub 发布记录"

PROJECT_DOCUMENT_COPIES = {
    "README.md": "07-项目文档/项目README.md",
    "REPRO.md": "07-项目文档/REPRO.md",
    "LESSONS.md": "07-项目文档/LESSONS.md",
    "pyproject.toml": "07-项目文档/pyproject.toml",
    ".gitignore": "07-项目文档/gitignore.txt",
}

CORE_DATA_COPIES = {
    "reports/candidates_30.csv": "06-核心数据/candidates_30.csv",
    "reports/candidates_30_lora.csv": "06-核心数据/candidates_30_lora.csv",
    "reports/dataset_v0.md": "06-核心数据/dataset_v0.md",
    "reports/dataset_v0_stats.json": "06-核心数据/dataset_v0_stats.json",
    "reports/endpoint_check_2026-10-18.md": (
        "06-核心数据/endpoint_check_2026-10-18.md"
    ),
    "reports/env_check.md": "06-核心数据/env_check.md",
    "reports/esm35_provenance_recheck_2026-10-26.md": (
        "06-核心数据/esm35_provenance_recheck_2026-10-26.md"
    ),
    "reports/mcc_repro.md": "06-核心数据/mcc_repro.md",
    "reports/esm150_lora_recheck_2026-10-26.md": (
        "06-核心数据/esm150_lora_recheck_2026-10-26.md"
    ),
}

PACKAGE_TREE_COPIES = {
    "reports/esm35_linear_probe_v0": "03-附件材料/ESM35 线性探针",
    "reports/esm150_lora_repro_v0": "03-附件材料/ESM150_LoRA 复算",
    "reports/esm150_w1_candidates_v0": "03-附件材料/三方法对拍/ESM150候选推理",
}

W1_PACKAGE_FILES = {
    "reports/w1_three_method_v0/comparison.csv": "03-附件材料/三方法对拍/comparison.csv",
    "reports/w1_three_method_v0/manifest.json": "03-附件材料/三方法对拍/manifest.json",
    "reports/w1_three_method_v0/metrics.json": "03-附件材料/三方法对拍/metrics.json",
    "reports/w1_three_method_v0/report.md": "03-附件材料/三方法对拍/report.md",
    "reports/w1_three_method_v0/review_top10.csv": (
        "03-附件材料/三方法对拍/review_top10.csv"
    ),
}

OFFICIAL_TREE_COPIES = {
    "reports/esm35_linear_probe_v0": "03-附件材料/ESM35线性探针_v0",
    "reports/esm150_lora_repro_v0": "03-附件材料/ESM150_LoRA复算_v0",
    "reports/esm150_w1_candidates_v0": (
        "03-附件材料/W1三方法对拍_v0/ESM150候选推理_v0"
    ),
}

W1_OFFICIAL_FILES = {
    "reports/w1_three_method_v0/comparison.csv": (
        "03-附件材料/W1三方法对拍_v0/三方法对拍产物_v0/comparison.csv"
    ),
    "reports/w1_three_method_v0/manifest.json": (
        "03-附件材料/W1三方法对拍_v0/三方法对拍产物_v0/manifest.json"
    ),
    "reports/w1_three_method_v0/metrics.json": (
        "03-附件材料/W1三方法对拍_v0/三方法对拍产物_v0/metrics.json"
    ),
    "reports/w1_three_method_v0/report.md": (
        "03-附件材料/W1三方法对拍_v0/三方法对拍产物_v0/report.md"
    ),
    "reports/w1_three_method_v0/review_top10.csv": (
        "03-附件材料/W1三方法对拍_v0/三方法对拍产物_v0/review_top10.csv"
    ),
}

OFFICIAL_ALIAS_COPIES = {
    "reports/esm35_linear_probe_v0/report.md": (
        "03-附件材料/2026-10-20_ESM35线性探针说明.md"
    ),
    "reports/esm150_lora_repro_v0/report.md": (
        "03-附件材料/2026-10-21_F1_ESM150_LoRA复算说明.md"
    ),
    "reports/w1_three_method_v0/report.md": (
        "03-附件材料/2026-10-22_W1三方法对拍说明.md"
    ),
    "reports/github_publish_2026-10-18.md": (
        "03-附件材料/2026-10-18_W01_GitHub发布记录.md"
    ),
    "reports/github_publish_2026-10-19.md": (
        "03-附件材料/2026-10-19_GitHub发布记录.md"
    ),
    "reports/github_publish_2026-10-20.md": (
        "03-附件材料/2026-10-20_GitHub发布记录.md"
    ),
    "reports/github_publish_2026-10-21.md": (
        "03-附件材料/2026-10-21_GitHub发布记录.md"
    ),
    "reports/github_publish_2026-10-22.md": (
        "03-附件材料/2026-10-22_GitHub发布记录.md"
    ),
    "reports/github_publish_2026-10-23.md": (
        "03-附件材料/2026-10-23_GitHub发布记录.md"
    ),
    "reports/github_publish_2026-10-25.md": (
        "03-附件材料/2026-10-25_GitHub发布记录.md"
    ),
}

OFFICIAL_EXTRA_ALIAS_COPIES = {
    "reports/github_publish_2026-10-23.md": (
        "03-附件材料/W1三方法对拍_v0/2026-10-23_GitHub发布记录.md"
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def replace_tree(source: Path, destination: Path) -> None:
    require(source.is_dir(), f"Missing source directory: {source}")
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def markdown_files(root: Path) -> Iterable[Path]:
    return (
        path
        for path in root.rglob("*.md")
        if path.is_file() and "_废弃" not in path.parts
    )


def contains_han(text: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in text)


def validate_review_csv(root: Path) -> None:
    review_path = root / "05-人工复核/review_top10.csv"
    require(review_path.is_file(), f"Missing manual review CSV: {review_path}")
    with review_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    require(len(rows) == 10, "Manual review CSV must contain ten rows")
    prose_columns = (
        "selection_criteria",
        "manual_review_question",
        "reviewer_note",
    )
    for row_number, row in enumerate(rows, start=2):
        for column in prose_columns:
            value = row.get(column, "")
            require(
                contains_han(value),
                f"review_top10.csv:{row_number}: {column} must contain Chinese prose",
            )


def validate_markdown(root: Path) -> None:
    failures: list[str] = []
    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root).as_posix()
        if not contains_han(text):
            failures.append(f"{relative}: does not contain Chinese prose")
        if "\ufffd" in text:
            failures.append(f"{relative}: contains U+FFFD")
        if text.startswith("\ufeff"):
            failures.append(f"{relative}: contains UTF-8 BOM")
        in_code_block = False
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "\ufffd" in line:
                failures.append(f"{relative}:{line_number}: contains U+FFFD")
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            if (
                len(stripped) >= 24
                and stripped[0].isascii()
                and stripped[0].isalpha()
                and sum(character.isalpha() for character in stripped) >= 20
                and all(ord(character) < 128 for character in stripped)
                and "  " not in stripped
                and not stripped.startswith(("http://", "https://", "|"))
                and not stripped.startswith(
                    ("$", "&", ".venv", "D:\\", "PowerShell", "cd ", "base_model.")
                )
            ):
                failures.append(f"{relative}:{line_number}: untranslated English prose: {stripped}")
    require(not failures, "Markdown validation failed:\n" + "\n".join(failures))


def validate_json_files(root: Path) -> None:
    failures: list[str] = []
    for path in root.rglob("*.json"):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        if b"\r\n" in raw:
            failures.append(f"{relative}: contains CRLF")
        if b'":  ' in raw:
            failures.append(f"{relative}: contains doubled JSON spacing")
        try:
            json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            failures.append(f"{relative}: invalid UTF-8 JSON: {error}")
    require(not failures, "JSON validation failed:\n" + "\n".join(failures))


def write_checksums(root: Path) -> tuple[int, int]:
    checksum_path = root / "SHA256SUMS.txt"
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path != checksum_path
    )
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in files]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(files), len(lines)


def write_nested_checksums(root: Path) -> tuple[int, int]:
    checksum_path = root / "SHA256SUMS.txt"
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path != checksum_path
    )
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in files]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(files), len(lines)


def verify_checksums(root: Path) -> tuple[int, int, int]:
    checksum_path = root / "SHA256SUMS.txt"
    lines = [
        line
        for line in checksum_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matches = 0
    mismatches = 0
    missing = 0
    for line in lines:
        digest, relative = line.split("  ", 1)
        path = root / relative
        if not path.is_file():
            missing += 1
        elif sha256_file(path) == digest:
            matches += 1
        else:
            mismatches += 1
    return matches, mismatches, missing


def sync_delivery() -> None:
    for source_relative, destination_relative in REPORT_COPIES.items():
        source = REPO_ROOT / source_relative
        require(source.is_file(), f"Missing report source: {source}")
        copy_file(source, DELIVERY_ROOT / destination_relative)

    for source_relative, destination_relative in PROJECT_DOCUMENT_COPIES.items():
        source = REPO_ROOT / source_relative
        require(source.is_file(), f"Missing document file: {source}")
        copy_file(source, DELIVERY_ROOT / destination_relative)

    for source_relative, destination_relative in CORE_DATA_COPIES.items():
        source = REPO_ROOT / source_relative
        require(source.is_file(), f"Missing core data file: {source}")
        copy_file(source, DELIVERY_ROOT / destination_relative)

    for source_relative, destination_relative in PACKAGE_TREE_COPIES.items():
        replace_tree(
            REPO_ROOT / source_relative,
            DELIVERY_ROOT / destination_relative,
        )

    for source_relative, destination_relative in W1_PACKAGE_FILES.items():
        copy_file(
            REPO_ROOT / source_relative,
            DELIVERY_ROOT / destination_relative,
        )

    copy_file(
        REPO_ROOT / "reports/w1_three_method_v0/review_top10.csv",
        DELIVERY_ROOT / "05-人工复核/review_top10.csv",
    )

    replace_tree(REPO_ROOT / "scripts", DELIVERY_ROOT / "08-源代码/scripts")
    replace_tree(REPO_ROOT / "tests", DELIVERY_ROOT / "08-源代码/tests")

    official_report = OFFICIAL_WEEK / "02-进度报告/2026-10-27_W01_进度报告.md"
    copy_file(
        REPO_ROOT / "reports/weekly/W01_2026-10-27_progress.md",
        official_report,
    )

    for source_relative, destination_relative in OFFICIAL_TREE_COPIES.items():
        replace_tree(
            REPO_ROOT / source_relative,
            OFFICIAL_WEEK / destination_relative,
        )

    for source_relative, destination_relative in W1_OFFICIAL_FILES.items():
        copy_file(REPO_ROOT / source_relative, OFFICIAL_WEEK / destination_relative)

    for source_relative, destination_relative in PROJECT_DOCUMENT_COPIES.items():
        copy_file(
            REPO_ROOT / source_relative,
            OFFICIAL_WEEK / destination_relative,
        )

    for source_relative, destination_relative in CORE_DATA_COPIES.items():
        copy_file(
            REPO_ROOT / source_relative,
            OFFICIAL_WEEK / destination_relative.replace("06-核心数据/", "03-附件材料/"),
        )

    replace_tree(REPO_ROOT / "scripts", OFFICIAL_WEEK / "08-源代码/scripts")
    replace_tree(REPO_ROOT / "tests", OFFICIAL_WEEK / "08-源代码/tests")

    github_records = sorted((REPO_ROOT / GITHUB_RECORD_DIR).glob(GITHUB_RECORD_GLOB))
    require(github_records, "Missing GitHub publication records")
    for source in github_records:
        copy_file(source, DELIVERY_ROOT / GITHUB_RECORD_DESTINATION / source.name)
        copy_file(source, OFFICIAL_WEEK / "03-附件材料" / source.name)

    for alias_map in (OFFICIAL_ALIAS_COPIES, OFFICIAL_EXTRA_ALIAS_COPIES):
        for source_relative, destination_relative in alias_map.items():
            source = REPO_ROOT / source_relative
            require(source.is_file(), f"Missing official alias source: {source}")
            copy_file(source, OFFICIAL_WEEK / destination_relative)

    for filename in (
        "esm150_lora_recheck_2026-10-26.md",
        "esm35_provenance_recheck_2026-10-26.md",
        "mcc_repro.md",
    ):
        copy_file(
            REPO_ROOT / "reports" / filename,
            OFFICIAL_WEEK / "03-附件材料" / filename,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    if not args.verify_only:
        sync_delivery()

    validate_markdown(DELIVERY_ROOT)
    validate_review_csv(DELIVERY_ROOT)
    validate_json_files(DELIVERY_ROOT)
    validate_markdown(OFFICIAL_WEEK)
    validate_json_files(OFFICIAL_WEEK)
    write_nested_checksums(DELIVERY_ROOT / "03-附件材料/三方法对拍")
    write_nested_checksums(OFFICIAL_WEEK / "03-附件材料/W1三方法对拍_v0")
    expected_video = DELIVERY_ROOT / "01-视频/2026-10-27_W01_周视频.mp4"
    video_state = "present" if expected_video.is_file() else "pending"
    checksum_files, checksum_lines = write_checksums(DELIVERY_ROOT)
    official_checksum_files, _ = write_checksums(OFFICIAL_WEEK)
    checksum_matches, checksum_mismatches, checksum_missing = verify_checksums(
        DELIVERY_ROOT
    )
    official_matches, official_mismatches, official_missing = verify_checksums(
        OFFICIAL_WEEK
    )
    require(checksum_mismatches == 0, f"SHA256 mismatches: {checksum_mismatches}")
    require(checksum_missing == 0, f"SHA256 missing files: {checksum_missing}")
    require(
        official_mismatches == 0,
        f"Official SHA256 mismatches: {official_mismatches}",
    )
    require(
        official_missing == 0,
        f"Official SHA256 missing files: {official_missing}",
    )

    tree = git_output("rev-parse", "HEAD^{tree}")
    summary = {
        "status": "PASS" if video_state == "present" else "PASS_WITH_VIDEO_PENDING",
        "delivery_root": str(DELIVERY_ROOT),
        "delivery_files": checksum_files + 1,
        "checksum_entries": checksum_lines,
        "checksum_matches": checksum_matches,
        "checksum_mismatches": checksum_mismatches,
        "checksum_missing": checksum_missing,
        "official_checksum_matches": official_matches,
        "official_checksum_mismatches": official_mismatches,
        "official_checksum_missing": official_missing,
        "official_delivery_files": official_checksum_files + 1,
        "video": video_state,
        "video_path": str(expected_video),
        "head": git_output("rev-parse", "HEAD"),
        "tree": tree,
        "tracked_files": len(git_output("ls-files").splitlines()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
