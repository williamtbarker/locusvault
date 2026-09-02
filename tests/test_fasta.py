from __future__ import annotations

import gzip
import io
import tempfile
import unittest
from pathlib import Path

from locusvault.fasta import FastaFormatError, iter_fasta, open_fasta


class FastaTests(unittest.TestCase):
    def test_reads_multiline_records(self) -> None:
        text = ">ACC-1|ISO-1|DNA|HA\nacgt\nnn\n>PROT-1|ISO-1|protein|HA\nMKT\n"
        records = list(iter_fasta(io.StringIO(text)))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].sequence, "ACGTNN")
        self.assertEqual(records[1].molecule, "PROTEIN")

    def test_requires_explicit_header_contract(self) -> None:
        with self.assertRaisesRegex(FastaFormatError, "expected"):
            list(iter_fasta(io.StringIO(">ACC-1 vague header\nACGT\n")))

    def test_rejects_sequence_before_header(self) -> None:
        with self.assertRaisesRegex(FastaFormatError, "before"):
            list(iter_fasta(io.StringIO("ACGT\n")))

    def test_rejects_empty_record(self) -> None:
        text = ">ACC-1|ISO-1|DNA|HA\n>ACC-2|ISO-1|DNA|NA\nACGT\n"
        with self.assertRaisesRegex(FastaFormatError, "no sequence"):
            list(iter_fasta(io.StringIO(text)))

    def test_reads_gzip_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "sequences.fasta.gz")
            with gzip.open(path, "wt", encoding="ascii") as handle:
                handle.write(">ACC-1|ISO-1|DNA|HA\nACGT\n")
            with open_fasta(path) as handle:
                record = next(iter_fasta(handle))
            self.assertEqual(record.accession, "ACC-1")


if __name__ == "__main__":
    unittest.main()
