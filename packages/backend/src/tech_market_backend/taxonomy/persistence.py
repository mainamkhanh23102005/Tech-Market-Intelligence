import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from tech_market_backend.platform.models import (
    JobSkill,
    Skill,
    SkillAlias,
    SkillCandidate,
    SkillRelationship,
    SnapshotNormalization,
    TaxonomySkillVersion,
    TaxonomyVersion,
)

from .catalog import manifest_hash

_ID_NAMESPACE = UUID("f84263c5-985d-40e4-a226-e8197546761e")


class SkillDefinition(Protocol):
    id: str
    name: str
    category: str
    aliases: Sequence[object]
    status: str
    valid_from: str | None
    valid_to: str | None


class RelationshipDefinition(Protocol):
    parent_id: str
    child_id: str
    relationship_type: str


class SkillEvidence(Protocol):
    skill_id: str
    source: object
    start: int
    end: int
    matched_alias: str
    method: object
    version: str


class CandidateEvidence(Protocol):
    skill_id: str
    source: object
    start: int
    end: int
    matched_alias: str
    reason: str
    status: str
    version: str


class NormalizedRecord(Protocol):
    snapshot_id: UUID
    method: str
    processor_version: str
    normalization_version: str
    extraction_version: str
    status: str
    role: str | None
    role_status: object
    seniority: str | None
    seniority_status: object
    location_original: str | None
    location_city: str | None
    location_region: str | None
    location_country: str | None
    work_arrangement: str | None
    location_status: object
    skills: Sequence[SkillEvidence]
    candidates: Sequence[CandidateEvidence]


@dataclass(frozen=True)
class PersistenceResult:
    normalization_id: UUID
    evidence_count: int


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _stable_id(kind: str, *parts: object) -> UUID:
    payload = json.dumps([kind, *parts], ensure_ascii=False, separators=(",", ":"), default=str)
    return uuid5(_ID_NAMESPACE, payload)


def _alias_value(alias: object) -> str:
    return str(getattr(alias, "value", alias))


