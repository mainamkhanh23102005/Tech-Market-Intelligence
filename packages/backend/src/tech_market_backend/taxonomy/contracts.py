from dataclasses import dataclass
from enum import StrEnum


class NormalizationStatus(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class LocationMode(StrEnum):
    REMOTE_ONLY = "remote_only"
    WORK_ARRANGEMENT = "work_arrangement"


class TextSource(StrEnum):
    TITLE = "title"
    DESCRIPTION = "description"
    REQUIREMENTS = "requirements"


class MatchMethod(StrEnum):
    ALIAS = "alias"
    REGEX = "regex"


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    value: str | None
    status: NormalizationStatus
    version: str
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LocationResult:
    original: str
    city: str | None
    region: str | None
    country: str | None
    work_arrangement: str | None
    status: NormalizationStatus
    version: str


@dataclass(frozen=True, slots=True)
class SkillAlias:
    value: str
    locale: str = "en"
    matching_mode: str = "literal"
    case_sensitive: bool = False
    boundary_rule: str = "token"
    ambiguity_status: str = "unambiguous"
    evidence: str = "curated"


@dataclass(frozen=True, slots=True)
class Skill:
    id: str
    name: str
    category: str
    aliases: tuple[SkillAlias, ...]
    status: str = "active"
    valid_from: str | None = None
    valid_to: str | None = None


@dataclass(frozen=True, slots=True)
class SkillRelationship:
    parent_id: str
    child_id: str
    relationship_type: str


@dataclass(frozen=True, slots=True)
class SkillMatch:
    skill_id: str
    source: TextSource
    start: int
    end: int
    matched_alias: str
    method: MatchMethod
    version: str


@dataclass(frozen=True, slots=True)
class SkillCandidate:
    skill_id: str
    source: TextSource
    start: int
    end: int
    matched_alias: str
    reason: str
    status: str
    version: str
