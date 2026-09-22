import hashlib
import json
from collections.abc import Sequence
from typing import Any, Protocol

from .contracts import Skill, SkillAlias, SkillRelationship
from .versions import CATALOG_VERSION


class SkillDefinition(Protocol):
    id: str
    name: str
    category: str
    aliases: Sequence[object]
    status: str
    valid_from: str | None
    valid_to: str | None


def _skill(key: str, name: str, category: str, *aliases: str | SkillAlias) -> Skill:
    return Skill(
        key,
        name,
        category,
        tuple(alias if isinstance(alias, SkillAlias) else SkillAlias(alias) for alias in aliases),
    )


def _regex_alias(value: str) -> SkillAlias:
    return SkillAlias(value, matching_mode="regex")


SKILLS = (
    _skill("python", "Python", "language", "Python"),
    _skill("javascript", "JavaScript", "language", "JavaScript", "JS"),
    _skill("typescript", "TypeScript", "language", "TypeScript"),
    _skill("java", "Java", "language", "Java"),
    _skill("csharp", "C#", "language", _regex_alias("C#"), "C Sharp"),
    _skill("cpp", "C++", "language", _regex_alias("C++"), "C Plus Plus"),
    _skill("go", "Go", "language", "Go", "Golang"),
    _skill("rust", "Rust", "language", "Rust"),
    _skill("r", "R", "language", "R"),
    _skill("sql", "SQL", "language", "SQL"),
    _skill("dotnet", ".NET", "framework", _regex_alias(".NET"), "dotnet"),
    _skill("nodejs", "Node.js", "runtime", _regex_alias("Node.js"), "NodeJS"),
    _skill("react", "React", "framework", "React", _regex_alias("React.js")),
    _skill("angular", "Angular", "framework", "Angular"),
    _skill("django", "Django", "framework", "Django"),
    _skill("fastapi", "FastAPI", "framework", "FastAPI"),
    _skill("spring", "Spring", "framework", "Spring Boot", "Spring"),
    _skill("postgresql", "PostgreSQL", "database", "PostgreSQL", "Postgres"),
    _skill("mysql", "MySQL", "database", "MySQL"),
    _skill("mongodb", "MongoDB", "database", "MongoDB"),
    _skill("redis", "Redis", "database", "Redis"),
    _skill("aws", "AWS", "cloud", "AWS", "Amazon Web Services"),
    _skill("aws_ec2", "Amazon EC2", "cloud_service", "AWS EC2", "Amazon EC2"),
    _skill("azure", "Azure", "cloud", "Microsoft Azure", "Azure"),
    _skill("gcp", "Google Cloud", "cloud", "Google Cloud Platform", "GCP"),
    _skill("docker", "Docker", "platform", "Docker"),
    _skill("kubernetes", "Kubernetes", "platform", "Kubernetes", "K8s"),
    _skill("terraform", "Terraform", "platform", "Terraform"),
    _skill("git", "Git", "tool", "Git"),
    _skill("pytorch", "PyTorch", "machine_learning", "PyTorch"),
    _skill("tensorflow", "TensorFlow", "machine_learning", "TensorFlow"),
)

RELATIONSHIPS = (SkillRelationship("aws", "aws_ec2", "PART_OF"),)
SKILLS_BY_ID = {skill.id: skill for skill in SKILLS}


def _alias_manifest(alias: object) -> dict[str, object]:
    return {
        "value": str(getattr(alias, "value", alias)),
        "locale": str(getattr(alias, "locale", "en")),
        "matching_mode": str(getattr(alias, "matching_mode", "literal")),
        "case_sensitive": bool(getattr(alias, "case_sensitive", False)),
        "boundary_rule": str(getattr(alias, "boundary_rule", "token")),
        "ambiguity_status": str(getattr(alias, "ambiguity_status", "unambiguous")),
        "evidence": str(getattr(alias, "evidence", "curated")),
    }


def canonical_manifest(skills: Sequence[Any]) -> list[dict[str, object]]:
    return [
        {
            "id": skill.id,
            "name": skill.name,
            "category": skill.category,
            "status": skill.status,
            "valid_from": skill.valid_from,
            "valid_to": skill.valid_to,
            "aliases": sorted(
                (_alias_manifest(alias) for alias in skill.aliases),
                key=lambda alias: json.dumps(alias, sort_keys=True, separators=(",", ":")),
            ),
        }
        for skill in sorted(skills, key=lambda item: item.id)
    ]


def manifest_hash(skills: Sequence[Any]) -> str:
    payload = json.dumps(canonical_manifest(skills), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


__all__ = [
    "CATALOG_VERSION",
    "RELATIONSHIPS",
    "SKILLS",
    "SKILLS_BY_ID",
    "canonical_manifest",
    "manifest_hash",
]
