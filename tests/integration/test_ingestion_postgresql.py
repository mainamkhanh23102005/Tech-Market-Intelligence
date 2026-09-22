import os
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from tech_market_backend.ingestion.contracts import PermissionManifest
from tech_market_backend.ingestion.provenance import inspect_provenance
from tech_market_backend.ingestion.service import IngestionService
from tech_market_backend.platform.database import create_database_engine, session_factory
from tech_market_backend.platform.models import (
    Job,
    JobSnapshot,
    ProcessingAttempt,
    ProcessingFailure,
    RawRecord,
)

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.integration


@pytest.fixture()
def database():
    if not DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")
    database = make_url(DATABASE_URL).database
    if database is None or "test" not in database.casefold():
        pytest.fail("TEST_DATABASE_URL database name must contain 'test'")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_database_engine(DATABASE_URL)
    yield session_factory(engine)
    engine.dispose()


def test_replay_change_partial_failure_and_provenance(database) -> None:
    manifest = PermissionManifest.model_validate_json(
        Path("data/manifests/synthetic-jobs.json").read_text(encoding="utf-8")
    )
    service = IngestionService(database)
    first = service.import_file(Path("data/fixtures/jobs.csv"), manifest)
    replay = service.import_file(Path("data/fixtures/jobs.csv"), manifest)
    changed = service.import_file(Path("data/fixtures/jobs-changed.json"), manifest)
    changed_replay = service.import_file(Path("data/fixtures/jobs-changed.json"), manifest)
    assert (first.accepted, first.duplicates, first.failures) == (4, 1, 1)
    assert (replay.accepted, replay.duplicates, replay.failures) == (4, 4, 1)
    assert (changed.accepted, changed.duplicates, changed.failures) == (2, 0, 0)
    assert (changed_replay.accepted, changed_replay.duplicates, changed_replay.failures) == (
        2,
        2,
        0,
    )
    with database() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 4
        assert session.scalar(select(func.count()).select_from(RawRecord)) == 5
        assert session.scalar(select(func.count()).select_from(JobSnapshot)) == 5
        assert session.scalar(select(func.count()).select_from(ProcessingFailure)) == 2
        failure_states = session.scalars(
            select(ProcessingAttempt.state).where(ProcessingAttempt.state.like("FAILED_%"))
        ).all()
        assert failure_states == ["FAILED_TERMINAL", "FAILED_TERMINAL"]
        source_job = session.scalar(select(Job).where(Job.source_posting_id == "job-001"))
        assert source_job is not None
        provenance = inspect_provenance(session, job_id=source_job.id)
        assert provenance is not None
        assert provenance["raw_hash"]
        assert provenance["permission_status"] == "approved"
        historical = inspect_provenance(session, snapshot_id=UUID(provenance["snapshot_id"]))
        assert historical == provenance


def test_retryable_failure_can_be_recovered_by_replay(database, monkeypatch) -> None:
    manifest = PermissionManifest.model_validate_json(
        Path("data/manifests/synthetic-jobs.json").read_text(encoding="utf-8")
    )
    service = IngestionService(database)
    original_store = service._store
    failed_once = False

    def transient_store(*args, **kwargs):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise ConnectionError("transient database failure")
        return original_store(*args, **kwargs)

    monkeypatch.setattr(service, "_store", transient_store)
    failed = service.import_file(Path("data/fixtures/jobs-changed.json"), manifest)
    monkeypatch.setattr(service, "_store", original_store)
    recovered = service.import_file(Path("data/fixtures/jobs-changed.json"), manifest)

    assert (failed.accepted, failed.failures) == (1, 1)
    assert (recovered.accepted, recovered.duplicates, recovered.failures) == (2, 1, 0)
    with database() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ProcessingFailure)
                .where(ProcessingFailure.retryable)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ProcessingAttempt)
                .where(ProcessingAttempt.state == "FAILED_RETRYABLE")
            )
            == 1
        )
