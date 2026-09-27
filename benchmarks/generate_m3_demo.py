import argparse
import ctypes
import json
import os
import platform
import statistics
import time
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Any, ClassVar

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from tech_market_backend.analytics.persistence import AnalyticsPersistence
from tech_market_backend.ingestion.contracts import PermissionManifest
from tech_market_backend.ingestion.service import IngestionService
from tech_market_backend.platform.database import create_database_engine, session_factory
from tech_market_backend.platform.models import (
    AnalyticsRun,
    AnalyticsRunMember,
    CorpusSnapshot,
    CorpusSnapshotMember,
    JobSnapshot,
    MarketStatistic,
)
from tech_market_backend.taxonomy.service import TaxonomyService
from tech_market_backend.taxonomy.versions import (
    CATALOG_VERSION,
    EXTRACTION_VERSION,
    NORMALIZATION_VERSION,
)

CUTOFF = datetime.fromisoformat("2026-09-20T00:00:00+00:00")
QUERIES = {
    "snapshot_members": (
        "SELECT job_snapshot_id FROM corpus_snapshot_members "
        "WHERE corpus_snapshot_id = :snapshot ORDER BY job_snapshot_id LIMIT 100"
    ),
    "skill_statistics": (
        "SELECT id, value, numerator, denominator FROM market_statistics "
        "WHERE metric_key = 'skill_prevalence' AND analytics_run_id = :run "
        "ORDER BY value DESC, id LIMIT 100"
    ),
    "evidence": (
        "SELECT js.id, js.title, js.company, rr.content_hash FROM job_snapshots js "
        "JOIN raw_records rr ON rr.id = js.raw_record_id "
        "JOIN corpus_snapshot_members csm ON csm.job_snapshot_id = js.id "
        "WHERE csm.corpus_snapshot_id = :snapshot AND js.id = :evidence"
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    database = make_url(args.database_url).database or ""
    if "test" not in database.casefold():
        parser.error("database name must contain 'test'")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", args.database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_database_engine(args.database_url)
    sessions = session_factory(engine)
    fixture = Path("data/fixtures/m3-demo-jobs.json")
    manifest = PermissionManifest.model_validate_json(
        Path("data/manifests/m3-demo-jobs.json").read_text(encoding="utf-8")
    )
    imported = IngestionService(sessions).import_file(fixture, manifest)
    with sessions() as session:
        snapshot_ids = list(
            session.scalars(
                select(JobSnapshot.id)
                .where(JobSnapshot.observed_at <= CUTOFF)
                .order_by(JobSnapshot.id)
            )
        )
    taxonomy = TaxonomyService(sessions)
    for snapshot_id in snapshot_ids:
        taxonomy.normalize_snapshot(snapshot_id)
    versions = {
        "taxonomy": CATALOG_VERSION,
        "normalization": NORMALIZATION_VERSION,
        "extraction": EXTRACTION_VERSION,
    }
    run_id = AnalyticsPersistence(sessions).publish(
        CUTOFF, versions, ("backend_engineer", "data_engineer")
    )
    report = build_report(engine, sessions, run_id, imported, args.iterations)
    args.json_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.markdown_output.write_text(markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "analytics_run_id": str(run_id),
                "corpus_snapshot_id": report["corpus"]["snapshot_id"],
            },
            sort_keys=True,
        )
    )
    engine.dispose()


def build_report(
    engine: Any, sessions: Any, run_id: Any, imported: Any, iterations: int
) -> dict[str, Any]:
    with sessions() as session:
        run = session.get(AnalyticsRun, run_id)
        if run is None:
            raise RuntimeError("analytics run missing")
        corpus = session.get(CorpusSnapshot, run.corpus_snapshot_id)
        if corpus is None:
            raise RuntimeError("corpus snapshot missing")
        statistics_rows = list(
            session.scalars(
                select(MarketStatistic)
                .where(MarketStatistic.analytics_run_id == run_id)
                .order_by(MarketStatistic.metric_key, MarketStatistic.id)
            )
        )
        current_count = session.scalar(
            select(func.count())
            .select_from(CorpusSnapshotMember)
            .where(CorpusSnapshotMember.corpus_snapshot_id == corpus.id)
        )
        evidence_id = session.scalar(
            select(CorpusSnapshotMember.job_snapshot_id)
            .where(CorpusSnapshotMember.corpus_snapshot_id == corpus.id)
            .order_by(CorpusSnapshotMember.job_snapshot_id)
            .limit(1)
        )
        run_members = list(
            session.scalars(
                select(AnalyticsRunMember)
                .where(AnalyticsRunMember.analytics_run_id == run_id)
                .order_by(AnalyticsRunMember.job_id)
            )
        )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in statistics_rows:
        grouped.setdefault(row.metric_key, []).append(
            {
                "dimensions": row.dimensions,
                "numerator": row.numerator,
                "denominator": row.denominator,
                "value": float(row.value),
                "warning": row.coverage_warning,
                "metadata": row.metadata_,
            }
        )
    for values in grouped.values():
        values.sort(
            key=lambda item: (-item["value"], json.dumps(item["dimensions"], sort_keys=True))
        )
    benchmark = benchmark_queries(
        engine,
        {
            "snapshot": corpus.id,
            "run": run_id,
            "evidence": evidence_id,
            "corpus_count": corpus.job_count,
        },
        iterations,
    )
    return {
        "title": "Synthetic M3 deterministic analytics engineering report",
        "synthetic": True,
        "fixture": "data/fixtures/m3-demo-jobs.json",
        "license": "CC0-1.0",
        "ingestion": {
            "accepted": imported.accepted,
            "duplicates": imported.duplicates,
            "failures": imported.failures,
        },
        "corpus": {
            "logical_job_count": corpus.job_count,
            "current_snapshot_count": current_count,
            "source_cutoff": corpus.source_cutoff.isoformat(),
            "snapshot_id": str(corpus.id),
            "membership_hash": corpus.membership_hash,
        },
        "analytics": {
            "run_id": str(run_id),
            "result_hash": run.result_hash,
            "versions": {
                "publication": run.metric_version,
                "taxonomy": run.taxonomy_version,
                "normalization": run.normalization_version,
                "extraction": run.extraction_version,
            },
            "role_pair": run.parameters.get("role_pair"),
            "roles": counts(row.role or "unknown" for row in run_members),
            "work_arrangements": counts(row.work_arrangement or "unknown" for row in run_members),
            "top_skills": grouped.get("skill_prevalence", []),
            "locations_and_work_modes": grouped.get("location_distribution", []),
            "role_comparison": grouped.get("role_comparison", []),
            "cooccurrences": grouped.get("skill_cooccurrence", [])[:10],
        },
        "benchmark": benchmark,
        "limitations": [
            "All records are synthetic and cannot support real labor-market claims.",
            "Six logical jobs are too small for representative inference.",
            "Observed dates and revisions are fixture-authored, not live-source history.",
            "Timings are local single-process measurements, not production load tests.",
        ],
    }


