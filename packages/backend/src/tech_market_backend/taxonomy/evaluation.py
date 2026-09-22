import json
from collections import Counter
from collections.abc import Hashable, Sequence
from pathlib import Path
from typing import Any, TypedDict, cast

from .catalog import SKILLS, SKILLS_BY_ID, manifest_hash
from .contracts import (
    LocationMode,
    LocationResult,
    NormalizationResult,
    NormalizationStatus,
    TextSource,
)
from .extraction import extract_skills
from .normalization import normalize_location, normalize_role, normalize_seniority
from .versions import CATALOG_VERSION, EXTRACTION_VERSION, NORMALIZATION_VERSION


class SkillSpan(TypedDict):
    skill: str
    source: str
    start: int
    end: int
    text: str


class Labels(TypedDict):
    role: str | None
    seniority: str | None
    location: str | None
    skills: list[str]
    skill_spans: list[SkillSpan]


class Example(TypedDict):
    id: str
    cohort: str
    title: str
    description: str
    requirements: str
    location: str
    labels: Labels


class Corpus(TypedDict):
    manifest: dict[str, object]
    annotation_guide: dict[str, str]
    examples: list[dict[str, Any]]


def load_corpus(path: Path) -> Corpus:
    data = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(data, dict):
        raise ValueError("Corpus root must be an object")
    corpus = cast(Corpus, data)
    manifest = corpus.get("manifest")
    guide = corpus.get("annotation_guide")
    examples = corpus.get("examples")
    if not isinstance(manifest, dict) or not isinstance(guide, dict):
        raise ValueError("Corpus metadata is required")
    required_manifest = {
        "name": str,
        "version": str,
        "license": str,
        "provenance": str,
        "language": str,
        "example_count": int,
        "seed": int,
        "catalog_version": str,
        "normalization_version": str,
        "extraction_version": str,
    }
    if set(manifest) != set(required_manifest) or any(
        not isinstance(manifest[key], expected_type)
        or (expected_type is int and isinstance(manifest[key], bool))
        for key, expected_type in required_manifest.items()
    ):
        raise ValueError("Invalid corpus manifest")
    if manifest["catalog_version"] != CATALOG_VERSION:
        raise ValueError("Manifest catalog_version does not match evaluator")
    if manifest["normalization_version"] != NORMALIZATION_VERSION:
        raise ValueError("Manifest normalization_version does not match evaluator")
    if manifest["extraction_version"] != EXTRACTION_VERSION:
        raise ValueError("Manifest extraction_version does not match evaluator")
    if not isinstance(examples, list) or not examples:
        raise ValueError("Corpus examples must be a non-empty list")
    required_labels = {"role", "seniority", "location", "skills", "skill_spans"}
    ids: set[str] = set()
    for example in examples:
        if not isinstance(example, dict) or set(example) != {
            "id",
            "cohort",
            "title",
            "description",
            "location",
            "labels",
        }:
            raise ValueError("Invalid example fields")
        if not all(
            isinstance(value, str)
            for value in (
                example["id"],
                example["cohort"],
                example["title"],
                example["description"],
                example["location"],
            )
        ):
            raise ValueError("Example text fields must be strings")
        example_id = example["id"]
        if not example_id or example_id in ids:
            raise ValueError(f"Duplicate or empty example id: {example_id}")
        ids.add(example_id)
        labels = example.get("labels")
        if not isinstance(labels, dict) or set(labels) != required_labels:
            raise ValueError(f"Invalid labels for example: {example_id}")
        if any(
            value is not None and not isinstance(value, str)
            for value in (labels["role"], labels["seniority"], labels["location"])
        ):
            raise ValueError(f"Invalid canonical label type for example: {example_id}")
        skills = labels["skills"]
        spans = labels["skill_spans"]
        if not isinstance(skills, list) or any(not isinstance(skill, str) for skill in skills):
            raise ValueError(f"Invalid skills for example: {example_id}")
        if len(skills) != len(set(skills)) or any(skill not in SKILLS_BY_ID for skill in skills):
            raise ValueError(f"Invalid canonical skills for example: {example_id}")
        if not isinstance(spans, list):
            raise ValueError(f"Invalid skill spans for example: {example_id}")
        span_skills: set[str] = set()
        for span in spans:
            if not isinstance(span, dict) or set(span) != {
                "skill",
                "source",
                "start",
                "end",
                "text",
            }:
                raise ValueError(f"Invalid skill span fields for example: {example_id}")
            if (
                not isinstance(span["skill"], str)
                or not isinstance(span["source"], str)
                or not isinstance(span["text"], str)
                or not isinstance(span["start"], int)
                or isinstance(span["start"], bool)
                or not isinstance(span["end"], int)
                or isinstance(span["end"], bool)
            ):
                raise ValueError(f"Invalid skill span types for example: {example_id}")
            if span["source"] not in {"title", "description"}:
                raise ValueError(f"Invalid span source for example: {example_id}")
            source_text = example["title"] if span["source"] == "title" else example["description"]
            if not 0 <= span["start"] < span["end"] <= len(source_text):
                raise ValueError(f"Invalid skill span for example: {example_id}")
            if source_text[span["start"] : span["end"]] != span["text"]:
                raise ValueError(f"Skill span text mismatch for example: {example_id}")
            if span["skill"] not in SKILLS_BY_ID:
                raise ValueError(f"Unknown canonical skill for example: {example_id}")
            span_skills.add(span["skill"])
        if set(skills) != span_skills:
            raise ValueError(f"Skills and skill spans disagree for example: {example_id}")
    if manifest["example_count"] != len(examples):
        raise ValueError("Manifest example_count does not match corpus")
    return corpus


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return numerator / denominator if denominator else 0.0


