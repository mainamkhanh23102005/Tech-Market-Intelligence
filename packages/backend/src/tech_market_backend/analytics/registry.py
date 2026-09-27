from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    version: str
    formula: str
    denominator: str
    dimensions: tuple[str, ...]
    unit: str = "ratio"


METRICS = {
    "skill_prevalence": MetricDefinition(
        "skill_prevalence",
        "skill-prevalence-1.0.0",
        "distinct logical jobs requesting skill / distinct logical jobs in cohort",
        "distinct logical jobs in cohort",
        ("skill", "role", "seniority", "location", "work_arrangement"),
    ),
    "role_comparison": MetricDefinition(
        "role_comparison",
        "role-comparison-1.0.0",
        "skill prevalence in left role compared with skill prevalence in right role",
        "distinct logical jobs in each role cohort",
        ("left_role", "right_role", "skill"),
    ),
    "location_distribution": MetricDefinition(
        "location_distribution",
        "location-distribution-1.0.0",
        "distinct logical jobs in location / distinct logical jobs in cohort",
        "distinct logical jobs in cohort",
        ("location", "work_arrangement"),
    ),
    "skill_cooccurrence": MetricDefinition(
        "skill_cooccurrence",
        "skill-cooccurrence-1.0.0",
        "distinct logical jobs requesting both skills / distinct logical jobs in cohort",
        "distinct logical jobs in cohort",
        ("skill_a", "skill_b"),
    ),
}


def coverage_warning(denominator: int) -> str | None:
    if denominator < 10:
        return f"Small sample: {denominator} distinct logical jobs; interpret cautiously."
    return None
