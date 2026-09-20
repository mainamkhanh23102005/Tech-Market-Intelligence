from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from tech_market_contracts import (
    ApiError,
    ErrorEnvelope,
    EvidenceReference,
    MarketFactProvenance,
    PageInfo,
)


def test_error_envelope_has_stable_shape() -> None:
    envelope = ErrorEnvelope(
        error=ApiError(
            code="VALIDATION_ERROR",
            message="Request is invalid",
            details={"field": "roleId"},
            request_id="request-1",
        )
    )

    assert envelope.model_dump() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request is invalid",
            "details": {"field": "roleId"},
            "request_id": "request-1",
        }
    }


def test_page_info_models_cursor_pagination_only() -> None:
    page = PageInfo(next_cursor="opaque-cursor", has_more=True)

    assert page.next_cursor == "opaque-cursor"
    assert page.has_more is True


def test_provenance_preserves_required_market_fact_context() -> None:
    provenance = MarketFactProvenance(
        corpus_snapshot_id="corpus-1",
        metric_version="skill-prevalence-v1",
        taxonomy_version="skills-v1",
        numerator=4,
        denominator=10,
        unit="percent",
        dimensions={"role": "Data Engineer", "seniority": "Junior"},
        source_cutoff=datetime(2026, 9, 20, tzinfo=UTC),
        evidence_references=[
            EvidenceReference(
                evidence_id="evidence-1",
                job_snapshot_id="job-snapshot-1",
                source_url="https://example.invalid/jobs/1",
            )
        ],
        coverage_warning="Small sample",
    )

    assert provenance.numerator == 4
    assert provenance.denominator == 10
    assert provenance.evidence_references[0].job_snapshot_id == "job-snapshot-1"


def test_provenance_rejects_impossible_ratio() -> None:
    with pytest.raises(ValidationError, match="numerator must not exceed denominator"):
        MarketFactProvenance(
            corpus_snapshot_id="corpus-1",
            metric_version="metric-v1",
            taxonomy_version="taxonomy-v1",
            numerator=11,
            denominator=10,
            unit="percent",
            dimensions={},
            source_cutoff=datetime(2026, 9, 20, tzinfo=UTC),
            evidence_references=[],
        )
