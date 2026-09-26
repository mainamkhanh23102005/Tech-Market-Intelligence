"""M3 deterministic analytics schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_m3_analytics"
down_revision: str | None = "0002_m2_normalization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_job_snapshots_id_job", "job_snapshots", ["id", "job_id"])
    op.create_table(
        "metric_definitions",
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("denominator", sa.Text(), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("key", "version"),
    )
    op.create_table(
        "corpus_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("membership_hash", sa.String(64), nullable=False),
        sa.Column("job_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("job_count >= 0", name="ck_corpus_snapshots_job_count"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_cutoff", "membership_hash", name="uq_corpus_snapshot_identity"),
    )
    op.create_table(
        "corpus_snapshot_members",
        sa.Column("corpus_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["corpus_snapshot_id"], ["corpus_snapshots.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(
            ["job_snapshot_id", "job_id"], ["job_snapshots.id", "job_snapshots.job_id"]
        ),
        sa.PrimaryKeyConstraint("corpus_snapshot_id", "job_id"),
        sa.UniqueConstraint(
            "corpus_snapshot_id", "job_snapshot_id", name="uq_corpus_member_snapshot"
        ),
    )
    op.create_index("ix_corpus_members_snapshot", "corpus_snapshot_members", ["job_snapshot_id"])
    op.create_table(
        "analytics_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("corpus_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_version", sa.String(64), nullable=False),
        sa.Column("taxonomy_version", sa.String(64), nullable=False),
        sa.Column("normalization_version", sa.String(64), nullable=False),
        sa.Column("extraction_version", sa.String(64), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'FAILED')", name="ck_analytics_runs_status"
        ),
        sa.ForeignKeyConstraint(["corpus_snapshot_id"], ["corpus_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "analytics_run_members",
        sa.Column("analytics_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("normalization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("normalization_status", sa.String(32), nullable=False),
        sa.Column("normalization_method", sa.String(64), nullable=True),
        sa.Column("processor_version", sa.String(64), nullable=True),
        sa.Column("role", sa.String(128), nullable=True),
        sa.Column("seniority", sa.String(128), nullable=True),
        sa.Column("location", sa.String(256), nullable=True),
        sa.Column("work_arrangement", sa.String(64), nullable=True),
        sa.Column("skills", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["analytics_run_id"], ["analytics_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(
            ["job_snapshot_id", "job_id"], ["job_snapshots.id", "job_snapshots.job_id"]
        ),
        sa.PrimaryKeyConstraint("analytics_run_id", "job_id"),
    )
    op.create_index(
        "ix_analytics_run_members_snapshot", "analytics_run_members", ["job_snapshot_id"]
    )
    op.create_table(
        "market_statistics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analytics_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_key", sa.String(128), nullable=False),
        sa.Column("metric_version", sa.String(64), nullable=False),
        sa.Column("value", sa.Numeric(20, 10), nullable=False),
        sa.Column("numerator", sa.Integer(), nullable=False),
        sa.Column("denominator", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(), nullable=False),
        sa.Column("coverage_warning", sa.Text(), nullable=True),
        sa.Column("evidence_snapshot_ids", postgresql.JSONB(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("numerator >= 0", name="ck_market_statistics_numerator"),
        sa.CheckConstraint("denominator > 0", name="ck_market_statistics_denominator"),
        sa.CheckConstraint("numerator <= denominator", name="ck_market_statistics_cardinality"),
        sa.CheckConstraint("value >= 0 AND value <= 1", name="ck_market_statistics_value"),
        sa.CheckConstraint(
            "value = ROUND(numerator::numeric / denominator, 10)",
            name="ck_market_statistics_ratio",
        ),
        sa.ForeignKeyConstraint(["analytics_run_id"], ["analytics_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["metric_key", "metric_version"],
            ["metric_definitions.key", "metric_definitions.version"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_market_statistics_metric_dimensions",
        "market_statistics",
        ["metric_key", "metric_version"],
        postgresql_include=["dimensions"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_statistics_metric_dimensions", table_name="market_statistics")
    op.drop_table("market_statistics")
    op.drop_index("ix_analytics_run_members_snapshot", table_name="analytics_run_members")
    op.drop_table("analytics_run_members")
    op.drop_table("analytics_runs")
    op.drop_index("ix_corpus_members_snapshot", table_name="corpus_snapshot_members")
    op.drop_table("corpus_snapshot_members")
    op.drop_table("corpus_snapshots")
    op.drop_table("metric_definitions")
    op.drop_constraint("uq_job_snapshots_id_job", "job_snapshots", type_="unique")
