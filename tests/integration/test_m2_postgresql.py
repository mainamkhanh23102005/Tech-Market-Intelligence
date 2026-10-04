import base64
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, insert, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from tech_market_api import create_app
from tech_market_api.market import MarketNotFoundError, get_market_reader
from tech_market_api.postgres_reader import PostgresMarketReader
from tech_market_backend.analytics.engine import AnalyticsEngine, GoldenJob, Statistic
from tech_market_backend.analytics.persistence import AnalyticsPersistence
from tech_market_backend.analytics.registry import METRICS
from tech_market_backend.platform.database import create_database_engine, session_factory
from tech_market_backend.platform.models import (
    AnalyticsRun,
    AnalyticsRunMember,
    CorpusSnapshot,
    CorpusSnapshotMember,
    Job,
    JobSkill,
    JobSnapshot,
    MarketStatistic,
    MetricDefinitionRecord,
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
    return _job_row(
        sessions,
        title="Senior Python Backend Engineer",
        description="Build FastAPI and Node.js services with PostgreSQL and Python",
        location="Hybrid - London, UK",
    )


def _job_row(
    sessions: sessionmaker[Session],
    *,
    title: str,
    description: str,
    location: str = "Remote",
) -> UUID:
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
            insert(Job).values(id=job_id, source_id=source_id, source_posting_id=str(job_id))
        )
        session.execute(
            insert(JobSnapshot).values(
                id=snapshot_id,
                job_id=job_id,
                raw_record_id=raw_id,
                content_hash="a" * 64,
                processor_version="m1-v1",
                title=title,
                company="Example",
                location=location,
                description=description,
                observed_at=now,
            )
        )
    return snapshot_id


def _versions() -> dict[str, str]:
    return {
        "taxonomy": CATALOG_VERSION,
        "normalization": NORMALIZATION_VERSION,
        "extraction": EXTRACTION_VERSION,
    }


def _multi_role_corpus(sessions: sessionmaker[Session]) -> list[UUID]:
    snapshots = [
        _job_row(
            sessions,
            title="Senior Python Backend Engineer",
            description="Build FastAPI and Node.js services with PostgreSQL and Python",
            location="Hybrid - London, UK",
        ),
        _job_row(
            sessions,
            title="Senior Data Engineer",
            description="Create Python SQL pipelines using Airflow PostgreSQL and AWS",
            location="Hanoi, Vietnam",
        ),
        _job_row(
            sessions,
            title="Platform Engineer",
            description="Run AWS Kubernetes Docker PostgreSQL infrastructure",
            location="Remote",
        ),
    ]
    service = TaxonomyService(sessions)
    for snapshot_id in snapshots:
        service.normalize_snapshot(snapshot_id)
    return snapshots


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
    command.upgrade(config, "0003_m3_analytics")
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


def test_m3_publication_is_complete_deterministic_and_provenance_resolves(
    migrated_database,
) -> None:
    _, sessions = migrated_database
    snapshot_id = _m1_row(sessions)
    TaxonomyService(sessions).normalize_snapshot(snapshot_id)
    cutoff = datetime.now(UTC)
    versions = {
        "taxonomy": CATALOG_VERSION,
        "normalization": NORMALIZATION_VERSION,
        "extraction": EXTRACTION_VERSION,
    }
    persistence = AnalyticsPersistence(sessions)
    first = persistence.publish(cutoff, versions)
    second = persistence.publish(cutoff, versions)
    assert first == second
    with sessions() as session:
        run = session.get(AnalyticsRun, first)
        assert run is not None
        assert run.status == "SUCCEEDED"
        assert run.result_hash is not None
        corpus = session.get(CorpusSnapshot, run.corpus_snapshot_id)
        assert corpus is not None
        assert corpus.job_count == 1
        member = session.scalar(
            select(CorpusSnapshotMember).where(CorpusSnapshotMember.corpus_snapshot_id == corpus.id)
        )
        assert member is not None
        assert member.job_snapshot_id == snapshot_id
        definitions = set(
            session.execute(
                select(MetricDefinitionRecord.key, MetricDefinitionRecord.version)
            ).all()
        )
        assert definitions == {(metric.key, metric.version) for metric in METRICS.values()}
        statistics = list(
            session.scalars(
                select(MarketStatistic).where(MarketStatistic.analytics_run_id == first)
            )
        )
        assert statistics
        python = next(row for row in statistics if row.dimensions.get("skill") == "python")
        assert (python.numerator, python.denominator) == (1, 1)
        assert python.evidence_snapshot_ids == [str(snapshot_id)]
    reader = PostgresMarketReader(sessions)
    market = reader.market("skill_prevalence", corpus.id, first, None, 20)
    jobs = reader.jobs(corpus.id, None, 20)
    evidence = reader.evidence(corpus.id, snapshot_id)
    assert market.data[0].snapshot == str(corpus.id)
    assert market.data[0].versions.taxonomy == CATALOG_VERSION
    assert jobs.data[0].snapshot_id == str(snapshot_id)
    assert evidence.raw_record_hash == "a" * 64


