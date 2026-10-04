from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from fastapi.testclient import TestClient
from tech_market_api import create_app
from tech_market_api.market import MarketNotFoundError, get_market_reader
from tech_market_contracts import (
    EvidenceDetail,
    JobPage,
    JobSearchPage,
    JobSearchResult,
    JobSummary,
    MarketPage,
    MarketStatisticResponse,
    PageInfo,
    VersionTuple,
)

SNAPSHOT = UUID("00000000-0000-0000-0000-000000000001")
EVIDENCE = UUID("00000000-0000-0000-0000-000000000002")
RUN = UUID("00000000-0000-0000-0000-000000000005")


class Reader:
    requested_runs: ClassVar[list[UUID | None]] = []
    versions = VersionTuple(
        metric="skill-prevalence-1.0.0",
        taxonomy="skills-v1",
        normalization="normalization-v1",
        extraction="extraction-v1",
    )
    job = JobSummary(
        job_id=str(UUID(int=3)),
        snapshot_id=str(EVIDENCE),
        title="Backend Engineer",
        company="Example",
        location=None,
        observed_at=datetime(2026, 9, 20, tzinfo=UTC),
    )

    def market(
        self,
        metric: str,
        snapshot: UUID,
        run: UUID | None,
        cursor: UUID | None,
        limit: int,
        left_role: str | None,
        right_role: str | None,
    ) -> MarketPage:
        self.requested_runs.append(run)
        if metric == "missing":
            raise MarketNotFoundError("METRIC_NOT_FOUND", "Metric is not registered")
        if metric == "role_comparison" and (left_role, right_role) != (
            "backend_engineer",
            "data_engineer",
        ):
            raise MarketNotFoundError(
                "ROLE_PAIR_NOT_FOUND", "Requested role pair was not published"
            )
        return MarketPage(
            analytics_run_id=str(run or RUN),
            data=[
                MarketStatisticResponse(
                    id=str(UUID(int=4)),
                    value=Decimal("0.5"),
                    numerator=1,
                    denominator=2,
                    unit="ratio",
                    dimensions=(
                        {
                            "skill": "python",
                            "left_role": "backend_engineer",
                            "right_role": "data_engineer",
                        }
                        if metric == "role_comparison"
                        else {"skill": "python", "location": "unknown"}
                    ),
                    cutoff=datetime(2026, 9, 20, tzinfo=UTC),
                    snapshot=str(snapshot),
                    versions=self.versions,
                    warning="Small sample",
                    evidence=[str(EVIDENCE)],
                    metadata=(
                        {
                            "left_numerator": 1,
                            "right_numerator": 0,
                            "left_denominator": 1,
                            "right_denominator": 1,
                        }
                        if metric == "role_comparison"
                        else {}
                    ),
                )
            ],
            page=PageInfo(next_cursor=None, has_more=False),
        )

    def jobs(self, snapshot: UUID, cursor: UUID | None, limit: int) -> JobPage:
        return JobPage(data=[self.job], page=PageInfo(next_cursor=None, has_more=False))

    def search_jobs(
        self, corpus_snapshot_id: UUID, analytics_run_id: UUID, **kwargs
    ) -> JobSearchPage:
        return JobSearchPage(
            corpus_snapshot_id=str(corpus_snapshot_id),
            analytics_run_id=str(analytics_run_id),
            data=[
                JobSearchResult(
                    **self.job.model_dump(),
                    evidence_url=f"/api/v1/evidence/{EVIDENCE}?snapshot={corpus_snapshot_id}",
                )
            ],
            page=PageInfo(next_cursor=None, has_more=False),
        )

    def evidence(self, snapshot: UUID, snapshot_id: UUID) -> EvidenceDetail:
        if snapshot != SNAPSHOT or snapshot_id != EVIDENCE:
            raise MarketNotFoundError("EVIDENCE_NOT_FOUND", "Evidence snapshot was not found")
        return EvidenceDetail(
            job=self.job,
            description="Build APIs",
            source_url="https://example.invalid/job-1",
            raw_record_hash="a" * 64,
        )


def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_market_reader] = Reader
    return TestClient(app)


def test_versioned_market_endpoint_returns_complete_statistic() -> None:
    Reader.requested_runs.clear()
    response = client().get(f"/api/v1/market/skill_prevalence?snapshot={SNAPSHOT}&limit=10")
    assert response.status_code == 200
    assert response.json()["data"][0]["versions"] == {
        "metric": "skill-prevalence-1.0.0",
        "taxonomy": "skills-v1",
        "normalization": "normalization-v1",
        "extraction": "extraction-v1",
    }
    assert response.json()["data"][0]["snapshot"] == str(SNAPSHOT)
    assert response.json()["data"][0]["metadata"] == {}
    assert response.json()["analytics_run_id"] == str(RUN)
    assert Reader.requested_runs == [None]


