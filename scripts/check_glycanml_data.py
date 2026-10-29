"""Download GlycanML downstream CSVs and verify their MD5 checksums.

The URLs and MD5 values are parsed from the upstream dataset classes so this
script fails if the clone and the recorded expectations drift apart. Files are
kept under data/raw/glycanml/ for the F2 recomputation.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "data" / "raw" / "glycanml"
OUT_DIR = ROOT / "reports" / "w2_day1"
UPSTREAM = Path(r"D:\wbworkspace\GlycanML\module\custom_datasets")
MODULES = {
    "glycan_classification": "glycan_classification.py",
    "glycan_interaction": "glycan_interaction.py",
    "glycan_immunogenicity": "glycan_immunogenicity.py",
    "glycan_properties": "glycan_properties.py",
    "glycan_link": "glycan_link.py",
}
URL_RE = re.compile(r'url\s*=\s*"([^"]+)"')
MD5_RE = re.compile(r'md5\s*=\s*"([0-9a-f]{32})"')


def parse_expectations() -> dict[str, dict[str, str]]:
    expected: dict[str, dict[str, str]] = {}
    for name, filename in MODULES.items():
        text = (UPSTREAM / filename).read_text(encoding="utf-8")
        url = URL_RE.search(text)
        md5 = MD5_RE.search(text)
        if not url or not md5:
            raise SystemExit(f"cannot parse url/md5 from {filename}")
        expected[name] = {"url": url.group(1), "md5": md5.group(1)}
    return expected


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> tuple[str, int, float]:
    digest = hashlib.md5()
    size = 0
    started = time.perf_counter()
    headers = {"User-Agent": "glyco-analysis-w2/0.1"}
    part = target.with_suffix(target.suffix + ".part")
    with requests.get(url, headers=headers, stream=True, timeout=(10, 60)) as response, part.open("wb") as handle:
        response.raise_for_status()
        expected_size = response.headers.get("Content-Length")
        if expected_size and int(expected_size) <= 0:
            raise ValueError(f"empty response body (Content-Length={expected_size})")
        for chunk in response.iter_content(chunk_size=64 * 1024):
            handle.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        if size == 0:
            raise ValueError("downloaded zero bytes")
        if expected_size and size != int(expected_size):
            raise ValueError(f"truncated body: got {size} of {expected_size} bytes")
    part.replace(target)
    return digest.hexdigest(), size, time.perf_counter() - started


def main() -> int:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for name, spec in parse_expectations().items():
        target = DATASET_DIR / f"{name}.csv"
        try:
            upstream_url = spec["url"]
            if target.exists() and md5_file(target) == spec["md5"]:
                actual, size, elapsed = spec["md5"], target.stat().st_size, 0.0
                working_url = upstream_url
                status = "PASS_CACHED"
                if upstream_url.rsplit("/", 1)[-1] != f"{name}.csv":
                    working_url = upstream_url.rsplit("/", 1)[0] + f"/{name}.csv"
                    status = "PASS_URL_FIX"
            else:
                actual, size, elapsed = download(upstream_url, target)
                working_url = upstream_url
                status = "PASS" if actual == spec["md5"] else "FAIL"
                if status == "FAIL":
                    # Some upstream modules point at a sibling file with the
                    # right checksum but the wrong name. Try the dataset's own
                    # CSV name and keep the correction in the report.
                    fallback = upstream_url.rsplit("/", 1)[0] + f"/{name}.csv"
                    if fallback != upstream_url:
                        fallback_actual, size, elapsed = download(fallback, target)
                        if fallback_actual == spec["md5"]:
                            actual = fallback_actual
                            working_url = fallback
                            status = "PASS_URL_FIX"
            with target.open("rb") as handle:
                header = handle.readline().decode("utf-8", "replace").strip()
            rows = sum(1 for _ in target.open("rb")) - 1
            results.append(
                {
                    "dataset": name,
                    "status": status,
                    "url": upstream_url,
                    "working_url": working_url,
                    "expected_md5": spec["md5"],
                    "actual_md5": actual,
                    "bytes": size,
                    "rows": rows,
                    "columns": header.split(","),
                    "seconds": round(elapsed, 2),
                }
            )
        except Exception as exc:  # noqa: BLE001 - report every dataset failure
            results.append({"dataset": name, "status": "FAIL", "error": repr(exc)})

    summary = {
        "status": "PASS" if all(r["status"].startswith("PASS") for r in results) else "FAIL",
        "upstream_url_issues": [
            r["dataset"] for r in results if r["status"] == "PASS_URL_FIX"
        ],
        "datasets": results,
        "total_bytes": sum(r.get("bytes", 0) for r in results),
    }
    (OUT_DIR / "glycanml_data_check.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