def test_m4_structured_search_is_snapshot_pinned_and_cursor_scope_bound(migrated_database) -> None:
    _, sessions = migrated_database
    snapshot_ids = [
        _job_row(sessions, title="Backend Engineer", description="A", location="Remote"),
        _job_row(sessions, title="Backend Engineer", description="B", location="Remote"),
        _job_row(sessions, title="Data Engineer", description="C", location="Hanoi"),
    ]
    for snapshot_id in snapshot_ids[:2]:
        TaxonomyService(sessions).normalize_snapshot(snapshot_id)
    cutoff = datetime.now(UTC)
    run_id = AnalyticsPersistence(sessions).publish(cutoff, _versions())
    with sessions() as session:
        run = session.get(AnalyticsRun, run_id)
        assert run is not None
        corpus_id = run.corpus_snapshot_id
    reader = PostgresMarketReader(sessions)
    first = reader.search_jobs(
        corpus_id,
        run_id,
        query=None,
        role="backend_engineer",
        seniority=None,
        location=None,
        skills=[],
        observed_from=None,
        observed_to=None,
        cursor=None,
        limit=1,
    )
    assert len(first.data) == 1
    assert first.page.has_more
    assert first.data[0].evidence_url.endswith(f"?snapshot={corpus_id}")
    second = reader.search_jobs(
        corpus_id,
        run_id,
        query=None,
        role="backend_engineer",
        seniority=None,
        location=None,
        skills=[],
        observed_from=None,
        observed_to=None,
        cursor=first.page.next_cursor,
        limit=1,
    )
    assert len(second.data) == 1
    assert second.data[0].snapshot_id != first.data[0].snapshot_id
    with pytest.raises(MarketNotFoundError, match="Search cursor is invalid"):
        reader.search_jobs(
            corpus_id,
            run_id,
            query=None,
            role="data_engineer",
            seniority=None,
            location=None,
            skills=[],
            observed_from=None,
            observed_to=None,
            cursor=first.page.next_cursor,
            limit=1,
        )
    _job_row(
        sessions,
        title="Platform Engineer",
        description="New posting for foreign corpus",
        location="Remote",
    )
    foreign_corpus = AnalyticsPersistence(sessions).create_corpus_snapshot(datetime.now(UTC))
    assert foreign_corpus != corpus_id
    with pytest.raises(MarketNotFoundError, match="Search cursor is invalid"):
        reader.search_jobs(
            foreign_corpus,
            run_id,
            query=None,
            role="backend_engineer",
            seniority=None,
            location=None,
            skills=[],
            observed_from=None,
            observed_to=None,
            cursor=first.page.next_cursor,
            limit=1,
        )


def test_m4_keyset_pagination_is_stable_when_observed_at_ties(migrated_database) -> None:
    from datetime import timedelta

    from tech_market_backend.platform.models import JobSnapshot

    _, sessions = migrated_database
    snapshot_ids = [
        _job_row(
            sessions,
            title="Backend Engineer",
            description="Tie A",
            location="Remote",
        ),
        _job_row(
            sessions,
            title="Backend Engineer",
            description="Tie B",
            location="Remote",
        ),
        _job_row(
            sessions,
            title="Backend Engineer",
            description="Tie C",
            location="Remote",
        ),
    ]

    tied_observed_at = datetime.now(UTC)
    with sessions() as session:
        for snapshot_id in snapshot_ids:
            snapshot = session.get(JobSnapshot, snapshot_id)
            assert snapshot is not None
            snapshot.observed_at = tied_observed_at
        session.commit()

    for snapshot_id in snapshot_ids:
        TaxonomyService(sessions).normalize_snapshot(snapshot_id)

    run_id = AnalyticsPersistence(sessions).publish(
        tied_observed_at + timedelta(seconds=1),
        _versions(),
    )
    with sessions() as session:
        run = session.get(AnalyticsRun, run_id)
        assert run is not None
        corpus_id = run.corpus_snapshot_id

    reader = PostgresMarketReader(sessions)
    seen: list[UUID] = []
    cursor: str | None = None

    for index in range(3):
        page = reader.search_jobs(
            corpus_id,
            run_id,
            query=None,
            role="backend_engineer",
            seniority=None,
            location=None,
            skills=[],
            observed_from=None,
            observed_to=None,
            cursor=cursor,
            limit=1,
        )
        assert len(page.data) == 1
        seen.append(UUID(str(page.data[0].snapshot_id)))

        if index < 2:
            assert page.page.has_more
            assert page.page.next_cursor is not None

        cursor = page.page.next_cursor

    assert len(set(seen)) == 3
    assert seen == sorted(seen)
    assert not page.page.has_more
    assert page.page.next_cursor is None


def test_m3_result_hash_uses_persisted_canonical_values(migrated_database) -> None:
    _, sessions = migrated_database
    snapshot_id = _m1_row(sessions)
    TaxonomyService(sessions).normalize_snapshot(snapshot_id)
    versions = {
        "taxonomy": CATALOG_VERSION,
        "normalization": NORMALIZATION_VERSION,
        "extraction": EXTRACTION_VERSION,
    }
    run_id = AnalyticsPersistence(sessions).publish(datetime.now(UTC), versions)
    with sessions() as session:
        run = session.get(AnalyticsRun, run_id)
        assert run is not None
        corpus = session.get(CorpusSnapshot, run.corpus_snapshot_id)
        assert corpus is not None
        statistics = list(
            session.scalars(
                select(MarketStatistic).where(MarketStatistic.analytics_run_id == run_id)
            )
        )
    persistence = AnalyticsPersistence(sessions)
    payloads = [
        {
            "metric": row.metric_key,
            "value": str(row.value),
            "numerator": row.numerator,
            "denominator": row.denominator,
            "unit": row.unit,
            "dimensions": row.dimensions,
            "cutoff": corpus.source_cutoff,
            "corpus_snapshot_id": str(corpus.id),
            "versions": {
                "taxonomy": run.taxonomy_version,
                "normalization": run.normalization_version,
                "extraction": run.extraction_version,
                "metric": row.metric_version,
            },
            "warning": row.coverage_warning,
            "evidence": row.evidence_snapshot_ids,
            "metadata": row.metadata_,
        }
        for row in statistics
    ]
    assert persistence.result_hash(payloads) == run.result_hash
    statistic = Statistic(
        Decimal("0.3333333333333"),
        1,
        3,
        "ratio",
        {},
        corpus.source_cutoff,
        str(corpus.id),
        versions,
        None,
        (),
        {},
    )
    equivalent = Statistic(
        Decimal("0.3333333333334"),
        1,
        3,
        "ratio",
        {},
        corpus.source_cutoff,
        str(corpus.id),
        versions,
        None,
        (),
        {},
    )
    visible = Statistic(
        Decimal("0.33333333336"),
        1,
        3,
        "ratio",
        {},
        corpus.source_cutoff,
        str(corpus.id),
        versions,
        None,
        (),
        {},
    )
    first = persistence._statistic_payload(
        "skill_prevalence", statistic, persistence._canonical_value(statistic.value)
    )
    second = persistence._statistic_payload(
        "skill_prevalence", equivalent, persistence._canonical_value(equivalent.value)
    )
    changed = persistence._statistic_payload(
        "skill_prevalence", visible, persistence._canonical_value(visible.value)
    )
    assert persistence._hash(first) == persistence._hash(second)
    assert persistence._hash(first) != persistence._hash(changed)


