from urllib.parse import urlsplit
from uuid import UUID

from pydantic import HttpUrl
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker
from tech_market_backend.analytics.registry import METRICS
from tech_market_backend.platform.models import (
    AnalyticsRun,
    CorpusSnapshot,
    CorpusSnapshotMember,
    Job,
    JobSnapshot,
    MarketStatistic,
    RawRecord,
)
from tech_market_contracts import (
    EvidenceDetail,
    JobPage,
    JobSummary,
    MarketPage,
    MarketStatisticResponse,
    PageInfo,
    VersionTuple,
)

from tech_market_api.market import MarketNotFoundError


class PostgresMarketReader:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def market(
        self,
        metric: str,
        snapshot: UUID,
        run: UUID | None,
        cursor: UUID | None,
        limit: int,
        left_role: str | None = None,
        right_role: str | None = None,
    ) -> MarketPage:
        if metric not in METRICS:
            raise MarketNotFoundError("METRIC_NOT_FOUND", "Metric is not registered")
        with self.sessions() as session:
            corpus = session.get(CorpusSnapshot, snapshot)
            if corpus is None:
                raise MarketNotFoundError("SNAPSHOT_NOT_FOUND", "Corpus snapshot was not found")
            selected_run = self._run(session, snapshot, run, metric, left_role, right_role)
            filters = [
                MarketStatistic.metric_key == metric,
                MarketStatistic.analytics_run_id == selected_run.id,
            ]
            if metric == "role_comparison":
                if left_role is None or right_role is None:
                    raise MarketNotFoundError(
                        "ROLE_PAIR_INVALID", "Role comparison requires two distinct selected roles"
                    )
                filters.extend(
                    (
                        MarketStatistic.dimensions["left_role"].astext == left_role,
                        MarketStatistic.dimensions["right_role"].astext == right_role,
                    )
                )
                if list(selected_run.parameters.get("role_pair") or []) != [left_role, right_role]:
                    raise MarketNotFoundError(
                        "ROLE_PAIR_NOT_FOUND", "Requested role pair was not published"
                    )
            query = (
                select(MarketStatistic)
                .where(*filters)
                .order_by(MarketStatistic.value.desc(), MarketStatistic.id)
                .limit(limit + 1)
            )
            if cursor is not None:
                cursor_row = session.scalar(
                    select(MarketStatistic).where(MarketStatistic.id == cursor, *filters)
                )
                if cursor_row is None:
                    raise MarketNotFoundError(
                        "CURSOR_NOT_FOUND", "Market pagination cursor was not found"
                    )
                query = query.where(
                    or_(
                        MarketStatistic.value < cursor_row.value,
                        and_(
                            MarketStatistic.value == cursor_row.value,
                            MarketStatistic.id > cursor_row.id,
                        ),
                    )
                )
            rows = list(session.scalars(query))
            data = [self._statistic(item, selected_run, corpus) for item in rows[:limit]]
            return MarketPage(
                analytics_run_id=str(selected_run.id),
                data=data,
                page=PageInfo(
                    has_more=len(rows) > limit,
                    next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
                ),
            )

    def jobs(self, snapshot: UUID, cursor: UUID | None, limit: int) -> JobPage:
        with self.sessions() as session:
            if session.get(CorpusSnapshot, snapshot) is None:
                raise MarketNotFoundError("SNAPSHOT_NOT_FOUND", "Corpus snapshot was not found")
            query = (
                select(Job, JobSnapshot)
                .join(CorpusSnapshotMember, CorpusSnapshotMember.job_id == Job.id)
                .join(
                    JobSnapshot,
                    (CorpusSnapshotMember.job_snapshot_id == JobSnapshot.id)
                    & (CorpusSnapshotMember.job_id == JobSnapshot.job_id),
                )
                .where(CorpusSnapshotMember.corpus_snapshot_id == snapshot)
                .order_by(JobSnapshot.id)
                .limit(limit + 1)
            )
            if cursor is not None:
                cursor_exists = session.scalar(
                    select(CorpusSnapshotMember.job_snapshot_id).where(
                        CorpusSnapshotMember.corpus_snapshot_id == snapshot,
                        CorpusSnapshotMember.job_snapshot_id == cursor,
                    )
                )
                if cursor_exists is None:
                    raise MarketNotFoundError(
                        "CURSOR_NOT_FOUND", "Jobs pagination cursor was not found"
                    )
                query = query.where(JobSnapshot.id > cursor)
            rows = session.execute(query).all()
            return JobPage(
                data=[self._job(job, item) for job, item in rows[:limit]],
                page=PageInfo(
                    has_more=len(rows) > limit,
                    next_cursor=str(rows[limit - 1][1].id) if len(rows) > limit else None,
                ),
            )

    def evidence(self, corpus_snapshot: UUID, snapshot_id: UUID) -> EvidenceDetail:
        with self.sessions() as session:
            row = session.execute(
                select(Job, JobSnapshot, RawRecord)
                .join(JobSnapshot, JobSnapshot.job_id == Job.id)
                .join(RawRecord, JobSnapshot.raw_record_id == RawRecord.id)
                .join(
                    CorpusSnapshotMember,
                    CorpusSnapshotMember.job_snapshot_id == JobSnapshot.id,
                )
                .where(
                    CorpusSnapshotMember.corpus_snapshot_id == corpus_snapshot,
                    JobSnapshot.id == snapshot_id,
                )
            ).one_or_none()
            if row is None:
                raise MarketNotFoundError("EVIDENCE_NOT_FOUND", "Evidence snapshot was not found")
            job, snapshot, raw = row
            return EvidenceDetail(
                job=self._job(job, snapshot),
                description=snapshot.description,
                source_url=self._safe_source_url(job.canonical_url),
                raw_record_hash=raw.content_hash,
            )

    @staticmethod
    def _run(
        session: Session,
        snapshot: UUID,
        run: UUID | None,
        metric: str,
        left_role: str | None,
        right_role: str | None,
    ) -> AnalyticsRun:
        query = select(AnalyticsRun).where(
            AnalyticsRun.corpus_snapshot_id == snapshot,
            AnalyticsRun.status == "SUCCEEDED",
        )
        if run is not None:
            query = query.where(AnalyticsRun.id == run)
        else:
            if metric == "role_comparison" and left_role is not None and right_role is not None:
                query = query.where(
                    AnalyticsRun.parameters["role_pair"][0].astext == left_role,
                    AnalyticsRun.parameters["role_pair"][1].astext == right_role,
                )
            query = query.order_by(AnalyticsRun.finished_at.desc(), AnalyticsRun.id.desc()).limit(1)
        selected = session.scalar(query)
        if selected is None:
            if run is not None:
                raise MarketNotFoundError(
                    "RUN_NOT_FOUND", "Successful analytics publication was not found"
                )
            if metric == "role_comparison":
                raise MarketNotFoundError(
                    "ROLE_PAIR_NOT_FOUND", "Requested role pair was not published"
                )
            raise MarketNotFoundError(
                "PUBLICATION_NOT_FOUND", "Successful analytics publication was not found"
            )
        return selected

    @staticmethod
    def _statistic(
        statistic: MarketStatistic, run: AnalyticsRun, corpus: CorpusSnapshot
    ) -> MarketStatisticResponse:
        return MarketStatisticResponse(
            id=str(statistic.id),
            value=statistic.value,
            numerator=statistic.numerator,
            denominator=statistic.denominator,
            unit=statistic.unit,
            dimensions=statistic.dimensions,
            cutoff=corpus.source_cutoff,
            snapshot=str(corpus.id),
            versions=VersionTuple(
                metric=statistic.metric_version,
                taxonomy=run.taxonomy_version,
                normalization=run.normalization_version,
                extraction=run.extraction_version,
            ),
            warning=statistic.coverage_warning,
            evidence=statistic.evidence_snapshot_ids,
            metadata=statistic.metadata_,
        )

    @staticmethod
    def _safe_source_url(value: str | None) -> HttpUrl | None:
        if value is None or urlsplit(value).scheme not in {"http", "https"}:
            return None
        return HttpUrl(value)

    @staticmethod
    def _job(job: Job, snapshot: JobSnapshot) -> JobSummary:
        return JobSummary(
            job_id=str(job.id),
            snapshot_id=str(snapshot.id),
            title=snapshot.title,
            company=snapshot.company,
            location=snapshot.location,
            observed_at=snapshot.observed_at,
        )
