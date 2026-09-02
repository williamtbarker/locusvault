"""Validated records crossing the ingestion boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from hashlib import sha256

DNA_ALPHABET = frozenset("ACGTRYSWKMBDHVN")
PROTEIN_ALPHABET = frozenset("ACDEFGHIKLMNPQRSTVWYBXZJUO*")
CANONICAL_DNA = frozenset("ACGT")
CANONICAL_PROTEIN = frozenset("ACDEFGHIKLMNPQRSTVWY")


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


@dataclass(frozen=True, slots=True)
class IsolateMetadata:
    isolate_id: str
    isolate_name: str | None = None
    subtype: str | None = None
    lineage: str | None = None
    host: str | None = None
    location: str | None = None
    collection_date: str | None = None

    @classmethod
    def from_mapping(cls, row: Mapping[str, str | None]) -> IsolateMetadata:
        isolate_id = (row.get("isolate_id") or "").strip()
        if not isolate_id:
            raise ValueError("isolate_id is required")
        collection_date = _optional_text(row.get("collection_date"))
        if collection_date is not None:
            try:
                parsed = date.fromisoformat(collection_date)
            except ValueError as error:
                raise ValueError("collection_date must use ISO format YYYY-MM-DD") from error
            collection_date = parsed.isoformat()
        return cls(
            isolate_id=isolate_id,
            isolate_name=_optional_text(row.get("isolate_name")),
            subtype=_optional_text(row.get("subtype")),
            lineage=_optional_text(row.get("lineage")),
            host=_optional_text(row.get("host")),
            location=_optional_text(row.get("location")),
            collection_date=collection_date,
        )


@dataclass(frozen=True, slots=True)
class SequenceEntry:
    accession: str
    isolate_id: str
    molecule: str
    segment: str
    sequence: str

    def __post_init__(self) -> None:
        normalized_molecule = self.molecule.upper()
        normalized_sequence = "".join(self.sequence.split()).upper()
        if not self.accession.strip():
            raise ValueError("sequence accession is required")
        if not self.isolate_id.strip():
            raise ValueError("sequence isolate_id is required")
        if not self.segment.strip():
            raise ValueError("sequence segment is required")
        if normalized_molecule not in {"DNA", "PROTEIN"}:
            raise ValueError("molecule must be DNA or PROTEIN")
        if not normalized_sequence:
            raise ValueError("sequence cannot be empty")
        alphabet = DNA_ALPHABET if normalized_molecule == "DNA" else PROTEIN_ALPHABET
        invalid = next((symbol for symbol in normalized_sequence if symbol not in alphabet), None)
        if invalid is not None:
            raise ValueError(f"unsupported {normalized_molecule} symbol {invalid!r}")
        object.__setattr__(self, "accession", self.accession.strip())
        object.__setattr__(self, "isolate_id", self.isolate_id.strip())
        object.__setattr__(self, "molecule", normalized_molecule)
        object.__setattr__(self, "segment", self.segment.strip().upper())
        object.__setattr__(self, "sequence", normalized_sequence)

    @property
    def digest(self) -> str:
        return sha256(self.sequence.encode("ascii")).hexdigest()

    @property
    def ambiguous_symbols(self) -> int:
        canonical = CANONICAL_DNA if self.molecule == "DNA" else CANONICAL_PROTEIN
        return sum(symbol not in canonical for symbol in self.sequence)

    @property
    def gc_fraction(self) -> float | None:
        if self.molecule != "DNA":
            return None
        canonical_count = sum(symbol in CANONICAL_DNA for symbol in self.sequence)
        if canonical_count == 0:
            return None
        gc_count = self.sequence.count("G") + self.sequence.count("C")
        return gc_count / canonical_count


@dataclass(frozen=True, slots=True)
class IngestResult:
    run_id: int
    status: str
    inserted_rows: int
    updated_rows: int
    rejected_rows: int
    source_sha256: str