def test_m3_rejects_unknown_provenance_versions(migrated_database) -> None:
    _, sessions = migrated_database
    snapshot_id = _m1_row(sessions)
    TaxonomyService(sessions).normalize_snapshot(snapshot_id)
    persistence = AnalyticsPersistence(sessions)
    valid = {
        "taxonomy": CATALOG_VERSION,
        "normalization": NORMALIZATION_VERSION,
        "extraction": EXTRACTION_VERSION,
    }
    assert persistence.publish(datetime.now(UTC), valid)
    for key in valid:
        invalid = {**valid, key: "unknown-version"}
        with pytest.raises(ValueError, match=key.split("_")[0]):
            persistence.publish(datetime.now(UTC), invalid)
    for invalid in ({}, {**valid, "taxonomy": ""}):
        with pytest.raises(ValueError, match="exact taxonomy"):
            persistence.publish(datetime.now(UTC), invalid)
    with sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AnalyticsRun)
                .where(AnalyticsRun.status == "SUCCEEDED")
            )
            == 1
        )


def test_m3_selects_latest_normalization_by_created_at_then_id(migrated_database) -> None:
    _, sessions = migrated_database
    snapshot_id = _m1_row(sessions)
    version_id = TaxonomyPersistence(sessions).seed(CATALOG_VERSION, SKILLS)
    older_id = UUID(int=10)
    newer_id = UUID(int=11)
    created_at = datetime(2026, 9, 20, tzinfo=UTC)
    with sessions.begin() as session:
        for normalization_id, role, processor_version in (
            (older_id, "backend_engineer", "m2-tie-a"),
            (newer_id, "data_engineer", "m2-tie-b"),
        ):
            session.add(
                SnapshotNormalization(
                    id=normalization_id,
                    snapshot_id=snapshot_id,
                    taxonomy_version_id=version_id,
                    method="deterministic",
                    processor_version=processor_version,
                    normalization_version=NORMALIZATION_VERSION,
                    extraction_version=EXTRACTION_VERSION,
                    status="SUCCEEDED",
                    role=role,
                    role_status="matched",
                    seniority_status="unknown",
                    location_status="unknown",
                    created_at=created_at,
                )
            )
    persistence = AnalyticsPersistence(sessions)
    corpus_id = persistence.create_corpus_snapshot(datetime.now(UTC))
    rows = persistence._load_rows(
        corpus_id,
        {
            "taxonomy": CATALOG_VERSION,
            "normalization": NORMALIZATION_VERSION,
            "extraction": EXTRACTION_VERSION,
        },
    )
    assert len(rows) == 1
    assert rows[0].role == "data_engineer"


def test_m3_keeps_unnormalized_corpus_members_in_metric_denominators(migrated_database) -> None:
    _, sessions = migrated_database
    normalized_snapshot = _m1_row(sessions)
    _m1_row(sessions)
    TaxonomyService(sessions).normalize_snapshot(normalized_snapshot)
    versions = {
        "taxonomy": CATALOG_VERSION,
        "normalization": NORMALIZATION_VERSION,
        "extraction": EXTRACTION_VERSION,
    }
    run_id = AnalyticsPersistence(sessions).publish(datetime.now(UTC), versions)
    with sessions() as session:
        run = session.get(AnalyticsRun, run_id)
        assert run is not None
        corpus = session.get(CorpusSnapshot, run.corpus_snapshot_id)
        assert corpus is not None
        assert corpus.job_count == 2
        statistics = list(
            session.scalars(
                select(MarketStatistic).where(MarketStatistic.analytics_run_id == run_id)
            )
        )
        python = next(row for row in statistics if row.dimensions.get("skill") == "python")
        assert (python.numerator, python.denominator) == (1, 2)
        unknown = next(
            row
            for row in statistics
            if row.metric_key == "location_distribution"
            and row.dimensions == {"location": "unknown"}
        )
        assert (unknown.numerator, unknown.denominator) == (1, 2)


def test_m3_reader_scopes_evidence_and_job_cursors_to_corpus(migrated_database) -> None:
    _, sessions = migrated_database
    first_snapshot = _m1_row(sessions)
    first_corpus = AnalyticsPersistence(sessions).create_corpus_snapshot(datetime.now(UTC))
    second_snapshot = _m1_row(sessions)
    AnalyticsPersistence(sessions).create_corpus_snapshot(datetime.now(UTC))
    reader = PostgresMarketReader(sessions)
    assert reader.evidence(first_corpus, first_snapshot).raw_record_hash == "a" * 64
    with pytest.raises(Exception, match="Evidence snapshot was not found"):
        reader.evidence(first_corpus, second_snapshot)
    with pytest.raises(Exception, match="Jobs pagination cursor was not found"):
        reader.jobs(first_corpus, second_snapshot, 20)


def test_corpus_membership_rejects_snapshot_from_another_job(migrated_database) -> None:
    _, sessions = migrated_database
    first_snapshot = _m1_row(sessions)
    second_snapshot = _m1_row(sessions)
    cutoff = datetime.now(UTC)
    corpus_id = AnalyticsPersistence(sessions).create_corpus_snapshot(cutoff)
    with sessions() as session:
        first_job = session.get(JobSnapshot, first_snapshot).job_id
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(
            CorpusSnapshotMember(
                corpus_snapshot_id=corpus_id,
                job_id=first_job,
                job_snapshot_id=second_snapshot,
            )
        )


