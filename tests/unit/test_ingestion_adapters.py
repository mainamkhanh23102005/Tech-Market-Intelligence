import io
import json

from tech_market_backend.ingestion.adapters import CsvAdapter, JsonAdapter, RecordError
from tech_market_backend.ingestion.contracts import ImportLimits


def test_csv_and_json_share_validated_contract() -> None:
    csv_value = (
        "source_id,title,company,description,observed_at\n"
        "1,Engineer,Acme,Build,2026-01-01T00:00:00Z\n"
    )
    json_value = json.dumps(
        [
            {
                "source_id": "1",
                "title": "Engineer",
                "company": "Acme",
                "description": "Build",
                "observed_at": "2026-01-01T00:00:00Z",
            }
        ]
    )
    csv_record = next(CsvAdapter().records(io.StringIO(csv_value), ImportLimits()))
    json_record = next(JsonAdapter().records(io.StringIO(json_value), ImportLimits()))
    assert not isinstance(csv_record, RecordError)
    assert not isinstance(json_record, RecordError)
    assert csv_record == json_record


def test_malformed_and_oversized_records_are_terminal_failures() -> None:
    malformed = next(JsonAdapter().records(io.StringIO('[{"title":"x"}]'), ImportLimits()))
    oversized = next(
        JsonAdapter().records(io.StringIO('[{"source_id":"1"}]'), ImportLimits(max_row_bytes=3))
    )
    assert isinstance(malformed, RecordError)
    assert malformed.retryable is False
    assert isinstance(oversized, RecordError)
    assert str(oversized) == "record exceeds max_row_bytes"


def test_json_requires_array_root() -> None:
    result = list(JsonAdapter().records(io.StringIO("{}"), ImportLimits()))
    assert isinstance(result[0], RecordError)
