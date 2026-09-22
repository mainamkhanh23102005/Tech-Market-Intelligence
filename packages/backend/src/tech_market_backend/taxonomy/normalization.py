import re
from collections.abc import Mapping

from .contracts import LocationMode, LocationResult, NormalizationResult, NormalizationStatus
from .versions import NORMALIZATION_VERSION

_ROLE_ALIASES: Mapping[str, tuple[str, ...]] = {
    "data_engineer": ("data engineer",),
    "analytics_engineer": ("analytics engineer",),
    "data_analyst": ("data analyst",),
    "data_scientist": ("data scientist",),
    "machine_learning_engineer": (
        "machine learning software engineer",
        "machine learning engineer",
        "ml engineer",
    ),
    "ai_engineer": ("artificial intelligence engineer", "ai engineer"),
    "backend_engineer": ("backend engineer", "back-end engineer"),
    "software_engineer": ("software engineer", "software developer"),
    "devops_platform_engineer": (
        "devops / platform engineer",
        "devops engineer",
        "platform engineer",
        "site reliability engineer",
        "sre",
    ),
}
_ROLE_PRECEDENCE = tuple(_ROLE_ALIASES)
_SENIORITY = (
    ("director", ("director",)),
    ("manager", ("manager",)),
    ("principal", ("principal",)),
    ("staff", ("staff",)),
    ("lead", ("technical lead", "tech lead", "lead")),
    ("senior", ("senior", "sr")),
    ("mid", ("mid-level", "mid level", "intermediate")),
    ("junior", ("junior", "jr")),
    ("entry", ("entry level", "entry-level", "graduate")),
    ("intern", ("intern", "internship")),
)
_LOCATIONS: Mapping[str, tuple[str, str | None, str]] = {
    "london, uk": ("London", None, "United Kingdom"),
    "new york, ny, us": ("New York", "New York", "United States"),
    "san francisco, ca, us": ("San Francisco", "California", "United States"),
    "austin, tx, us": ("Austin", "Texas", "United States"),
    "toronto, ontario, canada": ("Toronto", "Ontario", "Canada"),
    "hanoi, vietnam": ("Hanoi", None, "Vietnam"),
}


def _contains(text: str, alias: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, re.IGNORECASE) is not None


def _result(
    value: str | None, status: NormalizationStatus, *candidates: str
) -> NormalizationResult:
    return NormalizationResult(value, status, NORMALIZATION_VERSION, tuple(candidates))


def normalize_role(title: str) -> NormalizationResult:
    matches = [
        role
        for role, aliases in _ROLE_ALIASES.items()
        if any(_contains(title, alias) for alias in aliases)
    ]
    if "machine_learning_engineer" in matches and "software_engineer" in matches:
        matches.remove("software_engineer")
    ordered = tuple(role for role in _ROLE_PRECEDENCE if role in matches)
    if len(ordered) == 1:
        return _result(ordered[0], NormalizationStatus.MATCHED, *ordered)
    if ordered:
        return _result(None, NormalizationStatus.AMBIGUOUS, *ordered)
    return _result(None, NormalizationStatus.UNKNOWN)


def normalize_seniority(title: str) -> NormalizationResult:
    for level, aliases in _SENIORITY:
        if any(_contains(title, alias) for alias in aliases):
            return _result(level, NormalizationStatus.MATCHED, level)
    return _result("unknown", NormalizationStatus.UNKNOWN)


def normalize_location(location: str, mode: LocationMode) -> LocationResult:
    arrangements = tuple(
        value for value in ("remote", "hybrid", "onsite") if _contains(location, value)
    )
    arrangement = arrangements[0] if len(arrangements) == 1 else None
    place_text = re.sub(
        r"^\s*(?:remote|hybrid|onsite)\s*(?:[-,:]|\bor\b)?\s*",
        "",
        location,
        flags=re.IGNORECASE,
    ).strip()
    place = _LOCATIONS.get(place_text.casefold())
    city, region, country = place or (None, None, None)
    remote_with_place = (
        mode is LocationMode.REMOTE_ONLY and arrangement == "remote" and bool(place_text)
    )
    if len(arrangements) > 1 or remote_with_place:
        status = NormalizationStatus.AMBIGUOUS
    elif place or arrangement:
        status = NormalizationStatus.MATCHED
    else:
        status = NormalizationStatus.UNKNOWN
    return LocationResult(
        location,
        city,
        region,
        country,
        arrangement,
        status,
        NORMALIZATION_VERSION,
    )
