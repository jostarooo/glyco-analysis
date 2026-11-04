from __future__ import annotations

import os
import unittest
from pathlib import Path

from system.predictor import Esm150Predictor
from system.samples import SampleProvider


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    os.environ.get("RUN_W3_REAL_MODEL") == "1",
    "set RUN_W3_REAL_MODEL=1 to load the real RTX 5060 checkpoint",
)
class RealEsm150PredictorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sample = SampleProvider(REPO_ROOT).load()
        if sample is None:
            raise unittest.SkipTest("O75144 sample data is unavailable")
        cls.sample = sample
        cls.predictor = Esm150Predictor()
        cls.result = cls.predictor.predict(sample.sequence)

    def test_all_expected_sequons_are_scored(self) -> None:
        self.assertEqual(
            [(site.position, site.motif) for site in self.result.candidates],
            [
                (site.position, site.motif)
                for site in self.sample.reference_sites
            ],
        )

    def test_predictions_match_the_historical_author_checkpoint_artifact(self) -> None:
        expected = {site.position: site for site in self.sample.reference_sites}
        for actual in self.result.candidates:
            reference = expected[actual.position]
            self.assertEqual(actual.predicted_label, reference.predicted_label)
            self.assertAlmostEqual(
                actual.prob_positive,
                reference.prob_positive,
                places=5,
            )

    def test_provenance_matches_the_fixed_author_checkpoint(self) -> None:
        self.assertEqual(self.result.sequence_length, 302)
        self.assertEqual(
            self.result.model["adapter_sha256"],
            "A4A5B486862724F459F60E8343AC135C340305D5A0F2E936EB5AD1DFD34788D4",
        )
        self.assertEqual(self.result.model["adapter_tensor_count"], 376)
        self.assertTrue(self.result.model["full_sequence"])
        self.assertFalse(self.result.model["truncation"])
        self.assertFalse(self.result.model["windowing"])


if __name__ == "__main__":
    unittest.main()
