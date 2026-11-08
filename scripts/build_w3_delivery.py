from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path(r"D:\毕设交付\W03_2026-11-10")
EVIDENCE_DIR = Path("03-附件材料") / "W03_核心证据"


class DeliveryError(ValueError):
    pass


class DeliveryCheckError(RuntimeError):
    pass


class PackageFile(NamedTuple):
    source: str
    destination: str


PACKAGE_FILES = (
    PackageFile(
        "reports/weekly/W03_2026-11-10_progress.md",
        "02-进度报告/W03_2026-11-10_progress.md",
    ),
    PackageFile(
        "reports/w3_day5/video_script.md",
        "02-进度报告/2026-11-08_W03_周视频脚本.md",
    ),
    PackageFile(
        "reports/esm150_lora_repro_v0/metrics.json",
        f"{EVIDENCE_DIR}/2026-11-08_W3_F1_metrics.json",
    ),
    PackageFile(
        "reports/w2_day1/glycanml_rgcn_recompute.json",
        f"{EVIDENCE_DIR}/2026-11-08_W3_F2_recompute.json",
    ),
    PackageFile(
        "reports/w2_day4/reference_values.json",
        f"{EVIDENCE_DIR}/2026-11-08_W3_F2_reference_values.json",
    ),
    PackageFile(
        "reports/w3_day4/f3_three_model_report.json",
        f"{EVIDENCE_DIR}/2026-11-08_W3_F3_three_model_report.json",
    ),
    PackageFile(
        "reports/w3_day4/f3_three_model_report.md",
        f"{EVIDENCE_DIR}/2026-11-08_W3_F3_three_model_report.md",
    ),
    PackageFile(
        "reports/w3_day1/real_e2e_2026-11-04.json",
        f"{EVIDENCE_DIR}/2026-11-08_W3_system_e2e.json",
    ),
    PackageFile(
        "reports/w3_day5/checkpoint.json",
        f"{EVIDENCE_DIR}/2026-11-08_W3_checkpoint.json",
    ),
    PackageFile(
        "reports/w3_day5/checkpoint.md",
        f"{EVIDENCE_DIR}/2026-11-08_W3_checkpoint.md",
    ),
    PackageFile(
        "reports/w3_day5/validation_2026-11-08.md",
        f"{EVIDENCE_DIR}/2026-11-08_W3_validation.md",
    ),
    PackageFile(
        "reports/w3_day5/unittest_2026-11-08.txt",
        f"{EVIDENCE_DIR}/2026-11-08_W3_unittest.txt",
    ),
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _write_if_changed(path: Path, data: bytes) -> None:
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _evidence_readme() -> bytes:
    lines = [
        "# W03 核心证据",
        "",
        "本目录是 W3 11/10 检查点的自包含证据副本。所有文件均由 `scripts/build_w3_delivery.py`",
        "从仓库固定路径复制，不用手工编辑。根级 `SHA256SUMS.txt` 覆盖整个交付包，",
        "本目录的 `SHA256SUMS.txt` 覆盖核心证据。",
        "",
        "| 交付文件 | 仓库来源 |",
        "|---|---|",
    ]
    prefix = EVIDENCE_DIR.as_posix() + "/"
    for item in PACKAGE_FILES:
        if item.destination.startswith(prefix):
            lines.append(f"| `{Path(item.destination).name}` | `{item.source}` |")
    lines += [
        "",
        "## 口径",
        "",
        "- F2 对齐 GlycanML Table 3，不是 Table 2。",
        "- F2 是 PyG 自实现，不是 TorchDrug 逐位克隆。",
        "- F3 轨迹指标不是答案正确率。",
        "- Kimi K3 是本地证据评分器，不等同于上游 GPT-4o。",
        "- 系统只预测 N-X-S/T sequon，不是实验证据或临床诊断。",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _manifest(root: Path, output: Path) -> bytes:
    rows: list[tuple[str, str]] = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        if path.resolve() == output.resolve():
            continue
        rows.append((path.relative_to(root).as_posix(), _sha256(path.read_bytes())))
    return "".join(f"{digest}  {relative}\n" for relative, digest in rows).encode("utf-8")


def _copy_source(repo: Path, item: PackageFile, destination: Path) -> None:
    source = (repo / item.source).resolve()
    try:
        source.relative_to(repo)
    except ValueError as exc:
        raise DeliveryError(f"{item.source}: path escapes repository") from exc
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise DeliveryError(f"{item.source}: unreadable source: {exc}") from exc
    _write_if_changed(destination / item.destination, data)


def build_delivery(repo_root: Path = ROOT, out_dir: Path = DEFAULT_OUT) -> int:
    repo = Path(repo_root).resolve()
    destination = Path(out_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for item in PACKAGE_FILES:
        _copy_source(repo, item, destination)
    evidence = destination / EVIDENCE_DIR
    _write_if_changed(evidence / "README.md", _evidence_readme())
    evidence_manifest = evidence / "SHA256SUMS.txt"
    _write_if_changed(evidence_manifest, _manifest(evidence, evidence_manifest))
    root_manifest = destination / "SHA256SUMS.txt"
    _write_if_changed(root_manifest, _manifest(destination, root_manifest))
    return len(PACKAGE_FILES) + 3


def check_delivery(repo_root: Path = ROOT, out_dir: Path = DEFAULT_OUT) -> None:
    repo = Path(repo_root).resolve()
    destination = Path(out_dir).resolve()
    problems: list[str] = []
    for item in PACKAGE_FILES:
        source = (repo / item.source).resolve()
        target = destination / item.destination
        if not target.exists():
            problems.append(f"missing {item.destination}")
        elif source.read_bytes() != target.read_bytes():
            problems.append(f"stale {item.destination}")
    evidence = destination / EVIDENCE_DIR
    evidence_readme = evidence / "README.md"
    if not evidence_readme.exists() or evidence_readme.read_bytes() != _evidence_readme():
        problems.append(f"stale {EVIDENCE_DIR.as_posix()}/README.md")
    evidence_manifest = evidence / "SHA256SUMS.txt"
    if not evidence_manifest.exists() or evidence_manifest.read_bytes() != _manifest(evidence, evidence_manifest):
        problems.append(f"stale {EVIDENCE_DIR.as_posix()}/SHA256SUMS.txt")
    root_manifest = destination / "SHA256SUMS.txt"
    if not root_manifest.exists() or root_manifest.read_bytes() != _manifest(destination, root_manifest):
        problems.append("stale SHA256SUMS.txt")
    if problems:
        raise DeliveryCheckError("; ".join(problems))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic W03 delivery package.")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check:
            check_delivery(args.repo_root, args.out_dir)
            print("PASS: W03 delivery package is current")
        else:
            count = build_delivery(args.repo_root, args.out_dir)
            print(f"PASS: built W03 delivery package with {count} managed files")
        return 0
    except DeliveryError as exc:
        print(f"W03 DELIVERY VALIDATION ERROR: {exc}", file=sys.stderr)
        return 2
    except DeliveryCheckError as exc:
        print(f"W03 DELIVERY CHECK ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"W03 DELIVERY IO ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
