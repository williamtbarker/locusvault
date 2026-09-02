from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from locusvault.warehouse import LocusVault, WarehouseError

METADATA_HEADER = "isolate_id,isolate_name,subtype,lineage,host,location,collection_date\n"


class WarehouseTests(unittest.TestCase):
    temporary_directory: tempfile.TemporaryDirectory[str]
    root: Path
    database: Path
    vault: LocusVault

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database = self.root / "warehouse.sqlite3"
        self.vault = LocusVault(self.database)
        self.assertEqual(self.vault.initialize(), 1)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _metadata(self, body: str, name: str = "metadata.csv") -> Path:
        path = self.root / name
        path.write_text(METADATA_HEADER + body, encoding="utf-8")
        return path

    def _fasta(self, text: str, name: str = "sequences.fasta") -> Path:
        path = self.root / name
        path.write_text(text, encoding="ascii")
        return path

    def test_end_to_end_ingest_summary_export_and_check(self) -> None:
        metadata = self._metadata(
            "ISO-1,Alpha,H1N1,seasonal,human,NC,2025-01-02\n"
            "ISO-2,Beta,H3N2,seasonal,human,VA,2025-02-03\n"
        )
        fasta = self._fasta(
            ">DNA-1|ISO-1|DNA|HA\nACGTNN\n"
            ">PROT-1|ISO-1|PROTEIN|HA\nMKTXX\n"
            ">DNA-2|ISO-2|DNA|NA\nGGCC\n"
        )
        metadata_result = self.vault.ingest_metadata(metadata)
        fasta_result = self.vault.ingest_fasta(fasta)
        self.assertEqual(metadata_result.inserted_rows, 2)
        self.assertEqual(fasta_result.inserted_rows, 3)

        summary = self.vault.summary()
        self.assertEqual(summary["isolates"], 2)
        self.assertEqual(summary["sequences"], 3)
        self.assertEqual(summary["sequences_by_molecule"], {"DNA": 2, "PROTEIN": 1})
        self.assertTrue(self.vault.integrity_check()["ok"])

        export = self.root / "catalog.csv"
        self.assertEqual(self.vault.export_catalog(export), 3)
        with export.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row["accession"] for row in rows], ["DNA-1", "PROT-1", "DNA-2"])
        self.assertEqual(rows[0]["ambiguous_symbols"], "2")

    def test_identical_source_is_skipped(self) -> None:
        metadata = self._metadata("ISO-1,Alpha,H1N1,seasonal,human,NC,2025-01-02\n")
        first = self.vault.ingest_metadata(metadata)
        second = self.vault.ingest_metadata(metadata)
        self.assertEqual(first.status, "completed")
        self.assertEqual(second.status, "skipped")
        self.assertEqual(second.run_id, first.run_id)
        self.assertEqual(self.vault.summary()["isolates"], 1)

    def test_modified_source_updates_without_erasing_existing_values(self) -> None:
        first = self._metadata("ISO-1,Alpha,H1N1,seasonal,human,NC,2025-01-02\n", "first.csv")
        second = self._metadata("ISO-1,Alpha Revised,H1N1,,,,\n", "second.csv")
        self.vault.ingest_metadata(first)
        result = self.vault.ingest_metadata(second)
        self.assertEqual(result.updated_rows, 1)
        with self.vault.connect() as connection:
            row = connection.execute(
                "SELECT isolate_name, host, location FROM isolates WHERE isolate_id = 'ISO-1'"
            ).fetchone()
        if row is None:
            self.fail("expected ISO-1 metadata")
        self.assertEqual(tuple(row), ("Alpha Revised", "human", "NC"))

    def test_strict_metadata_failure_rolls_back_rows_and_records_run(self) -> None:
        metadata = self._metadata(
            "ISO-1,Alpha,H1N1,seasonal,human,NC,2025-01-02\n"
            ",Missing identifier,H1N1,seasonal,human,NC,2025-01-02\n"
        )
        with self.assertRaisesRegex(WarehouseError, "row 3"):
            self.vault.ingest_metadata(metadata)
        self.assertEqual(self.vault.summary()["isolates"], 0)
        with self.vault.connect() as connection:
            row = connection.execute(
                "SELECT status, inserted_rows FROM ingest_runs ORDER BY run_id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            self.fail("expected a failed ingest run")
        self.assertEqual(tuple(row), ("failed", 0))

    def test_skip_invalid_records_error_and_commits_valid_rows(self) -> None:
        metadata = self._metadata(
            "ISO-1,Alpha,H1N1,seasonal,human,NC,2025-01-02\n"
            ",Missing identifier,H1N1,seasonal,human,NC,2025-01-02\n"
        )
        result = self.vault.ingest_metadata(metadata, skip_invalid=True)
        self.assertEqual(result.status, "completed_with_errors")
        self.assertEqual(result.inserted_rows, 1)
        self.assertEqual(result.rejected_rows, 1)
        with self.vault.connect() as connection:
            error = connection.execute(
                "SELECT row_number, raw_record FROM ingest_errors WHERE run_id = ?",
                (result.run_id,),
            ).fetchone()
        if error is None:
            self.fail("expected a recorded ingest error")
        self.assertEqual(error["row_number"], 3)
        self.assertEqual(json.loads(error["raw_record"])["isolate_id"], "")

    def test_fasta_foreign_key_failure_rolls_back_entire_file(self) -> None:
        metadata = self._metadata("ISO-1,Alpha,H1N1,seasonal,human,NC,2025-01-02\n")
        self.vault.ingest_metadata(metadata)
        fasta = self._fasta(">DNA-1|ISO-1|DNA|HA\nACGT\n>DNA-2|UNKNOWN|DNA|NA\nGGCC\n")
        with self.assertRaisesRegex(WarehouseError, "FOREIGN KEY"):
            self.vault.ingest_fasta(fasta)
        self.assertEqual(self.vault.summary()["sequences"], 0)

    def test_changed_fasta_upserts_sequence(self) -> None:
        metadata = self._metadata("ISO-1,Alpha,H1N1,seasonal,human,NC,2025-01-02\n")
        self.vault.ingest_metadata(metadata)
        first = self._fasta(">DNA-1|ISO-1|DNA|HA\nACGT\n", "first.fasta")
        second = self._fasta(">DNA-1|ISO-1|DNA|HA\nGGCC\n", "second.fasta")
        self.assertEqual(self.vault.ingest_fasta(first).inserted_rows, 1)
        self.assertEqual(self.vault.ingest_fasta(second).updated_rows, 1)
        with self.vault.connect() as connection:
            row = connection.execute("SELECT sequence FROM sequences").fetchone()
        if row is None:
            self.fail("expected an updated sequence")
        sequence = row[0]
        self.assertEqual(sequence, "GGCC")

    def test_export_cannot_overwrite_database(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot overwrite"):
            self.vault.export_catalog(self.database)


if __name__ == "__main__":
    unittest.main()
