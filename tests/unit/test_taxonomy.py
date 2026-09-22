import pytest
from tech_market_backend.taxonomy import (
    CATALOG_VERSION,
    SKILLS,
    LocationMode,
    MatchMethod,
    NormalizationStatus,
    TextSource,
    extract_skills,
    normalize_location,
    normalize_role,
    normalize_seniority,
)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Data Engineer", "data_engineer"),
        ("Analytics Engineer", "analytics_engineer"),
        ("Data Analyst", "data_analyst"),
        ("Data Scientist", "data_scientist"),
        ("Machine Learning Engineer", "machine_learning_engineer"),
        ("AI Engineer", "ai_engineer"),
        ("Backend Engineer", "backend_engineer"),
        ("Software Engineer", "software_engineer"),
        ("DevOps Engineer", "devops_platform_engineer"),
        ("Platform Engineer", "devops_platform_engineer"),
        ("DevOps / Platform Engineer", "devops_platform_engineer"),
    ],
)
def test_role_normalizes_required_canonical_roles(title: str, expected: str) -> None:
    result = normalize_role(title)
    assert result.value == expected
    assert result.status is NormalizationStatus.MATCHED


def test_role_abstains_when_mixed_title_has_distinct_roles() -> None:
    result = normalize_role("Data Engineer / Data Scientist")
    assert result.status is NormalizationStatus.AMBIGUOUS
    assert result.value is None
    assert result.candidates == ("data_engineer", "data_scientist")


def test_role_prefers_specific_role_over_software_engineer_suffix() -> None:
    result = normalize_role("Machine Learning Software Engineer")
    assert result.value == "machine_learning_engineer"
    assert result.status is NormalizationStatus.MATCHED


def test_role_abstains_on_unknown_title() -> None:
    assert normalize_role("Chief Happiness Wizard").status is NormalizationStatus.UNKNOWN


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Engineering Intern", "intern"),
        ("Graduate Software Engineer", "entry"),
        ("Entry Level Engineer", "entry"),
        ("Junior Developer", "junior"),
        ("Mid-level Developer", "mid"),
        ("Senior Engineer", "senior"),
        ("Staff Engineer", "staff"),
        ("Principal Engineer", "principal"),
        ("Technical Lead", "lead"),
        ("Engineering Manager", "manager"),
        ("Engineering Director", "director"),
    ],
)
def test_seniority_normalizes_canonical_levels(title: str, expected: str) -> None:
    assert normalize_seniority(title).value == expected


def test_seniority_manager_precedes_senior() -> None:
    assert normalize_seniority("Senior Engineering Manager").value == "manager"


def test_seniority_unknown_is_explicit() -> None:
    result = normalize_seniority("Software Engineer")
    assert result.value == "unknown"
    assert result.status is NormalizationStatus.UNKNOWN


@pytest.mark.parametrize(
    ("raw", "city", "region", "country"),
    [
        ("London, UK", "London", None, "United Kingdom"),
        ("New York, NY, US", "New York", "New York", "United States"),
        ("San Francisco, CA, US", "San Francisco", "California", "United States"),
        ("Austin, TX, US", "Austin", "Texas", "United States"),
        ("Toronto, Ontario, Canada", "Toronto", "Ontario", "Canada"),
        ("Hanoi, Vietnam", "Hanoi", None, "Vietnam"),
    ],
)
def test_location_parses_whitelisted_fixture(
    raw: str, city: str, region: str | None, country: str
) -> None:
    result = normalize_location(raw, LocationMode.WORK_ARRANGEMENT)
    assert result.original == raw
    assert result.city == city
    assert result.region == region
    assert result.country == country
    assert result.work_arrangement is None
    assert result.status is NormalizationStatus.MATCHED


def test_location_extracts_arrangement_and_whitelisted_place() -> None:
    result = normalize_location("Hybrid - London, UK", LocationMode.WORK_ARRANGEMENT)
    assert result.city == "London"
    assert result.country == "United Kingdom"
    assert result.work_arrangement == "hybrid"


def test_location_keeps_unresolved_fields_none() -> None:
    result = normalize_location("Berlin, Germany", LocationMode.WORK_ARRANGEMENT)
    assert result.original == "Berlin, Germany"
    assert result.city is None
    assert result.region is None
    assert result.country is None
    assert result.work_arrangement is None
    assert result.status is NormalizationStatus.UNKNOWN


def test_remote_only_mode_rejects_mixed_place() -> None:
    result = normalize_location("Remote or New York, NY, US", LocationMode.REMOTE_ONLY)
    assert result.status is NormalizationStatus.AMBIGUOUS
    assert result.work_arrangement == "remote"


def test_catalog_has_stable_unique_persistable_contracts() -> None:
    assert CATALOG_VERSION == "skills-2026-09-22"
    assert len(SKILLS) == 31
    assert len({skill.id for skill in SKILLS}) == len(SKILLS)
    assert all(skill.id and skill.category and skill.aliases for skill in SKILLS)


def test_skill_match_preserves_exact_evidence_and_classifies_method() -> None:
    text = "Build Node.js, React.js, and .NET services using C++ and C# with Python."
    matches = extract_skills(text, TextSource.REQUIREMENTS)
    assert [match.skill_id for match in matches] == [
        "nodejs",
        "react",
        "dotnet",
        "cpp",
        "csharp",
        "python",
    ]
    assert [match.method for match in matches] == [
        MatchMethod.REGEX,
        MatchMethod.REGEX,
        MatchMethod.REGEX,
        MatchMethod.REGEX,
        MatchMethod.REGEX,
        MatchMethod.ALIAS,
    ]
    assert all(text[match.start : match.end] == match.matched_alias for match in matches)
    assert all(match.source is TextSource.REQUIREMENTS for match in matches)
    assert all(match.version for match in matches)


def test_punctuation_sensitive_aliases_respect_boundaries() -> None:
    assert extract_skills("foo.NET C++Builder C#ish xNode.js") == ()
    assert [match.skill_id for match in extract_skills("(.NET), C++; C#; Node.js.")] == [
        "dotnet",
        "cpp",
        "csharp",
        "nodejs",
    ]
    assert all(
        match.method is MatchMethod.REGEX for match in extract_skills("(.NET), C++; C#; Node.js.")
    )


def test_go_alias_matches_in_explicit_skill_context() -> None:
    assert [match.skill_id for match in extract_skills("Experience using Go")] == ["go"]


def test_go_alias_abstains_in_prose_and_google() -> None:
    assert extract_skills("Go to Google headquarters") == ()


def test_r_alias_matches_in_explicit_skill_context() -> None:
    assert [match.skill_id for match in extract_skills("Programming in R")] == ["r"]


def test_r_alias_abstains_inside_words() -> None:
    assert extract_skills("Plan customer reporting") == ()


def test_java_does_not_overlap_javascript() -> None:
    assert [match.skill_id for match in extract_skills("JavaScript")] == ["javascript"]


def test_duplicate_mentions_emit_all_exact_evidence() -> None:
    matches = extract_skills("Python, python and PYTHON")
    assert len(matches) == 3
    assert [match.matched_alias for match in matches] == ["Python", "python", "PYTHON"]
    assert [match.start for match in matches] == [0, 8, 19]


def test_overlapping_aliases_emit_only_most_specific_evidence() -> None:
    assert [match.skill_id for match in extract_skills("JavaScript and PostgreSQL")] == [
        "javascript",
        "postgresql",
    ]
