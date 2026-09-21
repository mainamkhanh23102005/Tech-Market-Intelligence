import argparse
import json
import os
import time
import tracemalloc
from pathlib import Path

from tech_market_backend.ingestion.contracts import PermissionManifest
from tech_market_backend.ingestion.service import IngestionService
from tech_market_backend.platform.database import create_database_engine, session_factory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--database-url", default=os.getenv("BENCHMARK_DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or BENCHMARK_DATABASE_URL is required")
    manifest = PermissionManifest.model_validate_json(
        Path("data/manifests/synthetic-jobs.json").read_text(encoding="utf-8")
    )
    engine = create_database_engine(args.database_url)
    tracemalloc.start()
    started = time.perf_counter()
    result = IngestionService(session_factory(engine)).import_file(args.input, manifest)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    print(
        json.dumps(
            {
                "records": result.accepted,
                "duplicates": result.duplicates,
                "failures": result.failures,
                "seconds": elapsed,
                "records_per_second": result.accepted / elapsed,
                "peak_memory_bytes": peak,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