def counts(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def benchmark_queries(engine: Any, params: dict[str, Any], iterations: int) -> dict[str, Any]:
    output: dict[str, Any] = {}
    with engine.connect() as connection:
        for name, query in QUERIES.items():
            started = time.perf_counter()
            connection.execute(text(query), params).all()
            cold_ms = (time.perf_counter() - started) * 1000
            durations = []
            for _ in range(iterations):
                started = time.perf_counter()
                connection.execute(text(query), params).all()
                durations.append((time.perf_counter() - started) * 1000)
            plan = connection.execute(
                text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"), params
            ).scalar_one()
            output[name] = {
                "cold_ms": cold_ms,
                "warm_runs": iterations,
                "p50_ms": statistics.median(durations),
                "p95_ms": percentile(durations, 0.95),
                "plan": plan,
            }
    return {
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "cpu_logical_count": os.cpu_count(),
            "ram_bytes": total_ram(),
            "corpus_count": params["corpus_count"],
            "cold_runs": 1,
            "warm_runs_per_query": iterations,
        },
        "queries": output,
    }


def percentile(values: list[float], fraction: float) -> float:
    return sorted(values)[max(0, ceil(len(values) * fraction) - 1)]


def total_ram() -> int | None:
    if platform.system() != "Windows":
        return None

    class MemoryStatus(ctypes.Structure):
        _fields_: ClassVar[list[tuple[str, Any]]] = [
            ("length", ctypes.c_ulong),
            ("load", ctypes.c_ulong),
            ("total", ctypes.c_ulonglong),
            ("available", ctypes.c_ulonglong),
            ("page_total", ctypes.c_ulonglong),
            ("page_available", ctypes.c_ulonglong),
            ("virtual_total", ctypes.c_ulonglong),
            ("virtual_available", ctypes.c_ulonglong),
            ("extended_available", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    return (
        status.total if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else None
    )


def markdown(report: dict[str, Any]) -> str:
    analytics = report["analytics"]
    corpus = report["corpus"]
    lines = [
        "# Synthetic M3 Analytics Engineering Report",
        "",
        "**Synthetic evidence only. No real market claims.**",
        "",
        f"- Corpus snapshot: `{corpus['snapshot_id']}`",
        f"- Analytics run: `{analytics['run_id']}`",
        f"- Membership hash: `{corpus['membership_hash']}`",
        f"- Result hash: `{analytics['result_hash']}`",
        (
            "- Logical jobs/current snapshots: "
            f"{corpus['logical_job_count']} / {corpus['current_snapshot_count']}"
        ),
        f"- Role pair: {analytics['role_pair']}",
        f"- Roles: {analytics['roles']}",
        f"- Work arrangements: {analytics['work_arrangements']}",
        "",
        "## Top skills",
    ]
    for row in analytics["top_skills"]:
        dimensions = row["dimensions"]
        lines.append(
            f"- {dimensions['skill']}: {row['numerator']}/{row['denominator']} ({row['value']:.4f})"
        )
    lines.extend(["", "## Locations"])
    for row in analytics["locations_and_work_modes"]:
        lines.append(f"- {row['dimensions']['location']}: {row['numerator']}/{row['denominator']}")
    lines.extend(["", "## Role comparison"])
    for row in analytics["role_comparison"]:
        metadata = row.get("metadata", {})
        lines.append(
            f"- {row['dimensions']}: "
            f"{metadata.get('left_numerator', 0)}/{metadata.get('left_denominator', 0)} vs "
            f"{metadata.get('right_numerator', 0)}/{metadata.get('right_denominator', 0)}"
        )
    lines.extend(["", "## Top co-occurrences"])
    for row in analytics["cooccurrences"]:
        dimensions = row["dimensions"]
        lines.append(
            f"- {dimensions['skill_a']} + {dimensions['skill_b']}: "
            f"{row['numerator']}/{row['denominator']}"
        )
    lines.extend(["", "## Query benchmark"])
    for name, result in report["benchmark"]["queries"].items():
        lines.append(
            f"- {name}: cold {result['cold_ms']:.4f} ms; "
            f"warm p50 {result['p50_ms']:.4f} ms; p95 {result['p95_ms']:.4f} ms "
            f"({result['warm_runs']} runs)"
        )
    lines.extend(["", "## Versions"])
    for key, value in analytics["versions"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
