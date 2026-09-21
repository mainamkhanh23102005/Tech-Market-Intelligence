from tech_market_backend.ingestion.identity import content_hash, job_uuid


def test_hash_is_order_independent_canonical_json() -> None:
    assert content_hash({"b": 2, "a": 1}) == content_hash({"a": 1, "b": 2})


def test_job_identity_prefers_source_id_and_is_deterministic() -> None:
    first = job_uuid("source", "42", "https://example.invalid/old")
    second = job_uuid("source", "42", "https://example.invalid/new")
    assert first == second


def test_job_identity_falls_back_to_canonical_url() -> None:
    assert job_uuid("source", None, "https://example.invalid/42") == job_uuid(
        "source", None, "https://example.invalid/42"
    )
