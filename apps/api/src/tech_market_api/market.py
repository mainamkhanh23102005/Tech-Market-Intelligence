from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from tech_market_contracts import EvidenceDetail, JobPage, JobSearchPage, MarketPage


class MarketValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message


class MarketNotFoundError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message


class MarketReader(Protocol):
    def market(
        self,
        metric: str,
        snapshot: UUID,
        run: UUID | None,
        cursor: UUID | None,
        limit: int,
        left_role: str | None,
        right_role: str | None,
    ) -> MarketPage: ...

    def jobs(self, snapshot: UUID, cursor: UUID | None, limit: int) -> JobPage: ...

    def evidence(self, snapshot: UUID, snapshot_id: UUID) -> EvidenceDetail: ...

    def search_jobs(
        self,
        corpus_snapshot_id: UUID,
        analytics_run_id: UUID,
        *,
        query: str | None,
        role: str | None,
        seniority: str | None,
        location: str | None,
        skills: list[str],
        observed_from: datetime | None,
        observed_to: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> JobSearchPage: ...


class UnconfiguredMarketReader:
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
        raise RuntimeError("Market database is not configured")

    def jobs(self, snapshot: UUID, cursor: UUID | None, limit: int) -> JobPage:
        raise RuntimeError("Market database is not configured")

    def evidence(self, snapshot: UUID, snapshot_id: UUID) -> EvidenceDetail:
        raise RuntimeError("Market database is not configured")

    def search_jobs(self, *args: object, **kwargs: object) -> JobSearchPage:
        raise RuntimeError("Market database is not configured")


def get_market_reader() -> MarketReader:
    return UnconfiguredMarketReader()


READER_DEPENDENCY = Depends(get_market_reader)
PAGE_LIMIT = Query(ge=1, le=100)


def routes() -> Sequence[APIRouter]:
    market = APIRouter(prefix="/api/v1/market", tags=["market"])
    jobs = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])
    evidence = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])

    @market.get("/{metric}", response_model=MarketPage)
    def list_market(
        metric: str,
        snapshot: UUID,
        analytics_run_id: UUID | None = None,
        cursor: UUID | None = None,
        limit: Annotated[int, PAGE_LIMIT] = 20,
        left_role: str | None = None,
        right_role: str | None = None,
        reader: MarketReader = READER_DEPENDENCY,
    ) -> MarketPage:
        if metric == "role_comparison" and (
            not left_role or not right_role or left_role == right_role
        ):
            raise MarketNotFoundError(
                "ROLE_PAIR_INVALID", "Role comparison requires two distinct selected roles"
            )
        return reader.market(
            metric, snapshot, analytics_run_id, cursor, limit, left_role, right_role
        )

    @jobs.get("", response_model=JobPage)
    def list_jobs(
        snapshot: UUID,
        cursor: UUID | None = None,
        limit: Annotated[int, PAGE_LIMIT] = 20,
        reader: MarketReader = READER_DEPENDENCY,
    ) -> JobPage:
        return reader.jobs(snapshot, cursor, limit)

    @jobs.get("/search", response_model=JobSearchPage)
    def search_jobs(
        snapshot: UUID,
        analytics_run_id: UUID,
        query: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
        role: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
        seniority: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
        location: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
        skill: Annotated[list[str] | None, Query(max_length=20)] = None,
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        reader: MarketReader = READER_DEPENDENCY,
    ) -> JobSearchPage:
        normalized_query = query.strip() if query is not None else None
        normalized_role = role.strip() if role is not None else None
        normalized_seniority = seniority.strip() if seniority is not None else None
        normalized_location = location.strip() if location is not None else None
        normalized_skills = [value.strip() for value in skill] if skill is not None else []

        if normalized_query == "":
            raise MarketValidationError(
                "QUERY_INVALID", "Search query must contain non-whitespace text"
            )
        if any(
            value == ""
            for value in (normalized_role, normalized_seniority, normalized_location)
            if value is not None
        ):
            raise MarketValidationError(
                "FILTER_INVALID", "Structured filters must contain non-whitespace text"
            )
        if len(set(normalized_skills)) != len(normalized_skills) or any(
            not value for value in normalized_skills
        ):
            raise MarketValidationError("FILTER_INVALID", "Skills must be non-empty and unique")

        for name, value in (
            ("observed_from", observed_from),
            ("observed_to", observed_to),
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise MarketValidationError(
                    "FILTER_INVALID", f"{name} must include a timezone offset"
                )

        if observed_from is not None and observed_to is not None and observed_from > observed_to:
            raise MarketValidationError(
                "FILTER_INVALID", "observed_from must not be later than observed_to"
            )

        return reader.search_jobs(
            snapshot,
            analytics_run_id,
            query=normalized_query,
            role=normalized_role,
            seniority=normalized_seniority,
            location=normalized_location,
            skills=normalized_skills,
            observed_from=observed_from,
            observed_to=observed_to,
            cursor=cursor,
            limit=limit,
        )

    @evidence.get("/{snapshot_id}", response_model=EvidenceDetail)
    def get_evidence(
        snapshot_id: UUID,
        snapshot: UUID,
        reader: MarketReader = READER_DEPENDENCY,
    ) -> EvidenceDetail:
        return reader.evidence(snapshot, snapshot_id)

    return market, jobs, evidence
