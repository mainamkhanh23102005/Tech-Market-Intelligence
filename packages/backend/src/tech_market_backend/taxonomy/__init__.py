from .catalog import CATALOG_VERSION, SKILLS, SKILLS_BY_ID
from .contracts import (
    LocationMode,
    LocationResult,
    MatchMethod,
    NormalizationResult,
    NormalizationStatus,
    Skill,
    SkillMatch,
    TextSource,
)
from .extraction import extract_skills
from .normalization import normalize_location, normalize_role, normalize_seniority
from .versions import EXTRACTION_VERSION, NORMALIZATION_VERSION

__all__ = [
    "CATALOG_VERSION",
    "EXTRACTION_VERSION",
    "NORMALIZATION_VERSION",
    "SKILLS",
    "SKILLS_BY_ID",
    "LocationMode",
    "LocationResult",
    "MatchMethod",
    "NormalizationResult",
    "NormalizationStatus",
    "Skill",
    "SkillMatch",
    "TextSource",
    "extract_skills",
    "normalize_location",
    "normalize_role",
    "normalize_seniority",
]
