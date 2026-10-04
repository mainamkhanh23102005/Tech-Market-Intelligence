import base64
import binascii
import hashlib
import json
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import HttpUrl
from sqlalchemy import and_, cast, func, literal, literal_column, or_, select
from sqlalchemy.dialects.postgresql import JSONB, REGCONFIG
from sqlalchemy.orm import Session, sessionmaker
from tech_market_backend.analytics.registry import METRICS
from tech_market_backend.platform.models import (
    AnalyticsRun,
    AnalyticsRunMember,
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
    JobSearchPage,
    JobSearchResult,
    JobSummary,
    MarketPage,
    MarketStatisticResponse,
    PageInfo,
    VersionTuple,
)

from tech_market_api.market import MarketNotFoundError, MarketValidationError


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

    def search_jobs(
        self,
        corpus_snapshot_id: UUID,
        analytics_run_id: UUID,
        *,
        mode: Literal["structured", "lexical"] = "structured",
        query: str | None,
        role: str | None,
        seniority: str | None,
        location: str | None,
        skills: list[str],
        observed_from: datetime | None,
        observed_to: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> JobSearchPage:
        if mode == "lexical" and (query is None or not query.strip() or "\x00" in query):
            raise MarketValidationError(
                "QUERY_INVALID", "Search query must contain non-whitespace text without NUL bytes"
            )
        filters: dict[str, object] = {
            "query": query,
            "role": role,
            "seniority": seniority,
            "location": location,
            "skills": sorted(skills),
            "observed_from": observed_from.isoformat() if observed_from else None,
            "observed_to": observed_to.isoformat() if observed_to else None,
            "limit": limit,
        }
        if mode == "lexical":
            filters.update(mode=mode, version="lexical-v1")
        scope = hashlib.sha256(
            json.dumps(
                [str(corpus_snapshot_id), str(analytics_run_id), filters],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        position: tuple[datetime, UUID] | None = None
        if cursor is not None:
            try:
                payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
                if payload["scope"] != scope:
                    raise ValueError
                position = (
                    datetime.fromisoformat(payload["observed_at"]),
                    UUID(payload["snapshot_id"]),
                )
                if mode == "lexical" and (
                    position[0].tzinfo is None or position[0].utcoffset() is None
                ):
                    raise ValueError
            except (
                ValueError,
                KeyError,
                TypeError,
                IndexError,
                AttributeError,
                binascii.Error,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ) as error:
                raise MarketNotFoundError(
                    "CURSOR_INVALID", "Search cursor is invalid for this request"
                ) from error
        with self.sessions() as session:
            corpus = session.get(CorpusSnapshot, corpus_snapshot_id)
            run = session.get(AnalyticsRun, analytics_run_id)
            if corpus is None:
                raise MarketNotFoundError("SNAPSHOT_NOT_FOUND", "Corpus snapshot was not found")
            if (
                run is None
                or run.status != "SUCCEEDED"
                or run.corpus_snapshot_id != corpus_snapshot_id
            ):
                raise MarketNotFoundError(
                    "RUN_NOT_FOUND", "Compatible successful analytics run was not found"
                )
            statement = (
                select(AnalyticsRunMember, Job, JobSnapshot)
                .join(Job, Job.id == AnalyticsRunMember.job_id)
                .join(
                    JobSnapshot,
                    and_(
                        JobSnapshot.id == AnalyticsRunMember.job_snapshot_id,
                        JobSnapshot.job_id == AnalyticsRunMember.job_id,
                    ),
                )
                .where(AnalyticsRunMember.analytics_run_id == analytics_run_id)
            )
            rank = None
            if mode == "lexical":
                config = cast(literal("simple"), REGCONFIG)
                vector = (
                    func.setweight(
                        func.to_tsvector(config, JobSnapshot.title), literal_column("'A'")
                    )
                    .op("||")(
                        func.setweight(
                            func.jsonb_to_tsvector(
                                config, AnalyticsRunMember.skills, literal(["string"], type_=JSONB)
                            ),
                            literal_column("'B'"),
                        )
                    )
                    .op("||")(
                        func.setweight(
                            func.to_tsvector(config, JobSnapshot.company), literal_column("'C'")
                        )
                    )
                    .op("||")(
                        func.setweight(
                            func.to_tsvector(config, JobSnapshot.description), literal_column("'D'")
                        )
                    )
                )
                tsquery = func.websearch_to_tsquery(config, query)
                rank = func.ts_rank_cd(vector, tsquery)
                statement = statement.join(
                    CorpusSnapshotMember,
                    and_(
                        CorpusSnapshotMember.corpus_snapshot_id == corpus_snapshot_id,
                        CorpusSnapshotMember.job_id == AnalyticsRunMember.job_id,
                        CorpusSnapshotMember.job_snapshot_id == AnalyticsRunMember.job_snapshot_id,
                    ),
                ).where(vector.bool_op("@@")(tsquery))
            elif query:
                pattern = "%" + query.replace("%", "\\%").replace("_", "\\_") + "%"
                statement = statement.where(
                    or_(
                        JobSnapshot.title.ilike(pattern, escape="\\"),
                        JobSnapshot.company.ilike(pattern, escape="\\"),
                    )
                )
            if role is not None:
                statement = statement.where(AnalyticsRunMember.role == role)
            if seniority is not None:
                statement = statement.where(AnalyticsRunMember.seniority == seniority)
            if location is not None:
                statement = statement.where(AnalyticsRunMember.location == location)
            if skills:
                statement = statement.where(AnalyticsRunMember.skills.contains(sorted(skills)))
            if observed_from is not None:
                statement = statement.where(JobSnapshot.observed_at >= observed_from)
            if observed_to is not None:
                statement = statement.where(JobSnapshot.observed_at <= observed_to)
            if position is not None:
                observed_at, snapshot_id = position
                continuation = or_(
                    JobSnapshot.observed_at < observed_at,
                    and_(JobSnapshot.observed_at == observed_at, JobSnapshot.id > snapshot_id),
                )
                if rank is not None:
                    anchor = statement.where(
                        JobSnapshot.id == snapshot_id,
                        JobSnapshot.observed_at == observed_at,
                    )
                    if (
                        session.scalar(
                            anchor.with_only_columns(JobSnapshot.id, maintain_column_froms=True)
                        )
                        is None
                    ):
                        raise MarketNotFoundError(
                            "CURSOR_INVALID", "Search cursor is invalid for this request"
                        )
                    anchor_rank = (
                        anchor.with_only_columns(rank, maintain_column_froms=True)
                        .correlate(None)
                        .scalar_subquery()
                    )
                    continuation = or_(
                        rank < anchor_rank,
                        and_(rank == anchor_rank, continuation),
                    )
                statement = statement.where(continuation)
            if rank is not None:
                statement = statement.order_by(rank.desc())
            rows = list(
                session.execute(
                    statement.order_by(JobSnapshot.observed_at.desc(), JobSnapshot.id).limit(
                        limit + 1
                    )
                )
            )
            results = [
                JobSearchResult(
                    **self._job(job, snapshot).model_dump(),
                    evidence_url=f"/api/v1/evidence/{snapshot.id}?snapshot={corpus_snapshot_id}",
                )
                for _, job, snapshot in rows[:limit]
            ]
            has_more = len(rows) > limit
            next_cursor = None
            if has_more and rows:
                member, _, snapshot = rows[limit - 1]
                body = json.dumps(
                    {
                        "scope": scope,
                        "observed_at": snapshot.observed_at.isoformat(),
                        "snapshot_id": str(snapshot.id),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                next_cursor = base64.urlsafe_b64encode(body).decode().rstrip("=")
            return JobSearchPage(
                corpus_snapshot_id=str(corpus_snapshot_id),
                analytics_run_id=str(analytics_run_id),
                data=results,
                page=PageInfo(has_more=has_more, next_cursor=next_cursor),
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
