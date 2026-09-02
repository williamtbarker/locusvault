"""Command-line interface for LocusVault."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from locusvault import __version__
from locusvault.warehouse import LocusVault, WarehouseError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="locusvault",
        description="Build and query a provenance-aware SQLite sequence warehouse.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="initialize or migrate a database")
    init_parser.add_argument("database", type=Path)

    metadata_parser = subparsers.add_parser("ingest-metadata", help="ingest isolate CSV metadata")
    metadata_parser.add_argument("database", type=Path)
    metadata_parser.add_argument("csv", type=Path)
    metadata_parser.add_argument(
        "--skip-invalid", action="store_true", help="record invalid rows and continue"
    )

    fasta_parser = subparsers.add_parser("ingest-fasta", help="ingest DNA or protein FASTA")
    fasta_parser.add_argument("database", type=Path)
    fasta_parser.add_argument("fasta", type=Path)

    summary_parser = subparsers.add_parser("summary", help="print warehouse counts and audit runs")
    summary_parser.add_argument("database", type=Path)

    export_parser = subparsers.add_parser("export", help="export the joined sequence catalog")
    export_parser.add_argument("database", type=Path)
    export_parser.add_argument("csv", type=Path)

    check_parser = subparsers.add_parser("check", help="run SQLite integrity checks")
    check_parser.add_argument("database", type=Path)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parser = build_parser()
    namespace = parser.parse_args(arguments)
    vault = LocusVault(namespace.database)
    try:
        if namespace.command == "init":
            print(json.dumps({"database": str(vault.database_path), "schema": vault.initialize()}))
        elif namespace.command == "ingest-metadata":
            result = vault.ingest_metadata(namespace.csv, skip_invalid=namespace.skip_invalid)
            print(json.dumps(asdict(result), sort_keys=True))
        elif namespace.command == "ingest-fasta":
            result = vault.ingest_fasta(namespace.fasta)
            print(json.dumps(asdict(result), sort_keys=True))
        elif namespace.command == "summary":
            print(json.dumps(vault.summary(), indent=2, sort_keys=True))
        elif namespace.command == "export":
            rows = vault.export_catalog(namespace.csv)
            print(json.dumps({"destination": str(namespace.csv), "rows": rows}))
        elif namespace.command == "check":
            check_result = vault.integrity_check()
            print(json.dumps(check_result, indent=2, sort_keys=True))
            return 0 if check_result["ok"] else 1
        else:
            parser.error(f"unsupported command {namespace.command!r}")
    except (OSError, UnicodeError, ValueError, WarehouseError) as error:
        parser.exit(1, f"locusvault: error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
