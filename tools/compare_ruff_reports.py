"""Compare Ruff JSON reports from two checkouts by repository-relative path."""

import json
import sys
from collections import Counter
from pathlib import Path


def diagnostics(report: Path, checkout: Path):
    """Yield a stable fingerprint and location for each lint finding."""
    for item in json.loads(report.read_text(encoding="utf-8")):
        filename = Path(item["filename"]).relative_to(checkout)
        yield (filename, item["code"], item["message"]), item["location"]


def main(base_report: Path, base_root: Path, head_report: Path, head_root: Path) -> int:
    """Print findings exceeding the base count, allowing line numbers to shift."""
    remaining = Counter(key for key, _ in diagnostics(base_report, base_root))
    new_count = 0
    for key, location in diagnostics(head_report, head_root):
        if remaining[key]:
            remaining[key] -= 1
            continue
        filename, code, message = key
        print(f"{filename}:{location['row']}:{location['column']}: {code} {message}")
        new_count += 1
    print(f"{new_count} new Ruff violation(s).")
    return int(new_count > 0)


if __name__ == "__main__":
    raise SystemExit(main(*map(Path, sys.argv[1:])))
