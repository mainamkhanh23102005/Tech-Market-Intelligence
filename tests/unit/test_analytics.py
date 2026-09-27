from datetime import UTC, datetime
from decimal import Decimal

from tech_market_backend.analytics.engine import AnalyticsEngine, GoldenJob
from tech_market_backend.analytics.persistence import AnalyticsPersistence
from tech_market_backend.analytics.registry import METRICS, coverage_warning

CUTOFF = datetime(2026, 9, 20, tzinfo=UTC)
VERSIONS = {
    "metric": "skill-prevalence-1.0.0",
    "taxonomy": "skills-2026-09-22",
    "normalization": "normalization-2026-09-01",
    "extraction": "extraction-2026-09-22",
}


def jobs() -> list[GoldenJob]:
    return [
        GoldenJob(
            "job-a",
            "snap-a-old",
            datetime(2026, 9, 1, tzinfo=UTC),
            "backend_engineer",
            "junior",
            "London",
            "hybrid",
            ("python",),
        ),
        GoldenJob(
            "job-a",
            "snap-a",
            datetime(2026, 9, 10, tzinfo=UTC),
            "backend_engineer",
            "junior",
            "London",
            "hybrid",
            ("python", "postgresql", "python"),
        ),
        GoldenJob(
            "job-b",
            "snap-b",
            datetime(2026, 9, 10, tzinfo=UTC),
            "data_engineer",
            None,
            None,
            None,
            ("python", "postgresql"),
        ),
        GoldenJob(
            "job-c",
            "snap-z",
            datetime(2026, 9, 10, tzinfo=UTC),
            None,
            "senior",
            "Hanoi",
            "remote",
            ("python",),
        ),
        GoldenJob(
            "job-c",
            "snap-a-tie",
            datetime(2026, 9, 10, tzinfo=UTC),
            None,
            "senior",
            "Hanoi",
            "remote",
            ("sql",),
        ),
        GoldenJob(
            "job-d",
            "snap-future",
            datetime(2026, 9, 21, tzinfo=UTC),
            "backend_engineer",
            "senior",
            "London",
            "onsite",
            ("go",),
        ),
    ]


def test_registry_defines_formula_dimensions_denominator_and_versions() -> None:
    metric = METRICS["skill_prevalence"]
    assert (
        metric.formula == "distinct logical jobs requesting skill / distinct logical jobs in cohort"
    )
    assert metric.denominator == "distinct logical jobs in cohort"
    assert "role" in metric.dimensions
    assert metric.version == "skill-prevalence-1.0.0"


def test_snapshot_selects_latest_before_cutoff_with_snapshot_id_tie_break() -> None:
    selected = AnalyticsEngine.snapshot(jobs(), CUTOFF)
    assert [(row.job_id, row.snapshot_id) for row in selected] == [
        ("job-a", "snap-a"),
        ("job-b", "snap-b"),
        ("job-c", "snap-z"),
    ]


def test_skill_distribution_deduplicates_jobs_and_skills_and_keeps_unknown_dimensions() -> None:
    engine = AnalyticsEngine("corpus-golden", CUTOFF, VERSIONS)
    results = engine.skill_distribution(jobs())
    python = next(result for result in results if result.dimensions["skill"] == "python")
    assert python.value == Decimal("1")
    assert (python.numerator, python.denominator, python.unit) == (3, 3, "ratio")
    assert python.evidence == ("snap-a", "snap-b", "snap-z")
    unknown_role = engine.skill_distribution(jobs(), {"role": "unknown"})
    assert unknown_role[0].dimensions["role"] == "unknown"
    assert unknown_role[0].denominator == 1


def test_role_comparison_location_and_cooccurrence_are_exact() -> None:
    engine = AnalyticsEngine("corpus-golden", CUTOFF, VERSIONS)
    comparison = engine.role_comparison(jobs(), "backend_engineer", "data_engineer")
    postgres = next(result for result in comparison if result.dimensions["skill"] == "postgresql")
    assert postgres.metadata == {
        "left_numerator": 1,
        "right_numerator": 1,
        "left_denominator": 1,
        "right_denominator": 1,
    }
    locations = engine.location_distribution(jobs())
    assert {(r.dimensions["location"], r.numerator) for r in locations} == {
        ("London", 1),
        ("Hanoi", 1),
        ("unknown", 1),
    }
    pairs = engine.skill_cooccurrence(jobs())
    pair = next(result for result in pairs if result.dimensions["skill_a"] == "postgresql")
    assert (pair.dimensions["skill_b"], pair.numerator, pair.denominator) == ("python", 2, 3)


def test_small_sample_warning_is_explicit() -> None:
    assert coverage_warning(3) == "Small sample: 3 distinct logical jobs; interpret cautiously."
    assert coverage_warning(30) is None


def test_canonical_value_uses_round_half_away_from_zero_like_postgres() -> None:
    canonical = AnalyticsPersistence._canonical_value
    assert canonical(Decimal("0.00048828125")) == Decimal("0.0004882813")
    assert canonical(Decimal("-0.00048828125")) == Decimal("-0.0004882813")
    assert canonical(Decimal(1) / Decimal(2048)) == Decimal("0.0004882813")
    assert canonical(Decimal(-1) / Decimal(2048)) == Decimal("-0.0004882813")
    assert canonical(Decimal("1.00000000005")) == Decimal("1.0000000001")
    assert canonical(Decimal("-1.00000000005")) == Decimal("-1.0000000001")
    assert canonical(Decimal("0.00048828115")) == Decimal("0.0004882812")


def test_metric_definitions_payload_is_complete_and_deterministic() -> None:
    payload = AnalyticsPersistence._metric_definitions_payload()
    assert AnalyticsPersistence._hash(payload) == AnalyticsPersistence._hash(
        AnalyticsPersistence._metric_definitions_payload()
    )
    changed = [dict(row) for row in payload]
    changed[0]["formula"] = "different computation with same nominal version"
    assert AnalyticsPersistence._hash(changed) != AnalyticsPersistence._hash(payload)
    assert [row["key"] for row in payload] == sorted(METRICS)
    assert len(payload) == len(METRICS)
    for row, metric in zip(payload, [METRICS[key] for key in sorted(METRICS)], strict=True):
        assert row == {
            "key": metric.key,
            "version": metric.version,
            "formula": metric.formula,
            "denominator": metric.denominator,
            "dimensions": list(metric.dimensions),
            "unit": metric.unit,
        }
