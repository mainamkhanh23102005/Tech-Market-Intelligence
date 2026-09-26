from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from itertools import combinations

from tech_market_backend.analytics.registry import METRICS, coverage_warning


@dataclass(frozen=True)
class GoldenJob:
    job_id: str
    snapshot_id: str
    observed_at: datetime
    role: str | None
    seniority: str | None
    location: str | None
    work_arrangement: str | None
    skills: tuple[str, ...]
    normalization_id: str | None = None
    normalization_status: str = "unresolved"
    normalization_method: str | None = None
    processor_version: str | None = None


@dataclass(frozen=True)
class Statistic:
    value: Decimal
    numerator: int
    denominator: int
    unit: str
    dimensions: dict[str, str]
    cutoff: datetime
    corpus_snapshot_id: str
    versions: dict[str, str]
    warning: str | None
    evidence: tuple[str, ...]
    metadata: dict[str, int] = field(default_factory=dict)


class AnalyticsEngine:
    def __init__(
        self,
        corpus_snapshot_id: str,
        cutoff: datetime,
        versions: Mapping[str, str],
    ) -> None:
        self.corpus_snapshot_id = corpus_snapshot_id
        self.cutoff = cutoff
        self.versions = dict(versions)

    @staticmethod
    def snapshot(rows: list[GoldenJob], cutoff: datetime) -> list[GoldenJob]:
        selected: dict[str, GoldenJob] = {}
        for row in rows:
            if row.observed_at > cutoff:
                continue
            current = selected.get(row.job_id)
            if current is None or (row.observed_at, row.snapshot_id) > (
                current.observed_at,
                current.snapshot_id,
            ):
                selected[row.job_id] = row
        return sorted(selected.values(), key=lambda item: item.job_id)

    def _cohort(
        self, rows: list[GoldenJob], dimensions: Mapping[str, str] | None = None
    ) -> list[GoldenJob]:
        selected = self.snapshot(rows, self.cutoff)
        filters = dimensions or {}
        return [
            row
            for row in selected
            if all((getattr(row, key) or "unknown") == value for key, value in filters.items())
        ]

    def _statistic(
        self,
        metric: str,
        numerator: int,
        denominator: int,
        dimensions: dict[str, str],
        evidence: tuple[str, ...],
        metadata: dict[str, int] | None = None,
    ) -> Statistic:
        versions = {**self.versions, "metric": METRICS[metric].version}
        return Statistic(
            value=Decimal(numerator) / Decimal(denominator),
            numerator=numerator,
            denominator=denominator,
            unit=METRICS[metric].unit,
            dimensions=dimensions,
            cutoff=self.cutoff,
            corpus_snapshot_id=self.corpus_snapshot_id,
            versions=versions,
            warning=coverage_warning(denominator),
            evidence=evidence,
            metadata=metadata or {},
        )

    def skill_distribution(
        self, rows: list[GoldenJob], dimensions: Mapping[str, str] | None = None
    ) -> list[Statistic]:
        cohort = self._cohort(rows, dimensions)
        denominator = len(cohort)
        if not denominator:
            return []
        skills = sorted({skill for row in cohort for skill in set(row.skills)})
        return [
            self._statistic(
                "skill_prevalence",
                sum(skill in set(row.skills) for row in cohort),
                denominator,
                {**(dict(dimensions or {})), "skill": skill},
                tuple(row.snapshot_id for row in cohort if skill in set(row.skills)),
            )
            for skill in skills
        ]

    def role_comparison(
        self, rows: list[GoldenJob], left_role: str, right_role: str
    ) -> list[Statistic]:
        left = self._cohort(rows, {"role": left_role})
        right = self._cohort(rows, {"role": right_role})
        skills = sorted({skill for row in left + right for skill in set(row.skills)})
        results = []
        for skill in skills:
            left_count = sum(skill in set(row.skills) for row in left)
            right_count = sum(skill in set(row.skills) for row in right)
            results.append(
                self._statistic(
                    "role_comparison",
                    left_count + right_count,
                    len(left) + len(right),
                    {"left_role": left_role, "right_role": right_role, "skill": skill},
                    tuple(row.snapshot_id for row in left + right if skill in set(row.skills)),
                    {
                        "left_numerator": left_count,
                        "right_numerator": right_count,
                        "left_denominator": len(left),
                        "right_denominator": len(right),
                    },
                )
            )
        return results

    def location_distribution(self, rows: list[GoldenJob]) -> list[Statistic]:
        cohort = self._cohort(rows)
        counts = Counter(row.location or "unknown" for row in cohort)
        return [
            self._statistic(
                "location_distribution",
                count,
                len(cohort),
                {"location": location},
                tuple(row.snapshot_id for row in cohort if (row.location or "unknown") == location),
            )
            for location, count in sorted(counts.items())
        ]

    def skill_cooccurrence(self, rows: list[GoldenJob]) -> list[Statistic]:
        cohort = self._cohort(rows)
        counts: Counter[tuple[str, str]] = Counter()
        evidence: dict[tuple[str, str], list[str]] = {}
        for row in cohort:
            for pair in combinations(sorted(set(row.skills)), 2):
                counts[pair] += 1
                evidence.setdefault(pair, []).append(row.snapshot_id)
        return [
            self._statistic(
                "skill_cooccurrence",
                count,
                len(cohort),
                {"skill_a": pair[0], "skill_b": pair[1]},
                tuple(evidence[pair]),
            )
            for pair, count in sorted(counts.items())
        ]
