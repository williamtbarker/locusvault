from __future__ import annotations

import unittest

from locusvault.models import IsolateMetadata, SequenceEntry


class IsolateMetadataTests(unittest.TestCase):
    def test_mapping_normalizes_optional_fields(self) -> None:
        record = IsolateMetadata.from_mapping(
            {
                "isolate_id": " ISO-001 ",
                "isolate_name": "Example isolate",
                "subtype": " ",
                "collection_date": "2025-03-14",
            }
        )
        self.assertEqual(record.isolate_id, "ISO-001")
        self.assertIsNone(record.subtype)
        self.assertEqual(record.collection_date, "2025-03-14")

    def test_mapping_requires_identifier(self) -> None:
        with self.assertRaisesRegex(ValueError, "isolate_id"):
            IsolateMetadata.from_mapping({"isolate_id": ""})

    def test_mapping_validates_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            IsolateMetadata.from_mapping({"isolate_id": "ISO-001", "collection_date": "03/14/2025"})


class SequenceEntryTests(unittest.TestCase):
    def test_dna_is_normalized_and_featured(self) -> None:
        record = SequenceEntry("ACC-1", "ISO-1", "dna", "ha", " acgtn ")
        self.assertEqual(record.sequence, "ACGTN")
        self.assertEqual(record.segment, "HA")
        self.assertEqual(record.gc_fraction, 0.5)
        self.assertEqual(record.ambiguous_symbols, 1)
        self.assertEqual(len(record.digest), 64)

    def test_protein_has_no_gc_fraction(self) -> None:
        record = SequenceEntry("PROT-1", "ISO-1", "protein", "ha", "MKTXX*")
        self.assertIsNone(record.gc_fraction)
        self.assertEqual(record.ambiguous_symbols, 3)

    def test_invalid_symbol_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported DNA"):
            SequenceEntry("ACC-1", "ISO-1", "DNA", "HA", "ACGT?")


if __name__ == "__main__":
    unittest.main()