def test_market_endpoint_accepts_explicit_analytics_run_id() -> None:
    Reader.requested_runs.clear()
    response = client().get(
        f"/api/v1/market/skill_prevalence?snapshot={SNAPSHOT}&analytics_run_id={RUN}"
    )
    assert response.status_code == 200
    assert response.json()["analytics_run_id"] == str(RUN)
    assert Reader.requested_runs == [RUN]


def test_role_comparison_exposes_separate_cohort_counts() -> None:
    response = client().get(
        f"/api/v1/market/role_comparison?snapshot={SNAPSHOT}&left_role=backend_engineer&right_role=data_engineer&limit=10"
    )
    assert response.status_code == 200
    assert response.json()["data"][0]["metadata"] == {
        "left_numerator": 1,
        "right_numerator": 0,
        "left_denominator": 1,
        "right_denominator": 1,
    }


def test_jobs_and_evidence_are_paginated_and_resolvable() -> None:
    jobs = client().get(f"/api/v1/jobs?snapshot={SNAPSHOT}")
    evidence = client().get(f"/api/v1/evidence/{EVIDENCE}?snapshot={SNAPSHOT}")
    assert jobs.json()["page"] == {"next_cursor": None, "has_more": False}
    assert evidence.json()["raw_record_hash"] == "a" * 64


def test_role_comparison_requires_distinct_selected_roles() -> None:
    response = client().get(f"/api/v1/market/role_comparison?snapshot={SNAPSHOT}")
    duplicate = client().get(
        f"/api/v1/market/role_comparison?snapshot={SNAPSHOT}&left_role=backend_engineer&right_role=backend_engineer"
    )
    missing = client().get(
        f"/api/v1/market/role_comparison?snapshot={SNAPSHOT}&left_role=unknown&right_role=data_engineer"
    )
    assert response.status_code == 404
    assert duplicate.status_code == 404
    assert missing.status_code == 404
    assert response.json()["error"]["code"] == "ROLE_PAIR_INVALID"
    assert missing.json()["error"]["code"] == "ROLE_PAIR_NOT_FOUND"


def test_role_pair_errors_remain_structured_for_frontend_localization() -> None:
    missing = client().get(
        f"/api/v1/market/role_comparison?snapshot={SNAPSHOT}&left_role=unknown&right_role=data_engineer"
    )
    invalid = client().get(
        f"/api/v1/market/role_comparison?snapshot={SNAPSHOT}&left_role=backend_engineer&right_role=backend_engineer"
    )
    assert missing.json()["error"]["code"] == "ROLE_PAIR_NOT_FOUND"
    assert invalid.json()["error"]["code"] == "ROLE_PAIR_INVALID"
    assert missing.json()["error"]["request_id"]
    assert invalid.json()["error"]["request_id"]


def test_validation_and_not_found_errors_use_structured_envelope() -> None:
    invalid = client().get("/api/v1/jobs?snapshot=not-a-uuid")
    missing = client().get(f"/api/v1/market/missing?snapshot={SNAPSHOT}")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "METRIC_NOT_FOUND"


def test_page_limit_is_bounded() -> None:
    response = client().get(f"/api/v1/jobs?snapshot={SNAPSHOT}&limit=101")
    assert response.status_code == 422


