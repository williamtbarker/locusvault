# Changelog

All notable changes to this project are documented here.

## [0.1.0] - 2026-09-02

### Added

- Versioned SQLite schema for isolate metadata, sequences, and ingest audits.
- Strict CSV and streaming plain/gzip FASTA ingestion.
- Transactional rollback and optional invalid-row quarantine.
- SHA-256 source provenance and idempotent repeat ingestion.
- Derived sequence hashes, lengths, ambiguity counts, and DNA GC fractions.
- Deterministic atomic catalog export and database integrity checks.
- Dependency-free CLI, test suite, CI matrix, and reproducible verifier.