def test_m3_freezes_complete_selected_normalization_input(migrated_database) -> None:
    _, sessions = migrated_database
    snapshot_id = _m1_row(sessions)
    TaxonomyService(sessions).normalize_snapshot(snapshot_id)
    versions = {
        "taxonomy": CATALOG_VERSION,
        "normalization": NORMALIZATION_VERSION,
        "extraction": EXTRACTION_VERSION,
    }
    cutoff = datetime.now(UTC)
    run_id = AnalyticsPersistence(sessions).publish(cutoff, versions)
    with sessions.begin() as session:
        member = session.scalar(
            select(AnalyticsRunMember).where(AnalyticsRunMember.analytics_run_id == run_id)
        )
        assert member is not None
        original_role = member.role
        normalization = session.get(SnapshotNormalization, member.normalization_id)
        assert normalization is not None
        normalization.role = "data_engineer"
    replacement_run_id = AnalyticsPersistence(sessions).publish(cutoff, versions)
    assert replacement_run_id != run_id
    with sessions() as session:
        frozen = session.scalar(
            select(AnalyticsRunMember).where(AnalyticsRunMember.analytics_run_id == run_id)
        )
        assert frozen is not None
        assert frozen.role == original_role
        assert frozen.normalization_id is not None
        assert frozen.normalization_status == "SUCCEEDED"
        assert frozen.skills == sorted(frozen.skills)
        assert frozen.skills


def test_m3_rejects_naive_cutoff_and_unpublished_role_pair(migrated_database) -> None:
    _, sessions = migrated_database
    snapshot_id = _m1_row(sessions)
    TaxonomyService(sessions).normalize_snapshot(snapshot_id)
    versions = {
        "taxonomy": CATALOG_VERSION,
        "normalization": NORMALIZATION_VERSION,
        "extraction": EXTRACTION_VERSION,
    }
    persistence = AnalyticsPersistence(sessions)
    with pytest.raises(ValueError, match="timezone-aware"):
        persistence.publish(datetime.now(), versions)
    run_id = persistence.publish(datetime.now(UTC), versions)
    with sessions() as session:
        run = session.get(AnalyticsRun, run_id)
        assert run is not None
        corpus_id = run.corpus_snapshot_id
    with pytest.raises(Exception, match="Requested role pair was not published"):
        PostgresMarketReader(sessions).market(
            "role_comparison", corpus_id, run_id, None, 20, "backend_engineer", "data_engineer"
        )


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


def test_m3_multi_run_pagination_pins_explicit_run_and_rejects_foreign_cursor(
    migrated_database,
) -> None:
    _, sessions = migrated_database
    _multi_role_corpus(sessions)
    versions = _versions()
    persistence = AnalyticsPersistence(sessions)
    cutoff = datetime.now(UTC)
    run_ab = persistence.publish(cutoff, versions, ("backend_engineer", "data_engineer"))
    reader = PostgresMarketReader(sessions)
    with sessions() as session:
        corpus_id = session.get(AnalyticsRun, run_ab).corpus_snapshot_id
    page_one = reader.market("skill_prevalence", corpus_id, None, None, 1)
    assert page_one.analytics_run_id == str(run_ab)
    assert page_one.page.has_more is True
    cursor = UUID(page_one.page.next_cursor)

    run_cd = persistence.publish(cutoff, versions, ("backend_engineer", "devops_platform_engineer"))
    assert run_ab != run_cd
    with sessions() as session:
        finished = {
            run.id: run.finished_at
            for run in session.scalars(
                select(AnalyticsRun).where(AnalyticsRun.id.in_((run_ab, run_cd)))
            )
        }
    assert finished[run_cd] is not None and finished[run_ab] is not None
    assert finished[run_cd] >= finished[run_ab]
    page_two = reader.market("skill_prevalence", corpus_id, run_ab, cursor, 1)
    assert page_two.analytics_run_id == str(run_ab)
    assert page_two.data
    assert all(item.id != page_one.data[0].id for item in page_two.data)
    implicit = reader.market("skill_prevalence", corpus_id, None, None, 1)
    assert implicit.analytics_run_id == str(run_cd)
    with pytest.raises(Exception, match="cursor"):
        reader.market("skill_prevalence", corpus_id, run_cd, cursor, 1)


def test_m3_coexisting_role_pairs_and_implicit_pair_selection(migrated_database) -> None:
    _, sessions = migrated_database
    _multi_role_corpus(sessions)
    versions = _versions()
    persistence = AnalyticsPersistence(sessions)
    cutoff = datetime.now(UTC)
    run_ab = persistence.publish(cutoff, versions, ("backend_engineer", "data_engineer"))
    run_cd = persistence.publish(cutoff, versions, ("backend_engineer", "devops_platform_engineer"))
    with sessions() as session:
        corpus_id = session.get(AnalyticsRun, run_ab).corpus_snapshot_id
        assert session.get(AnalyticsRun, run_cd).corpus_snapshot_id == corpus_id
        pairs = {
            run.id: run.parameters.get("role_pair")
            for run in session.scalars(
                select(AnalyticsRun).where(AnalyticsRun.id.in_((run_ab, run_cd)))
            )
        }
    assert pairs == {
        run_ab: ["backend_engineer", "data_engineer"],
        run_cd: ["backend_engineer", "devops_platform_engineer"],
    }
    reader = PostgresMarketReader(sessions)
    selected_ab = reader.market(
        "role_comparison", corpus_id, None, None, 20, "backend_engineer", "data_engineer"
    )
    assert selected_ab.analytics_run_id == str(run_ab)
    selected_cd = reader.market(
        "role_comparison",
        corpus_id,
        None,
        None,
        20,
        "backend_engineer",
        "devops_platform_engineer",
    )
    assert selected_cd.analytics_run_id == str(run_cd)
    with pytest.raises(Exception, match="Requested role pair was not published"):
        reader.market(
            "role_comparison", corpus_id, None, None, 20, "data_engineer", "backend_engineer"
        )
    explicit_ab = reader.market(
        "role_comparison", corpus_id, run_ab, None, 20, "backend_engineer", "data_engineer"
    )
    assert explicit_ab.analytics_run_id == str(run_ab)
    with pytest.raises(Exception, match="Requested role pair was not published"):
        reader.market(
            "role_comparison",
            corpus_id,
            run_cd,
            None,
            20,
            "backend_engineer",
            "data_engineer",
        )