def _prf(tp: int, fp: int, fn: int) -> dict[str, int | float]:
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": _ratio(2 * precision * recall, precision + recall),
    }


def score_items(
    expected: Sequence[Sequence[Hashable]], predicted: Sequence[Sequence[Hashable]]
) -> dict[str, int | float]:
    if len(expected) != len(predicted):
        raise ValueError("Expected and predicted rows must have equal length")
    tp = fp = fn = 0
    for expected_row, predicted_row in zip(expected, predicted, strict=True):
        expected_count = Counter(expected_row)
        predicted_count = Counter(predicted_row)
        tp += sum((expected_count & predicted_count).values())
        fp += sum((predicted_count - expected_count).values())
        fn += sum((expected_count - predicted_count).values())
    return _prf(tp, fp, fn)


def score_skills(
    expected: Sequence[Sequence[str]], predicted: Sequence[Sequence[str]]
) -> dict[str, object]:
    expected = [sorted(set(row)) for row in expected]
    predicted = [sorted(set(row)) for row in predicted]
    totals: dict[str, object] = dict(score_items(expected, predicted))
    skill_ids = sorted({skill for row in (*expected, *predicted) for skill in row})
    per_skill = {
        skill: score_items(
            [[value for value in row if value == skill] for row in expected],
            [[value for value in row if value == skill] for row in predicted],
        )
        for skill in skill_ids
    }
    totals["macro_f1"] = _ratio(
        sum(float(metrics["f1"]) for metrics in per_skill.values()), len(per_skill)
    )
    totals["per_skill"] = per_skill
    return totals


def score_exact_labels(
    expected: Sequence[str | None], predicted: Sequence[str | None], example_ids: Sequence[str]
) -> dict[str, object]:
    if len(expected) != len(predicted) or len(expected) != len(example_ids):
        raise ValueError("Expected, predicted, and example IDs must have equal length")
    errors = [
        {"id": example_id, "expected": gold, "predicted": guess}
        for gold, guess, example_id in zip(expected, predicted, example_ids, strict=True)
        if gold != guess
    ]
    classes = sorted({value for value in (*expected, *predicted) if value is not None})
    per_class: dict[str, dict[str, int | float]] = {}
    for label in classes:
        tp = sum(
            gold == label and guess == label
            for gold, guess in zip(expected, predicted, strict=True)
        )
        fp = sum(
            gold != label and guess == label
            for gold, guess in zip(expected, predicted, strict=True)
        )
        fn = sum(
            gold == label and guess != label
            for gold, guess in zip(expected, predicted, strict=True)
        )
        per_class[label] = _prf(tp, fp, fn)
    abstentions = sum(value is None for value in predicted)
    return {
        "correct": len(expected) - len(errors),
        "total": len(expected),
        "accuracy": _ratio(len(expected) - len(errors), len(expected)),
        "abstentions": abstentions,
        "abstention_rate": _ratio(abstentions, len(predicted)),
        "macro_f1": _ratio(sum(float(row["f1"]) for row in per_class.values()), len(per_class)),
        "per_class": per_class,
        "errors": errors,
    }


