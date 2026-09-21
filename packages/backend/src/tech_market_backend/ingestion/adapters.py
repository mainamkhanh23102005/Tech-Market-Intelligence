import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol, TextIO

from pydantic import ValidationError

from tech_market_backend.ingestion.contracts import CanonicalJobInput, ImportLimits


class RecordError(ValueError):
    def __init__(self, record_number: int, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.record_number = record_number
        self.retryable = retryable


class FileAdapter(Protocol):
    def records(
        self, stream: TextIO, limits: ImportLimits
    ) -> Iterator[CanonicalJobInput | RecordError]: ...


def _validate(value: Any, number: int, limits: ImportLimits) -> CanonicalJobInput | RecordError:
    try:
        size = len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        if size > limits.max_row_bytes:
            return RecordError(number, "record exceeds max_row_bytes")
        return CanonicalJobInput.model_validate(value)
    except (TypeError, ValueError, ValidationError) as exc:
        return RecordError(number, str(exc))


class CsvAdapter:
    def records(
        self, stream: TextIO, limits: ImportLimits
    ) -> Iterator[CanonicalJobInput | RecordError]:
        try:
            reader = csv.DictReader(stream)
            for number, row in enumerate(reader, 1):
                if number > limits.max_records:
                    yield RecordError(number, "input exceeds max_records")
                    return
                metadata = row.pop("metadata", "")
                if metadata:
                    try:
                        row["metadata"] = json.loads(metadata)
                    except json.JSONDecodeError as exc:
                        yield RecordError(number, f"invalid metadata JSON: {exc}")
                        continue
                yield _validate(row, number, limits)
        except (csv.Error, UnicodeError) as exc:
            yield RecordError(0, str(exc))


class JsonAdapter:
    def records(
        self, stream: TextIO, limits: ImportLimits
    ) -> Iterator[CanonicalJobInput | RecordError]:
        try:
            value = json.load(stream)
        except (json.JSONDecodeError, UnicodeError) as exc:
            yield RecordError(0, str(exc))
            return
        if not isinstance(value, list):
            yield RecordError(0, "JSON root must be an array")
            return
        for number, record in enumerate(value, 1):
            if number > limits.max_records:
                yield RecordError(number, "input exceeds max_records")
                return
            yield _validate(record, number, limits)


def adapter_for(path: Path) -> FileAdapter:
    if path.suffix.lower() == ".csv":
        return CsvAdapter()
    if path.suffix.lower() == ".json":
        return JsonAdapter()
    raise ValueError("supported file extensions: .csv, .json")
