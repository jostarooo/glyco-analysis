"""从 UniProt 构建 F1（N-糖基化位点预测）数据集 v0。

一行 = 一个候选位点，(accession, pos) 唯一。产物：
  reports/candidates_30.csv        主产物，13 列
  reports/candidates_30_lora.csv   作者 test.csv 的形状（label,id,pos,sequence）
  reports/dataset_v0_stats.json    本次运行的统计

原始 JSON 缓存在 data/raw/uniprot（已 gitignore），fetched_at 取自缓存文件 mtime，
所以同一组参数重跑逐字节一致，且第二次运行的 network_fetches 应为 0。

用法：
    $env:PYTHONUTF8='1'
    & 'D:\\wbworkspace\\glyco-analysis\\.venv\\Scripts\\python.exe' scripts\\build_dataset.py
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[1]
REST_BASE = "https://rest.uniprot.org"
ACCESSION_QUERY = "(organism_id:9606) AND (reviewed:true) AND (ft_carbohyd_exp:*)"
USER_AGENT = "glyco-analysis/0.1 (undergraduate thesis dataset builder)"
LIST_CACHE_NAME = "_list.json"

REQUEST_TIMEOUT_S = 90
RETRY_BACKOFF_S = (1.0, 2.0, 4.0)
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
REQUEST_GAP_S = 0.2

DEFAULT_COUNT = 30
DEFAULT_SEED = 20261020

# 领域规则只在这里出现：linkage 决定该位点必须是什么残基才算已验证。
LINKAGE_RESIDUES = {"N-linked": "N", "O-linked": "ST"}
# 前瞻写法让 finditer 允许重叠，否则 NNST 里第 2 位起的 sequon 会被漏掉。
SEQUON = re.compile(r"(?=(N[^P][ST]))")

CANDIDATE_COLUMNS = (
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
)
LORA_COLUMNS = ("label", "id", "pos", "sequence")


class UniprotError(RuntimeError):
    """取数失败；消息必须带上出问题的 accession。"""


@dataclass(frozen=True)
class Annotation:
    linkage: str
    evidence: tuple
    n_features: int


@dataclass(frozen=True)
class GlycosylationIndex:
    """verified 只收残基与 linkage 一致的位点；declared_n_linked 收上游声明为 N-linked 的全部位点。"""

    verified: dict
    declared_n_linked: frozenset


class Row(NamedTuple):
    """字段顺序即 candidates CSV 的列顺序。"""

    accession: str
    protein_name: str
    seq_len: int
    pos: int
    residue: str
    motif: str
    sequon: int
    label: int
    linkage: str
    n_features: int
    evidence: str
    uniprot_release: str
    fetched_at: str


def cache_mtime(path):
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def protein_name_of(record):
    description = record.get("proteinDescription") or {}
    recommended = (description.get("recommendedName") or {}).get("fullName") or {}
    if recommended.get("value"):
        return recommended["value"]
    for submitted in description.get("submissionNames") or []:
        value = (submitted.get("fullName") or {}).get("value")
        if value:
            return value
    return ""


def glycosylation_index(sequence, features):
    """按 1-based 位置聚合同一个位点的冗余糖基化记录，得到查表用的索引。

    UniProt 对同一位置会重复记录（P01857 的 180 位有 28 条），故按位置去重；
    只有 linkage 与序列残基一致（N-linked 必须是 N）的记录才算已验证位点。
    declared_n_linked 不做残基过滤，留给模体外统计暴露上游噪声。
    """
    linkages = {}
    evidence = {}
    raw_counts = {}
    declared = set()
    for feature in features:
        if feature.get("type") != "Glycosylation":
            continue
        location = feature.get("location") or {}
        pos = (location.get("start") or {}).get("value")
        if pos is None:
            continue
        raw_counts[pos] = raw_counts.get(pos, 0) + 1
        description = str(feature.get("description", ""))
        linkage = next((key for key in LINKAGE_RESIDUES if description.startswith(key)), None)
        if linkage is None:
            continue
        if linkage == "N-linked":
            declared.add(pos)
        if not 0 < pos <= len(sequence):
            continue
        if sequence[pos - 1] not in LINKAGE_RESIDUES[linkage]:
            continue
        linkages[pos] = linkage
        codes = evidence.setdefault(pos, set())
        for item in feature.get("evidences") or []:
            code = item.get("evidenceCode")
            if code:
                codes.add(code)
    verified = {
        pos: Annotation(linkages[pos], tuple(sorted(evidence[pos])), raw_counts[pos])
        for pos in linkages
    }
    return GlycosylationIndex(verified, frozenset(declared))


def candidate_rows(accession, name, sequence, seq_len, index, release, fetched_at):
    """返回 (sequon 候选行, 模体外 N-linked 声明数, 其中残基与 N 不符的个数)。

    候选集取自全序列的 sequon 位点，故 motif/sequon 两列恒为模体与 1。模体外
    指标是数据质量指标，统计上游标了 N-linked 却不在 sequon 上的位点，它不进入
    候选集，与 CSV 行数无关。
    """
    motifs = {match.start() + 1: match.group(1) for match in SEQUON.finditer(sequence)}
    linked = {pos for pos, annotation in index.verified.items() if annotation.linkage == "N-linked"}
    off_sequon_declared = index.declared_n_linked - set(motifs)
    rows = []
    for pos, motif in sorted(motifs.items()):
        annotation = index.verified.get(pos)
        # label=0 表示「有模体但无实验标注」，不代表已证明不糖基化。
        label = 1 if annotation is not None and annotation.linkage == "N-linked" else 0
        rows.append(
            Row(
                accession=accession,
                protein_name=name,
                seq_len=seq_len,
                pos=pos,
                residue=sequence[pos - 1],
                motif=motif,
                sequon=1,
                label=label,
                linkage="N-linked" if label else "",
                n_features=annotation.n_features if annotation else 0,
                evidence=";".join(annotation.evidence) if annotation else "",
                uniprot_release=release,
                fetched_at=fetched_at,
            )
        )
    return rows, len(off_sequon_declared), len(off_sequon_declared - linked)


def atomic_write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def atomic_write_bytes(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(body)
    os.replace(temporary, path)


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
    os.replace(temporary, path)


class UniprotClient:
    """缓存在前、网络在后的取数适配器；重试与礼貌延迟只在这个边界里出现。"""

    def __init__(self, cache_dir, refresh):
        self.cache_dir = cache_dir
        self.refresh = refresh
        self.network_fetches = 0
        self.cache_hits = 0
        self._last_request_at = None

    def _pace(self):
        if self._last_request_at is not None:
            remaining = REQUEST_GAP_S - (time.monotonic() - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()

    def _request(self, url, label):
        failure = None
        for backoff in (0.0,) + RETRY_BACKOFF_S:
            if backoff:
                time.sleep(backoff)
            self._pace()
            self.network_fetches += 1
            request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
                    return response.read(), dict(response.headers)
            except urllib.error.HTTPError as error:
                if error.code not in RETRYABLE_STATUS:
                    raise UniprotError(f"{label} 请求失败：HTTP {error.code} {error.reason}（{url}）") from error
                failure = error
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                failure = error
        raise UniprotError(f"{label} 重试 {len(RETRY_BACKOFF_S)} 次后仍失败：{failure!r}（{url}）")

    def accessions(self):
        cache = self.cache_dir / LIST_CACHE_NAME
        if cache.exists() and not self.refresh:
            self.cache_hits += 1
            payload = json.loads(cache.read_text(encoding="utf-8"))
            return payload["accessions"], payload["release"]
        query = urllib.parse.urlencode({"query": ACCESSION_QUERY, "format": "list"})
        body, headers = self._request(f"{REST_BASE}/uniprotkb/stream?{query}", "蛋白清单")
        release = headers.get("X-UniProt-Release", "")
        accessions = body.decode("utf-8").split()
        payload = {"release": release, "accessions": accessions}
        atomic_write_bytes(cache, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        return accessions, release

    def record(self, accession):
        cache = self.cache_dir / f"{accession}.json"
        if cache.exists() and not self.refresh:
            self.cache_hits += 1
            return json.loads(cache.read_text(encoding="utf-8")), cache_mtime(cache)
        body, _ = self._request(f"{REST_BASE}/uniprotkb/{accession}.json", f"accession {accession}")
        atomic_write_bytes(cache, body)
        return json.loads(body.decode("utf-8")), cache_mtime(cache)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="从 UniProt 构建 F1 数据集 v0（可重复执行）")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help=f"抽样蛋白数（默认 {DEFAULT_COUNT}）")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"抽样随机种子（默认 {DEFAULT_SEED}）")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存，强制重新抓取（含蛋白清单）")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=REPO_ROOT / "data/raw/uniprot",
        help="原始 JSON 缓存目录（默认 data/raw/uniprot）",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "reports",
        help="产物目录（默认 reports）",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    client = UniprotClient(args.cache_dir, args.refresh)
    try:
        accessions, release = client.accessions()
        # 抽样前先排序：UniProt 返回的清单顺序不是 Python 的字符串序，不排会让样本随清单顺序漂移。
        accessions.sort()
        if not 1 <= args.count <= len(accessions):
            raise UniprotError(f"--count 需在 1..{len(accessions)} 之间，收到 {args.count}")
        sampled = sorted(random.Random(args.seed).sample(accessions, args.count))
        print(f"蛋白清单 {len(accessions)} 条，release {release}，抽样 {len(sampled)} 条（seed={args.seed}）")

        rows = []
        sequences = {}
        off_sequon_total = 0
        off_sequon_unverified_total = 0
        for number, accession in enumerate(sampled, start=1):
            record, fetched_at = client.record(accession)
            sequence = record["sequence"]["value"]
            seq_len = record["sequence"].get("length") or len(sequence)
            if seq_len != len(sequence):
                print(f"警告：{accession} 声明长度 {seq_len} 与序列长度 {len(sequence)} 不一致")
            index = glycosylation_index(sequence, record.get("features") or [])
            protein_rows, off_sequon, off_sequon_unverified = candidate_rows(
                accession, protein_name_of(record), sequence, seq_len, index, release, fetched_at
            )
            rows.extend(protein_rows)
            sequences[accession] = sequence
            off_sequon_total += off_sequon
            off_sequon_unverified_total += off_sequon_unverified
            positives = sum(row.label for row in protein_rows)
            print(
                f"[{number}/{len(sampled)}] {accession} 长度 {seq_len} "
                f"候选 {len(protein_rows)} label1 {positives} 模体外声明 {off_sequon}"
            )

        label1_total = sum(row.label for row in rows)
        stats = {
            "seed": args.seed,
            "count": args.count,
            "release": release,
            "accessions": sampled,
            "rows": {"total": len(rows), "label1": label1_total, "label0": len(rows) - label1_total},
            "proteins_with_positive": sum(1 for acc in sampled if any(r.label for r in rows if r.accession == acc)),
            "off_sequon_n_linked_total": off_sequon_total,
            "network_fetches": client.network_fetches,
            "cache_hits": client.cache_hits,
        }
        candidates_path = args.out_dir / "candidates_30.csv"
        lora_path = args.out_dir / "candidates_30_lora.csv"
        stats_path = args.out_dir / "dataset_v0_stats.json"
        write_csv(candidates_path, CANDIDATE_COLUMNS, rows)
        write_csv(lora_path, LORA_COLUMNS, ((r.label, r.accession, r.pos, sequences[r.accession]) for r in rows))
        atomic_write_text(stats_path, json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
    except UniprotError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1

    print(
        f"候选行 {len(rows)}（label1 {label1_total} / label0 {len(rows) - label1_total}）；"
        f"模体外 N-linked 声明 {off_sequon_total}"
        f"（其中残基与 N 不符 {off_sequon_unverified_total}）；"
        f"网络请求 {client.network_fetches} 次，缓存命中 {client.cache_hits} 次"
    )
    print(f"已写出 {candidates_path} / {lora_path} / {stats_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
