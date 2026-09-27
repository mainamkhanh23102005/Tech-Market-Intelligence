from collections.abc import Sequence
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from tech_market_contracts import EvidenceDetail, JobPage, MarketPage


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

    @evidence.get("/{snapshot_id}", response_model=EvidenceDetail)
    def get_evidence(
        snapshot_id: UUID,
        snapshot: UUID,
        reader: MarketReader = READER_DEPENDENCY,
    ) -> EvidenceDetail:
        return reader.evidence(snapshot, snapshot_id)

    return market, jobs, evidence
