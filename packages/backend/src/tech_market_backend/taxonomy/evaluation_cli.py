import argparse
import json
from pathlib import Path

from .evaluation import write_report

DEFAULT_CORPUS = Path("data/benchmarks/extraction/corpus.json")
DEFAULT_REPORT = Path("data/benchmarks/extraction/report.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = write_report(args.corpus, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
