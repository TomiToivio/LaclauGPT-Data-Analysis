#!/usr/bin/env python3
"""Offline AI26 research-record contract check against sibling repositories.

Non-destructive: reads public JSON schemas only; needs no credentials or services.
Exit 0 means strict schema versions and top-level required fields agree, *not*
that Mongo routing, field semantics or an end-to-end deployment was tested.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def contract(root: Path) -> tuple[str, set[str]]:
    path = root / "schemas" / "research-record.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    version = schema["properties"]["schema_version"]["const"]
    return version, set(schema["required"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--visualization", type=Path, required=True)
    args = parser.parse_args()
    paths = {"analysis": args.analysis, "collection": args.collection, "visualization": args.visualization}
    try:
        results = {name: contract(root) for name, root in paths.items()}
    except (OSError, KeyError, ValueError, TypeError) as error:
        print(f"Contract check cannot read/parse schema: {error}", file=sys.stderr)
        return 2
    for name, (version, fields) in results.items():
        print(f"{name}: schema_version={version}, required={','.join(sorted(fields))}")
    versions = {value[0] for value in results.values()}
    fields = {frozenset(value[1]) for value in results.values()}
    if len(versions) != 1 or len(fields) != 1:
        print("FAIL: strict cross-repository research-record schema mismatch", file=sys.stderr)
        return 1
    print("PASS: exact schema-version and top-level required-field agreement (offline only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
