from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from locusvault.cli import main


class CliTests(unittest.TestCase):
    def test_cli_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "warehouse.sqlite3"
            metadata = root / "metadata.csv"
            fasta = root / "sequences.fasta"
            export = root / "catalog.csv"
            metadata.write_text("isolate_id,isolate_name\nISO-1,Example\n", encoding="utf-8")
            fasta.write_text(">DNA-1|ISO-1|DNA|HA\nACGT\n", encoding="ascii")

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["init", str(database)]), 0)
                self.assertEqual(main(["ingest-metadata", str(database), str(metadata)]), 0)
                self.assertEqual(main(["ingest-fasta", str(database), str(fasta)]), 0)
                self.assertEqual(main(["export", str(database), str(export)]), 0)
                self.assertEqual(main(["check", str(database)]), 0)
            lines = output.getvalue().splitlines()
            self.assertEqual(json.loads(lines[0])["schema"], 1)
            self.assertTrue(export.exists())


if __name__ == "__main__":
    unittest.main()
