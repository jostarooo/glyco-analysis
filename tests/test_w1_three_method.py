from __future__ import annotations

import csv
import importlib.util
import io
import json
import math
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = load_script("run_w1_three_method_test", "scripts/run_w1_three_method.py")
checker = load_script(
    "check_w1_three_method_test",
    "scripts/check_w1_three_method.py",
)


def write_csv(
    path: Path,
    columns: tuple[str, ...],
    rows: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def softmax_two(negative: float, positive: float) -> tuple[float, float]:
    maximum = max(negative, positive)
    first = math.exp(negative - maximum)
    second = math.exp(positive - maximum)
    total = first + second
    return first / total, second / total


class SyntheticRun:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.candidates = self.root / "candidates_30.csv"
        self.candidates_lora = self.root / "candidates_30_lora.csv"
        self.esm35 = self.root / "esm35"
        self.esm150 = self.root / "esm150"
        self.adapter = self.root / "adapter"
        self.compat = self.root / "compat"
        self.out_dir = self.root / "comparison"
        self.sites: list[dict[str, object]] = []
        self.lora_rows: list[dict[str, object]] = []
        self.esm35_rows: list[dict[str, object]] = []
        self.esm150_rows: list[dict[str, object]] = []
        self.esm35_manifest: dict[str, object] = {}
        self._build()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.temporary.cleanup()

    def _build(self) -> None:
        self.adapter.mkdir()
        (self.adapter / "adapter_model.safetensors").write_text(
            "synthetic adapter weights\n",
            encoding="ascii",
        )
        write_json(self.adapter / "adapter_config.json", {"fixture": True})
        self.compat.mkdir()

        honest_accessions = [f"P{index:04d}" for index in range(1, 29)]
        all_accessions = [*honest_accessions, "P13611"]
        categories = {
            accession: {
                "experimental_positive": 1,
                "unannotated_control": 1,
                "inferred_positive": 0,
            }
            for accession in honest_accessions
        }
        categories["P13611"] = {
            "experimental_positive": 0,
            "unannotated_control": 0,
            "inferred_positive": 1,
        }
        for index in range(54):
            categories[honest_accessions[index % len(honest_accessions)]][
                "experimental_positive"
            ] += 1
        for index in range(20):
            categories[honest_accessions[index % len(honest_accessions)]][
                "unannotated_control"
            ] += 1
        for index in range(70):
            categories[honest_accessions[index % len(honest_accessions)]][
                "inferred_positive"
            ] += 1

        alphabet = "ACDEFGHIKLMNPQRSTVWY"
        sequence_by_accession: dict[str, str] = {}
        category_index = {
            "experimental_positive": 0,
            "unannotated_control": 0,
            "inferred_positive": 0,
        }
        pattern35: dict[tuple[str, int], int] = {}
        pattern150: dict[tuple[str, int], int] = {}
        probability35: dict[tuple[str, int], float] = {}
        probability150: dict[tuple[str, int], float] = {}

        for accession_index, accession in enumerate(all_accessions):
            count = sum(categories[accession].values())
            sequence_length = 4 * count + 8
            filler = alphabet[accession_index % len(alphabet)] + alphabet[
                (accession_index // len(alphabet)) % len(alphabet)
            ]
            characters = [filler[index % 2] for index in range(sequence_length)]
            characters[0] = "M"
            sequence_by_accession[accession] = "".join(characters)
            position_index = 0
            for evidence_class in (
                "experimental_positive",
                "inferred_positive",
                "unannotated_control",
            ):
                for _ in range(categories[accession][evidence_class]):
                    position = 2 + 4 * position_index
                    position_index += 1
                    characters = list(sequence_by_accession[accession])
                    characters[position - 1 : position + 2] = ["N", "S", "T"]
                    sequence_by_accession[accession] = "".join(characters)
                    key = (accession, position)
                    if evidence_class == "experimental_positive":
                        label = 1
                        linkage = "N-linked"
                        evidence = "ECO:0000269"
                        evaluation_label: object = 1
                        included = 1
                        variant = category_index[evidence_class] % 3
                        if variant == 0:
                            pred35, pred150 = 0, 0
                        elif variant == 1:
                            pred35, pred150 = 0, 1
                        else:
                            pred35, pred150 = 1, 0
                    elif evidence_class == "inferred_positive":
                        label = 1
                        linkage = "N-linked"
                        evidence = "ECO:0000255"
                        evaluation_label = ""
                        included = 0
                        pred35, pred150 = 1, 1
                    else:
                        label = 0
                        linkage = "unannotated_control"
                        evidence = ""
                        evaluation_label = 0
                        included = 1
                        variant = category_index[evidence_class] % 3
                        if variant == 0:
                            pred35, pred150 = 1, 1
                        elif variant == 1:
                            pred35, pred150 = 1, 0
                        else:
                            pred35, pred150 = 0, 1
                    category_index[evidence_class] += 1

                    if pred35 == 1:
                        p35 = 0.58 + 0.01 * (
                            category_index[evidence_class] % 20
                        )
                    else:
                        p35 = 0.42 - 0.01 * (
                            category_index[evidence_class] % 20
                        )
                    margin150 = 0.4 + 0.02 * (
                        category_index[evidence_class] % 20
                    )
                    logit150 = margin150 if pred150 == 1 else -margin150
                    _, p150 = softmax_two(0.0, logit150)
                    pattern35[key] = pred35
                    pattern150[key] = pred150
                    probability35[key] = p35
                    probability150[key] = p150
                    self.sites.append(
                        {
                            "accession": accession,
                            "protein_name": f"Protein {accession}",
                            "seq_len": sequence_length,
                            "pos": position,
                            "residue": "N",
                            "motif": "NST",
                            "sequon": 1,
                            "label": label,
                            "linkage": linkage,
                            "n_features": 1,
                            "evidence": evidence,
                            "uniprot_release": "2026_03",
                            "fetched_at": "fixture",
                            "_class": evidence_class,
                            "_evaluation_label": evaluation_label,
                            "_included": included,
                        }
                    )

        write_csv(
            self.candidates,
            runner.CANDIDATE_COLUMNS,
            [
                {name: row[name] for name in runner.CANDIDATE_COLUMNS}
                for row in self.sites
            ],
        )
        self.lora_rows = [
            {
                "label": row["label"],
                "id": row["accession"],
                "pos": row["pos"],
                "sequence": sequence_by_accession[str(row["accession"])],
            }
            for row in self.sites
        ]
        write_csv(self.candidates_lora, checker.LORA_COLUMNS, self.lora_rows)

        honest = [row for row in self.sites if row["_included"] == 1]
        self.esm35_rows = []
        for row_index, row in enumerate(honest):
            key = (str(row["accession"]), int(row["pos"]))
            probability = probability35[key]
            self.esm35_rows.append(
                {
                    "row_id": f"{key[0]}:{key[1]}",
                    "accession": key[0],
                    "pos": key[1],
                    "label": row["_evaluation_label"],
                    "fold_id": f"lopo:{key[0]}",
                    "logit": math.log(probability / (1.0 - probability)),
                    "probability": repr(probability),
                    "prediction": int(probability >= 0.5),
                }
            )
        write_csv(self.esm35 / "predictions.csv", runner.ESM35_COLUMNS, self.esm35_rows)
        labels = [int(row["_evaluation_label"]) for row in honest]
        predictions = [int(row["prediction"]) for row in self.esm35_rows]
        probabilities = [float(row["probability"]) for row in self.esm35_rows]
        recomputed = runner.binary_metrics(labels, predictions, probabilities)
        confusion = recomputed["confusion"]
        metrics35 = {
            "schema": runner.ESM35_SCHEMA,
            "benchmark_id": runner.BENCHMARK_ID,
            "threshold": 0.5,
            "confusion": {
                "experimental_positive": {
                    "predicted_control": confusion["fn"],
                    "predicted_positive": confusion["tp"],
                },
                "unannotated_control": {
                    "predicted_control": confusion["tn"],
                    "predicted_positive": confusion["fp"],
                },
            },
            "metrics": recomputed["metrics"],
            "null_reasons": recomputed["null_reasons"],
        }
        write_json(self.esm35 / "metrics.json", metrics35)
        self.esm35_manifest = {
            "schema": runner.ESM35_SCHEMA,
            "status": "complete",
            "inputs": {
                "candidates": {
                    "path": str(self.candidates),
                    "sha256": checker.sha256_file(self.candidates),
                }
            },
            "artifacts": {
                "predictions.csv": {
                    "sha256": checker.sha256_file(self.esm35 / "predictions.csv"),
                    "bytes": (self.esm35 / "predictions.csv").stat().st_size,
                },
                "metrics.json": {
                    "sha256": checker.sha256_file(self.esm35 / "metrics.json"),
                    "bytes": (self.esm35 / "metrics.json").stat().st_size,
                },
            },
        }
        write_json(self.esm35 / "manifest.json", self.esm35_manifest)

        self.esm150_rows = []
        for row_index, row in enumerate(self.sites):
            accession = str(row["accession"])
            position = int(row["pos"])
            key = (accession, position)
            sequence = sequence_by_accession[accession]
            pred150 = pattern150[key]
            margin = 0.4 + 0.02 * (row_index % 20)
            logit_negative = 0.0
            logit_positive = margin if pred150 == 1 else -margin
            prob_negative, prob_positive = softmax_two(
                logit_negative, logit_positive
            )
            self.esm150_rows.append(
                {
                    "row_index": row_index,
                    "accession": accession,
                    "position": position,
                    "label": row["label"],
                    "sequence_sha256": checker.sha256_text(sequence),
                    "sequence_length": len(sequence),
                    "token_length": len(sequence) + 2,
                    "residue": "N",
                    "motif": "NST",
                    "is_sequon": 1,
                    "logit_negative": repr(logit_negative),
                    "logit_positive": repr(logit_positive),
                    "prob_negative": repr(prob_negative),
                    "prob_positive": repr(prob_positive),
                    "predicted_label": int(logit_positive > logit_negative),
                }
            )
        write_csv(self.esm150 / "predictions.csv", runner.ESM150_COLUMNS, self.esm150_rows)
        (self.esm150 / "report.md").write_text(
            "# Synthetic ESM-150M candidate inference\n",
            encoding="utf-8",
        )
        manifest150 = {
            "schema": runner.ESM150_SCHEMA,
            "status": "complete",
            "inputs": {
                "candidates_lora": {
                    "path": str(self.candidates_lora),
                    "sha256": checker.sha256_file(self.candidates_lora),
                    "row_count": 201,
                    "protein_count": 29,
                    "unique_sequence_count": 29,
                },
                "adapter": {
                    "model_sha256": checker.sha256_file(
                        self.adapter / "adapter_model.safetensors"
                    ),
                    "tensor_count": 376,
                },
                "base_model": {
                    "id": runner.EXPECTED_BASE_MODEL_ID,
                    "revision": runner.EXPECTED_BASE_MODEL_REVISION,
                    "weights_sha256": runner.EXPECTED_BASE_WEIGHTS_SHA256,
                },
            },
            "counts": {
                "rows": 201,
                "accessions": 29,
                "unique_sequences": 29,
                "encoder_forwards": 29,
            },
            "inference": {
                "rows": 201,
                "decision_rule": "logit_positive > logit_negative",
            },
            "artifacts": {
                "predictions.csv": {
                    "sha256": checker.sha256_file(self.esm150 / "predictions.csv"),
                    "bytes": (self.esm150 / "predictions.csv").stat().st_size,
                },
                "report.md": {
                    "sha256": checker.sha256_file(self.esm150 / "report.md"),
                    "bytes": (self.esm150 / "report.md").stat().st_size,
                },
            },
        }
        write_json(self.esm150 / "manifest.json", manifest150)

    @contextmanager
    def patch_expected_hashes(self):
        with mock.patch.multiple(
            runner,
            EXPECTED_CANDIDATES_SHA256=checker.sha256_file(self.candidates),
            EXPECTED_CANDIDATES_LORA_SHA256=checker.sha256_file(
                self.candidates_lora
            ),
            EXPECTED_ESM35_PREDICTIONS_SHA256=checker.sha256_file(
                self.esm35 / "predictions.csv"
            ),
            EXPECTED_ESM35_METRICS_SHA256=checker.sha256_file(
                self.esm35 / "metrics.json"
            ),
            EXPECTED_ESM35_MANIFEST_SHA256=checker.sha256_file(
                self.esm35 / "manifest.json"
            ),
            EXPECTED_ADAPTER_SHA256=checker.sha256_file(
                self.adapter / "adapter_model.safetensors"
            ),
        ), mock.patch.multiple(
            checker,
            EXPECTED_CANDIDATES_SHA256=checker.sha256_file(self.candidates),
            EXPECTED_CANDIDATES_LORA_SHA256=checker.sha256_file(
                self.candidates_lora
            ),
            EXPECTED_ADAPTER_SHA256=checker.sha256_file(
                self.adapter / "adapter_model.safetensors"
            ),
        ):
            yield

    def generate(self) -> tuple[object, object, object]:
        sites, _ = runner.load_annotation_sites(self.candidates)
        votes35 = runner.load_esm35_votes(self.esm35, sites)
        votes150 = runner.load_esm150_votes(self.esm150, sites)
        compared = runner.build_comparison(sites, votes35, votes150)
        metrics = runner.compute_metrics(compared)
        review = runner.select_top_disagreements(compared)
        compared = runner.apply_review_ranks(compared, review)
        runner.write_comparison_run(
            runner.ComparisonConfig(
                candidates=self.candidates,
                esm35_run_dir=self.esm35,
                esm150_run_dir=self.esm150,
                out_dir=self.out_dir,
            ),
            sites,
            compared,
            metrics,
            review,
        )
        return sites, compared, review

    def mutate_35_to_inferred_key(self) -> None:
        inferred = next(
            row for row in self.sites if row["_class"] == "inferred_positive"
        )
        rows = [dict(row) for row in self.esm35_rows]
        rows[-1] = {
            **rows[-1],
            "row_id": f"{inferred['accession']}:{inferred['pos']}",
            "accession": inferred["accession"],
            "pos": inferred["pos"],
            "label": 1,
            "fold_id": f"lopo:{inferred['accession']}",
        }
        write_csv(self.esm35 / "predictions.csv", runner.ESM35_COLUMNS, rows)
        artifacts = self.esm35_manifest["artifacts"]
        artifacts["predictions.csv"] = {
            "sha256": checker.sha256_file(self.esm35 / "predictions.csv"),
            "bytes": (self.esm35 / "predictions.csv").stat().st_size,
        }
        write_json(self.esm35 / "manifest.json", self.esm35_manifest)

    def apply_manual_review(
        self,
        statuses: dict[str, str],
        notes: dict[str, str],
        *,
        base_commit: str,
        reviewed_at: str,
    ) -> None:
        review_path = self.out_dir / "review_top10.csv"
        rows = checker.read_csv_exact(review_path, checker.REVIEW_COLUMNS)
        for row in rows:
            row_id = row["row_id"]
            row["review_status"] = statuses[row_id]
            row["reviewer_note"] = notes[row_id]
        write_csv(review_path, checker.REVIEW_COLUMNS, rows)

        report_path = self.out_dir / "report.md"
        statuses_in_report = sorted({row["review_status"] for row in rows})
        report_path.write_text(
            report_path.read_text(encoding="utf-8")
            + "\nManual review statuses: "
            + ", ".join(statuses_in_report)
            + "\n",
            encoding="utf-8",
        )

        manifest_path = self.out_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["manual_review"] = {
            "base_commit": base_commit,
            "reviewed_at": reviewed_at,
            "status_counts": checker.manual_review_counts(rows),
        }
        for name, path in (
            ("review_top10.csv", review_path),
            ("report.md", report_path),
        ):
            manifest["artifacts"][name] = {
                "bytes": path.stat().st_size,
                "sha256": checker.sha256_file(path),
            }
        write_json(manifest_path, manifest)


class MetricTests(unittest.TestCase):
    def test_confusion_mcc_and_undefined_mcc(self):
        result = runner.binary_metrics([1, 1, 0, 0], [1, 0, 0, 1], [0.9, 0.4, 0.1, 0.8])
        self.assertEqual(result["confusion"], {"tp": 1, "fp": 1, "tn": 1, "fn": 1})
        self.assertAlmostEqual(result["metrics"]["mcc"], 0.0)
        self.assertTrue(result["mcc_defined"])

        undefined = runner.binary_metrics([1, 1], [1, 1], [0.9, 0.8])
        self.assertEqual(undefined["metrics"]["mcc"], 0.0)
        self.assertFalse(undefined["mcc_defined"])
        self.assertIsNone(undefined["metrics"]["roc_auc"])
        self.assertEqual(
            undefined["null_reasons"]["roc_auc"],
            "requires_both_label_classes",
        )

    def test_roc_auc_is_tie_aware(self):
        self.assertEqual(
            runner.roc_auc([1, 0], [0.5, 0.5]),
            0.5,
        )
        self.assertEqual(
            runner.roc_auc([1, 0, 1, 0], [0.9, 0.7, 0.8, 0.6]),
            1.0,
        )
        self.assertEqual(
            checker.roc_auc([1, 0], [0.2, 0.8]),
            0.0,
        )

    def test_runner_and_checker_metric_arithmetic_agree(self):
        labels = [1, 0, 1, 0, 1]
        predictions = [1, 0, 0, 1, 1]
        probabilities = [0.9, 0.2, 0.4, 0.7, 0.8]
        left = runner.binary_metrics(labels, predictions, probabilities)
        right = checker.binary_metrics(labels, predictions, probabilities)
        self.assertEqual(left["confusion"], right["confusion"])
        self.assertEqual(left["metrics"], right["metrics"])
        self.assertEqual(left["mcc_defined"], right["mcc_defined"])


class EndToEndTests(unittest.TestCase):
    def test_full_fixture_inferred_exclusion_and_checker_pass(self):
        with SyntheticRun() as fixture:
            with fixture.patch_expected_hashes():
                _, compared, review = fixture.generate()
                comparison = checker.read_csv_exact(
                    fixture.out_dir / "comparison.csv",
                    checker.COMPARISON_COLUMNS,
                )
                metrics = json.loads(
                    (fixture.out_dir / "metrics.json").read_text(encoding="utf-8")
                )
                before = sorted(
                    (path.name, path.stat().st_size)
                    for path in fixture.out_dir.iterdir()
                )
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    status = checker.main(
                        [
                            "--comparison-dir",
                            str(fixture.out_dir),
                            "--candidates",
                            str(fixture.candidates),
                            "--candidates-lora",
                            str(fixture.candidates_lora),
                            "--esm35-run-dir",
                            str(fixture.esm35),
                            "--esm150-run-dir",
                            str(fixture.esm150),
                            "--adapter-dir",
                            str(fixture.adapter),
                            "--compat-path",
                            str(fixture.compat),
                        ]
                    )
                after = sorted(
                    (path.name, path.stat().st_size)
                    for path in fixture.out_dir.iterdir()
                )

        self.assertEqual(status, 0, stdout.getvalue())
        self.assertIn('"status": "PASS"', stdout.getvalue())
        self.assertEqual(before, after)
        self.assertEqual(len(comparison), 201)
        included = [row for row in comparison if row["evaluation_included"] == "1"]
        inferred = [row for row in comparison if row["evaluation_included"] == "0"]
        self.assertEqual(len(included), 130)
        self.assertEqual(len(inferred), 71)
        self.assertTrue(all(row["evaluation_label"] == "" for row in inferred))
        self.assertTrue(
            all(row["disagreement_pattern"] == "display_only_inferred" for row in inferred)
        )
        self.assertEqual(metrics["benchmark"]["evaluation_rows"], 130)
        self.assertEqual(metrics["benchmark"]["inferred_display_only"], 71)
        self.assertIsNone(
            metrics["benchmark_reference"]["metrics"]["roc_auc"]
        )

    def test_review_selection_is_deterministic_and_covers_six_strata(self):
        with SyntheticRun() as fixture:
            with fixture.patch_expected_hashes():
                sites, _ = runner.load_annotation_sites(fixture.candidates)
                votes35 = runner.load_esm35_votes(fixture.esm35, sites)
                votes150 = runner.load_esm150_votes(fixture.esm150, sites)
                compared = runner.build_comparison(sites, votes35, votes150)
                first = runner.select_top_disagreements(compared)
                reversed35 = dict(reversed(list(votes35.items())))
                reversed150 = dict(reversed(list(votes150.items())))
                rebuilt = runner.build_comparison(sites, reversed35, reversed150)
                second = runner.select_top_disagreements(rebuilt)

        first_ids = [item.compared.site.key for item in first]
        second_ids = [item.compared.site.key for item in second]
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(len(first_ids), 10)
        self.assertEqual(len(set(first_ids)), 10)
        self.assertEqual(
            {item.stratum for item in first},
            set(runner.STRATA_ORDER),
        )

    def test_git_state_is_captured_before_staging_directory_exists(self):
        with SyntheticRun() as fixture:
            def capture_clean_state():
                self.assertEqual(
                    list(fixture.root.glob(".comparison.tmp-*")),
                    [],
                )
                return {"git_commit": "0" * 40, "git_dirty": False}

            with fixture.patch_expected_hashes(), mock.patch.object(
                runner,
                "_git_state",
                side_effect=capture_clean_state,
            ):
                fixture.generate()

            manifest = json.loads(
                (fixture.out_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["source"],
                {"git_commit": "0" * 40, "git_dirty": False},
            )

    def test_35m_key_boundary_rejects_inferred_key(self):
        with SyntheticRun() as fixture:
            fixture.mutate_35_to_inferred_key()
            with fixture.patch_expected_hashes():
                sites, _ = runner.load_annotation_sites(fixture.candidates)
                with self.assertRaisesRegex(
                    runner.ComparisonError,
                    "outside the honest population",
                ):
                    runner.load_esm35_votes(fixture.esm35, sites)


class CheckerHelperTests(unittest.TestCase):
    def test_manual_review_status_and_note_contract(self):
        checker.validate_review_outcome("PENDING_MANUAL_REVIEW", "")
        for status in checker.REVIEW_STATUS_VALUES[1:]:
            checker.validate_review_outcome(status, "独立证据")
        with self.assertRaisesRegex(checker.CheckError, "pending manual review"):
            checker.validate_review_outcome("PENDING_MANUAL_REVIEW", "note")
        for status in checker.REVIEW_STATUS_VALUES[1:]:
            with self.assertRaisesRegex(checker.CheckError, "empty reviewer note"):
                checker.validate_review_outcome(status, "   ")
        with self.assertRaisesRegex(checker.CheckError, "unknown manual review"):
            checker.validate_review_outcome("REVIEWED", "note")

    def test_manual_review_text_is_chinese(self):
        positive_question = checker._manual_review_question(
            {"evaluation_label": "1"}
        )
        control_question = checker._manual_review_question(
            {"evaluation_label": "0"}
        )
        self.assertIn("独立文献", positive_question)
        self.assertIn("漏注释", control_question)
        self.assertNotIn("Does independent", positive_question)
        self.assertNotIn("Is there", control_question)

    def test_manual_review_summary_must_match_status_counts(self):
        rows = [
            {
                "review_status": "SUPPORTED_EXPERIMENTAL_POSITIVE",
                "reviewer_note": "已整理证据",
            }
            for _ in range(6)
        ] + [
            {
                "review_status": "MISSED_ANNOTATION_CANDIDATE",
                "reviewer_note": "注释候选",
            }
            for _ in range(3)
        ] + [
            {
                "review_status": "NO_INDEPENDENT_EVIDENCE_FOUND",
                "reviewer_note": "未找到证据",
            }
        ]
        manifest = {
            "manual_review": {
                "base_commit": "a" * 40,
                "reviewed_at": "2026-10-23",
                "status_counts": checker.manual_review_counts(rows),
            }
        }
        checker.verify_manual_review(manifest, rows)
        manifest["manual_review"]["status_counts"][
            "MISSED_ANNOTATION_CANDIDATE"
        ] = 2
        with self.assertRaisesRegex(checker.CheckError, "status counts mismatch"):
            checker.verify_manual_review(manifest, rows)

    def test_reviewed_statuses_pass_end_to_end_checker(self):
        with SyntheticRun() as fixture:
            with fixture.patch_expected_hashes():
                fixture.generate()
                review = checker.read_csv_exact(
                    fixture.out_dir / "review_top10.csv",
                    checker.REVIEW_COLUMNS,
                )
                statuses = {
                    row["row_id"]: "SUPPORTED_EXPERIMENTAL_POSITIVE"
                    for row in review
                }
                notes = {
                    row_id: f"{row_id} 有独立证据"
                    for row_id in statuses
                }
                fixture.apply_manual_review(
                    statuses,
                    notes,
                    base_commit="b" * 40,
                    reviewed_at="2026-10-23",
                )
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    status = checker.main(
                        [
                            "--comparison-dir",
                            str(fixture.out_dir),
                            "--candidates",
                            str(fixture.candidates),
                            "--candidates-lora",
                            str(fixture.candidates_lora),
                            "--esm35-run-dir",
                            str(fixture.esm35),
                            "--esm150-run-dir",
                            str(fixture.esm150),
                            "--adapter-dir",
                            str(fixture.adapter),
                            "--compat-path",
                            str(fixture.compat),
                        ]
                    )
        self.assertEqual(status, 0, stdout.getvalue())
        self.assertIn('"status": "PASS"', stdout.getvalue())
        self.assertIn(
            '"SUPPORTED_EXPERIMENTAL_POSITIVE": 10',
            stdout.getvalue(),
        )

    def test_artifact_hash_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            payload = run_dir / "payload.csv"
            payload.write_text("a,b\n1,2\n", encoding="utf-8")
            manifest = {
                "schema": "fixture/v1",
                "status": "complete",
                "artifacts": {
                    "payload.csv": {
                        "sha256": checker.sha256_file(payload),
                        "bytes": payload.stat().st_size,
                    }
                },
            }
            write_json(run_dir / "manifest.json", manifest)
            self.assertEqual(
                checker.verify_manifest_and_hashes(
                    run_dir,
                    "fixture/v1",
                    ("payload.csv",),
                ),
                manifest,
            )
            payload.write_text("a,b\n1,3\n", encoding="utf-8")
            with self.assertRaisesRegex(checker.CheckError, "hash mismatch"):
                checker.verify_manifest_and_hashes(
                    run_dir,
                    "fixture/v1",
                    ("payload.csv",),
                )

    def test_author_replay_prediction_input_is_rejected(self):
        manifest = {
            "no_author_replay_prediction_input": True,
            "author_replay_prediction_input": False,
            "inputs": {
                "frozen_legacy": {
                    "role": "provenance_only",
                    "path": "reports/esm150_lora_repro_v0/predictions.csv",
                }
            },
        }
        checker.assert_no_author_replay_prediction_input(manifest)
        manifest["inputs"]["frozen_legacy"]["role"] = "prediction_input"
        with self.assertRaisesRegex(checker.CheckError, "author-replay"):
            checker.assert_no_author_replay_prediction_input(manifest)

        manifest["no_author_replay_prediction_input"] = False
        manifest["inputs"]["frozen_legacy"]["role"] = "provenance_only"
        with self.assertRaisesRegex(checker.CheckError, "explicitly exclude"):
            checker.assert_no_author_replay_prediction_input(manifest)


if __name__ == "__main__":
    unittest.main()
