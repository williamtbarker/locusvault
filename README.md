# LocusVault

[![CI](https://github.com/williamtbarker/locusvault/actions/workflows/ci.yml/badge.svg)](https://github.com/williamtbarker/locusvault/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

LocusVault is a dependency-free Python command-line application for building a small,
auditable SQLite warehouse from isolate metadata and DNA or protein FASTA records.

It demonstrates the less glamorous parts of scientific data engineering that matter in
practice: explicit input contracts, schema migrations, atomic writes, referential integrity,
idempotent ingestion, provenance hashes, rejected-row auditing, and deterministic export.

## Why this exists

Ad hoc sequence scripts tend to accumulate incompatible tables, silently coerce bad records,
and become difficult to reproduce. LocusVault keeps the workflow deliberately small while
making its guarantees visible and testable:

- each input file receives a SHA-256 provenance record;
- ingesting the same bytes again is a no-op;
- strict ingestion rolls back the entire file on failure;
- metadata can optionally quarantine invalid rows and continue;
- sequence records must reference an existing isolate;
- updates preserve existing metadata when a later CSV field is blank;
- exports are atomically replaced and use a stable row order; and
- SQLite integrity and foreign-key checks are exposed through the CLI.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

locusvault init demo.sqlite3
locusvault ingest-metadata demo.sqlite3 examples/isolate_metadata.csv
locusvault ingest-fasta demo.sqlite3 examples/sequences.fasta
locusvault summary demo.sqlite3
locusvault check demo.sqlite3
locusvault export demo.sqlite3 catalog.csv
```

The example inputs are synthetic. The resulting catalog contains joined isolate metadata and
derived sequence features without duplicating raw sequence text in the export.

## Input contracts

Metadata is UTF-8 CSV. `isolate_id` is required; every other column is optional:

```text
isolate_id,isolate_name,subtype,lineage,host,location,collection_date
```

Dates must use `YYYY-MM-DD`. Unknown columns are rejected so a misspelled heading cannot
silently discard data. Add `--skip-invalid` to store malformed row details in `ingest_errors`
while committing valid rows.

FASTA may be plain text or gzip-compressed and uses this header contract:

```text
>accession|isolate_id|molecule|segment
```

`molecule` must be `DNA` or `PROTEIN`. DNA accepts IUPAC ambiguity codes; protein accepts the
standard alphabet plus common ambiguity and special symbols. Sequences are normalized to
uppercase and validated before storage.

## Data model

| Relation | Purpose |
|---|---|
| `isolates` | Stable isolate identifiers and descriptive metadata |
| `sequences` | Validated sequences, hashes, lengths, and derived features |
| `ingest_runs` | Source hashes, status, row counts, and failure messages |
| `ingest_errors` | Row-level errors from tolerant metadata imports |
| `schema_migrations` | Applied schema versions |
| `sequence_catalog` | Deterministic joined view used by `export` |

All application operations use Python's standard library. SQLite runs with foreign keys,
write-ahead logging, and normal synchronous mode enabled.

## Commands

```text
locusvault init DATABASE
locusvault ingest-metadata DATABASE CSV [--skip-invalid]
locusvault ingest-fasta DATABASE FASTA
locusvault summary DATABASE
locusvault export DATABASE CSV
locusvault check DATABASE
```

Each command emits machine-readable JSON on standard output. Errors are written to standard
error and return a non-zero exit status.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
./scripts/verify.sh
```

The verification script runs compilation, 22 tests, formatting and linting when Ruff is
installed, strict typing when mypy is installed, an end-to-end example, and wheel creation.
CI performs the complete toolchain on Python 3.10 through 3.13.

## Scope

LocusVault is a compact local warehouse and reference implementation, not a clinical system,
shared database server, or replacement for specialized sequence repositories. It does not
interpret sequences, make biological claims, or fetch remote data.

## License

MIT. See [LICENSE](LICENSE).
