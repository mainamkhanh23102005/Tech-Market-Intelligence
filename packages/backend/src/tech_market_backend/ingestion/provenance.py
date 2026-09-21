from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tech_market_backend.platform.models import (
    Job,
    JobSnapshot,
    RawRecord,
    Source,
    SourcePermission,
)


def inspect_provenance(
    session: Session, *, job_id: UUID | None = None, snapshot_id: UUID | None = None
) -> dict[str, Any] | None:
    if (job_id is None) == (snapshot_id is None):
        raise ValueError("exactly one of job_id or snapshot_id is required")
    query = (
        select(Job, JobSnapshot, RawRecord, Source, SourcePermission)
        .join(JobSnapshot, JobSnapshot.job_id == Job.id)
        .join(RawRecord, RawRecord.id == JobSnapshot.raw_record_id)
        .join(Source, Source.id == Job.source_id)
        .join(SourcePermission, SourcePermission.source_id == Source.id)
    )
    query = query.where(Job.id == job_id) if job_id else query.where(JobSnapshot.id == snapshot_id)
    row = session.execute(
        query.order_by(JobSnapshot.observed_at.desc(), SourcePermission.reviewed_at.desc()).limit(1)
    ).one_or_none()
    if row is None:
        return None
    job, snapshot, raw, source, permission = row
    return {
        "job_id": str(job.id),
        "snapshot_id": str(snapshot.id),
        "raw_record_id": str(raw.id),
        "raw_hash": raw.content_hash,
        "source_namespace": source.namespace,
        "source_url": job.canonical_url,
        "observed_at": snapshot.observed_at.isoformat(),
        "processor_version": snapshot.processor_version,
        "permission_status": permission.status,
        "permission_manifest": permission.manifest,
    }
