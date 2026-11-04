from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SAMPLE_ACCESSION = "O75144"


@dataclass(frozen=True)
class ReferenceSite:
    position: int
    motif: str
    label: int
    predicted_label: int
    prob_positive: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "motif": self.motif,
            "label": self.label,
            "predicted_label": self.predicted_label,
            "prob_positive": self.prob_positive,
        }


@dataclass(frozen=True)
class SampleSequence:
    accession: str
    sequence: str
    source: str
    reference_sites: tuple[ReferenceSite, ...]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "accession": self.accession,
            "sequence": self.sequence,
            "source": self.source,
        }


class SampleProvider:
    def __init__(
        self,
        repo_root: Path,
        *,
        accession: str = DEFAULT_SAMPLE_ACCESSION,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.accession = accession
        self._sample: SampleSequence | None = None

    def load(self) -> SampleSequence | None:
        if self._sample is not None:
            return self._sample

        candidates_path = self.repo_root / "reports" / "candidates_30_lora.csv"
        predictions_path = (
            self.repo_root
            / "reports"
            / "esm150_w1_candidates_v0"
            / "predictions.csv"
        )
        if not candidates_path.is_file() or not predictions_path.is_file():
            return None

        sequence = ""
        with candidates_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["id"] == self.accession:
                    sequence = row["sequence"]
                    break
        if not sequence:
            return None

        reference_sites: list[ReferenceSite] = []
        with predictions_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["accession"] != self.accession:
                    continue
                reference_sites.append(
                    ReferenceSite(
                        position=int(row["position"]),
                        motif=row["motif"],
                        label=int(row["label"]),
                        predicted_label=int(row["predicted_label"]),
                        prob_positive=float(row["prob_positive"]),
                    )
                )
        reference_sites.sort(key=lambda site: site.position)
        self._sample = SampleSequence(
            accession=self.accession,
            sequence=sequence,
            source=(
                "reports/candidates_30_lora.csv + "
                "reports/esm150_w1_candidates_v0/predictions.csv"
            ),
            reference_sites=tuple(reference_sites),
        )
        return self._sample
