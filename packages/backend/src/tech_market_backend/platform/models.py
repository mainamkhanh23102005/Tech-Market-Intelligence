from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
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


class TaxonomyVersion(Base):
    __tablename__ = "taxonomy_versions"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), unique=True)
    manifest_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'RETIRED')", name="ck_taxonomy_versions_status"
        ),
    )


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True)


class TaxonomySkillVersion(Base):
    __tablename__ = "taxonomy_skill_versions"
    skill_id: Mapped[UUID] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    taxonomy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("taxonomy_versions.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(256))
    category: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    valid_from: Mapped[str | None] = mapped_column(String(64))
    valid_to: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'deprecated', 'retired')", name="ck_skill_versions_status"
        ),
        Index("ix_skill_versions_name", "taxonomy_version_id", "name"),
    )


class SkillAlias(Base):
    __tablename__ = "skill_aliases"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    skill_id: Mapped[UUID]
    taxonomy_version_id: Mapped[UUID]
    alias: Mapped[str] = mapped_column(String(256))
    normalized_alias: Mapped[str] = mapped_column(String(256))
    locale: Mapped[str] = mapped_column(String(16))
    matching_mode: Mapped[str] = mapped_column(String(32))
    case_sensitive: Mapped[bool]
    boundary_rule: Mapped[str] = mapped_column(String(32))
    ambiguity_status: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(
            ["skill_id", "taxonomy_version_id"],
            ["taxonomy_skill_versions.skill_id", "taxonomy_skill_versions.taxonomy_version_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "skill_id", "taxonomy_version_id", "alias", name="uq_skill_aliases_skill_version_alias"
        ),
        Index("ix_skill_aliases_alias", "alias"),
    )


class SkillRelationship(Base):
    __tablename__ = "skill_relationships"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    taxonomy_version_id: Mapped[UUID] = mapped_column(ForeignKey("taxonomy_versions.id"))
    parent_skill_id: Mapped[UUID] = mapped_column(ForeignKey("skills.id"))
    child_skill_id: Mapped[UUID] = mapped_column(ForeignKey("skills.id"))
    relationship_type: Mapped[str] = mapped_column(String(32))
    __table_args__ = (
        CheckConstraint(
            "relationship_type IN ('PART_OF', 'RELATED_TO', 'REQUIRES')",
            name="ck_skill_relationships_type",
        ),
        CheckConstraint(
            "parent_skill_id <> child_skill_id", name="ck_skill_relationships_distinct"
        ),
        UniqueConstraint(
            "taxonomy_version_id",
            "parent_skill_id",
            "child_skill_id",
            "relationship_type",
            name="uq_skill_relationships_edge",
        ),
    )


class SnapshotNormalization(Base):
    __tablename__ = "snapshot_normalizations"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("job_snapshots.id", ondelete="CASCADE"))
    taxonomy_version_id: Mapped[UUID] = mapped_column(ForeignKey("taxonomy_versions.id"))
    method: Mapped[str] = mapped_column(String(64))
    processor_version: Mapped[str] = mapped_column(String(64))
    normalization_version: Mapped[str] = mapped_column(String(64))
    extraction_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    role: Mapped[str | None] = mapped_column(String(128))
    role_status: Mapped[str] = mapped_column(String(32))
    seniority: Mapped[str | None] = mapped_column(String(64))
    seniority_status: Mapped[str] = mapped_column(String(32))
    location_original: Mapped[str | None] = mapped_column(String(512))
    location_city: Mapped[str | None] = mapped_column(String(256))
    location_region: Mapped[str | None] = mapped_column(String(256))
    location_country: Mapped[str | None] = mapped_column(String(256))
    work_arrangement: Mapped[str | None] = mapped_column(String(32))
    location_status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint(
            "status IN ('SUCCEEDED', 'PARTIAL', 'FAILED')",
            name="ck_snapshot_normalizations_status",
        ),
        CheckConstraint(
            "role_status IN ('matched', 'ambiguous', 'unknown')",
            name="ck_snapshot_normalizations_role_status",
        ),
        CheckConstraint(
            "seniority_status IN ('matched', 'ambiguous', 'unknown')",
            name="ck_snapshot_normalizations_seniority_status",
        ),
        CheckConstraint(
            "location_status IN ('matched', 'ambiguous', 'unknown')",
            name="ck_snapshot_normalizations_location_status",
        ),
        UniqueConstraint("id", "taxonomy_version_id", name="uq_normalizations_id_version"),
        UniqueConstraint(
            "snapshot_id",
            "taxonomy_version_id",
            "method",
            "processor_version",
            "normalization_version",
            "extraction_version",
            name="uq_snapshot_normalizations_result",
        ),
        Index("ix_snapshot_normalizations_snapshot", "snapshot_id", "created_at"),
    )


class SkillCandidate(Base):
    __tablename__ = "skill_candidates"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    normalization_id: Mapped[UUID] = mapped_column(
        ForeignKey("snapshot_normalizations.id", ondelete="CASCADE")
    )
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("job_snapshots.id", ondelete="CASCADE"))
    taxonomy_version_id: Mapped[UUID]
    skill_id: Mapped[UUID]
    source_field: Mapped[str] = mapped_column(String(32))
    evidence_start: Mapped[int]
    evidence_end: Mapped[int]
    matched_alias: Mapped[str] = mapped_column(String(256))
    reason: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    extractor_version: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        ForeignKeyConstraint(
            ["skill_id", "taxonomy_version_id"],
            ["taxonomy_skill_versions.skill_id", "taxonomy_skill_versions.taxonomy_version_id"],
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')", name="ck_skill_candidates_status"
        ),
        UniqueConstraint(
            "normalization_id",
            "skill_id",
            "source_field",
            "evidence_start",
            "evidence_end",
            name="uq_skill_candidates_evidence",
        ),
    )


class JobSkill(Base):
    __tablename__ = "job_skills"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    normalization_id: Mapped[UUID]
    skill_id: Mapped[UUID]
    taxonomy_version_id: Mapped[UUID]
    source_field: Mapped[str] = mapped_column(String(32))
    evidence_start: Mapped[int]
    evidence_end: Mapped[int]
    matched_alias: Mapped[str] = mapped_column(String(256))
    method: Mapped[str] = mapped_column(String(64))
    extractor_version: Mapped[str] = mapped_column(String(64))
    reviewed_state: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    __table_args__ = (
        ForeignKeyConstraint(
            ["normalization_id", "taxonomy_version_id"],
            ["snapshot_normalizations.id", "snapshot_normalizations.taxonomy_version_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["skill_id", "taxonomy_version_id"],
            ["taxonomy_skill_versions.skill_id", "taxonomy_skill_versions.taxonomy_version_id"],
        ),
        CheckConstraint(
            "source_field IN ('title', 'description', 'requirements')",
            name="ck_job_skills_source_field",
        ),
        CheckConstraint("evidence_start >= 0", name="ck_job_skills_evidence_start"),
        CheckConstraint("evidence_end > evidence_start", name="ck_job_skills_evidence_span"),
        CheckConstraint(
            "reviewed_state IN ('accepted', 'rejected', 'pending')",
            name="ck_job_skills_reviewed_state",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_job_skills_confidence"),
        UniqueConstraint(
            "normalization_id",
            "skill_id",
            "source_field",
            "evidence_start",
            "evidence_end",
            name="uq_job_skills_evidence",
        ),
        Index("ix_job_skills_skill", "skill_id"),
        Index("ix_job_skills_evidence", "normalization_id", "source_field", "evidence_start"),
    )
