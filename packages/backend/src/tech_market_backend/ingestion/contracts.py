from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


class PermissionStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"


class IngestionState(StrEnum):
    DISCOVERED = "DISCOVERED"
    RAW_STORED = "RAW_STORED"
    PARSED = "PARSED"
    NORMALIZED = "NORMALIZED"
    READY = "READY"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"


class PermissionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_namespace: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    source_name: str = Field(min_length=1, max_length=256)
    publisher: str = Field(min_length=1, max_length=256)
    license_name: str = Field(min_length=1, max_length=256)
    permission_basis: str = Field(min_length=1, max_length=1000)
    status: PermissionStatus
    reviewed_at: datetime
    source_url: AnyHttpUrl | None = None
    attribution: str = Field(min_length=1, max_length=1000)


class CanonicalJobInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_id: str | None = Field(default=None, max_length=512)
    canonical_url: AnyHttpUrl | None = None
    title: str = Field(min_length=1, max_length=512)
    company: str = Field(min_length=1, max_length=512)
    location: str | None = Field(default=None, max_length=512)
    description: str = Field(min_length=1, max_length=100_000)
    observed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def identity_required(self) -> "CanonicalJobInput":
        if not self.source_id and not self.canonical_url:
            raise ValueError("source_id or canonical_url is required")
        return self


class ImportLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_file_bytes: int = Field(default=10_000_000, ge=1)
    max_records: int = Field(default=100_000, ge=1)
    max_row_bytes: int = Field(default=1_000_000, ge=1)
