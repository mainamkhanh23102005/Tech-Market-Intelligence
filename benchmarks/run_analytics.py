import argparse
import json
import platform
import statistics
import time
from math import ceil
from pathlib import Path

from sqlalchemy import Connection, create_engine, text

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

RUN_SNAPSHOT_QUERY = (
    "SELECT corpus_snapshot_id FROM analytics_runs WHERE id = :run AND status = 'SUCCEEDED'"
)


def validate_run_snapshot(connection: Connection, snapshot: str, run: str) -> None:
    """Reject benchmark inputs that would mix a run with another corpus."""
    run_snapshot = connection.execute(text(RUN_SNAPSHOT_QUERY), {"run": run}).scalar_one_or_none()
    if run_snapshot is None or str(run_snapshot) != snapshot:
        raise ValueError("Selected analytics run does not belong to requested corpus snapshot")


def run_benchmark(
    connection: Connection, params: dict[str, str], iterations: int
) -> dict[str, dict[str, object]]:
    validate_run_snapshot(connection, params["snapshot"], params["run"])
    queries: dict[str, dict[str, object]] = {}
    for name, query in QUERIES.items():
        plan = connection.execute(
            text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"), params
        ).scalar_one()
        durations = []
        for _ in range(iterations):
            started = time.perf_counter()
            connection.execute(text(query), params).all()
            durations.append((time.perf_counter() - started) * 1000)
        queries[name] = {
            "p50_ms": statistics.median(durations),
            "p95_ms": percentile(durations, 0.95),
            "plan": plan,
        }
    return queries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = create_engine(args.database_url)
    params = {"snapshot": args.snapshot, "run": args.run, "evidence": args.evidence}
    report = {
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "iterations": args.iterations,
        },
        "queries": {},
    }
    with engine.connect() as connection:
        report["queries"] = run_benchmark(connection, params, args.iterations)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")


def percentile(values: list[float], fraction: float) -> float:
    return sorted(values)[max(0, ceil(len(values) * fraction) - 1)]


if __name__ == "__main__":
    main()
