import argparse
import os
from datetime import datetime

from tech_market_backend.analytics.persistence import AnalyticsPersistence
from tech_market_backend.platform.database import create_database_engine, session_factory
from tech_market_backend.taxonomy.versions import (
    CATALOG_VERSION,
    EXTRACTION_VERSION,
    NORMALIZATION_VERSION,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--left-role")
    parser.add_argument("--right-role")
    args = parser.parse_args()
    if bool(args.left_role) != bool(args.right_role):
        parser.error("--left-role and --right-role must be supplied together")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required")
    cutoff = datetime.fromisoformat(args.cutoff.replace("Z", "+00:00"))
    run_id = AnalyticsPersistence(session_factory(create_database_engine(database_url))).publish(
        cutoff,
        {
            "taxonomy": CATALOG_VERSION,
            "normalization": NORMALIZATION_VERSION,
            "extraction": EXTRACTION_VERSION,
        },
        (args.left_role, args.right_role) if args.left_role else None,
    )
    print(run_id)


if __name__ == "__main__":
    main()
