import os
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, insert, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from tech_market_backend.platform.database import create_database_engine, session_factory
from tech_market_backend.platform.models import (
    Job,
    JobSkill,
    JobSnapshot,
    RawRecord,
    Skill,
    SkillAlias,
    SnapshotNormalization,
    Source,
    TaxonomySkillVersion,
    TaxonomyVersion,
)
from tech_market_backend.taxonomy.catalog import SKILLS
from tech_market_backend.taxonomy.persistence import TaxonomyPersistence
from tech_market_backend.taxonomy.service import TaxonomyService
from tech_market_backend.taxonomy.versions import (
    CATALOG_VERSION,
    EXTRACTION_VERSION,
    NORMALIZATION_VERSION,
)

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.integration


def _test_database_url() -> str:
    if not DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")
    database = make_url(DATABASE_URL).database
    if database is None or "test" not in database.casefold():
        pytest.fail("TEST_DATABASE_URL database name must contain 'test'")
    return DATABASE_URL


@pytest.fixture()
def migrated_database() -> tuple[Engine, sessionmaker[Session]]:
    database_url = _test_database_url()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_database_engine(database_url)
    yield engine, session_factory(engine)
    engine.dispose()


def _m1_row(sessions: sessionmaker[Session]) -> UUID:
    source_id, raw_id, job_id, snapshot_id = (uuid4() for _ in range(4))
    now = datetime.now(UTC)
    with sessions.begin() as session:
        session.execute(
            insert(Source).values(id=source_id, namespace=f"source-{source_id}", name="Source")
        )
        session.execute(
            insert(RawRecord).values(
                id=raw_id,
                source_id=source_id,
                content_hash="a" * 64,
                payload={"representative": True},
                observed_at=now,
            )
        )
        session.execute(
            insert(Job).values(id=job_id, source_id=source_id, source_posting_id="m1-row")
        )
        session.execute(
            insert(JobSnapshot).values(
                id=snapshot_id,
                job_id=job_id,
                raw_record_id=raw_id,
                content_hash="a" * 64,
                processor_version="m1-v1",
                title="Senior Python Backend Engineer",
                company="Example",
                location="Hybrid - London, UK",
                description="Build FastAPI and Node.js services with PostgreSQL and Python",
                observed_at=now,
            )
        )
    return snapshot_id


def test_empty_database_upgrades_to_head(migrated_database) -> None:
    engine, _ = migrated_database
    assert {
        "taxonomy_versions",
        "skills",
        "skill_aliases",
        "snapshot_normalizations",
        "job_skills",
    } <= set(inspect(engine).get_table_names())


def test_m1_to_m2_preserves_m1_row() -> None:
    database_url = _test_database_url()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "0001_m1_corpus")
    engine = create_database_engine(database_url)
    sessions = session_factory(engine)
    snapshot_id = _m1_row(sessions)
    command.upgrade(config, "0002_m2_normalization")
    with sessions() as session:
        assert session.get(JobSnapshot, snapshot_id) is not None
    engine.dispose()


def test_real_taxonomy_pipeline_persists_complete_idempotent_result(
    migrated_database,
) -> None:
    _, sessions = migrated_database
    snapshot_id = _m1_row(sessions)
    service = TaxonomyService(sessions)
    first = service.normalize_snapshot(snapshot_id)
    second = service.normalize_snapshot(snapshot_id)
    assert first == second
    with sessions() as session:
        result = session.get(SnapshotNormalization, first.normalization_id)
        assert result is not None
        assert (result.role, result.role_status) == ("backend_engineer", "matched")
        assert (result.seniority, result.seniority_status) == ("senior", "matched")
        assert (
            result.location_original,
            result.location_city,
            result.location_country,
            result.work_arrangement,
            result.location_status,
        ) == ("Hybrid - London, UK", "London", "United Kingdom", "hybrid", "matched")
        assert result.method == "deterministic"
        assert result.processor_version == "m2-v1"
        assert result.normalization_version == NORMALIZATION_VERSION
        assert result.extraction_version == EXTRACTION_VERSION
        assert result.status == "SUCCEEDED"
        assert session.scalar(select(func.count()).select_from(TaxonomyVersion)) == 1
        assert session.scalar(select(func.count()).select_from(Skill)) == len(SKILLS)
        assert session.scalar(select(func.count()).select_from(SkillAlias)) == sum(
            len(skill.aliases) for skill in SKILLS
        )
        assert (
            session.scalar(
                select(TaxonomySkillVersion.category)
                .join(Skill, TaxonomySkillVersion.skill_id == Skill.id)
                .where(Skill.key == "python")
            )
            == "language"
        )
        assert (
            session.scalar(select(SkillAlias.normalized_alias).where(SkillAlias.alias == "C Sharp"))
            == "c sharp"
        )
        evidence = session.execute(
            select(
                JobSkill.source_field,
                JobSkill.matched_alias,
                Skill.key,
                JobSkill.method,
                JobSkill.reviewed_state,
                JobSkill.confidence,
            )
            .join(Skill, JobSkill.skill_id == Skill.id)
            .where(JobSkill.normalization_id == first.normalization_id)
            .order_by(JobSkill.source_field, JobSkill.evidence_start)
        ).all()
        assert ("title", "Python", "python", "alias", "accepted", 1.0) in evidence
        assert ("description", "FastAPI", "fastapi", "alias", "accepted", 1.0) in evidence
        assert ("description", "Node.js", "nodejs", "regex", "accepted", 1.0) in evidence
        assert all(row[0] in {"title", "description"} for row in evidence)


@pytest.mark.parametrize("version", ["NORMALIZATION_VERSION", "EXTRACTION_VERSION"])
def test_version_change_creates_distinct_normalization(
    migrated_database, monkeypatch, version
) -> None:
    _, sessions = migrated_database
    snapshot_id = _m1_row(sessions)
    service = TaxonomyService(sessions)
    first = service.normalize_snapshot(snapshot_id)
    monkeypatch.setattr(f"tech_market_backend.taxonomy.service.{version}", "next-version")
    second = service.normalize_snapshot(snapshot_id)
    assert first.normalization_id != second.normalization_id
    assert service.normalize_snapshot(snapshot_id) == second
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(SnapshotNormalization)) == 2


def test_taxonomy_version_rejects_changed_content(migrated_database) -> None:
    _, sessions = migrated_database
    persistence = TaxonomyPersistence(sessions)
    persistence.seed(CATALOG_VERSION, SKILLS)
    changed = (replace(SKILLS[0], name="Changed Python"), *SKILLS[1:])
    with pytest.raises(ValueError, match="already has different content"):
        persistence.seed(CATALOG_VERSION, changed)


def test_constraints_and_foreign_keys_are_enforced(migrated_database) -> None:
    _, sessions = migrated_database
    snapshot_id = _m1_row(sessions)
    version_id = TaxonomyPersistence(sessions).seed(CATALOG_VERSION, SKILLS)
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(
            SnapshotNormalization(
                id=uuid4(),
                snapshot_id=snapshot_id,
                taxonomy_version_id=version_id,
                method="deterministic",
                processor_version="bad",
                normalization_version="v1",
                extraction_version="v1",
                status="INVALID",
                role_status="unknown",
                seniority_status="unknown",
                location_status="unknown",
            )
        )
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(
            JobSkill(
                id=uuid4(),
                normalization_id=uuid4(),
                skill_id=uuid4(),
                taxonomy_version_id=version_id,
                source_field="title",
                evidence_start=2,
                evidence_end=2,
                matched_alias="",
                method="alias",
                extractor_version="v1",
            )
        )
