import hashlib
import json
import uuid
from typing import Any

NAMESPACE = uuid.UUID("f8f5de8c-06cc-5e9d-bf6e-e709e01b5194")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def source_uuid(namespace: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, namespace)


def job_uuid(namespace: str, source_id: str | None, canonical_url: str | None) -> uuid.UUID:
    identity = source_id or canonical_url
    if not identity:
        raise ValueError("source_id or canonical_url is required")
    return uuid.uuid5(source_uuid(namespace), identity)


def raw_record_uuid(source_id: uuid.UUID, digest: str) -> uuid.UUID:
    return uuid.uuid5(source_id, digest)


def snapshot_uuid(job_id: uuid.UUID, digest: str, processor_version: str) -> uuid.UUID:
    return uuid.uuid5(job_id, f"{digest}:{processor_version}")
