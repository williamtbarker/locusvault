"""Transactional ingestion, auditing, querying, and export."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO, cast

from locusvault.fasta import iter_fasta, open_fasta
from locusvault.models import IngestResult, IsolateMetadata, SequenceEntry
from locusvault.schema import configure, migrate

METADATA_COLUMNS = (
    "isolate_id",
    "isolate_name",
    "subtype",
    "lineage",
    "host",
    "location",
    "collection_date",
)

CATALOG_COLUMNS = (
    "isolate_id",
    "isolate_name",
    "subtype",
    "lineage",
    "host",
    "location",
    "collection_date",
    "accession",
    "molecule",
    "segment",
    "sequence_sha256",
    "length",
    "gc_fraction",
    "ambiguous_symbols",
)


class WarehouseError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _scalar_count(connection: sqlite3.Connection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None:
        raise WarehouseError("count query returned no row")
    return int(row[0])


@contextmanager
def _atomic_text_destination(path: Path) -> Iterator[TextIO]:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            yield handle
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


class LocusVault:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.expanduser().resolve()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        configure(connection)
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> int:
        with self.connect() as connection:
            return migrate(connection)

    @staticmethod
    def _find_completed_run(
        connection: sqlite3.Connection, kind: str, source_sha256: str
    ) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            connection.execute(
                """
                SELECT * FROM ingest_runs
                WHERE kind = ? AND source_sha256 = ?
                  AND status IN ('completed', 'completed_with_errors')
                ORDER BY run_id DESC LIMIT 1
                """,
                (kind, source_sha256),
            ).fetchone(),
        )

    @staticmethod
    def _start_run(
        connection: sqlite3.Connection, kind: str, source: Path, source_sha256: str
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO ingest_runs(kind, source_path, source_sha256, started_at, status)
            VALUES (?, ?, ?, ?, 'running')
            """,
            (kind, str(source), source_sha256, _now()),
        )
        connection.commit()
        if cursor.lastrowid is None:
            raise WarehouseError("database did not return an ingest run identifier")
        return int(cursor.lastrowid)

    @staticmethod
    def _finish_run(
        connection: sqlite3.Connection,
        run_id: int,
        *,
        status: str,
        inserted: int,
        updated: int,
        rejected: int,
        error_message: str | None = None,
    ) -> None:
        connection.execute(
            """
            UPDATE ingest_runs
            SET finished_at = ?, status = ?, inserted_rows = ?, updated_rows = ?,
                rejected_rows = ?, error_message = ?
            WHERE run_id = ?
            """,
            (_now(), status, inserted, updated, rejected, error_message, run_id),
        )
        connection.commit()

    @staticmethod
    def _skipped_result(row: sqlite3.Row, digest: str) -> IngestResult:
        return IngestResult(
            run_id=int(row["run_id"]),
            status="skipped",
            inserted_rows=0,
            updated_rows=0,
            rejected_rows=0,
            source_sha256=digest,
        )

    def ingest_metadata(self, path: Path, *, skip_invalid: bool = False) -> IngestResult:
        source = path.expanduser().resolve()
        source_sha256 = _file_digest(source)
        with self.connect() as connection:
            migrate(connection)
            completed = self._find_completed_run(connection, "metadata", source_sha256)
            if completed is not None:
                return self._skipped_result(completed, source_sha256)
            run_id = self._start_run(connection, "metadata", source, source_sha256)
            inserted = updated = rejected = 0
            try:
                connection.execute("BEGIN")
                with source.open("r", encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    if reader.fieldnames is None or "isolate_id" not in reader.fieldnames:
                        raise ValueError("metadata CSV must contain an isolate_id column")
                    unexpected = set(reader.fieldnames) - set(METADATA_COLUMNS)
                    if unexpected:
                        names = ", ".join(sorted(unexpected))
                        raise ValueError(f"unexpected metadata columns: {names}")
                    for row_number, row in enumerate(reader, start=2):
                        try:
                            record = IsolateMetadata.from_mapping(row)
                        except ValueError as error:
                            if not skip_invalid:
                                raise ValueError(f"row {row_number}: {error}") from error
                            rejected += 1
                            connection.execute(
                                """
                                INSERT INTO ingest_errors(run_id, row_number, message, raw_record)
                                VALUES (?, ?, ?, ?)
                                """,
                                (run_id, row_number, str(error), json.dumps(row, sort_keys=True)),
                            )
                            continue
                        exists = connection.execute(
                            "SELECT 1 FROM isolates WHERE isolate_id = ?", (record.isolate_id,)
                        ).fetchone()
                        self._upsert_isolate(connection, record)
                        if exists is None:
                            inserted += 1
                        else:
                            updated += 1
                connection.commit()
                status = "completed_with_errors" if rejected else "completed"
                self._finish_run(
                    connection,
                    run_id,
                    status=status,
                    inserted=inserted,
                    updated=updated,
                    rejected=rejected,
                )
            except (OSError, UnicodeError, ValueError, sqlite3.Error) as error:
                connection.rollback()
                self._finish_run(
                    connection,
                    run_id,
                    status="failed",
                    inserted=0,
                    updated=0,
                    rejected=rejected,
                    error_message=str(error),
                )
                raise WarehouseError(f"metadata ingestion failed: {error}") from error
        return IngestResult(run_id, status, inserted, updated, rejected, source_sha256)

    @staticmethod
    def _upsert_isolate(connection: sqlite3.Connection, record: IsolateMetadata) -> None:
        now = _now()
        connection.execute(
            """
            INSERT INTO isolates(
                isolate_id, isolate_name, subtype, lineage, host, location,
                collection_date, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(isolate_id) DO UPDATE SET
                isolate_name = COALESCE(excluded.isolate_name, isolates.isolate_name),
                subtype = COALESCE(excluded.subtype, isolates.subtype),
                lineage = COALESCE(excluded.lineage, isolates.lineage),
                host = COALESCE(excluded.host, isolates.host),
                location = COALESCE(excluded.location, isolates.location),
                collection_date = COALESCE(excluded.collection_date, isolates.collection_date),
                updated_at = excluded.updated_at
            """,
            (
                record.isolate_id,
                record.isolate_name,
                record.subtype,
                record.lineage,
                record.host,
                record.location,
                record.collection_date,
                now,
                now,
            ),
        )

    def ingest_fasta(self, path: Path) -> IngestResult:
        source = path.expanduser().resolve()
        source_sha256 = _file_digest(source)
        with self.connect() as connection:
            migrate(connection)
            completed = self._find_completed_run(connection, "fasta", source_sha256)
            if completed is not None:
                return self._skipped_result(completed, source_sha256)
            run_id = self._start_run(connection, "fasta", source, source_sha256)
            inserted = updated = 0
            try:
                connection.execute("BEGIN")
                with open_fasta(source) as handle:
                    for record in iter_fasta(handle):
                        exists = connection.execute(
                            """
                            SELECT 1 FROM sequences
                            WHERE isolate_id = ? AND accession = ?
                              AND molecule = ? AND segment = ?
                            """,
                            (
                                record.isolate_id,
                                record.accession,
                                record.molecule,
                                record.segment,
                            ),
                        ).fetchone()
                        self._upsert_sequence(connection, record)
                        if exists is None:
                            inserted += 1
                        else:
                            updated += 1
                connection.commit()
                self._finish_run(
                    connection,
                    run_id,
                    status="completed",
                    inserted=inserted,
                    updated=updated,
                    rejected=0,
                )
            except (OSError, UnicodeError, ValueError, sqlite3.Error) as error:
                connection.rollback()
                self._finish_run(
                    connection,
                    run_id,
                    status="failed",
                    inserted=0,
                    updated=0,
                    rejected=0,
                    error_message=str(error),
                )
                raise WarehouseError(f"FASTA ingestion failed: {error}") from error
        return IngestResult(run_id, "completed", inserted, updated, 0, source_sha256)

    @staticmethod
    def _upsert_sequence(connection: sqlite3.Connection, record: SequenceEntry) -> None:
        now = _now()
        connection.execute(
            """
            INSERT INTO sequences(
                accession, isolate_id, molecule, segment, sequence,
                sequence_sha256, length, gc_fraction, ambiguous_symbols,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(isolate_id, accession, molecule, segment) DO UPDATE SET
                sequence = excluded.sequence,
                sequence_sha256 = excluded.sequence_sha256,
                length = excluded.length,
                gc_fraction = excluded.gc_fraction,
                ambiguous_symbols = excluded.ambiguous_symbols,
                updated_at = excluded.updated_at
            """,
            (
                record.accession,
                record.isolate_id,
                record.molecule,
                record.segment,
                record.sequence,
                record.digest,
                len(record.sequence),
                record.gc_fraction,
                record.ambiguous_symbols,
                now,
                now,
            ),
        )

    def summary(self) -> dict[str, Any]:
        with self.connect() as connection:
            migrate(connection)
            isolates = _scalar_count(connection, "SELECT COUNT(*) FROM isolates")
            sequences = _scalar_count(connection, "SELECT COUNT(*) FROM sequences")
            by_molecule = {
                str(row["molecule"]): int(row["count"])
                for row in connection.execute(
                    "SELECT molecule, COUNT(*) AS count FROM sequences GROUP BY molecule"
                )
            }
            by_segment = {
                str(row["segment"]): int(row["count"])
                for row in connection.execute(
                    "SELECT segment, COUNT(*) AS count FROM sequences GROUP BY segment"
                )
            }
            runs = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT run_id, kind, source_sha256, status, inserted_rows,
                           updated_rows, rejected_rows, started_at, finished_at
                    FROM ingest_runs ORDER BY run_id DESC LIMIT 10
                    """
                )
            ]
        return {
            "database": str(self.database_path),
            "isolates": isolates,
            "sequences": sequences,
            "sequences_by_molecule": by_molecule,
            "sequences_by_segment": by_segment,
            "recent_ingest_runs": runs,
        }

    def export_catalog(self, destination: Path) -> int:
        output = destination.expanduser().resolve()
        if output == self.database_path:
            raise ValueError("export destination cannot overwrite the database")
        with self.connect() as connection:
            migrate(connection)
            rows = connection.execute(
                """
                SELECT * FROM sequence_catalog
                ORDER BY isolate_id, molecule, segment, accession
                """
            ).fetchall()
        with _atomic_text_destination(output) as handle:
            writer = csv.DictWriter(handle, fieldnames=CATALOG_COLUMNS)
            writer.writeheader()
            writer.writerows(dict(row) for row in rows)
        return len(rows)

    def integrity_check(self) -> dict[str, Any]:
        with self.connect() as connection:
            migrate(connection)
            integrity_rows = [
                str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()
            ]
            foreign_key_rows = [
                tuple(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()
            ]
        return {
            "integrity": integrity_rows,
            "foreign_key_violations": foreign_key_rows,
            "ok": integrity_rows == ["ok"] and not foreign_key_rows,
        }
