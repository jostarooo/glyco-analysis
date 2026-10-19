"""Re-derive the v0 dataset from the cached UniProt JSON and compare it to the CSVs.

This checker shares no code with ``build_dataset.py`` on purpose. It re-reads the
raw cache, re-applies the sequon and annotation rules from scratch, and compares
the result field by field, so a bug shared by both would have to be written twice.

Usage:
    .venv\\Scripts\\python.exe scripts\\check_dataset.py
    .venv\\Scripts\\python.exe scripts\\check_dataset.py --reports-dir reports
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
import sys

# Lookahead so finditer enumerates every sequon start, including overlapping
# ones: in "NNSS" both index 0 (NNS) and index 1 (NSS) are real starts, and a
# plain non-overlapping scan silently drops the second. Same rule as UniProt
# annotation positions must be compared against.
SEQUON = re.compile(r"(?=(N[^P][ST]))")
ROW_COLUMNS = [
    "accession",
    "protein_name",
    "seq_len",
    "pos",
    "residue",
    "motif",
    "sequon",
    "label",
    "linkage",
    "n_features",
    "evidence",
    "uniprot_release",
    "fetched_at",
]
LORA_COLUMNS = ["label", "id", "pos", "sequence"]
MAX_EXAMPLES = 5


class Checker:
    def __init__(self) -> None:
        self.failures: Counter[str] = Counter()
        self.examples: dict[str, list[str]] = {}
        self.passed = 0

    def check(self, condition: bool, kind: str, detail: str) -> bool:
        if condition:
            self.passed += 1
            return True
        self.failures[kind] += 1
        bucket = self.examples.setdefault(kind, [])
        if len(bucket) < MAX_EXAMPLES:
            bucket.append(detail)
        return False

    def report(self) -> int:
        print(f"通过的断言: {self.passed}")
        if not self.failures:
            print("结论: PASS —— 数据集与原始 UniProt 缓存逐项一致")
            return 0
        print(f"结论: FAIL —— {sum(self.failures.values())} 处不一致")
        for kind, count in self.failures.most_common():
            print(f"  [{kind}] {count} 处")
            for detail in self.examples[kind]:
                print(f"      {detail}")
        return 1


def annotation_index(entry: dict) -> dict[int, dict]:
    """position -> {linkage, evidence, n_features} for Glycosylation features."""
    sequence = entry["sequence"]["value"]
    index: dict[int, dict] = {}
    for feature in entry["features"]:
        if feature["type"] != "Glycosylation":
            continue
        start = feature["location"]["start"]["value"]
        description = feature.get("description") or ""
        if description.startswith("N-linked"):
            linkage = "N-linked"
        elif description.startswith("O-linked"):
            linkage = "O-linked"
        else:
            linkage = "unknown"
        residue = sequence[start - 1] if 0 < start <= len(sequence) else "?"
        codes = sorted({item["evidenceCode"] for item in feature.get("evidences", [])})
        slot = index.setdefault(start, {"linkage": linkage, "evidence": set(), "count": 0})
        slot["linkage"] = linkage if slot["linkage"] == linkage else "mixed"
        slot["evidence"].update(codes)
        slot["count"] += 1
        slot.setdefault("residues", set()).add(residue)
    return index


def expected_rows(accession: str, entry: dict) -> dict[int, dict]:
    sequence = entry["sequence"]["value"]
    index = annotation_index(entry)
    rows = {}
    for match in SEQUON.finditer(sequence):
        pos = match.start() + 1
        slot = index.get(pos)
        is_n_linked = bool(slot and slot["linkage"] == "N-linked")
        rows[pos] = {
            "accession": accession,
            "seq_len": str(len(sequence)),
            "pos": str(pos),
            "residue": sequence[pos - 1],
            "motif": match.group(1),
            "sequon": "1",
            "label": "1" if is_n_linked else "0",
            "linkage": "N-linked" if is_n_linked else "",
            "n_features": str(slot["count"]) if slot else "0",
            "evidence": ";".join(sorted(slot["evidence"])) if slot else "",
        }
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports-dir", default=None)
    parser.add_argument("--cache-dir", default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    reports = Path(args.reports_dir) if args.reports_dir else root / "reports"
    cache = Path(args.cache_dir) if args.cache_dir else root / "data" / "raw" / "uniprot"

    stats_path = reports / "dataset_v0_stats.json"
    rows_path = reports / "candidates_30.csv"
    lora_path = reports / "candidates_30_lora.csv"
    for path in (stats_path, rows_path, lora_path):
        if not path.is_file():
            print(f"缺少产物: {path}", file=sys.stderr)
            return 2

    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    check = Checker()

    with rows_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        check.check(reader.fieldnames == ROW_COLUMNS, "主表列顺序", f"实际 {reader.fieldnames}")
        rows = list(reader)
    with lora_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        check.check(reader.fieldnames == LORA_COLUMNS, "LoRA 表列顺序", f"实际 {reader.fieldnames}")
        lora_rows = list(reader)

    accessions = stats.get("accessions") or []
    check.check(
        len(accessions) == stats.get("count"),
        "stats.accessions 与 count",
        f"{len(accessions)} vs {stats.get('count')}",
    )
    check.check(
        accessions == sorted(accessions),
        "accessions 排序",
        "抽样后的 accession 未按升序排列",
    )

    expected: dict[tuple[str, int], dict] = {}
    sequences: dict[str, str] = {}
    off_sequon = 0
    for accession in accessions:
        entry_path = cache / f"{accession}.json"
        if not check.check(entry_path.is_file(), "缓存缺失", str(entry_path)):
            continue
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
        sequences[accession] = entry["sequence"]["value"]
        index = annotation_index(entry)
        sequence = sequences[accession]
        for pos, slot in index.items():
            if slot["linkage"] == "N-linked" and not (
                0 < pos <= len(sequence) and SEQUON.match(sequence, pos - 1)
            ):
                off_sequon += 1
        for pos, row in expected_rows(accession, entry).items():
            expected[(accession, pos)] = row

    check.check(
        off_sequon == stats.get("off_sequon_n_linked_total"),
        "off_sequon_n_linked_total",
        f"重算 {off_sequon} vs stats {stats.get('off_sequon_n_linked_total')}",
    )

    actual = {(row["accession"], int(row["pos"])) for row in rows}
    missing = sorted(set(expected) - actual)[:MAX_EXAMPLES]
    extra = sorted(actual - set(expected))[:MAX_EXAMPLES]
    check.check(not missing, "漏掉的候选位点", f"应为候选却缺失: {missing}")
    check.check(not extra, "多出的候选位点", f"不该出现却存在: {extra}")

    release_seen = set()
    for row in rows:
        key = (row["accession"], int(row["pos"]))
        want = expected.get(key)
        if want is None:
            continue
        for field in ("residue", "motif", "sequon", "label", "linkage", "n_features", "evidence", "seq_len"):
            check.check(
                row[field] == want[field],
                f"字段 {field}",
                f"{key[0]}#{key[1]} 实际 {row[field]!r} 期望 {want[field]!r}",
            )
        check.check(
            row["seq_len"] == str(len(sequences[row["accession"]])),
            "seq_len 与缓存序列",
            f"{key[0]} 实际 {row['seq_len']} 期望 {len(sequences[key[0]])}",
        )
        release_seen.add(row["uniprot_release"])
    check.check(
        len(release_seen) <= 1 and all(release_seen),
        "uniprot_release 一致性",
        f"实际 {sorted(release_seen)}",
    )

    order = [(row["accession"], int(row["pos"])) for row in rows]
    check.check(order == sorted(order), "主表行序", "未按 (accession, pos) 升序")

    labels = Counter(row["label"] for row in rows)
    check.check(
        labels["1"] == stats.get("rows", {}).get("label1"),
        "stats.rows.label1",
        f"实际 {labels['1']} vs stats {stats.get('rows', {}).get('label1')}",
    )
    check.check(
        labels["0"] == stats.get("rows", {}).get("label0"),
        "stats.rows.label0",
        f"实际 {labels['0']} vs stats {stats.get('rows', {}).get('label0')}",
    )

    positives = {row["accession"] for row in rows if row["label"] == "1"}
    check.check(
        len(positives) == stats.get("proteins_with_positive"),
        "stats.proteins_with_positive",
        f"实际 {len(positives)} vs stats {stats.get('proteins_with_positive')}",
    )

    lora_map = {(row["id"], int(row["pos"])): row for row in lora_rows}
    check.check(
        len(lora_rows) == len(rows),
        "LoRA 表行数",
        f"实际 {len(lora_rows)} vs 主表 {len(rows)}",
    )
    mismatched = []
    for row in rows:
        key = (row["accession"], int(row["pos"]))
        other = lora_map.get(key)
        if other is None:
            mismatched.append(f"{key[0]}#{key[1]} 在 LoRA 表缺失")
        elif other["label"] != row["label"]:
            mismatched.append(f"{key[0]}#{key[1]} label {other['label']} vs {row['label']}")
        elif other["sequence"] != sequences.get(key[0]):
            mismatched.append(f"{key[0]} 序列与缓存不一致")
        elif not 1 <= key[1] <= len(other["sequence"]):
            mismatched.append(f"{key[0]}#{key[1]} pos 越界")
    check.check(not mismatched, "LoRA 表与主表对齐", "; ".join(mismatched[:MAX_EXAMPLES]))

    stray = [key for key in lora_map if key not in actual][:MAX_EXAMPLES]
    check.check(not stray, "LoRA 表多余行", f"{stray}")

    print(f"抽样蛋白: {len(accessions)}　主表行数: {len(rows)}　正样本: {labels['1']}　负样本: {labels['0']}")
    print(f"非模体但标了 N-linked 的位置: {off_sequon}　release: {sorted(release_seen)}")
    return check.report()


if __name__ == "__main__":
    raise SystemExit(main())
