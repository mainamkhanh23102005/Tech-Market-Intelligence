from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, Any] | None = None
    request_id: str = Field(min_length=1)


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ApiError


class PageInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_cursor: str | None = None
    has_more: bool
