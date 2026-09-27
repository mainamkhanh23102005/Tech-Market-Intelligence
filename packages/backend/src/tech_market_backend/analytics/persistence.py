import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid5

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased, sessionmaker

from tech_market_backend.analytics.engine import AnalyticsEngine, GoldenJob, Statistic
from tech_market_backend.analytics.registry import METRICS
from tech_market_backend.platform.models import (
    AnalyticsRun,
    AnalyticsRunMember,
    CorpusSnapshot,
    CorpusSnapshotMember,
    JobSkill,
    JobSnapshot,
    MarketStatistic,
    MetricDefinitionRecord,
    Skill,
    SnapshotNormalization,
    TaxonomyVersion,
)
from tech_market_backend.taxonomy.versions import EXTRACTION_VERSION, NORMALIZATION_VERSION

NAMESPACE = UUID("5f764454-90d4-44cc-a19d-d30df64a3208")
PUBLICATION_VERSION = "m3-market-1.0.0"


class AnalyticsPersistence:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def create_corpus_snapshot(self, cutoff: datetime) -> UUID:
        cutoff = self._utc(cutoff)
        with self.sessions.begin() as session:
            rows = session.execute(
                select(JobSnapshot.id, JobSnapshot.job_id, JobSnapshot.observed_at)
                .where(JobSnapshot.observed_at <= cutoff)
                .order_by(
                    JobSnapshot.job_id,
                    JobSnapshot.observed_at.desc(),
                    JobSnapshot.id.desc(),
                )
            ).all()
            members: dict[UUID, UUID] = {}
            for snapshot_id, job_id, _ in rows:
                members.setdefault(job_id, snapshot_id)
            canonical = [(str(job), str(snapshot)) for job, snapshot in sorted(members.items())]
            membership_hash = hashlib.sha256(
                json.dumps(canonical, separators=(",", ":")).encode()
            ).hexdigest()
            corpus_id = uuid5(NAMESPACE, f"{cutoff.isoformat()}:{membership_hash}")
            if session.get(CorpusSnapshot, corpus_id) is None:
                session.add(
                    CorpusSnapshot(
                        id=corpus_id,
                        source_cutoff=cutoff,
                        membership_hash=membership_hash,
                        job_count=len(members),
                    )
                )
                session.add_all(
                    CorpusSnapshotMember(
                        corpus_snapshot_id=corpus_id,
                        job_id=job_id,
                        job_snapshot_id=snapshot_id,
                    )
                    for job_id, snapshot_id in members.items()
                )
            return corpus_id

    def publish(
        self, cutoff: datetime, versions: dict[str, str], role_pair: tuple[str, str] | None = None
    ) -> UUID:
        if role_pair is not None and (len(role_pair) != 2 or role_pair[0] == role_pair[1]):
            raise ValueError("role comparison requires two distinct roles")
        cutoff = self._utc(cutoff)
        self._validate_versions(versions)
        self._validate_known_versions(versions)
        corpus_id = self.create_corpus_snapshot(cutoff)
        rows = self._load_rows(corpus_id, versions)
        run_versions = {**versions, "metric": PUBLICATION_VERSION}
        input_data = {
            "schema_version": "analytics-run-input-2",
            "corpus": str(corpus_id),
            "cutoff": cutoff,
            "versions": run_versions,
            "parameters": {"role_pair": list(role_pair) if role_pair is not None else None},
            "metric_definitions": self._metric_definitions_payload(),
            "members": [self._member_payload(row) for row in rows],
        }
        input_hash = self._hash(input_data)
        run_id = uuid5(NAMESPACE, input_hash)
        with self.sessions.begin() as session:
            self._seed_metrics(session)
            existing = session.get(AnalyticsRun, run_id)
            if existing is not None and existing.status == "SUCCEEDED":
                return run_id
            session.flush()
            if existing is None:
                session.add(
                    AnalyticsRun(
                        id=run_id,
                        corpus_snapshot_id=corpus_id,
                        metric_version=PUBLICATION_VERSION,
                        taxonomy_version=versions["taxonomy"],
                        normalization_version=versions["normalization"],
                        extraction_version=versions["extraction"],
                        parameters={
                            "role_pair": list(role_pair) if role_pair is not None else None
                        },
                        status="RUNNING",
                        input_hash=input_hash,
                    )
                )
                session.add_all(
                    AnalyticsRunMember(
                        analytics_run_id=run_id,
                        job_id=UUID(row.job_id),
                        job_snapshot_id=UUID(row.snapshot_id),
                        observed_at=row.observed_at,
                        normalization_id=(
                            UUID(row.normalization_id) if row.normalization_id else None
                        ),
                        normalization_status=row.normalization_status,
                        normalization_method=row.normalization_method,
                        processor_version=row.processor_version,
                        role=row.role,
                        seniority=row.seniority,
                        location=row.location,
                        work_arrangement=row.work_arrangement,
                        skills=list(row.skills),
                    )
                    for row in rows
                )
            engine = AnalyticsEngine(str(corpus_id), cutoff, versions)
            statistics = {
                "skill_prevalence": engine.skill_distribution(rows),
                "location_distribution": engine.location_distribution(rows),
                "skill_cooccurrence": engine.skill_cooccurrence(rows),
            }
            if role_pair is not None:
                available_roles = {row.role or "unknown" for row in rows}
                if not set(role_pair) <= available_roles:
                    raise ValueError("requested role comparison cohort is not present")
                statistics["role_comparison"] = engine.role_comparison(rows, *role_pair)
            canonical_results: list[dict[str, object]] = []
            for metric, results in statistics.items():
                for result in results:
                    value = self._canonical_value(result.value)
                    payload = self._statistic_payload(metric, result, value)
                    canonical_results.append(payload)
                    session.add(
                        MarketStatistic(
                            id=uuid5(NAMESPACE, f"{run_id}:{self._hash(payload)}"),
                            analytics_run_id=run_id,
                            metric_key=metric,
                            metric_version=METRICS[metric].version,
                            value=value,
                            numerator=result.numerator,
                            denominator=result.denominator,
                            unit=result.unit,
                            dimensions=result.dimensions,
                            coverage_warning=result.warning,
                            evidence_snapshot_ids=list(result.evidence),
                            metadata_=result.metadata,
                        )
                    )
            run = session.get(AnalyticsRun, run_id)
            if run is None:
                session.flush()
                run = session.get(AnalyticsRun, run_id)
            if run is None:
                raise RuntimeError("analytics run persistence failed")
            run.result_hash = self.result_hash(canonical_results)
            run.status = "SUCCEEDED"
            run.finished_at = datetime.now(UTC)
        return run_id

    def _load_rows(self, corpus_id: UUID, versions: dict[str, str]) -> list[GoldenJob]:
        ranked_normalizations = (
            select(
                SnapshotNormalization.id.label("id"),
                SnapshotNormalization.snapshot_id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=SnapshotNormalization.snapshot_id,
                    order_by=(
                        SnapshotNormalization.created_at.desc(),
                        SnapshotNormalization.id.desc(),
                    ),
                )
                .label("rank"),
            )
            .join(TaxonomyVersion, SnapshotNormalization.taxonomy_version_id == TaxonomyVersion.id)
            .where(
                TaxonomyVersion.version == versions["taxonomy"],
                SnapshotNormalization.normalization_version == versions["normalization"],
                SnapshotNormalization.extraction_version == versions["extraction"],
                SnapshotNormalization.status.in_(("SUCCEEDED", "PARTIAL")),
            )
            .subquery()
        )
        selected_normalization = aliased(SnapshotNormalization)
        with self.sessions() as session:
            records = session.execute(
                select(
                    CorpusSnapshotMember.job_id,
                    JobSnapshot,
                    selected_normalization,
                    Skill.key,
                )
                .join(JobSnapshot, CorpusSnapshotMember.job_snapshot_id == JobSnapshot.id)
                .outerjoin(
                    ranked_normalizations,
                    and_(
                        ranked_normalizations.c.snapshot_id == JobSnapshot.id,
                        ranked_normalizations.c.rank == 1,
                    ),
                )
                .outerjoin(
                    selected_normalization, selected_normalization.id == ranked_normalizations.c.id
                )
                .outerjoin(
                    JobSkill,
                    (JobSkill.normalization_id == selected_normalization.id)
                    & (JobSkill.reviewed_state == "accepted")
                    & (JobSkill.extractor_version == versions["extraction"]),
                )
                .outerjoin(Skill, JobSkill.skill_id == Skill.id)
                .where(CorpusSnapshotMember.corpus_snapshot_id == corpus_id)
                .order_by(CorpusSnapshotMember.job_id, Skill.key)
            ).all()
        grouped: dict[UUID, tuple[JobSnapshot, SnapshotNormalization | None, set[str]]] = {}
        for job_id, snapshot, normalization, skill in records:
            current = grouped.setdefault(job_id, (snapshot, normalization, set()))
            if skill is not None:
                current[2].add(skill)
        return [
            GoldenJob(
                str(job_id),
                str(snapshot.id),
                snapshot.observed_at,
                normalization.role if normalization is not None else None,
                normalization.seniority if normalization is not None else None,
                (
                    normalization.location_city or normalization.location_country
                    if normalization is not None
                    else None
                ),
                normalization.work_arrangement if normalization is not None else None,
                tuple(sorted(skills)),
                str(normalization.id) if normalization is not None else None,
                normalization.status if normalization is not None else "unresolved",
                normalization.method if normalization is not None else None,
                normalization.processor_version if normalization is not None else None,
            )
            for job_id, (snapshot, normalization, skills) in sorted(grouped.items())
        ]

    def _validate_versions(self, versions: dict[str, str]) -> None:
        required = {"taxonomy", "normalization", "extraction"}
        if set(versions) != required or not all(versions.values()):
            raise ValueError("exact taxonomy, normalization, and extraction versions are required")

    def _validate_known_versions(self, versions: dict[str, str]) -> None:
        if versions["normalization"] != NORMALIZATION_VERSION:
            raise ValueError("normalization version is not supported")
        if versions["extraction"] != EXTRACTION_VERSION:
            raise ValueError("extraction version is not supported")
        with self.sessions() as session:
            known_taxonomy = session.scalar(
                select(TaxonomyVersion.id).where(TaxonomyVersion.version == versions["taxonomy"])
            )
        if known_taxonomy is None:
            raise ValueError("taxonomy version is not seeded")

    @staticmethod
    def _seed_metrics(session: Session) -> None:
        for metric in METRICS.values():
            existing = session.get(MetricDefinitionRecord, (metric.key, metric.version))
            if existing is None:
                session.add(
                    MetricDefinitionRecord(
                        key=metric.key,
                        version=metric.version,
                        formula=metric.formula,
                        denominator=metric.denominator,
                        dimensions=list(metric.dimensions),
                        unit=metric.unit,
                    )
                )
                continue
            if (
                existing.formula != metric.formula
                or existing.denominator != metric.denominator
                or list(existing.dimensions) != list(metric.dimensions)
                or existing.unit != metric.unit
            ):
                raise ValueError(f"metric definition content mismatch for {metric.key}")

    @staticmethod
    def _metric_definitions_payload() -> list[dict[str, object]]:
        return [
            {
                "key": metric.key,
                "version": metric.version,
                "formula": metric.formula,
                "denominator": metric.denominator,
                "dimensions": list(metric.dimensions),
                "unit": metric.unit,
            }
            for metric in sorted(METRICS.values(), key=lambda item: (item.key, item.version))
        ]

    @staticmethod
    def _member_payload(row: GoldenJob) -> dict[str, object]:
        return {
            "job_id": row.job_id,
            "snapshot_id": row.snapshot_id,
            "observed_at": row.observed_at,
            "normalization_id": row.normalization_id,
            "normalization_status": row.normalization_status,
            "normalization_method": row.normalization_method,
            "processor_version": row.processor_version,
            "role": row.role,
            "seniority": row.seniority,
            "location": row.location,
            "work_arrangement": row.work_arrangement,
            "skills": list(row.skills),
        }

    @staticmethod
    def _canonical_value(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)

    @classmethod
    def result_hash(cls, payloads: list[dict[str, object]]) -> str:
        return cls._hash(sorted(payloads, key=cls._hash))

    @staticmethod
    def _statistic_payload(metric: str, result: Statistic, value: Decimal) -> dict[str, object]:
        return {
            "metric": metric,
            "value": str(value),
            "numerator": result.numerator,
            "denominator": result.denominator,
            "unit": result.unit,
            "dimensions": result.dimensions,
            "cutoff": result.cutoff,
            "corpus_snapshot_id": result.corpus_snapshot_id,
            "versions": result.versions,
            "warning": result.warning,
            "evidence": list(result.evidence),
            "metadata": result.metadata,
        }

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("cutoff must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _hash(value: object) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