class TaxonomyPersistence:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def seed(
        self,
        version: str,
        skills: Iterable[Any],
        relationships: Iterable[Any] = (),
        status: str = "ACTIVE",
    ) -> UUID:
        definitions = tuple(skills)
        version_id = _stable_id("taxonomy", version)
        taxonomy_manifest_hash = manifest_hash(definitions)
        with self.sessions.begin() as session:
            existing_hash = session.scalar(
                select(TaxonomyVersion.manifest_hash).where(TaxonomyVersion.version == version)
            )
            if existing_hash is not None and existing_hash != taxonomy_manifest_hash:
                raise ValueError(f"taxonomy version {version!r} already has different content")
            session.execute(
                insert(TaxonomyVersion)
                .values(
                    id=version_id,
                    version=version,
                    manifest_hash=taxonomy_manifest_hash,
                    status=status,
                )
                .on_conflict_do_nothing(index_elements=["version"])
            )
            for definition in sorted(definitions, key=lambda item: item.id):
                skill_id = _stable_id("skill", definition.id)
                session.execute(
                    insert(Skill)
                    .values(id=skill_id, key=definition.id)
                    .on_conflict_do_nothing(index_elements=["key"])
                )
                session.execute(
                    insert(TaxonomySkillVersion)
                    .values(
                        skill_id=skill_id,
                        taxonomy_version_id=version_id,
                        name=definition.name,
                        category=definition.category,
                        status=definition.status,
                        valid_from=definition.valid_from,
                        valid_to=definition.valid_to,
                    )
                    .on_conflict_do_nothing(index_elements=["skill_id", "taxonomy_version_id"])
                )
                for alias in definition.aliases:
                    alias_value = _alias_value(alias)
                    session.execute(
                        insert(SkillAlias)
                        .values(
                            id=_stable_id("alias", version_id, skill_id, alias_value),
                            skill_id=skill_id,
                            taxonomy_version_id=version_id,
                            alias=alias_value,
                            normalized_alias=" ".join(alias_value.casefold().split()),
                            locale=getattr(alias, "locale", "en"),
                            matching_mode=getattr(alias, "matching_mode", "literal"),
                            case_sensitive=getattr(alias, "case_sensitive", False),
                            boundary_rule=getattr(alias, "boundary_rule", "token"),
                            ambiguity_status=getattr(alias, "ambiguity_status", "unambiguous"),
                            evidence=getattr(alias, "evidence", "curated"),
                        )
                        .on_conflict_do_nothing(
                            index_elements=["skill_id", "taxonomy_version_id", "alias"]
                        )
                    )
            for relationship in relationships:
                parent = _stable_id("skill", relationship.parent_id)
                child = _stable_id("skill", relationship.child_id)
                session.execute(
                    insert(SkillRelationship)
                    .values(
                        id=_stable_id(
                            "relationship",
                            version_id,
                            parent,
                            child,
                            relationship.relationship_type,
                        ),
                        taxonomy_version_id=version_id,
                        parent_skill_id=parent,
                        child_skill_id=child,
                        relationship_type=relationship.relationship_type,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            "taxonomy_version_id",
                            "parent_skill_id",
                            "child_skill_id",
                            "relationship_type",
                        ]
                    )
                )
        return version_id

    def persist(self, taxonomy_version: str, record: Any) -> PersistenceResult:
        version_id = _stable_id("taxonomy", taxonomy_version)
        normalization_id = _stable_id(
            "normalization",
            record.snapshot_id,
            version_id,
            record.method,
            record.processor_version,
            record.normalization_version,
            record.extraction_version,
        )
        with self.sessions.begin() as session:
            session.execute(
                insert(SnapshotNormalization)
                .values(
                    id=normalization_id,
                    snapshot_id=record.snapshot_id,
                    taxonomy_version_id=version_id,
                    method=record.method,
                    processor_version=record.processor_version,
                    normalization_version=record.normalization_version,
                    extraction_version=record.extraction_version,
                    status=record.status,
                    role=record.role,
                    role_status=_value(record.role_status),
                    seniority=record.seniority,
                    seniority_status=_value(record.seniority_status),
                    location_original=record.location_original,
                    location_city=record.location_city,
                    location_region=record.location_region,
                    location_country=record.location_country,
                    work_arrangement=record.work_arrangement,
                    location_status=_value(record.location_status),
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        "snapshot_id",
                        "taxonomy_version_id",
                        "method",
                        "processor_version",
                        "normalization_version",
                        "extraction_version",
                    ]
                )
            )
            for item in record.skills:
                skill_id = _stable_id("skill", item.skill_id)
                source = _value(item.source)
                session.execute(
                    insert(JobSkill)
                    .values(
                        id=_stable_id(
                            "evidence", normalization_id, skill_id, source, item.start, item.end
                        ),
                        normalization_id=normalization_id,
                        skill_id=skill_id,
                        taxonomy_version_id=version_id,
                        source_field=source,
                        evidence_start=item.start,
                        evidence_end=item.end,
                        matched_alias=item.matched_alias,
                        method=_value(item.method),
                        extractor_version=item.version,
                        reviewed_state="accepted",
                        confidence=1.0,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            "normalization_id",
                            "skill_id",
                            "source_field",
                            "evidence_start",
                            "evidence_end",
                        ]
                    )
                )
            for candidate in record.candidates:
                skill_id = _stable_id("skill", candidate.skill_id)
                source = _value(candidate.source)
                session.execute(
                    insert(SkillCandidate)
                    .values(
                        id=_stable_id(
                            "candidate",
                            normalization_id,
                            skill_id,
                            source,
                            candidate.start,
                            candidate.end,
                        ),
                        normalization_id=normalization_id,
                        snapshot_id=record.snapshot_id,
                        taxonomy_version_id=version_id,
                        skill_id=skill_id,
                        source_field=source,
                        evidence_start=candidate.start,
                        evidence_end=candidate.end,
                        matched_alias=candidate.matched_alias,
                        reason=candidate.reason,
                        status=candidate.status,
                        extractor_version=candidate.version,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            "normalization_id",
                            "skill_id",
                            "source_field",
                            "evidence_start",
                            "evidence_end",
                        ]
                    )
                )
        return PersistenceResult(normalization_id, len(record.skills))
