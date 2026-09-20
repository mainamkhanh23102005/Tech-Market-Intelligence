from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    job_snapshot_id: str = Field(min_length=1)
    source_url: str | None = None


class MarketFactProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_snapshot_id: str = Field(min_length=1)
    metric_version: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    numerator: int = Field(ge=0)
    denominator: int = Field(gt=0)
    unit: str = Field(min_length=1)
    dimensions: dict[str, str]
    source_cutoff: datetime
    evidence_references: list[EvidenceReference]
    coverage_warning: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def numerator_must_not_exceed_denominator(self) -> "MarketFactProvenance":
        if self.numerator > self.denominator:
            raise ValueError("numerator must not exceed denominator")
        return self
