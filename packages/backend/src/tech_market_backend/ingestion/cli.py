import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from tech_market_backend.ingestion.contracts import PermissionManifest
from tech_market_backend.ingestion.provenance import inspect_provenance
from tech_market_backend.ingestion.service import ImportResult, IngestionService
from tech_market_backend.platform.database import create_database_engine, session_factory


def main() -> None:
    parser = argparse.ArgumentParser(prog="tech-market-ingestion")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("import")
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--manifest", required=True, type=Path)
    provenance = subparsers.add_parser("provenance")
    identity = provenance.add_mutually_exclusive_group(required=True)
    identity.add_argument("--job-id", type=UUID)
    identity.add_argument("--snapshot-id", type=UUID)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    engine = create_database_engine(args.database_url)
    sessions = session_factory(engine)
    if args.command == "import":
        manifest = PermissionManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        import_result = IngestionService(sessions).import_file(args.path, manifest)
        print(json.dumps(_result_payload(import_result), sort_keys=True))
        return
    with sessions() as session:
        provenance_result = inspect_provenance(
            session, job_id=args.job_id, snapshot_id=args.snapshot_id
        )
    if provenance_result is None:
        raise SystemExit("provenance not found")
    print(json.dumps(provenance_result, sort_keys=True))


def _result_payload(result: ImportResult) -> dict[str, int | str]:
    return {
        "run_id": str(result.run_id),
        "accepted": result.accepted,
        "duplicates": result.duplicates,
        "failures": result.failures,
    }


if __name__ == "__main__":
    main()
