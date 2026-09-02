"""Versioned SQLite schema management."""

from __future__ import annotations

import sqlite3

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE isolates (
            isolate_id TEXT PRIMARY KEY,
            isolate_name TEXT,
            subtype TEXT,
            lineage TEXT,
            host TEXT,
            location TEXT,
            collection_date TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE sequences (
            sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
            accession TEXT NOT NULL,
            isolate_id TEXT NOT NULL REFERENCES isolates(isolate_id) ON DELETE CASCADE,
            molecule TEXT NOT NULL CHECK (molecule IN ('DNA', 'PROTEIN')),
            segment TEXT NOT NULL,
            sequence TEXT NOT NULL,
            sequence_sha256 TEXT NOT NULL,
            length INTEGER NOT NULL CHECK (length > 0),
            gc_fraction REAL CHECK (gc_fraction IS NULL OR gc_fraction BETWEEN 0.0 AND 1.0),
            ambiguous_symbols INTEGER NOT NULL CHECK (ambiguous_symbols >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (isolate_id, accession, molecule, segment)
        );

        CREATE INDEX sequences_isolate_idx ON sequences(isolate_id);
        CREATE INDEX sequences_segment_idx ON sequences(segment);
        CREATE INDEX sequences_digest_idx ON sequences(sequence_sha256);

        CREATE TABLE ingest_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK (kind IN ('metadata', 'fasta')),
            source_path TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL CHECK (
                status IN ('running', 'completed', 'completed_with_errors', 'failed')
            ),
            inserted_rows INTEGER NOT NULL DEFAULT 0,
            updated_rows INTEGER NOT NULL DEFAULT 0,
            rejected_rows INTEGER NOT NULL DEFAULT 0,
            error_message TEXT
        );

        CREATE INDEX ingest_runs_source_idx
            ON ingest_runs(kind, source_sha256, status);

        CREATE TABLE ingest_errors (
            error_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES ingest_runs(run_id) ON DELETE CASCADE,
            row_number INTEGER,
            message TEXT NOT NULL,
            raw_record TEXT
        );

        CREATE VIEW sequence_catalog AS
        SELECT
            i.isolate_id,
            i.isolate_name,
            i.subtype,
            i.lineage,
            i.host,
            i.location,
            i.collection_date,
            s.accession,
            s.molecule,
            s.segment,
            s.sequence_sha256,
            s.length,
            s.gc_fraction,
            s.ambiguous_symbols
        FROM isolates AS i
        JOIN sequences AS s USING (isolate_id);
        """,
    ),
)


def configure(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")


def migrate(connection: sqlite3.Connection) -> int:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied = {
        row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
    }
    for version, sql in MIGRATIONS:
        if version in applied:
            continue
        connection.executescript(sql)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
        connection.commit()
    row = connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
    return int(row[0]) if row is not None else 0