def _value(result: NormalizationResult) -> str | None:
    return None if result.status is NormalizationStatus.UNKNOWN else result.value


def _location_value(result: LocationResult) -> str | None:
    return result.work_arrangement if result.status is NormalizationStatus.MATCHED else None


def evaluate_corpus(corpus: Corpus) -> dict[str, object]:
    examples = corpus["examples"]
    ids = [example["id"] for example in examples]
    matches = [
        tuple(
            match
            for source, text in (
                (TextSource.TITLE, example["title"]),
                (TextSource.DESCRIPTION, example["description"]),
            )
            for match in extract_skills(text, source)
        )
        for example in examples
    ]
    expected_skills = [example["labels"]["skills"] for example in examples]
    predicted_skills = [[match.skill_id for match in row] for row in matches]
    expected_spans = [
        [
            (span["skill"], span["source"], span["start"], span["end"])
            for span in example["labels"]["skill_spans"]
        ]
        for example in examples
    ]
    predicted_spans = [
        [(match.skill_id, match.source.value, match.start, match.end) for match in row]
        for row in matches
    ]
    role_results = [normalize_role(example["title"]) for example in examples]
    seniority_results = [normalize_seniority(example["title"]) for example in examples]
    location_results = [
        normalize_location(example["location"], LocationMode.WORK_ARRANGEMENT)
        for example in examples
    ]
    expected_role = [example["labels"]["role"] for example in examples]
    predicted_role = [_value(result) for result in role_results]
    expected_seniority = [example["labels"]["seniority"] for example in examples]
    predicted_seniority = [_value(result) for result in seniority_results]
    cohorts: dict[str, object] = {}
    for cohort in sorted({example["cohort"] for example in examples}):
        indexes = [index for index, example in enumerate(examples) if example["cohort"] == cohort]
        cohorts[cohort] = {
            "count": len(indexes),
            "skills": score_skills(
                [expected_skills[i] for i in indexes], [predicted_skills[i] for i in indexes]
            ),
            "role": score_exact_labels(
                [expected_role[i] for i in indexes],
                [predicted_role[i] for i in indexes],
                [ids[i] for i in indexes],
            ),
            "seniority": score_exact_labels(
                [expected_seniority[i] for i in indexes],
                [predicted_seniority[i] for i in indexes],
                [ids[i] for i in indexes],
            ),
        }
    return {
        "corpus": {"size": len(examples), "manifest": corpus["manifest"]},
        "versions": {
            "catalog": CATALOG_VERSION,
            "normalization": NORMALIZATION_VERSION,
            "extraction": EXTRACTION_VERSION,
            "taxonomy_manifest_hash": manifest_hash(SKILLS),
        },
        "definitions": {
            "canonical_skill": "Micro exact match of unique canonical skill IDs per example.",
            "exact_span": (
                "Micro exact match of skill ID, source field, start offset, and end offset."
            ),
            "label": "Exact canonical label accuracy; macro F1 averages one-vs-rest class F1.",
        },
        "known_limitations": [
            "Small synthetic English corpus is not representative of production distributions.",
            "Baseline is deterministic alias/regex matching, not contextual semantic extraction.",
            "Offsets are Unicode code-point indexes within each source field.",
        ],
        "baseline": (
            "Deterministic in-repository canonical normalizer and precompiled boundary-aware "
            "alias/regex extractor; no tuning on external data."
        ),
        "extraction_methods": ["alias", "regex"],
        "skills": score_skills(expected_skills, predicted_skills),
        "exact_spans": score_items(expected_spans, predicted_spans),
        "role": score_exact_labels(expected_role, predicted_role, ids),
        "seniority": score_exact_labels(expected_seniority, predicted_seniority, ids),
        "location": score_exact_labels(
            [example["labels"]["location"] for example in examples],
            [_location_value(result) for result in location_results],
            ids,
        ),
        "ambiguity": {
            "role": sum(result.status is NormalizationStatus.AMBIGUOUS for result in role_results),
            "seniority": sum(
                result.status is NormalizationStatus.AMBIGUOUS for result in seniority_results
            ),
            "location": sum(
                result.status is NormalizationStatus.AMBIGUOUS for result in location_results
            ),
        },
        "cohorts": cohorts,
    }


def write_report(corpus_path: Path, report_path: Path) -> dict[str, object]:
    report = evaluate_corpus(load_corpus(corpus_path))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
