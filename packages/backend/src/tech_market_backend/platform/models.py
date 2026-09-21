from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(128), unique=True)
    name: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourcePermission(Base):
    __tablename__ = "source_permissions"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"))
    input_name: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32))
    accepted_count: Mapped[int] = mapped_column(default=0)
    duplicate_count: Mapped[int] = mapped_column(default=0)
    failure_count: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RawRecord(Base):
    __tablename__ = "raw_records"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"))
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("source_id", "content_hash"),)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"))
    source_posting_id: Mapped[str | None] = mapped_column(String(512))
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobSnapshot(Base):
    __tablename__ = "job_snapshots"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"))
    raw_record_id: Mapped[UUID] = mapped_column(ForeignKey("raw_records.id"))
    content_hash: Mapped[str] = mapped_column(String(64))
    processor_version: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(512))
    company: Mapped[str] = mapped_column(String(512))
    location: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("job_id", "content_hash", "processor_version"),)


class ProcessingAttempt(Base):
    __tablename__ = "processing_attempts"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_runs.id"))
    record_number: Mapped[int]
    job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    raw_hash: Mapped[str | None] = mapped_column(String(64))
    stage: Mapped[str] = mapped_column(String(32))
    processor_version: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessingFailure(Base):
    __tablename__ = "processing_failures"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("processing_attempts.id"))
    error_type: Mapped[str] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(Text)
    retryable: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
