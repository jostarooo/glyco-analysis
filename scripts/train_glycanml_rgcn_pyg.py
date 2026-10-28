"""Reproducible PyG RGCN benchmark for GlycanML Table 3.

The graph construction intentionally mirrors the upstream GlycanML
``Glycan.from_iupac`` parser.  Only the ``get_core`` helper from glycowork is
vendored here, so the benchmark does not need the full glycowork package.

Run the full benchmark with the default seeds 0, 1, and 2:

    .venv\\Scripts\\python.exe scripts\\train_glycanml_rgcn_pyg.py

Run the non-writing smoke check:

    .venv\\Scripts\\python.exe scripts\\train_glycanml_rgcn_pyg.py --smoke
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import pickle
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

# CUBLAS reproducibility is configured before importing torch.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
# The host is memory constrained, and GPU training does not benefit from a
# multi-threaded OpenBLAS pool.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import torch
from sklearn.metrics import accuracy_score, average_precision_score, f1_score, roc_auc_score
from torch import nn
from torch.nn import functional as F
from torch_geometric.data import Batch, Data
from torch_geometric.nn import global_max_pool, global_mean_pool


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data" / "raw" / "glycanml"
DEFAULT_VOCAB = Path(r"D:\wbworkspace\GlycanML\module\custom_data\glycoword_vocab.pkl")
DEFAULT_OUT = ROOT / "reports" / "w2_day1" / "glycanml_rgcn_recompute.json"

EMBEDDING_ROWS = 143
HIDDEN_DIM = 128
NUM_LAYERS = 3
NUM_RELATIONS_EXPECTED = 84
NUM_UNITS_EXPECTED = 127
BATCH_SIZE = 256
EPOCHS = 50
LR = 5e-4
WEIGHT_DECAY = 1e-3
T_MAX = 100

SPLIT_COLUMNS = ("train", "valid", "test")
REQUIRED_COLUMNS = ("glycan_id", "glycan", *SPLIT_COLUMNS)


class GraphParseError(ValueError):
    """Raised when an upstream-compatible graph cannot be built."""


class DataError(ValueError):
    """Raised when a CSV row or split does not match the fixed contract."""


# This order is copied from glycowork 1.11.0 tokenization._CORES.
_CORES = [
    "dHexNAc",
    "GlcNAc",
    "GalNAc",
    "ManNAc",
    "FucNAc",
    "QuiNAc",
    "RhaNAc",
    "GulNAc",
    "IdoNAc",
    "Ins",
    "MurNAc",
    "6dAltNAc",
    "AcoNAc",
    "HexA",
    "GlcA",
    "AltA",
    "GalA",
    "ManA",
    "Tyv",
    "Yer",
    "Abe",
    "GlcfNAc",
    "GalfNAc",
    "ManfNAc",
    "FucfNAc",
    "IdoA",
    "GulA",
    "LDManHep",
    "DDManHep",
    "DDGlcHep",
    "LyxHep",
    "ManHep",
    "DDAltHep",
    "IdoHep",
    "DLGlcHep",
    "GalHep",
    "ddHex",
    "ddNon",
    "Unknown",
    "Assigned",
    "MurNGc",
    "6dTalNAc",
    "6dGul",
    "AllA",
    "TalA",
    "AllNAc",
    "TalNAc",
    "Kdn",
    "Pen",
    "GlcN",
    "GalN",
    "ManN",
    "FucN",
    "QuiN",
    "RhaN",
    "AraN",
    "IdoN",
    "Glcf",
    "Galf",
    "Manf",
    "Fucf",
    "Araf",
    "Lyxf",
    "Xylf",
    "6dAltf",
    "Ribf",
    "Fruf",
    "Apif",
    "Kdof",
    "Sedf",
    "6dTal",
    "AltNAc",
    "6dAlt",
    "dHex",
    "HexNAc",
    "dNon",
    "4eLeg",
    "GulN",
    "AltN",
    "AllN",
    "TalN",
    "HexN",
    "Glc",
    "Gal",
    "Man",
    "Fuc",
    "Qui",
    "Rha",
    "Ara",
    "Oli",
    "Gul",
    "Lyx",
    "Xyl",
    "Dha",
    "Rib",
    "Kdo",
    "Tal",
    "All",
    "Pse",
    "Leg",
    "Asc",
    "Hex",
    "Fru",
    "Alt",
    "Xluf",
    "Api",
    "Ko",
    "Pau",
    "Fus",
    "Erwiniose",
    "Aco",
    "Bac",
    "Dig",
    "Thre-ol",
    "Ery-ol",
    "Tag",
    "Sor",
    "Psi",
    "Mur",
    "Aci",
    "Sia",
    "Par",
    "Col",
    "Ido",
]

_LINKAGE_RE = re.compile(r"^[0-9]+(-[0-9]+)+$")
_POSITION_LIST_RE = re.compile(r"(\d(?:,\d)+)([A-Z][a-z]*)\d+")


def _expand_position_lists(sugar: str) -> str:
    """Spell out position lists such as Neu5,9Ac2 before core detection."""
    if "," not in sugar:
        return sugar
    return _POSITION_LIST_RE.sub(
        lambda match: "".join(
            position + match.group(2) for position in match.group(1).split(",")
        ),
        sugar,
    )


def get_core(sugar: str) -> str:
    """Vendored glycowork 1.11.0 get_core with the upstream _CORES order."""
    sugar = _expand_position_lists(sugar)
    for core in _CORES:
        if core in sugar:
            return core
    if "Neu" in sugar:
        if "5Ac" in sugar:
            return "Neu5Ac"
        if "5Gc" in sugar:
            return "Neu5Gc"
        if "4Ac" in sugar:
            return "Neu4Ac"
        return "Neu"
    if is_linkage_token(sugar):
        return sugar
    return "Monosaccharide"


def is_linkage_token(value: str) -> bool:
    """Use the same token filter as the upstream Glycan parser."""
    return value.startswith(("a", "b", "?")) or _LINKAGE_RE.match(value) is not None


def _multireplace(value: str, replacements: Mapping[str, str]) -> str:
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def _unit_spans(part: str) -> list[tuple[int, int]]:
    """Replicate upstream get_unit_id2start_end for one branch part."""
    normalized = _multireplace(part, {"[": "", "]": "", ")": "("})
    tokens = [token for token in normalized.split("(") if token]
    units = [token for token in tokens if not is_linkage_token(token)]
    spans: list[tuple[int, int]] = []
    current = 0
    for unit in units:
        start = part[current:].index(unit) + current
        spans.append((start, start + len(unit)))
        current = start + len(unit)
    return spans


def _locate_brackets(value: str) -> tuple[list[int], list[int]]:
    left: list[int] = []
    right: list[int] = []
    for index, character in enumerate(value):
        if character == "[":
            left.append(index)
        if character == "]" and len(left) > len(right):
            right.append(index)
    return left, right


def _on_branch(
    index: int, left_indices: Sequence[int], right_indices: Sequence[int]
) -> bool:
    return any(
        left <= index <= right
        for left, right in zip(left_indices, right_indices)
    )


def _link_relation(inner_part: str, link_to_id: Mapping[str, int]) -> int | None:
    """Replicate upstream Glycan.get_link_type."""
    left_indices, right_indices = _locate_brackets(inner_part)
    if not left_indices and not right_indices:
        link = "".join(
            character for character in inner_part if character not in "()[]"
        )
    elif len(left_indices) != len(right_indices):
        return None
    else:
        link = "".join(
            character
            for index, character in enumerate(inner_part)
            if character not in "()[]"
            and not _on_branch(index, left_indices, right_indices)
        )
    return link_to_id.get(get_core(link))


def _extract_node_tokens(iupac: str) -> list[str]:
    """Replicate the node-token extraction in Glycan.from_iupac."""
    normalized = _multireplace(
        iupac, {"[": "", "]": "", "{": "", "}": "", ")": "("}
    )
    tokens = [token for token in normalized.split("(") if token]
    return [token for token in tokens if not is_linkage_token(token)]


def _extract_edges(
    iupac: str, link_to_id: Mapping[str, int]
) -> tuple[list[tuple[int, int, int]], int]:
    """Replicate Glycan.get_edge_list, including both directed emissions."""
    parts = [
        part
        for part in _multireplace(iupac, {"}": "{"}).split("{")
        if part
    ]
    edges: list[tuple[int, int, int]] = []
    cumulative_units = 0
    for part in parts:
        spans = _unit_spans(part)
        num_units = len(spans)
        for source_id in range(num_units):
            for target_id in range(source_id + 1, num_units):
                source_end = spans[source_id][1]
                target_start = spans[target_id][0]
                if target_start <= source_end:
                    raise GraphParseError(
                        f"unit span order failed in part {part!r}: "
                        f"{spans[source_id]!r} -> {spans[target_id]!r}"
                    )
                relation = _link_relation(
                    part[source_end:target_start], link_to_id
                )
                if relation is not None:
                    source = source_id + cumulative_units
                    target = target_id + cumulative_units
                    edges.append((source, target, relation))
                    edges.append((target, source, relation))
        cumulative_units += num_units
    return edges, cumulative_units


@dataclass(frozen=True)
class Vocabulary:
    path: Path
    entities: tuple[str, ...]
    units: tuple[str, ...]
    links: tuple[str, ...]
    unit_to_id: Mapping[str, int]
    link_to_id: Mapping[str, int]


def load_vocabulary(path: Path) -> Vocabulary:
    if not path.is_file():
        raise FileNotFoundError(f"vocabulary not found: {path}")
    with path.open("rb") as handle:
        raw = pickle.load(handle)
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise DataError(f"vocabulary must be a list of strings: {path}")
    entities = tuple(raw)
    units = tuple(entity for entity in entities if not is_linkage_token(entity))
    links = tuple(entity for entity in entities if is_linkage_token(entity))
    if len(units) != NUM_UNITS_EXPECTED:
        raise DataError(
            f"expected {NUM_UNITS_EXPECTED} active units, found {len(units)} in {path}"
        )
    if len(links) != NUM_RELATIONS_EXPECTED:
        raise DataError(
            f"expected {NUM_RELATIONS_EXPECTED} relations, found {len(links)} in {path}"
        )
    unit_to_id = {unit: index for index, unit in enumerate(units)}
    link_to_id = {link: index for index, link in enumerate(links)}
    if "Monosaccharide" not in unit_to_id:
        raise DataError(f"Monosaccharide is missing from vocabulary: {path}")
    return Vocabulary(
        path=path,
        entities=entities,
        units=units,
        links=links,
        unit_to_id=unit_to_id,
        link_to_id=link_to_id,
    )


def parse_glycan(
    iupac: str,
    vocabulary: Vocabulary,
) -> tuple[Data, int, int]:
    """Parse one CSV glycan into a PyG Data object.

    Edges are already emitted in both directions by the upstream parser, so
    PyG transformations must not add ToUndirected edges or self-loops.
    """
    if not isinstance(iupac, str) or not iupac.strip():
        raise GraphParseError("empty glycan string")

    try:
        node_tokens = _extract_node_tokens(iupac)
        edges, edge_node_count = _extract_edges(iupac, vocabulary.link_to_id)
    except GraphParseError:
        raise
    except Exception as exc:  # include the upstream parser's lookup/assert errors
        raise GraphParseError(f"parser failure for {iupac!r}: {exc}") from exc

    if not node_tokens:
        raise GraphParseError(f"no monosaccharide units found in {iupac!r}")
    if edge_node_count != len(node_tokens):
        raise GraphParseError(
            f"node/edge branch mismatch for {iupac!r}: "
            f"{len(node_tokens)} node tokens versus {edge_node_count} branch nodes"
        )

    monosaccharide_id = vocabulary.unit_to_id["Monosaccharide"]
    unit_ids: list[int] = []
    for token in node_tokens:
        core = get_core(token)
        unit_ids.append(vocabulary.unit_to_id.get(core, monosaccharide_id))

    if edges:
        edge_index = torch.tensor(
            [[source, target] for source, target, _ in edges], dtype=torch.long
        ).t().contiguous()
        edge_type = torch.tensor(
            [relation for _, _, relation in edges], dtype=torch.long
        )
        if int(edge_type.min()) < 0 or int(edge_type.max()) >= len(vocabulary.links):
            raise GraphParseError(f"relation id out of range for {iupac!r}")
        if bool((edge_index[0] == edge_index[1]).any()):
            raise GraphParseError(f"self-loop emitted by parser for {iupac!r}")
    else:
        edge_index = torch.empty((2, 0), dtype=torch.long)
        edge_type = torch.empty((0,), dtype=torch.long)

    data = Data(
        unit_type=torch.tensor(unit_ids, dtype=torch.long),
        edge_index=edge_index,
        edge_type=edge_type,
        num_nodes=len(unit_ids),
    )
    return data, len(node_tokens), len(edges)


@dataclass(frozen=True)
class TaskSpec:
    key: str
    filename: str
    label_column: str
    num_classes: int
    expected_splits: Mapping[str, int]
    selection_metric: str
    report_metric: str
    label_map: Mapping[str, int] | None = None

    @property
    def total_expected(self) -> int:
        return sum(self.expected_splits.values())


TASKS: tuple[TaskSpec, ...] = (
    TaskSpec(
        key="immunogenicity",
        filename="glycan_immunogenicity.csv",
        label_column="immunogenicity",
        num_classes=1,
        expected_splits={"train": 1026, "valid": 149, "test": 145},
        selection_metric="auroc",
        report_metric="auprc",
    ),
    TaskSpec(
        key="glycosylation",
        filename="glycan_link.csv",
        label_column="link",
        num_classes=3,
        expected_splits={"train": 1356, "valid": 163, "test": 164},
        selection_metric="accuracy",
        report_metric="macro_f1",
        label_map={"N": 0, "O": 1, "free": 2},
    ),
)


@dataclass
class ParsedTask:
    spec: TaskSpec
    csv_path: Path
    graphs: list[Data]
    split_indices: dict[str, list[int]]
    split_counts: dict[str, int]
    label_counts: dict[str, int]
    node_count: int
    edge_count: int
    min_nodes: int
    max_nodes: int


def _cell(row: Mapping[str, Any], column: str) -> str:
    value = row.get(column)
    if value is None:
        return ""
    return str(value).strip()


def _parse_one_hot_split(row: Mapping[str, Any], row_number: int) -> str:
    active: list[str] = []
    for split in SPLIT_COLUMNS:
        value = _cell(row, split)
        try:
            numeric = float(value)
        except ValueError as exc:
            raise DataError(
                f"row {row_number}: split column {split!r} is not numeric: {value!r}"
            ) from exc
        if numeric not in (0.0, 1.0):
            raise DataError(
                f"row {row_number}: split column {split!r} must be 0 or 1, got {value!r}"
            )
        if numeric == 1.0:
            active.append(split)
    if len(active) != 1:
        raise DataError(
            f"row {row_number}: split one-hot has {len(active)} active columns "
            f"({active}); expected exactly one"
        )
    return active[0]


def _parse_target(spec: TaskSpec, row: Mapping[str, Any], row_number: int) -> int:
    value = _cell(row, spec.label_column)
    if spec.label_map is None:
        try:
            numeric = float(value)
        except ValueError as exc:
            raise DataError(
                f"row {row_number}: invalid {spec.label_column!r} value {value!r}"
            ) from exc
        if not math.isfinite(numeric) or numeric not in (0.0, 1.0):
            raise DataError(
                f"row {row_number}: {spec.label_column!r} must be 0 or 1, "
                f"got {value!r}"
            )
        return int(numeric)
    if value not in spec.label_map:
        raise DataError(
            f"row {row_number}: invalid {spec.label_column!r} value {value!r}; "
            f"expected one of {sorted(spec.label_map)}"
        )
    return spec.label_map[value]


def load_task(spec: TaskSpec, data_dir: Path, vocabulary: Vocabulary) -> ParsedTask:
    csv_path = data_dir / spec.filename
    if not csv_path.is_file():
        raise FileNotFoundError(f"{spec.key} CSV not found: {csv_path}")

    split_indices: dict[str, list[int]] = {split: [] for split in SPLIT_COLUMNS}
    graphs: list[Data] = []
    label_counts: Counter[str] = Counter()
    node_count = 0
    edge_count = 0
    min_nodes = 10**9
    max_nodes = 0

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise DataError(f"{csv_path}: missing CSV header")
        missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise DataError(f"{csv_path}: missing columns {missing}")

        for row_number, row in enumerate(reader, start=2):
            if not any(_cell(row, column) for column in reader.fieldnames):
                continue
            split = _parse_one_hot_split(row, row_number)
            target = _parse_target(spec, row, row_number)
            iupac = _cell(row, "glycan")
            try:
                graph, nodes, edges = parse_glycan(iupac, vocabulary)
            except GraphParseError as exc:
                raise GraphParseError(
                    f"{spec.key} {csv_path} data row {row_number}: {exc}"
                ) from exc

            graph.y = torch.tensor(
                [target],
                dtype=torch.float32 if spec.num_classes == 1 else torch.long,
            )
            graphs.append(graph)
            split_indices[split].append(len(graphs) - 1)
            label_counts[str(target)] += 1
            node_count += nodes
            edge_count += edges
            min_nodes = min(min_nodes, nodes)
            max_nodes = max(max_nodes, nodes)

    if not graphs:
        raise DataError(f"{spec.key} {csv_path}: no data rows")

    split_counts = {split: len(indices) for split, indices in split_indices.items()}
    expected = dict(spec.expected_splits)
    if len(graphs) != spec.total_expected:
        raise DataError(
            f"{spec.key} row count mismatch: expected {spec.total_expected}, "
            f"found {len(graphs)}"
        )
    if split_counts != expected:
        raise DataError(
            f"{spec.key} split counts mismatch: expected {expected}, "
            f"found {split_counts}"
        )

    return ParsedTask(
        spec=spec,
        csv_path=csv_path,
        graphs=graphs,
        split_indices=split_indices,
        split_counts=split_counts,
        label_counts=dict(label_counts),
        node_count=node_count,
        edge_count=edge_count,
        min_nodes=min_nodes,
        max_nodes=max_nodes,
    )


def load_all_tasks(
    data_dir: Path, vocabulary: Vocabulary
) -> dict[str, ParsedTask]:
    return {spec.key: load_task(spec, data_dir, vocabulary) for spec in TASKS}


class RelationalMeanLayer(nn.Module):
    """Mean neighbors per relation, concatenate relation channels, then combine."""

    # Processing relation channels in blocks keeps the batch-256 peak allocation
    # small while preserving the same concatenated linear map.
    _CHANNEL_BLOCK = 8

    def __init__(
        self, input_dim: int, output_dim: int, num_relations: int
    ) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.num_relations = num_relations
        self.relation_linear = nn.Linear(
            input_dim * num_relations, output_dim, bias=True
        )
        self.self_linear = nn.Linear(input_dim, output_dim, bias=True)

    def forward(
        self,
        node_features: torch.Tensor,
        edge_index: torch.Tensor,
        edge_type: torch.Tensor,
    ) -> torch.Tensor:
        num_nodes = node_features.size(0)
        source, target = edge_index
        relation = edge_type.long()
        output = self.relation_linear.bias.expand(num_nodes, self.output_dim).clone()
        for begin in range(0, self.num_relations, self._CHANNEL_BLOCK):
            end = min(begin + self._CHANNEL_BLOCK, self.num_relations)
            block_size = end - begin
            if relation.numel() == 0:
                relation_values = node_features.new_zeros(
                    (num_nodes, block_size * self.input_dim)
                )
            else:
                in_block = (relation >= begin) & (relation < end)
                block_sources = source[in_block]
                block_targets = target[in_block]
                block_slots = (
                    block_targets.long() * block_size
                    + (relation[in_block] - begin)
                )
                sums = node_features.new_zeros(
                    (num_nodes * block_size, self.input_dim)
                )
                sums.index_add_(0, block_slots, node_features[block_sources])
                counts = node_features.new_zeros((num_nodes * block_size, 1))
                counts.index_add_(
                    0,
                    block_slots,
                    node_features.new_ones((block_slots.numel(), 1)),
                )
                sums = sums / counts.clamp_min_(1.0)
                relation_values = sums.reshape(
                    num_nodes, block_size * self.input_dim
                )
            weight = self.relation_linear.weight[
                :, begin * self.input_dim : end * self.input_dim
            ]
            output = output + F.linear(relation_values, weight)

        return F.relu(output + self.self_linear(node_features))


class GlycanRGCNF2(nn.Module):
    """The requested three-layer relational F2 network."""

    def __init__(self, num_classes: int) -> None:
        super().__init__()
        self.embedding = nn.Embedding(EMBEDDING_ROWS, HIDDEN_DIM)
        self.layers = nn.ModuleList(
            [
                RelationalMeanLayer(HIDDEN_DIM, HIDDEN_DIM, NUM_RELATIONS_EXPECTED)
                for _ in range(NUM_LAYERS)
            ]
        )
        self.mlp = nn.Sequential(
            nn.Linear(HIDDEN_DIM * NUM_LAYERS * 2, HIDDEN_DIM * NUM_LAYERS * 2),
            nn.ReLU(),
            nn.Linear(HIDDEN_DIM * NUM_LAYERS * 2, num_classes),
        )

    def forward(self, batch: Batch) -> torch.Tensor:
        node_features = self.embedding(batch.unit_type.long())
        hiddens: list[torch.Tensor] = []
        for layer in self.layers:
            node_features = layer(
                node_features, batch.edge_index, batch.edge_type
            )
            hiddens.append(node_features)
        node_features = torch.cat(hiddens, dim=-1)
        graph_features = torch.cat(
            [
                global_mean_pool(node_features, batch.batch),
                global_max_pool(node_features, batch.batch),
            ],
            dim=-1,
        )
        return self.mlp(graph_features)


def task_loss(
    spec: TaskSpec, logits: torch.Tensor, labels: torch.Tensor
) -> torch.Tensor:
    if spec.num_classes == 1:
        return F.binary_cross_entropy_with_logits(
            logits.reshape(-1), labels.reshape(-1).float()
        )
    return F.cross_entropy(logits, labels.reshape(-1).long())


def _safe_auc(labels: np.ndarray, probabilities: np.ndarray) -> float | None:
    if np.unique(labels).size < 2:
        return None
    return float(roc_auc_score(labels, probabilities))


def _safe_average_precision(
    labels: np.ndarray, probabilities: np.ndarray
) -> float | None:
    if np.unique(labels).size < 2:
        return None
    return float(average_precision_score(labels, probabilities))


def compute_metrics(
    spec: TaskSpec, logits: torch.Tensor, labels: torch.Tensor
) -> dict[str, float | None]:
    logits = logits.detach().float().cpu()
    labels_np = labels.detach().cpu().reshape(-1).numpy()
    if spec.num_classes == 1:
        labels_np = labels_np.astype(np.int64)
        probabilities = torch.sigmoid(logits.reshape(-1)).numpy()
        predictions = (probabilities >= 0.5).astype(np.int64)
        return {
            "auroc": _safe_auc(labels_np, probabilities),
            "auprc": _safe_average_precision(labels_np, probabilities),
            "accuracy": float(accuracy_score(labels_np, predictions)),
        }

    labels_np = labels_np.astype(np.int64)
    predictions = logits.argmax(dim=1).numpy()
    return {
        "accuracy": float(accuracy_score(labels_np, predictions)),
        "macro_f1": float(
            f1_score(
                labels_np,
                predictions,
                labels=[0, 1, 2],
                average="macro",
                zero_division=0,
            )
        ),
    }


def _make_batch(
    graphs: Sequence[Data], indices: Sequence[int], device: torch.device
) -> Batch:
    batch = Batch.from_data_list([graphs[int(index)] for index in indices])
    return batch.to(device)


def _evaluate(
    model: GlycanRGCNF2,
    graphs: Sequence[Data],
    indices: Sequence[int],
    spec: TaskSpec,
    device: torch.device,
    batch_size: int = BATCH_SIZE,
) -> tuple[torch.Tensor, torch.Tensor]:
    model.eval()
    logits_parts: list[torch.Tensor] = []
    label_parts: list[torch.Tensor] = []
    with torch.no_grad():
        for start in range(0, len(indices), batch_size):
            batch_indices = indices[start : start + batch_size]
            batch = _make_batch(graphs, batch_indices, device)
            logits_parts.append(model(batch).detach().cpu())
            label_parts.append(batch.y.detach().cpu())
    if not logits_parts:
        raise DataError(f"{spec.key}: evaluation split is empty")
    return torch.cat(logits_parts, dim=0), torch.cat(label_parts, dim=0)


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def _train_one_seed(
    task: ParsedTask,
    seed: int,
    device: torch.device,
    epochs: int,
    batch_size: int,
) -> dict[str, Any]:
    spec = task.spec
    _seed_everything(seed)
    model = GlycanRGCNF2(spec.num_classes).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=T_MAX
    )

    train_indices = task.split_indices["train"]
    valid_indices = task.split_indices["valid"]
    test_indices = task.split_indices["test"]
    rng = np.random.default_rng(seed)
    best_value = -math.inf
    best_epoch = 0
    best_state: dict[str, torch.Tensor] | None = None
    last_train_loss = math.nan

    for epoch in range(1, epochs + 1):
        model.train()
        order = rng.permutation(len(train_indices))
        epoch_loss = 0.0
        seen = 0
        for start in range(0, len(order), batch_size):
            batch_indices = [
                train_indices[int(order[position])]
                for position in range(start, min(start + batch_size, len(order)))
            ]
            batch = _make_batch(task.graphs, batch_indices, device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(batch)
            loss = task_loss(spec, logits, batch.y)
            if not torch.isfinite(loss):
                raise FloatingPointError(
                    f"{spec.key} seed {seed} epoch {epoch}: non-finite loss"
                )
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.detach().cpu()) * len(batch_indices)
            seen += len(batch_indices)
        last_train_loss = epoch_loss / max(seen, 1)

        valid_logits, valid_labels = _evaluate(
            model, task.graphs, valid_indices, spec, device, batch_size
        )
        valid_metrics = compute_metrics(spec, valid_logits, valid_labels)
        selection_value = valid_metrics.get(spec.selection_metric)
        if selection_value is None or not math.isfinite(float(selection_value)):
            raise FloatingPointError(
                f"{spec.key} seed {seed} epoch {epoch}: "
                f"validation {spec.selection_metric} is undefined"
            )
        if float(selection_value) > best_value:
            best_value = float(selection_value)
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
        scheduler.step()

    if best_state is None:
        raise RuntimeError(f"{spec.key} seed {seed}: no best checkpoint was selected")
    model.load_state_dict(best_state)
    valid_logits, valid_labels = _evaluate(
        model, task.graphs, valid_indices, spec, device, batch_size
    )
    valid_metrics = compute_metrics(spec, valid_logits, valid_labels)
    test_logits, test_labels = _evaluate(
        model, task.graphs, test_indices, spec, device, batch_size
    )
    test_metrics = compute_metrics(spec, test_logits, test_labels)
    return {
        "seed": seed,
        "best_epoch": best_epoch,
        "last_train_loss": last_train_loss,
        "validation_selection": {
            "metric": spec.selection_metric,
            "value": best_value,
        },
        "validation": valid_metrics,
        "test": test_metrics,
    }


def _looks_like_cuda_failure(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "cuda",
            "cudnn",
            "cublas",
            "device-side",
            "out of memory",
            "graph",
        )
    )


def _resolve_device(requested: str) -> torch.device:
    if requested == "cpu":
        return torch.device("cpu")
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("--device cuda requested, but CUDA is unavailable")
        return torch.device("cuda:0")
    if requested == "auto":
        return torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    raise ValueError(f"unknown device selection: {requested!r}")


def _device_label(device: torch.device) -> str:
    if device.type == "cuda":
        return torch.cuda.get_device_name(device)
    return "cpu"


def _train_task(
    task: ParsedTask,
    seeds: Sequence[int],
    requested_device: str,
    epochs: int,
    batch_size: int,
) -> tuple[list[dict[str, Any]], torch.device, str | None]:
    device = _resolve_device(requested_device)
    per_seed: list[dict[str, Any]] = []
    fallback_reason: str | None = None
    try:
        for seed in seeds:
            result = _train_one_seed(task, seed, device, epochs, batch_size)
            result["device"] = str(device)
            per_seed.append(result)
            if device.type == "cuda":
                torch.cuda.empty_cache()
    except RuntimeError as exc:
        if (
            device.type == "cuda"
            and requested_device == "auto"
            and _looks_like_cuda_failure(exc)
        ):
            fallback_reason = f"{type(exc).__name__}: {exc}"
            device = torch.device("cpu")
            per_seed = []
            for seed in seeds:
                result = _train_one_seed(task, seed, device, epochs, batch_size)
                result["device"] = str(device)
                result["cuda_fallback_reason"] = fallback_reason
                per_seed.append(result)
        else:
            raise
    return per_seed, device, fallback_reason


def _aggregate_metrics(
    per_seed: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, float | int]]:
    metric_groups = {
        "validation": ("auroc", "auprc", "accuracy", "macro_f1"),
        "test": ("auroc", "auprc", "accuracy", "macro_f1"),
    }
    aggregate: dict[str, dict[str, float | int]] = {}
    for group, metric_names in metric_groups.items():
        for metric_name in metric_names:
            values = [
                result[group].get(metric_name)
                for result in per_seed
                if result[group].get(metric_name) is not None
            ]
            numeric = [
                float(value)
                for value in values
                if value is not None and math.isfinite(float(value))
            ]
            if numeric:
                aggregate[f"{group}_{metric_name}"] = {
                    "mean": float(np.mean(numeric)),
                    "std": float(np.std(numeric, ddof=1))
                    if len(numeric) > 1
                    else 0.0,
                    "n": len(numeric),
                }
    return aggregate


def _torchdrug_comparison() -> dict[str, Any]:
    return {
        "reference": "GlycanML GlycanRGCN (TorchDrug) + GlycanPropertyPrediction",
        "torchdrug_installed": False,
        "measured_numeric_delta": None,
        "notes": [
            "No TorchDrug runtime is installed in this environment, so no "
            "numeric delta was measured.",
            "This script implements the requested per-relation mean channels; "
            "it is structurally related to, but not a bitwise clone of, "
            "TorchDrug's RelationalGraphConv.",
            "The upstream link_RGCN.yaml specifies num_class: 2 while the CSV "
            "contains N, O, and free; this benchmark intentionally uses three "
            "classes as required for the Table 3 recomputation.",
            "The upstream dataset docstring also contains stale split "
            "statistics; this script validates the actual CSV one-hot counts.",
        ],
    }


def _smoke_forward_backward(
    task: ParsedTask,
    device: torch.device,
    batch_size: int = BATCH_SIZE,
) -> dict[str, Any]:
    spec = task.spec
    _seed_everything(0)
    model = GlycanRGCNF2(spec.num_classes).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY
    )
    train_indices = task.split_indices["train"]
    selected = train_indices[:batch_size]
    batch = _make_batch(task.graphs, selected, device)
    model.train()
    optimizer.zero_grad(set_to_none=True)
    logits = model(batch)
    loss = task_loss(spec, logits, batch.y)
    loss.backward()
    finite_gradients = all(
        parameter.grad is not None and bool(torch.isfinite(parameter.grad).all())
        for parameter in model.parameters()
    )
    gradients_present = all(
        parameter.grad is not None for parameter in model.parameters()
    )
    if not torch.isfinite(loss):
        raise FloatingPointError(f"{spec.key}: smoke loss is not finite")
    if not finite_gradients or not gradients_present:
        raise FloatingPointError(f"{spec.key}: smoke gradients are not finite")
    return {
        "rows": len(task.graphs),
        "split_counts": task.split_counts,
        "labels": task.label_counts,
        "nodes": task.node_count,
        "edges": task.edge_count,
        "min_nodes": task.min_nodes,
        "max_nodes": task.max_nodes,
        "batch_size": len(selected),
        "logits_shape": list(logits.shape),
        "loss": float(loss.detach().cpu()),
        "loss_finite": bool(torch.isfinite(loss)),
        "gradients_present": gradients_present,
        "gradients_finite": finite_gradients,
    }


def run_smoke(
    parsed: Mapping[str, ParsedTask],
    requested_device: str,
    vocabulary: Vocabulary,
    batch_size: int = BATCH_SIZE,
) -> dict[str, Any]:
    device = _resolve_device(requested_device)
    fallback_reason: str | None = None
    try:
        task_results = {
            key: _smoke_forward_backward(task, device, batch_size)
            for key, task in parsed.items()
        }
    except RuntimeError as exc:
        if (
            device.type == "cuda"
            and requested_device == "auto"
            and _looks_like_cuda_failure(exc)
        ):
            fallback_reason = f"{type(exc).__name__}: {exc}"
            device = torch.device("cpu")
            task_results = {
                key: _smoke_forward_backward(task, device, batch_size)
                for key, task in parsed.items()
            }
        else:
            raise
    return {
        "status": "PASS",
        "mode": "smoke",
        "device": str(device),
        "device_name": _device_label(device),
        "cuda_fallback": fallback_reason,
        "torch": torch.__version__,
        "pyg": __import__("torch_geometric").__version__,
        "vocab": {
            "path": str(vocabulary.path),
            "active_units": NUM_UNITS_EXPECTED,
            "relation_ids": NUM_RELATIONS_EXPECTED,
            "embedding_rows": EMBEDDING_ROWS,
        },
        "tasks": task_results,
        "final_benchmark_json_written": False,
    }


def build_report(
    parsed: Mapping[str, ParsedTask],
    seeds: Sequence[int],
    all_results: Mapping[str, Sequence[Mapping[str, Any]]],
    device_fallbacks: Mapping[str, tuple[torch.device, str | None]],
    epochs: int,
    batch_size: int,
) -> dict[str, Any]:
    task_reports: dict[str, Any] = {}
    for key, task in parsed.items():
        per_seed = list(all_results[key])
        device, fallback_reason = device_fallbacks[key]
        label_map = task.spec.label_map or {"0": 0, "1": 1}
        task_reports[key] = {
            "csv": str(task.csv_path),
            "target_column": task.spec.label_column,
            "num_classes": task.spec.num_classes,
            "class_mapping": label_map,
            "rows": len(task.graphs),
            "split_counts": task.split_counts,
            "label_counts": task.label_counts,
            "nodes": task.node_count,
            "edges": task.edge_count,
            "min_nodes": task.min_nodes,
            "max_nodes": task.max_nodes,
            "selection_metric": task.spec.selection_metric,
            "report_metric": task.spec.report_metric,
            "device": str(device),
            "cuda_fallback_reason": fallback_reason,
            "per_seed": per_seed,
            "aggregate": _aggregate_metrics(per_seed),
        }

    return {
        "status": "PASS",
        "benchmark": "GlycanML Table 3 RGCN F2 recompute",
        "mode": "full",
        "seeds": list(seeds),
        "vocab": {
            "active_units": NUM_UNITS_EXPECTED,
            "relation_ids": NUM_RELATIONS_EXPECTED,
            "embedding_rows": EMBEDDING_ROWS,
        },
        "parser": {
            "source": "GlycanML/module/custom_data/glycan.py",
            "edge_semantics": (
                "per-branch all ordered unit pairs; each resolved relation is "
                "emitted in both directions"
            ),
            "to_undirected": False,
            "self_loops": False,
            "deduplicate_edges": False,
        },
        "model": {
            "embedding": [EMBEDDING_ROWS, HIDDEN_DIM],
            "layers": NUM_LAYERS,
            "hidden_dim": HIDDEN_DIM,
            "relation_channels": NUM_RELATIONS_EXPECTED,
            "pooling": ["mean", "max"],
            "mlp": [HIDDEN_DIM * NUM_LAYERS * 2, HIDDEN_DIM * NUM_LAYERS * 2],
        },
        "training": {
            "optimizer": "Adam",
            "lr": LR,
            "weight_decay": WEIGHT_DECAY,
            "batch_size": batch_size,
            "epochs": epochs,
            "scheduler": "CosineAnnealingLR",
            "T_max": T_MAX,
            "deterministic_seed_control": True,
        },
        "tasks": task_reports,
        "torchdrug_comparison": _torchdrug_comparison(),
    }


def parse_seeds(value: str) -> list[int]:
    try:
        seeds = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid seed list: {value!r}") from exc
    if not seeds:
        raise argparse.ArgumentTypeError("at least one seed is required")
    return seeds


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="parse all rows and run one forward/backward per task")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--seeds", type=parse_seeds, default=parse_seeds("0,1,2"))
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--vocab", type=Path, default=DEFAULT_VOCAB)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.epochs <= 0:
        raise SystemExit("--epochs must be positive")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive")
    try:
        vocabulary = load_vocabulary(args.vocab)
        parsed = load_all_tasks(args.data_dir, vocabulary)
        if args.smoke:
            result = run_smoke(parsed, args.device, vocabulary, args.batch_size)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=False))
            return 0

        all_results: dict[str, list[dict[str, Any]]] = {}
        device_fallbacks: dict[str, tuple[torch.device, str | None]] = {}
        for key, task in parsed.items():
            results, device, fallback_reason = _train_task(
                task, args.seeds, args.device, args.epochs, args.batch_size
            )
            all_results[key] = results
            device_fallbacks[key] = (device, fallback_reason)

        report = build_report(
            parsed,
            args.seeds,
            all_results,
            device_fallbacks,
            args.epochs,
            args.batch_size,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (GraphParseError, DataError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
