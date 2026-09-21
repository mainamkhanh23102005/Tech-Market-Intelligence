from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tech_market_backend.ingestion.adapters import RecordError, adapter_for
from tech_market_backend.ingestion.contracts import ImportLimits, PermissionManifest
from tech_market_backend.ingestion.identity import (
    content_hash,
    job_uuid,
    raw_record_uuid,
    snapshot_uuid,
    source_uuid,
)
from tech_market_backend.platform.models import (
    IngestionRun,
    Job,
    JobSnapshot,
    ProcessingAttempt,
    ProcessingFailure,
    RawRecord,
    Source,
    SourcePermission,
)


@dataclass(frozen=True)
class ImportResult:
    run_id: UUID
    accepted: int
    duplicates: int
    failures: int


class IngestionService:
    def __init__(self, sessions: sessionmaker[Session], processor_version: str = "m1-v1") -> None:
        self.sessions = sessions
        self.processor_version = processor_version

    def import_file(
        self,
        path: Path,
        manifest: PermissionManifest,
        limits: ImportLimits | None = None,
    ) -> ImportResult:
        active_limits = limits or ImportLimits()
        if manifest.status.value != "approved":
            raise ValueError("source permission status must be approved")
        if path.stat().st_size > active_limits.max_file_bytes:
            raise ValueError("input exceeds max_file_bytes")
        source_id = source_uuid(manifest.source_namespace)
        run_id = uuid4()
        with self.sessions.begin() as session:
            source = session.get(Source, source_id)
            if source is None:
                session.add(
                    Source(
                        id=source_id, namespace=manifest.source_namespace, name=manifest.source_name
                    )
                )
            permission = session.scalar(
                select(SourcePermission).where(
                    SourcePermission.source_id == source_id,
                    SourcePermission.manifest == manifest.model_dump(mode="json"),
                )
            )
            if permission is None:
                session.add(
                    SourcePermission(
                        id=uuid4(),
                        source_id=source_id,
                        manifest=manifest.model_dump(mode="json"),
                        status=manifest.status.value,
                        reviewed_at=manifest.reviewed_at,
                    )
                )
            session.add(
                IngestionRun(id=run_id, source_id=source_id, input_name=path.name, status="RUNNING")
            )
        accepted = 0
        duplicates = 0
        failures = 0
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for number, item in enumerate(adapter_for(path).records(stream, active_limits), 1):
                try:
                    with self.sessions.begin() as session:
                        if isinstance(item, RecordError):
                            self._failure(session, run_id, item.record_number, item)
                            failures += 1
                        else:
                            created = self._store(
                                session, run_id, source_id, number, item.model_dump(mode="json")
                            )
                            accepted += 1
                            duplicates += not created
                except Exception as exc:
                    with self.sessions.begin() as session:
                        self._failure(session, run_id, number, RecordError(number, str(exc), True))
                    failures += 1
        with self.sessions.begin() as session:
            run = session.get(IngestionRun, run_id)
            if run is None:
                raise RuntimeError("ingestion run missing")
            run.status = "COMPLETED_WITH_FAILURES" if failures else "COMPLETED"
            run.accepted_count = accepted
            run.duplicate_count = duplicates
            run.failure_count = failures
            run.finished_at = datetime.now(UTC)
        return ImportResult(run_id, accepted, duplicates, failures)

    def _store(
        self,
        session: Session,
        run_id: UUID,
        source_id: UUID,
        number: int,
        payload: dict[str, object],
    ) -> bool:
        digest = content_hash(payload)
        source_posting_id = payload.get("source_id")
        canonical_url = payload.get("canonical_url")
        job_id = job_uuid(
            str(source_id),
            str(source_posting_id) if source_posting_id else None,
            str(canonical_url) if canonical_url else None,
        )
        raw_id = raw_record_uuid(source_id, digest)
        if session.get(RawRecord, raw_id) is None:
            session.add(
                RawRecord(
                    id=raw_id,
                    source_id=source_id,
                    content_hash=digest,
                    payload=payload,
                    observed_at=datetime.fromisoformat(str(payload["observed_at"])),
                )
            )
        if session.get(Job, job_id) is None:
            session.add(
                Job(
                    id=job_id,
                    source_id=source_id,
                    source_posting_id=str(source_posting_id) if source_posting_id else None,
                    canonical_url=str(canonical_url) if canonical_url else None,
                )
            )
        snapshot_id = snapshot_uuid(job_id, digest, self.processor_version)
        snapshot_created = session.get(JobSnapshot, snapshot_id) is None
        if snapshot_created:
            session.add(
                JobSnapshot(
                    id=snapshot_id,
                    job_id=job_id,
                    raw_record_id=raw_id,
                    content_hash=digest,
                    processor_version=self.processor_version,
                    title=str(payload["title"]),
                    company=str(payload["company"]),
                    location=str(payload["location"]) if payload.get("location") else None,
                    description=str(payload["description"]),
                    observed_at=datetime.fromisoformat(str(payload["observed_at"])),
                )
            )
        session.add(
            ProcessingAttempt(
                id=uuid4(),
                run_id=run_id,
                record_number=number,
                job_id=job_id,
                raw_hash=digest,
                stage="NORMALIZED",
                processor_version=self.processor_version,
                state="READY",
            )
        )
        return snapshot_created

    def _failure(self, session: Session, run_id: UUID, number: int, error: RecordError) -> None:
        attempt_id = uuid4()
        session.add(
            ProcessingAttempt(
                id=attempt_id,
                run_id=run_id,
                record_number=number,
                stage="PARSED",
                processor_version=self.processor_version,
                state="FAILED_RETRYABLE" if error.retryable else "FAILED_TERMINAL",
            )
        )
        session.add(
            ProcessingFailure(
                id=uuid4(),
                attempt_id=attempt_id,
                error_type=type(error).__name__,
                message=str(error)[:4000],
                retryable=error.retryable,
            )
        )
