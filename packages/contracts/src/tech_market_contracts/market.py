from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from tech_market_contracts.api import PageInfo


class VersionTuple(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    taxonomy: str
    normalization: str
    extraction: str


class MarketStatisticResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    value: Decimal
    numerator: int = Field(ge=0)
    denominator: int = Field(gt=0)
    unit: str
    dimensions: dict[str, str]
    cutoff: datetime
    snapshot: str
    versions: VersionTuple
    warning: str | None
    evidence: list[str]
    metadata: dict[str, int] = Field(default_factory=dict)


class MarketPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analytics_run_id: str
    data: list[MarketStatisticResponse]
    page: PageInfo


class JobSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    snapshot_id: str
    title: str
    company: str
    location: str | None
    observed_at: datetime


class JobPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[JobSummary]
    page: PageInfo


class EvidenceDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: JobSummary
    description: str
    source_url: HttpUrl | None
    raw_record_hash: str
