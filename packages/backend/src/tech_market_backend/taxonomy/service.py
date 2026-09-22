from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from tech_market_backend.platform.models import JobSnapshot

from .catalog import RELATIONSHIPS, SKILLS
from .contracts import LocationMode, SkillCandidate, SkillMatch, TextSource
from .extraction import extract_skill_evidence
from .normalization import normalize_location, normalize_role, normalize_seniority
from .persistence import PersistenceResult, TaxonomyPersistence
from .versions import CATALOG_VERSION, EXTRACTION_VERSION, NORMALIZATION_VERSION


@dataclass(frozen=True)
class SnapshotRecord:
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
    location_original: str
    location_city: str | None
    location_region: str | None
    location_country: str | None
    work_arrangement: str | None
    location_status: object
    skills: tuple[SkillMatch, ...]
    candidates: tuple[SkillCandidate, ...]


class TaxonomyService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions
        self.persistence = TaxonomyPersistence(sessions)

    def normalize_snapshot(self, snapshot_id: UUID) -> PersistenceResult:
        with self.sessions() as session:
            snapshot = session.get(JobSnapshot, snapshot_id)
            if snapshot is None:
                raise ValueError("job snapshot not found")
            role = normalize_role(snapshot.title)
            seniority = normalize_seniority(snapshot.title)
            location = normalize_location(snapshot.location or "", LocationMode.WORK_ARRANGEMENT)
            title_skills, title_candidates = extract_skill_evidence(
                snapshot.title, TextSource.TITLE
            )
            description_skills, description_candidates = extract_skill_evidence(
                snapshot.description, TextSource.DESCRIPTION
            )
            skills = (*title_skills, *description_skills)
            candidates = (*title_candidates, *description_candidates)
        self.persistence.seed(CATALOG_VERSION, SKILLS, RELATIONSHIPS)
        return self.persistence.persist(
            CATALOG_VERSION,
            SnapshotRecord(
                snapshot_id=snapshot_id,
                method="deterministic",
                processor_version="m2-v1",
                normalization_version=NORMALIZATION_VERSION,
                extraction_version=EXTRACTION_VERSION,
                status="SUCCEEDED",
                role=role.value,
                role_status=role.status,
                seniority=seniority.value,
                seniority_status=seniority.status,
                location_original=location.original,
                location_city=location.city,
                location_region=location.region,
                location_country=location.country,
                work_arrangement=location.work_arrangement,
                location_status=location.status,
                skills=skills,
                candidates=candidates,
            ),
        )
