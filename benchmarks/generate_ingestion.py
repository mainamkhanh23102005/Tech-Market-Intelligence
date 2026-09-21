import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def generate(count: int, destination: Path) -> None:
    records = [
        {
            "source_id": f"benchmark-{number:05d}",
            "canonical_url": f"https://example.invalid/benchmark/{number}",
            "title": "Synthetic Benchmark Engineer",
            "company": "Synthetic Benchmark Company",
            "location": "Remote",
            "description": f"Synthetic benchmark record {number}.",
            "observed_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            "metadata": {"synthetic": True},
        }
        for number in range(count)
    ]
    destination.write_text(json.dumps(records, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("count", choices=(1000, 10000), type=int)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    generate(args.count, args.destination)


if __name__ == "__main__":
    main()
