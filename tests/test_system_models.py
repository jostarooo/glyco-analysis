from __future__ import annotations

import unittest

from system.models import (
    MAX_SEQUENCE_LENGTH,
    ValidationError,
    find_sequons,
    normalize_sequence,
    sequence_sha256,
)


class SequenceNormalizationTests(unittest.TestCase):
    def test_fasta_header_whitespace_and_case_are_normalized(self) -> None:
        self.assertEqual(
            normalize_sequence(">protein\nac de\nf g\n"),
            "ACDEFG",
        )

    def test_empty_sequence_is_rejected(self) -> None:
        with self.assertRaises(ValidationError) as context:
            normalize_sequence(">only-header\n")
        self.assertEqual(context.exception.code, "SEQUENCE_EMPTY")

    def test_invalid_residue_is_rejected(self) -> None:
        with self.assertRaises(ValidationError) as context:
            normalize_sequence("ACD1FG")
        self.assertEqual(context.exception.code, "SEQUENCE_ALPHABET")

    def test_sequence_over_recorded_limit_is_rejected(self) -> None:
        with self.assertRaises(ValidationError) as context:
            normalize_sequence("A" * (MAX_SEQUENCE_LENGTH + 1))
        self.assertEqual(context.exception.code, "SEQUENCE_TOO_LONG")

    def test_sha256_is_uppercase_and_deterministic(self) -> None:
        self.assertEqual(sequence_sha256("NST"), sequence_sha256("NST"))
        self.assertRegex(sequence_sha256("NST"), r"^[0-9A-F]{64}$")


class SequonTests(unittest.TestCase):
    def test_nps_is_not_an_n_linked_sequon(self) -> None:
        self.assertEqual(find_sequons("ANPS"), ())

    def test_all_valid_nxs_and_nxt_sites_are_returned(self) -> None:
        sites = find_sequons("NSTNVTNPSXXXNFS")
        self.assertEqual(
            [(site.position, site.motif) for site in sites],
            [(1, "NST"), (4, "NVT"), (13, "NFS")],
        )

    def test_short_sequence_has_no_sites(self) -> None:
        self.assertEqual(find_sequons("NN"), ())


if __name__ == "__main__":
    unittest.main()