def test_structured_search_returns_snapshot_pinned_evidence_without_snippets() -> None:
    response = client().get(
        f"/api/v1/jobs/search?snapshot={SNAPSHOT}&analytics_run_id={RUN}&role=backend_engineer&skill=python"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["corpus_snapshot_id"] == str(SNAPSHOT)
    assert payload["analytics_run_id"] == str(RUN)
    assert payload["data"][0]["evidence_url"] == f"/api/v1/evidence/{EVIDENCE}?snapshot={SNAPSHOT}"
    assert "description" not in payload["data"][0]


def test_structured_search_rejects_empty_malformed_filters_and_unbounded_page() -> None:
    base = f"/api/v1/jobs/search?snapshot={SNAPSHOT}&analytics_run_id={RUN}"
    for suffix in (
        "&query=%20%20",
        "&role=%20%20",
        "&seniority=%20%20",
        "&location=%20%20",
        "&observed_from=not-a-date",
        "&limit=101",
        "&skill=",
        "&skill=python&skill=%20python%20",
    ):
        response = client().get(base + suffix)
        assert response.status_code == 422
        assert response.json()["error"]["request_id"]


def test_structured_search_rejects_naive_datetime_bounds() -> None:
    base = f"/api/v1/jobs/search?snapshot={SNAPSHOT}&analytics_run_id={RUN}"
    for suffix in (
        "&observed_from=2026-09-20T00:00:00",
        "&observed_to=2026-09-20T00:00:00",
        "&observed_from=2026-09-20T00:00:00&observed_to=2026-09-21T00:00:00Z",
    ):
        response = client().get(base + suffix)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FILTER_INVALID"


def test_structured_search_rejects_reversed_date_range() -> None:
    response = client().get(
        f"/api/v1/jobs/search?snapshot={SNAPSHOT}&analytics_run_id={RUN}"
        "&observed_from=2026-09-21T00:00:00Z&observed_to=2026-09-20T00:00:00Z"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FILTER_INVALID"


def test_search_modes_forward_normalized_parameters() -> None:
    requests: list[tuple[UUID, UUID, dict[str, object]]] = []

    class CapturingReader(Reader):
        def search_jobs(
            self, corpus_snapshot_id: UUID, analytics_run_id: UUID, **kwargs: object
        ) -> JobSearchPage:
            requests.append((corpus_snapshot_id, analytics_run_id, kwargs))
            return super().search_jobs(corpus_snapshot_id, analytics_run_id, **kwargs)

    for mode in (None, "structured", "lexical"):
        requests.clear()
        app = create_app()
        app.dependency_overrides[get_market_reader] = CapturingReader
        params = [
            ("snapshot", str(SNAPSHOT)),
            ("analytics_run_id", str(RUN)),
            ("query", '  "Python developer" OR SQL  '),
            ("role", " backend_engineer "),
            ("seniority", " senior "),
            ("location", " remote "),
            ("skill", " python "),
            ("skill", " sql "),
            ("observed_from", "2026-09-20T00:00:00Z"),
            ("observed_to", "2026-09-21T00:00:00Z"),
            ("cursor", "opaque-cursor"),
            ("limit", "7"),
        ]
        if mode is not None:
            params.append(("mode", mode))
        response = TestClient(app).get("/api/v1/jobs/search", params=params)
        assert response.status_code == 200
        assert requests == [
            (
                SNAPSHOT,
                RUN,
                {
                    "mode": mode or "structured",
                    "query": '"Python developer" OR SQL',
                    "role": "backend_engineer",
                    "seniority": "senior",
                    "location": "remote",
                    "skills": ["python", "sql"],
                    "observed_from": datetime(2026, 9, 20, tzinfo=UTC),
                    "observed_to": datetime(2026, 9, 21, tzinfo=UTC),
                    "cursor": "opaque-cursor",
                    "limit": 7,
                },
            )
        ]
        assert "description" not in response.json()["data"][0]
        assert "rank" not in response.json()["data"][0]


def test_search_rejects_invalid_modes_before_reader() -> None:
    app = create_app()

    class RejectingReader(Reader):
        def search_jobs(self, *args: object, **kwargs: object) -> JobSearchPage:
            raise AssertionError("Invalid request reached reader")

    app.dependency_overrides[get_market_reader] = RejectingReader
    for mode in ("unknown", "LEXICAL", "", " lexical "):
        response = TestClient(app).get(
            "/api/v1/jobs/search",
            params={
                "snapshot": str(SNAPSHOT),
                "analytics_run_id": str(RUN),
                "query": "python",
                "mode": mode,
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert response.json()["error"]["request_id"]


def test_lexical_search_requires_nonblank_query_before_reader() -> None:
    app = create_app()

    class RejectingReader(Reader):
        def search_jobs(self, *args: object, **kwargs: object) -> JobSearchPage:
            raise AssertionError("Invalid request reached reader")

    app.dependency_overrides[get_market_reader] = RejectingReader
    for query in (None, "", " \t "):
        params = {
            "snapshot": str(SNAPSHOT),
            "analytics_run_id": str(RUN),
            "mode": "lexical",
        }
        if query is not None:
            params["query"] = query
        response = TestClient(app).get("/api/v1/jobs/search", params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == (
            "VALIDATION_ERROR" if query == "" else "QUERY_INVALID"
        )
        assert response.json()["error"]["request_id"]


def test_search_rejects_nul_text_before_reader() -> None:
    app = create_app()

    class RejectingReader(Reader):
        def search_jobs(self, *args: object, **kwargs: object) -> JobSearchPage:
            raise AssertionError("Invalid request reached reader")

    app.dependency_overrides[get_market_reader] = RejectingReader
    for mode in ("structured", "lexical"):
        for field in ("query", "role", "seniority", "location", "skill"):
            response = TestClient(app).get(
                "/api/v1/jobs/search",
                params={
                    "snapshot": str(SNAPSHOT),
                    "analytics_run_id": str(RUN),
                    "mode": mode,
                    "query": "python",
                    field: "python\x00",
                },
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == (
                "QUERY_INVALID" if field == "query" else "FILTER_INVALID"
            )
            assert response.json()["error"]["request_id"]


def test_search_default_matches_explicit_structured_without_query() -> None:
    base = f"/api/v1/jobs/search?snapshot={SNAPSHOT}&analytics_run_id={RUN}"
    default = client().get(base)
    structured = client().get(base + "&mode=structured")
    assert default.status_code == structured.status_code == 200
    assert default.json() == structured.json()


def test_source_url_rejects_unsafe_scheme() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EvidenceDetail(
            job=Reader.job,
            description="x",
            source_url="javascript:alert(1)",
            raw_record_hash="a" * 64,
        )
