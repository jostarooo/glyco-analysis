from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Sequence


MAX_SEQUENCE_LENGTH = 5179
ALLOWED_RESIDUES = frozenset("ACDEFGHIKLMNPQRSTVWYBXZUOJ")


class ValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Sequon:
    position: int
    residue: str
    motif: str


@dataclass(frozen=True)
class SitePrediction:
    position: int
    motif: str
    prob_positive: float
    predicted_label: int
    logit_negative: float
    logit_positive: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "motif": self.motif,
            "prob_positive": self.prob_positive,
            "predicted_label": self.predicted_label,
            "logit_negative": self.logit_negative,
            "logit_positive": self.logit_positive,
        }


@dataclass(frozen=True)
class PredictionResult:
    sequence_sha256: str
    sequence_length: int
    candidates: tuple[SitePrediction, ...]
    elapsed_seconds: float
    model: dict[str, Any]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence_sha256": self.sequence_sha256,
            "sequence_length": self.sequence_length,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "elapsed_seconds": self.elapsed_seconds,
            "model": dict(self.model),
            "limitations": list(self.limitations),
        }


def normalize_sequence(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError("SEQUENCE_TYPE", "序列必须是字符串")

    residues: list[str] = []
    for line in value.splitlines():
        if line.startswith(">"):
            continue
        residues.append("".join(line.split()))
    sequence = "".join(residues).upper()

    if not sequence:
        raise ValidationError("SEQUENCE_EMPTY", "序列不能为空")
    if len(sequence) > MAX_SEQUENCE_LENGTH:
        raise ValidationError(
            "SEQUENCE_TOO_LONG",
            f"序列长度为 {len(sequence)}，上限为 {MAX_SEQUENCE_LENGTH}",
        )
    invalid = sorted(set(sequence) - ALLOWED_RESIDUES)
    if invalid:
        preview = "".join(invalid[:8])
        raise ValidationError(
            "SEQUENCE_ALPHABET",
            f"序列包含不支持的残基：{preview}",
        )
    return sequence


def sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("ascii")).hexdigest().upper()


def find_sequons(sequence: Sequence[str] | str) -> tuple[Sequon, ...]:
    found: list[Sequon] = []
    length = len(sequence)
    for index in range(length - 2):
        motif = sequence[index : index + 3]
        if motif[0] == "N" and motif[1] != "P" and motif[2] in {"S", "T"}:
            found.append(
                Sequon(
                    position=index + 1,
                    residue="N",
                    motif=motif,
                )
            )
    return tuple(found)
