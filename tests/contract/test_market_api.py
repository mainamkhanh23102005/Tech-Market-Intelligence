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
