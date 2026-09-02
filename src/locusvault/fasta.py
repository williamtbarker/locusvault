"""Strict streaming FASTA parsing with an explicit header contract."""

from __future__ import annotations

import gzip
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

from locusvault.models import SequenceEntry


class FastaFormatError(ValueError):
    def __init__(self, message: str, *, line: int | None = None) -> None:
        self.line = line
        prefix = f"line {line}: " if line is not None else ""
        super().__init__(prefix + message)


@contextmanager
def open_fasta(path: Path) -> Iterator[TextIO]:
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rt", encoding="ascii", newline="") as handle:
            yield handle
    else:
        with path.open("r", encoding="ascii", newline="") as handle:
            yield handle


def _parse_header(header: str, line: int) -> tuple[str, str, str, str]:
    fields = [field.strip() for field in header.split("|")]
    if len(fields) != 4 or any(not field for field in fields):
        raise FastaFormatError("expected >accession|isolate_id|molecule|segment", line=line)
    accession, isolate_id, molecule, segment = fields
    return accession, isolate_id, molecule, segment


def iter_fasta(handle: TextIO) -> Iterator[SequenceEntry]:
    """Yield records using ``>accession|isolate_id|molecule|segment`` headers."""

    current_header: tuple[str, str, str, str] | None = None
    current_header_line = 0
    sequence_parts: list[str] = []

    for line_number, raw_line in enumerate(handle, start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if current_header is not None:
                if not sequence_parts:
                    raise FastaFormatError("record has no sequence", line=current_header_line)
                try:
                    yield SequenceEntry(*current_header, sequence="".join(sequence_parts))
                except ValueError as error:
                    raise FastaFormatError(str(error), line=current_header_line) from error
            current_header_line = line_number
            current_header = _parse_header(line[1:], line_number)
            sequence_parts = []
        elif current_header is None:
            raise FastaFormatError("sequence appears before the first header", line=line_number)
        else:
            sequence_parts.append(line)

    if current_header is None:
        raise FastaFormatError("input contains no FASTA records", line=1)
    if not sequence_parts:
        raise FastaFormatError("record has no sequence", line=current_header_line)
    try:
        yield SequenceEntry(*current_header, sequence="".join(sequence_parts))
    except ValueError as error:
        raise FastaFormatError(str(error), line=current_header_line) from error
