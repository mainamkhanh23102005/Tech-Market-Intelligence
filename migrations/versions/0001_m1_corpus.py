"""M1 canonical corpus schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_m1_corpus"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("namespace", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("namespace"),
    )
    op.create_table(
        "source_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('approved', 'rejected', 'review_required')",
            name="ck_source_permissions_status",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "manifest", name="uq_source_permissions_manifest"),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input_name", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("accepted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'COMPLETED_WITH_FAILURES')",
            name="ck_ingestion_runs_status",
        ),
        sa.CheckConstraint("accepted_count >= 0", name="ck_ingestion_runs_accepted_count"),
        sa.CheckConstraint("duplicate_count >= 0", name="ck_ingestion_runs_duplicate_count"),
        sa.CheckConstraint("failure_count >= 0", name="ck_ingestion_runs_failure_count"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "raw_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_raw_records_content_hash"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "content_hash", name="uq_raw_records_source_hash"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_posting_id", sa.String(length=512), nullable=True),
        sa.Column("canonical_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source_posting_id IS NOT NULL OR canonical_url IS NOT NULL", name="ck_jobs_identity"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "job_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("processor_version", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("company", sa.String(length=512), nullable=False),
        sa.Column("location", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_job_snapshots_content_hash"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["raw_record_id"], ["raw_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id", "content_hash", "processor_version", name="uq_job_snapshots_version"
        ),
    )
    op.create_index("ix_job_snapshots_job_observed", "job_snapshots", ["job_id", "observed_at"])
    op.create_table(
        "processing_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_number", sa.Integer(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw_hash", sa.String(length=64), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("processor_version", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("record_number >= 0", name="ck_processing_attempts_record_number"),
        sa.CheckConstraint(
            "state IN ('DISCOVERED', 'RAW_STORED', 'PARSED', 'NORMALIZED', 'READY', "
            "'FAILED_RETRYABLE', 'FAILED_TERMINAL')",
            name="ck_processing_attempts_state",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["ingestion_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_processing_attempts_run_record", "processing_attempts", ["run_id", "record_number"]
    )
    op.create_table(
        "processing_failures",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("error_type", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["attempt_id"], ["processing_attempts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id"),
    )


def downgrade() -> None:
    op.drop_table("processing_failures")
    op.drop_index("ix_processing_attempts_run_record", table_name="processing_attempts")
    op.drop_table("processing_attempts")
    op.drop_index("ix_job_snapshots_job_observed", table_name="job_snapshots")
    op.drop_table("job_snapshots")
    op.drop_table("jobs")
    op.drop_table("raw_records")
    op.drop_table("ingestion_runs")
    op.drop_table("source_permissions")
    op.drop_table("sources")
