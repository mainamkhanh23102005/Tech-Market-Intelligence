import json
import subprocess
import sys
from pathlib import Path

import pytest
from tech_market_backend.taxonomy.evaluation import (
    evaluate_corpus,
    load_corpus,
    score_exact_labels,
    score_items,
    score_skills,
)

CORPUS = Path("data/benchmarks/extraction/corpus.json")


def test_skill_metrics_are_exact_micro_counts() -> None:
    metrics = score_skills([("python", "sql"), ("go",), ()], [("python", "java"), (), ("rust",)])

    assert metrics["tp"] == 1
    assert metrics["fp"] == 2
    assert metrics["fn"] == 2
    assert metrics["precision"] == pytest.approx(1 / 3)
    assert metrics["recall"] == pytest.approx(1 / 3)
    assert metrics["f1"] == pytest.approx(1 / 3)


def test_exact_span_metrics_count_duplicate_mentions() -> None:
    metrics = score_items(
        [[("python", "description", 0, 6), ("python", "description", 8, 14)]],
        [[("python", "description", 0, 6)]],
    )

    assert metrics == {
        "tp": 1,
        "fp": 0,
        "fn": 1,
        "precision": 1.0,
        "recall": 0.5,
        "f1": pytest.approx(2 / 3),
    }


def test_exact_label_metrics_include_abstentions_macro_f1_and_classes() -> None:
    metrics = score_exact_labels(
        ["data_engineer", "software_engineer", None, None],
        ["data_engineer", None, "data_scientist", None],
        ["one", "two", "three", "four"],
    )

    assert metrics["accuracy"] == 0.5
    assert metrics["abstention_rate"] == 0.5
    assert metrics["macro_f1"] == pytest.approx(1 / 3)
    assert set(metrics["per_class"]) == {"data_engineer", "data_scientist", "software_engineer"}


def test_corpus_loads_canonical_labels_and_valid_gold_spans() -> None:
    corpus = load_corpus(CORPUS)

    assert corpus["manifest"]["license"] == "CC0-1.0"
    assert len(corpus["examples"]) == 24
    for example in corpus["examples"]:
        assert set(example["labels"]) == {"role", "seniority", "location", "skills", "skill_spans"}
        assert example["labels"]["role"] != "product_manager"
        assert example["labels"]["role"] != "devops_engineer"
        for span in example["labels"]["skill_spans"]:
            assert example[span["source"]][span["start"] : span["end"]] == span["text"]


def test_baseline_report_has_required_sections_and_expected_metrics() -> None:
    report = evaluate_corpus(load_corpus(CORPUS))

    assert report["corpus"]["size"] == 24
    assert report["extraction_methods"] == ["alias", "regex"]
    assert set(report["versions"]) == {
        "catalog",
        "normalization",
        "extraction",
        "taxonomy_manifest_hash",
    }
    assert report["versions"]["taxonomy_manifest_hash"] == (
        "04d9fe6870cc20d03e77ed4c95aa5b8222478882581e8795f429fd9dff5a09b3"
    )
    assert report["skills"]["tp"] == 71
    assert report["skills"]["fp"] == 4
    assert report["skills"]["fn"] == 0
    assert report["skills"]["macro_f1"] == pytest.approx(17 / 18)
    assert report["exact_spans"]["tp"] == 75
    assert report["exact_spans"]["fp"] == 4
    assert report["exact_spans"]["fn"] == 0
    assert report["role"]["accuracy"] == 1.0
    assert report["seniority"]["accuracy"] == pytest.approx(20 / 24)
    assert report["ambiguity"] == {"role": 1, "seniority": 0, "location": 2}
    assert report["cohorts"]


def test_module_command_writes_report(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "tech_market_backend.taxonomy.evaluation_cli",
            "--corpus",
            str(CORPUS),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(output.read_text(encoding="utf-8"))["corpus"]["size"] == 24