def test_m3_statistic_evidence_lineage_is_scoped_to_run_corpus(migrated_database) -> None:
    _, sessions = migrated_database
    _multi_role_corpus(sessions)
    versions = _versions()
    persistence = AnalyticsPersistence(sessions)
    cutoff = datetime.now(UTC)
    run_id = persistence.publish(cutoff, versions, ("backend_engineer", "data_engineer"))
    with sessions() as session:
        run = session.get(AnalyticsRun, run_id)
        assert run is not None
        corpus_id = run.corpus_snapshot_id
        members = {
            str(row.job_snapshot_id)
            for row in session.scalars(
                select(CorpusSnapshotMember).where(
                    CorpusSnapshotMember.corpus_snapshot_id == corpus_id
                )
            )
        }
        run_members = {
            str(row.job_snapshot_id)
            for row in session.scalars(
                select(AnalyticsRunMember).where(AnalyticsRunMember.analytics_run_id == run_id)
            )
        }
    assert members == run_members
    reader = PostgresMarketReader(sessions)
    page = reader.market("skill_prevalence", corpus_id, run_id, None, 50)
    assert page.analytics_run_id == str(run_id)
    assert page.data
    evidence_ids = {evidence for item in page.data for evidence in item.evidence}
    assert evidence_ids
    assert evidence_ids <= members
    for evidence_id in evidence_ids:
        detail = reader.evidence(corpus_id, UUID(evidence_id))
        assert detail.raw_record_hash
    other_cutoff = cutoff.replace(year=cutoff.year - 1)
    other_corpus = persistence.create_corpus_snapshot(other_cutoff)
    with pytest.raises(Exception, match="Evidence snapshot was not found"):
        reader.evidence(other_corpus, UUID(next(iter(evidence_ids))))

    app = create_app()
    app.dependency_overrides[get_market_reader] = lambda: reader
    with TestClient(app) as client:
        market_response = client.get(
            f"/api/v1/market/skill_prevalence?snapshot={corpus_id}&analytics_run_id={run_id}&limit=50"
        )
        assert market_response.status_code == 200
        assert market_response.json()["analytics_run_id"] == str(run_id)
        api_evidence_ids = {
            evidence_id
            for statistic in market_response.json()["data"]
            for evidence_id in statistic["evidence"]
        }
        assert api_evidence_ids == evidence_ids
        for evidence_id in api_evidence_ids:
            detail_response = client.get(f"/api/v1/evidence/{evidence_id}?snapshot={corpus_id}")
            assert detail_response.status_code == 200
            assert detail_response.json()["job"]["snapshot_id"] == evidence_id
            assert detail_response.json()["raw_record_hash"]
        foreign = client.get(
            f"/api/v1/evidence/{next(iter(api_evidence_ids))}?snapshot={other_corpus}"
        )
        assert foreign.status_code == 404
        assert foreign.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_m3_canonical_rounding_matches_postgres_round_half_away(
    migrated_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, sessions = migrated_database
    snapshot_id = _m1_row(sessions)
    TaxonomyService(sessions).normalize_snapshot(snapshot_id)

    def halfway_distribution(self: AnalyticsEngine, rows: list[GoldenJob]) -> list[Statistic]:
        assert len(rows) == 1
        return [
            self._statistic(
                "skill_prevalence",
                1,
                2048,
                {"skill": "halfway", "role": "unknown"},
                (str(snapshot_id),),
            )
        ]

    monkeypatch.setattr(AnalyticsEngine, "skill_distribution", halfway_distribution)
    run_id = AnalyticsPersistence(sessions).publish(datetime.now(UTC), _versions())
    half = Decimal(1) / Decimal(2048)
    negative_half = -half
    canonical = AnalyticsPersistence._canonical_value
    assert canonical(half) == Decimal("0.0004882813")
    assert canonical(negative_half) == Decimal("-0.0004882813")
    with engine.connect() as connection:
        pg_half = connection.execute(
            text("SELECT ROUND(CAST(:value AS numeric), 10)"), {"value": str(half)}
        ).scalar_one()
        pg_negative = connection.execute(
            text("SELECT ROUND(CAST(:value AS numeric), 10)"), {"value": str(negative_half)}
        ).scalar_one()
    assert canonical(half) == Decimal(str(pg_half))
    assert canonical(negative_half) == Decimal(str(pg_negative))
    with sessions() as session:
        persisted = session.scalar(
            select(MarketStatistic).where(
                MarketStatistic.analytics_run_id == run_id,
                MarketStatistic.dimensions["skill"].astext == "halfway",
            )
        )
        published = session.get(AnalyticsRun, run_id)
    assert published is not None and published.status == "SUCCEEDED"
    assert published.result_hash is not None
    assert persisted is not None
    assert (persisted.numerator, persisted.denominator) == (1, 2048)
    assert persisted.value == canonical(half)
    with sessions() as session:
        corpus = session.get(CorpusSnapshot, published.corpus_snapshot_id)
        statistics = list(
            session.scalars(
                select(MarketStatistic).where(MarketStatistic.analytics_run_id == run_id)
            )
        )
    assert corpus is not None
    payloads = [
        {
            "metric": row.metric_key,
            "value": str(row.value),
            "numerator": row.numerator,
            "denominator": row.denominator,
            "unit": row.unit,
            "dimensions": row.dimensions,
            "cutoff": corpus.source_cutoff,
            "corpus_snapshot_id": str(corpus.id),
            "versions": {
                "taxonomy": published.taxonomy_version,
                "normalization": published.normalization_version,
                "extraction": published.extraction_version,
                "metric": row.metric_version,
            },
            "warning": row.coverage_warning,
            "evidence": row.evidence_snapshot_ids,
            "metadata": row.metadata_,
        }
        for row in statistics
    ]
    assert AnalyticsPersistence.result_hash(payloads) == published.result_hash


def test_m3_rejects_metric_definition_content_mismatch(migrated_database) -> None:
    _, sessions = migrated_database
    snapshot_id = _m1_row(sessions)
    TaxonomyService(sessions).normalize_snapshot(snapshot_id)
    persistence = AnalyticsPersistence(sessions)
    cutoff = datetime.now(UTC)
    run_id = persistence.publish(cutoff, _versions())
    assert run_id
    with sessions.begin() as session:
        record = session.get(MetricDefinitionRecord, ("skill_prevalence", "skill-prevalence-1.0.0"))
        assert record is not None
        record.formula = "tampered formula"
    with pytest.raises(ValueError, match="metric definition content mismatch"):
        persistence.publish(cutoff, _versions())
    with sessions() as session:
        record = session.get(MetricDefinitionRecord, ("skill_prevalence", "skill-prevalence-1.0.0"))
        assert record is not None
        assert record.formula == "tampered formula"


def _m42_publish(sessions):
    run_id = AnalyticsPersistence(sessions).publish(datetime.now(UTC), _versions())
    with sessions() as session:
        corpus_id = session.get(AnalyticsRun, run_id).corpus_snapshot_id
    return corpus_id, run_id


def _m42_search(reader, corpus_id, run_id, **overrides):
    options = dict(
        mode="lexical",
        query="cpp",
        role=None,
        seniority=None,
        location=None,
        skills=[],
        observed_from=None,
        observed_to=None,
        cursor=None,
        limit=20,
    )
    options.update(overrides)
    return reader.search_jobs(corpus_id, run_id, **options)


def _m42_cursor(payload):
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def test_m42_all_field_weights_rank_before_time_and_paginate_without_gaps(migrated_database):
    _, sessions = migrated_database
    fields = [
        ("cpp", "neutral", "Example"),
        ("Engineer", "C++", "Example"),
        ("Engineer", "neutral", "cpp"),
        ("Engineer", "cpp", "Example"),
    ]
    ids = []
    now = datetime.now(UTC) - timedelta(days=1)
    for index, (title, description, company) in enumerate(fields):
        snapshot_id = _job_row(sessions, title=title, description=description)
        with sessions.begin() as session:
            snapshot = session.get(JobSnapshot, snapshot_id)
            snapshot.company = company
            snapshot.observed_at = now + timedelta(hours=index)
        TaxonomyService(sessions).normalize_snapshot(snapshot_id)
        ids.append(snapshot_id)
    corpus_id, run_id = _m42_publish(sessions)
    reader = PostgresMarketReader(sessions)
    full = _m42_search(reader, corpus_id, run_id)
    assert [UUID(item.snapshot_id) for item in full.data] == ids
    assert not full.page.has_more and full.page.next_cursor is None
    with sessions() as session:
        member = session.scalar(
            select(AnalyticsRunMember).where(
                AnalyticsRunMember.analytics_run_id == run_id,
                AnalyticsRunMember.job_snapshot_id == ids[1],
            )
        )
        assert member.skills == ["cpp"]
    seen = []
    cursor = None
    for index in range(len(ids)):
        page = _m42_search(reader, corpus_id, run_id, cursor=cursor, limit=1)
        assert len(page.data) == 1
        seen.append(UUID(page.data[0].snapshot_id))
        assert page.page.has_more == (index < len(ids) - 1)
        assert (page.page.next_cursor is not None) == page.page.has_more
        cursor = page.page.next_cursor
    assert seen == ids and len(set(seen)) == len(ids)
    empty = _m42_search(reader, corpus_id, run_id, query="unfindablequartz")
    assert empty.data == []
    assert not empty.page.has_more and empty.page.next_cursor is None


def test_m42_equal_rank_orders_time_then_uuid_on_every_page(migrated_database):
    _, sessions = migrated_database
    now = datetime.now(UTC) - timedelta(days=1)
    ids = [_job_row(sessions, title="cpp", description="neutral") for _ in range(5)]
    times = [now, now, now + timedelta(hours=1), now, now - timedelta(hours=1)]
    with sessions.begin() as session:
        for snapshot_id, observed_at in zip(ids, times, strict=True):
            session.get(JobSnapshot, snapshot_id).observed_at = observed_at
    TaxonomyPersistence(sessions).seed(CATALOG_VERSION, SKILLS)
    corpus_id, run_id = _m42_publish(sessions)
    reader = PostgresMarketReader(sessions)
    expected = [ids[2], *sorted(ids[:2] + [ids[3]]), ids[4]]
    assert [
        UUID(item.snapshot_id) for item in _m42_search(reader, corpus_id, run_id).data
    ] == expected
    for limit in (1, 2, 3):
        seen, cursor = [], None
        for _ in range(len(ids)):
            page = _m42_search(reader, corpus_id, run_id, limit=limit, cursor=cursor)
            seen.extend(UUID(item.snapshot_id) for item in page.data)
            if not page.page.has_more:
                assert page.page.next_cursor is None
                break
            assert len(page.data) == limit and page.page.next_cursor is not None
            cursor = page.page.next_cursor
        else:
            pytest.fail("Lexical pagination did not terminate")
        assert seen == expected and len(set(seen)) == len(ids)


def test_m42_cursor_binds_every_scope_and_validates_anchor(migrated_database):
    _, sessions = migrated_database
    ids = [
        _job_row(
            sessions,
            title="Senior Backend Engineer cpp",
            description="Python AWS",
            location="London, UK",
        )
        for _ in range(3)
    ]
    for snapshot_id in ids:
        TaxonomyService(sessions).normalize_snapshot(snapshot_id)
    data_snapshot = _job_row(sessions, title="Data Engineer", description="neutral")
    TaxonomyService(sessions).normalize_snapshot(data_snapshot)
    corpus_id, run_id = _m42_publish(sessions)
    reader = PostgresMarketReader(sessions)
    first = _m42_search(reader, corpus_id, run_id, limit=1)
    cursor = first.page.next_cursor
    assert cursor is not None
    with sessions() as session:
        cutoff = session.get(CorpusSnapshot, corpus_id).source_cutoff
    second_run = AnalyticsPersistence(sessions).publish(
        cutoff, _versions(), ("backend_engineer", "data_engineer")
    )
    with sessions() as session:
        assert session.get(AnalyticsRun, second_run).corpus_snapshot_id == corpus_id
    assert second_run != run_id
    second_corpus = AnalyticsPersistence(sessions).create_corpus_snapshot(datetime.now(UTC))
    changes = [
        dict(query="CPP"),
        dict(mode="structured"),
        dict(role="backend_engineer"),
        dict(seniority="senior"),
        dict(location="London"),
        dict(skills=["python"]),
        dict(observed_from=datetime(2020, 1, 1, tzinfo=UTC)),
        dict(observed_to=datetime.now(UTC)),
        dict(limit=2),
    ]
    for changeset in changes:
        with pytest.raises(MarketNotFoundError, match="Search cursor is invalid"):
            _m42_search(reader, corpus_id, run_id, cursor=cursor, **{"limit": 1, **changeset})
    for corpus, run in ((corpus_id, second_run), (second_corpus, run_id)):
        with pytest.raises(MarketNotFoundError, match="Search cursor is invalid"):
            _m42_search(reader, corpus, run, cursor=cursor, limit=1)
    foreign = _job_row(sessions, title="cpp", description="outside published corpus")
    nonmatch = _job_row(sessions, title="unrelated", description="neutral")
    TaxonomyService(sessions).normalize_snapshot(nonmatch)
    newer_corpus, newer_run = _m42_publish(sessions)
    newer_page = _m42_search(reader, newer_corpus, newer_run, limit=1)
    payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    with sessions() as session:
        foreign_time = session.get(JobSnapshot, foreign).observed_at.isoformat()
        nonmatch_time = session.get(JobSnapshot, nonmatch).observed_at.isoformat()
    forged = [
        dict(snapshot_id=str(uuid4())),
        dict(snapshot_id="not-uuid"),
        dict(observed_at="not-time"),
        dict(observed_at="2026-01-01T00:00:00"),
        dict(
            observed_at=(
                datetime.fromisoformat(payload["observed_at"]) + timedelta(seconds=1)
            ).isoformat()
        ),
        dict(snapshot_id=str(foreign), observed_at=foreign_time),
    ]
    for change in forged:
        with pytest.raises(MarketNotFoundError, match="Search cursor is invalid"):
            _m42_search(
                reader, corpus_id, run_id, cursor=_m42_cursor({**payload, **change}), limit=1
            )
    newer_payload = json.loads(
        base64.urlsafe_b64decode(
            newer_page.page.next_cursor + "=" * (-len(newer_page.page.next_cursor) % 4)
        )
    )
    with pytest.raises(MarketNotFoundError, match="Search cursor is invalid"):
        _m42_search(
            reader,
            newer_corpus,
            newer_run,
            limit=1,
            cursor=_m42_cursor(
                {**newer_payload, "snapshot_id": str(nonmatch), "observed_at": nonmatch_time}
            ),
        )
    for malformed in ("!", "e30", _m42_cursor([]), _m42_cursor(None), "_w"):
        with pytest.raises(MarketNotFoundError, match="Search cursor is invalid"):
            _m42_search(reader, corpus_id, run_id, cursor=malformed, limit=1)
    scoped = _m42_search(reader, corpus_id, run_id, skills=["python", "aws"], limit=1)
    assert _m42_search(
        reader, corpus_id, run_id, skills=["aws", "python"], limit=1, cursor=scoped.page.next_cursor
    ).data


def test_m42_composes_all_filters_with_independent_distractors(migrated_database):
    _, sessions = migrated_database
    boundary = datetime.now(UTC) - timedelta(days=1)
    cases = [
        ("Senior Backend Engineer cpp", "Python AWS", "London, UK", boundary),
        ("Senior Data Engineer cpp", "Python AWS", "London, UK", boundary),
        ("Junior Backend Engineer cpp", "Python AWS", "London, UK", boundary),
        ("Senior Backend Engineer cpp", "Python AWS", "Hanoi, Vietnam", boundary),
        ("Senior Backend Engineer cpp", "AWS", "London, UK", boundary),
        ("Senior Backend Engineer cpp", "Python", "London, UK", boundary),
        (
            "Senior Backend Engineer cpp",
            "Python AWS",
            "London, UK",
            boundary - timedelta(seconds=1),
        ),
        (
            "Senior Backend Engineer cpp",
            "Python AWS",
            "London, UK",
            boundary + timedelta(seconds=1),
        ),
        ("Senior Backend Engineer", "Python AWS", "London, UK", boundary),
    ]
    ids = []
    for title, description, location, observed_at in cases:
        snapshot_id = _job_row(sessions, title=title, description=description, location=location)
        with sessions.begin() as session:
            session.get(JobSnapshot, snapshot_id).observed_at = observed_at
        TaxonomyService(sessions).normalize_snapshot(snapshot_id)
        ids.append(snapshot_id)
    corpus_id, run_id = _m42_publish(sessions)
    reader = PostgresMarketReader(sessions)
    filters = dict(
        role="backend_engineer",
        seniority="senior",
        location="London",
        skills=["python", "aws"],
        observed_from=boundary,
        observed_to=boundary,
    )
    page = _m42_search(reader, corpus_id, run_id, **filters)
    assert [UUID(item.snapshot_id) for item in page.data] == [ids[0]]
    assert not page.page.has_more
    for name, distractor in (
        ("role", 1),
        ("seniority", 2),
        ("location", 3),
        ("observed_from", 6),
        ("observed_to", 7),
    ):
        relaxed = _m42_search(reader, corpus_id, run_id, **{**filters, name: None})
        assert {UUID(item.snapshot_id) for item in relaxed.data} == {ids[0], ids[distractor]}
    for skills, distractor in ((["aws"], 4), (["python"], 5)):
        relaxed = _m42_search(reader, corpus_id, run_id, **{**filters, "skills": skills})
        assert {UUID(item.snapshot_id) for item in relaxed.data} == {ids[0], ids[distractor]}


def test_m42_frozen_skills_and_replacement_snapshot_keep_evidence_pinned(migrated_database):
    _, sessions = migrated_database
    original = _job_row(sessions, title="Backend Engineer", description="C++ original evidence")
    normalization_id = TaxonomyService(sessions).normalize_snapshot(original).normalization_id
    corpus_id, run_id = _m42_publish(sessions)
    reader = PostgresMarketReader(sessions)
    before = _m42_search(reader, corpus_id, run_id)
    assert [item.snapshot_id for item in before.data] == [str(original)]
    with sessions.begin() as session:
        normalization = session.get(SnapshotNormalization, normalization_id)
        normalization.role = "data_engineer"
        skill = session.scalar(
            select(JobSkill).where(JobSkill.normalization_id == normalization_id)
        )
        skill.reviewed_state = "rejected"
    changed_run = AnalyticsPersistence(sessions).publish(datetime.now(UTC), _versions())
    with sessions() as session:
        changed_corpus = session.get(AnalyticsRun, changed_run).corpus_snapshot_id
        frozen = session.scalar(
            select(AnalyticsRunMember).where(
                AnalyticsRunMember.analytics_run_id == run_id,
                AnalyticsRunMember.job_snapshot_id == original,
            )
        )
        assert frozen.skills == ["cpp"] and frozen.role == "backend_engineer"
    assert _m42_search(reader, corpus_id, run_id).model_dump() == before.model_dump()
    assert _m42_search(reader, changed_corpus, changed_run).data == []
    replacement = uuid4()
    with sessions.begin() as session:
        old = session.get(JobSnapshot, original)
        session.add(
            JobSnapshot(
                id=replacement,
                job_id=old.job_id,
                raw_record_id=old.raw_record_id,
                content_hash="b" * 64,
                processor_version=old.processor_version,
                title="Replacement AWS",
                company=old.company,
                location=old.location,
                description="replacement only evidence",
                observed_at=datetime.now(UTC),
            )
        )
    TaxonomyService(sessions).normalize_snapshot(replacement)
    latest_corpus, latest_run = _m42_publish(sessions)
    assert _m42_search(reader, latest_corpus, latest_run).data == []
    assert [
        item.snapshot_id
        for item in _m42_search(reader, latest_corpus, latest_run, query="AWS").data
    ] == [str(replacement)]
    app = create_app()
    app.dependency_overrides[get_market_reader] = lambda: reader
    with TestClient(app) as client:
        params = dict(
            snapshot=str(corpus_id), analytics_run_id=str(run_id), query="cpp", mode="lexical"
        )
        response = client.get("/api/v1/jobs/search", params=params)
        assert response.status_code == 200
        body = response.json()
        assert body["corpus_snapshot_id"] == str(corpus_id)
        assert body["analytics_run_id"] == str(run_id)
        assert "description" not in body["data"][0]
        assert "original evidence" not in response.text
        url = body["data"][0]["evidence_url"]
        assert url == f"/api/v1/evidence/{original}?snapshot={corpus_id}"
        evidence = client.get(url)
        assert evidence.status_code == 200
        assert evidence.json()["description"] == "C++ original evidence"
        assert evidence.json()["job"]["snapshot_id"] == str(original)
        assert evidence.json()["raw_record_hash"] == "a" * 64
        assert client.get(f"/api/v1/evidence/{replacement}?snapshot={corpus_id}").status_code == 404
        assert (
            client.get(f"/api/v1/evidence/{original}?snapshot={latest_corpus}").status_code == 404
        )


def test_m42_real_websearch_parser_simple_config_and_structured_default(migrated_database):
    _, sessions = migrated_database
    descriptions = [
        "Python PostgreSQL AWS",
        "Python AWS",
        "PostgreSQL AWS",
        "Python managed PostgreSQL",
        "Node.js C++ .NET",
        "running services",
        "run service",
        "drop table jobs",
        "unrelated",
    ]
    ids = [_job_row(sessions, title="Engineer", description=value) for value in descriptions]
    for snapshot_id in ids:
        TaxonomyService(sessions).normalize_snapshot(snapshot_id)
    corpus_id, run_id = _m42_publish(sessions)
    reader = PostgresMarketReader(sessions)
    cases = [
        ("Python PostgreSQL", {0, 3}),
        ("Python OR PostgreSQL", {0, 1, 2, 3}),
        ("Python -PostgreSQL", {1}),
        ('"Python PostgreSQL"', {0}),
        ('"Python PostgreSQL', {0}),
        ("Node.js", {4}),
        ("C++", {4}),
        (".NET", {4}),
        ("Python", {0, 1, 3}),
        ("PostgreSQL", {0, 2, 3}),
        ("AWS", {0, 1, 2}),
        ("running", {5}),
        ("run", {6}),
        ("!!!", set()),
        ("'; DROP TABLE jobs; --", {7}),
        ("' OR 1=1 --", set()),
    ]
    for query, indices in cases:
        page = _m42_search(reader, corpus_id, run_id, query=query)
        assert {item.snapshot_id for item in page.data} == {str(ids[index]) for index in indices}, (
            query
        )
        assert not page.page.has_more and page.page.next_cursor is None
    app = create_app()
    app.dependency_overrides[get_market_reader] = lambda: reader
    with TestClient(app) as client:
        params = dict(snapshot=str(corpus_id), analytics_run_id=str(run_id), query="Python")
        default = client.get("/api/v1/jobs/search", params=params)
        structured = client.get("/api/v1/jobs/search", params={**params, "mode": "structured"})
        lexical = client.get("/api/v1/jobs/search", params={**params, "mode": "lexical"})
        assert default.status_code == structured.status_code == lexical.status_code == 200
        assert default.json() == structured.json()
        assert default.json()["data"] == []
        assert {item["snapshot_id"] for item in lexical.json()["data"]} == {
            str(ids[i]) for i in (0, 1, 3)
        }
        for query in (None, "", "   "):
            invalid = {**params, "mode": "lexical"}
            if query is None:
                invalid.pop("query")
            else:
                invalid["query"] = query
            assert client.get("/api/v1/jobs/search", params=invalid).status_code == 422
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == len(ids)
