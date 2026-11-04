from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from system.predictor import Esm150Predictor


class LazyPredictorTests(unittest.TestCase):
    def test_no_sequon_returns_without_loading_the_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            predictor = Esm150Predictor(adapter_dir=Path(directory))
            self.assertEqual(predictor.state, "error")
            result = predictor.predict("ACDEFGHIK")
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.sequence_length, 9)


if __name__ == "__main__":
    unittest.main()
