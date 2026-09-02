#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v

if python3 -c 'import ruff' 2>/dev/null; then
  python3 -m ruff format --check .
  python3 -m ruff check .
else
  echo "ruff not installed; skipping format and lint checks"
fi

if python3 -c 'import mypy' 2>/dev/null; then
  python3 -m mypy
else
  echo "mypy not installed; skipping static type checks"
fi

verify_dir="$(mktemp -d "${TMPDIR:-/tmp}/locusvault-verify.XXXXXX")"
trap 'rm -rf "$verify_dir"' EXIT

database="$verify_dir/example.sqlite3"
catalog="$verify_dir/catalog.csv"
PYTHONPATH=src python3 -m locusvault.cli init "$database" >/dev/null
PYTHONPATH=src python3 -m locusvault.cli \
  ingest-metadata "$database" examples/isolate_metadata.csv >/dev/null
PYTHONPATH=src python3 -m locusvault.cli \
  ingest-fasta "$database" examples/sequences.fasta >/dev/null
PYTHONPATH=src python3 -m locusvault.cli check "$database" >/dev/null
PYTHONPATH=src python3 -m locusvault.cli export "$database" "$catalog" >/dev/null
test "$(wc -l < "$catalog")" -eq 4

mkdir -p "$verify_dir/wheels"
if python3 -c 'import setuptools.build_meta' 2>/dev/null; then
  PIP_NO_INDEX=1 python3 -m pip wheel \
    --no-deps --no-build-isolation --wheel-dir "$verify_dir/wheels" .
else
  python3 -m pip wheel --no-deps --wheel-dir "$verify_dir/wheels" .
fi

echo "All checks passed, including the example warehouse and wheel build."
