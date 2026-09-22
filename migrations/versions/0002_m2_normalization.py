"""M2 normalization and skill intelligence schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_m2_normalization"
down_revision: str | None = "0001_m1_corpus"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    statuses = "('matched', 'ambiguous', 'unknown')"
    op.create_table(
        "taxonomy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'RETIRED')", name="ck_taxonomy_versions_status"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version", name="uq_taxonomy_versions_version"),
    )
    op.create_table(
        "skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_skills_key"),
    )
    op.create_table(
        "taxonomy_skill_versions",
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("valid_from", sa.String(length=64), nullable=True),
        sa.Column("valid_to", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'deprecated', 'retired')", name="ck_skill_versions_status"
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["taxonomy_version_id"], ["taxonomy_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("skill_id", "taxonomy_version_id"),
    )
    op.create_index(
        "ix_skill_versions_name", "taxonomy_skill_versions", ["taxonomy_version_id", "name"]
    )
    op.create_table(
        "skill_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias", sa.String(length=256), nullable=False),
        sa.Column("normalized_alias", sa.String(length=256), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("matching_mode", sa.String(length=32), nullable=False),
        sa.Column("case_sensitive", sa.Boolean(), nullable=False),
        sa.Column("boundary_rule", sa.String(length=32), nullable=False),
        sa.Column("ambiguity_status", sa.String(length=32), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["skill_id", "taxonomy_version_id"],
            ["taxonomy_skill_versions.skill_id", "taxonomy_skill_versions.taxonomy_version_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "skill_id", "taxonomy_version_id", "alias", name="uq_skill_aliases_skill_version_alias"
        ),
    )
    op.create_index("ix_skill_aliases_alias", "skill_aliases", ["alias"])
    op.create_table(
        "skill_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("child_skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "relationship_type IN ('PART_OF', 'RELATED_TO', 'REQUIRES')",
            name="ck_skill_relationships_type",
        ),
        sa.CheckConstraint(
            "parent_skill_id <> child_skill_id", name="ck_skill_relationships_distinct"
        ),
        sa.ForeignKeyConstraint(["taxonomy_version_id"], ["taxonomy_versions.id"]),
        sa.ForeignKeyConstraint(["parent_skill_id"], ["skills.id"]),
        sa.ForeignKeyConstraint(["child_skill_id"], ["skills.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "taxonomy_version_id",
            "parent_skill_id",
            "child_skill_id",
            "relationship_type",
            name="uq_skill_relationships_edge",
        ),
    )
    op.create_table(
        "snapshot_normalizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("processor_version", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column("extraction_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=128), nullable=True),
        sa.Column("role_status", sa.String(length=32), nullable=False),
        sa.Column("seniority", sa.String(length=64), nullable=True),
        sa.Column("seniority_status", sa.String(length=32), nullable=False),
        sa.Column("location_original", sa.String(length=512), nullable=True),
        sa.Column("location_city", sa.String(length=256), nullable=True),
        sa.Column("location_region", sa.String(length=256), nullable=True),
        sa.Column("location_country", sa.String(length=256), nullable=True),
        sa.Column("work_arrangement", sa.String(length=32), nullable=True),
        sa.Column("location_status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED', 'PARTIAL', 'FAILED')", name="ck_snapshot_normalizations_status"
        ),
        sa.CheckConstraint(
            f"role_status IN {statuses}", name="ck_snapshot_normalizations_role_status"
        ),
        sa.CheckConstraint(
            f"seniority_status IN {statuses}", name="ck_snapshot_normalizations_seniority_status"
        ),
        sa.CheckConstraint(
            f"location_status IN {statuses}", name="ck_snapshot_normalizations_location_status"
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["job_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["taxonomy_version_id"], ["taxonomy_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "taxonomy_version_id", name="uq_normalizations_id_version"),
        sa.UniqueConstraint(
            "snapshot_id",
            "taxonomy_version_id",
            "method",
            "processor_version",
            "normalization_version",
            "extraction_version",
            name="uq_snapshot_normalizations_result",
        ),
    )
    op.create_index(
        "ix_snapshot_normalizations_snapshot",
        "snapshot_normalizations",
        ["snapshot_id", "created_at"],
    )
    op.create_table(
        "job_skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("normalization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_field", sa.String(length=32), nullable=False),
        sa.Column("evidence_start", sa.Integer(), nullable=False),
        sa.Column("evidence_end", sa.Integer(), nullable=False),
        sa.Column("matched_alias", sa.String(length=256), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("reviewed_state", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "source_field IN ('title', 'description', 'requirements')",
            name="ck_job_skills_source_field",
        ),
        sa.CheckConstraint("evidence_start >= 0", name="ck_job_skills_evidence_start"),
        sa.CheckConstraint("evidence_end > evidence_start", name="ck_job_skills_evidence_span"),
        sa.CheckConstraint(
            "reviewed_state IN ('accepted', 'rejected', 'pending')",
            name="ck_job_skills_reviewed_state",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_job_skills_confidence"),
        sa.ForeignKeyConstraint(
            ["normalization_id", "taxonomy_version_id"],
            ["snapshot_normalizations.id", "snapshot_normalizations.taxonomy_version_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id", "taxonomy_version_id"],
            ["taxonomy_skill_versions.skill_id", "taxonomy_skill_versions.taxonomy_version_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalization_id",
            "skill_id",
            "source_field",
            "evidence_start",
            "evidence_end",
            name="uq_job_skills_evidence",
        ),
    )
    op.create_index("ix_job_skills_skill", "job_skills", ["skill_id"])
    op.create_index(
        "ix_job_skills_evidence",
        "job_skills",
        ["normalization_id", "source_field", "evidence_start"],
    )
    op.create_table(
        "skill_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("normalization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_field", sa.String(length=32), nullable=False),
        sa.Column("evidence_start", sa.Integer(), nullable=False),
        sa.Column("evidence_end", sa.Integer(), nullable=False),
        sa.Column("matched_alias", sa.String(length=256), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')", name="ck_skill_candidates_status"
        ),
        sa.ForeignKeyConstraint(
            ["normalization_id"], ["snapshot_normalizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["job_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["skill_id", "taxonomy_version_id"],
            ["taxonomy_skill_versions.skill_id", "taxonomy_skill_versions.taxonomy_version_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalization_id",
            "skill_id",
            "source_field",
            "evidence_start",
            "evidence_end",
            name="uq_skill_candidates_evidence",
        ),
    )


def downgrade() -> None:
    op.drop_table("skill_candidates")
    op.drop_index("ix_job_skills_evidence", table_name="job_skills")
    op.drop_index("ix_job_skills_skill", table_name="job_skills")
    op.drop_table("job_skills")
    op.drop_index("ix_snapshot_normalizations_snapshot", table_name="snapshot_normalizations")
    op.drop_table("snapshot_normalizations")
    op.drop_table("skill_relationships")
    op.drop_index("ix_skill_aliases_alias", table_name="skill_aliases")
    op.drop_table("skill_aliases")
    op.drop_index("ix_skill_versions_name", table_name="taxonomy_skill_versions")
    op.drop_table("taxonomy_skill_versions")
    op.drop_table("skills")
    op.drop_table("taxonomy_versions")
