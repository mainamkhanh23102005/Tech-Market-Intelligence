import pytest

from benchmarks.run_analytics import QUERIES, percentile, run_benchmark, validate_run_snapshot


def test_evidence_benchmark_query_is_scoped_to_corpus() -> None:
    query = QUERIES["evidence"]
    assert "corpus_snapshot_members" in query
    assert "csm.corpus_snapshot_id = :snapshot" in query


def test_percentile_uses_nearest_rank() -> None:
    assert percentile(list(range(1, 31)), 0.95) == 29


class _Result:
    def __init__(self, value: str | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> str | None:
        return self.value


class _Connection:
    def __init__(self, corpus_snapshot_id: str | None) -> None:
        self.corpus_snapshot_id = corpus_snapshot_id
        self.calls = 0

    def execute(self, *_args: object, **_kwargs: object) -> _Result:
        self.calls += 1
        return _Result(self.corpus_snapshot_id)


def test_benchmark_accepts_run_from_requested_corpus_before_queries() -> None:
    connection = _Connection("corpus-a")
    validate_run_snapshot(connection, "corpus-a", "run-a")
    assert connection.calls == 1


@pytest.mark.parametrize("actual", [None, "corpus-b"])
def test_benchmark_rejects_missing_or_foreign_run_before_timing(actual: str | None) -> None:
    connection = _Connection(actual)
    with pytest.raises(ValueError, match="does not belong to requested corpus snapshot"):
        validate_run_snapshot(connection, "corpus-a", "run-a")
    assert connection.calls == 1


def test_benchmark_rejects_mismatched_identity_before_statistics_or_evidence_queries() -> None:
    connection = _Connection("corpus-b")
    with pytest.raises(ValueError, match="does not belong to requested corpus snapshot"):
        run_benchmark(connection, {"snapshot": "corpus-a", "run": "run-a", "evidence": "job-a"}, 1)
    assert connection.calls == 1
