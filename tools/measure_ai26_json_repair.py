#!/usr/bin/env python3
"""Measure the *shipped* repair ladder against the captured failures.

Imports the repository's own ``laclaugpt_data_analysis.llm.json_repair`` (not a copy)
so the number quoted in the issue is the number the code produces.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

from laclaugpt_data_analysis.llm.json_repair import (
    join_repairs,
    repaired_candidate,
)


def load_env(path: str) -> None:
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def main() -> int:
    load_env(os.environ.get("AI26_ENV", "/mnt/workspace/LaclauGPT-Private/analysis/ai26/laskin.env"))
    from pymongo import MongoClient

    client = MongoClient(os.environ["LACLAUGPT_MONGODB_URI"], serverSelectionTimeoutMS=8000)
    db = client[os.environ.get("LACLAUGPT_MONGODB_DATABASE", "laclaugpt")]
    failures = db["ai26__analysis_failures"]

    docs = list(
        failures.find({"error": {"$regex": "^JSONDecodeError"}, "response_raw": {"$exists": True}})
    )
    ladder: Counter = Counter()
    applied_counts: Counter = Counter()
    for doc in docs:
        raw = doc.get("response_raw") or ""
        if not raw:
            continue
        text, applied = repaired_candidate(raw)
        applied_counts[join_repairs(applied) or "none"] += 1
        try:
            json.loads(text)
        except Exception:
            ladder["unrecovered"] += 1
            continue
        ladder["recovered_by_repair" if applied else "recovered_strict"] += 1

    total = sum(ladder.values())
    recovered = total - ladder["unrecovered"]
    print("captured JSONDecodeErrors:", len(docs))
    print("ladder:", dict(ladder.most_common()))
    print(f"recovered {recovered}/{total} = {100 * recovered / max(total, 1):.1f}%")
    print("repairs applied:", dict(applied_counts.most_common(8)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
