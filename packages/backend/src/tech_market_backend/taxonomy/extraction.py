import re

from .catalog import SKILLS
from .contracts import MatchMethod, SkillCandidate, SkillMatch, TextSource
from .versions import EXTRACTION_VERSION

_SHORT_CONTEXT = re.compile(
    r"\b(?:use|using|with|in|code|develop(?:er|ment)?|programming)\s+$", re.I
)


def _pattern(alias: str) -> re.Pattern[str]:
    left_boundary = r"(?<![\w+#])" if alias.startswith(".") else r"(?<![\w+#.])"
    return re.compile(rf"{left_boundary}{re.escape(alias)}(?![\w+#])", re.IGNORECASE)


_ALIAS_PATTERNS = tuple(
    (
        skill,
        alias,
        _pattern(alias.value),
        MatchMethod.REGEX if alias.matching_mode == "regex" else MatchMethod.ALIAS,
    )
    for skill in SKILLS
    for alias in skill.aliases
)


def _allowed_short_alias(text: str, start: int, alias: str) -> bool:
    if alias.casefold() not in {"go", "r"}:
        return True
    before = text[max(0, start - 16) : start]
    end = start + len(alias)
    listed = text[start:end] == alias and end < len(text) and text[end] in ",.;)"
    return listed or _SHORT_CONTEXT.search(before) is not None


def extract_skill_evidence(
    text: str, source: TextSource = TextSource.DESCRIPTION
) -> tuple[tuple[SkillMatch, ...], tuple[SkillCandidate, ...]]:
    matches: list[SkillMatch] = []
    candidates: list[SkillCandidate] = []
    for skill, alias_definition, pattern, method in _ALIAS_PATTERNS:
        alias = alias_definition.value
        for match in pattern.finditer(text):
            if not _allowed_short_alias(text, match.start(), alias):
                candidates.append(
                    SkillCandidate(
                        skill.id,
                        source,
                        match.start(),
                        match.end(),
                        match.group(),
                        "short_alias_without_context",
                        "pending",
                        EXTRACTION_VERSION,
                    )
                )
                continue
            matches.append(
                SkillMatch(
                    skill.id,
                    source,
                    match.start(),
                    match.end(),
                    match.group(),
                    method,
                    EXTRACTION_VERSION,
                )
            )
    matches.sort(key=lambda item: (item.start, -(item.end - item.start), item.skill_id))
    accepted: list[SkillMatch] = []
    for skill_match in matches:
        if any(skill_match.start < item.end and item.start < skill_match.end for item in accepted):
            continue
        accepted.append(skill_match)
    accepted.sort(key=lambda item: (item.start, item.end, item.skill_id))
    candidates.sort(key=lambda item: (item.start, item.end, item.skill_id))
    return tuple(accepted), tuple(candidates)


def extract_skills(
    text: str, source: TextSource = TextSource.DESCRIPTION
) -> tuple[SkillMatch, ...]:
    return extract_skill_evidence(text, source)[0]
