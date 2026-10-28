#!/usr/bin/env python3
"""Compare frozen input and stage status of two independently executed EP24 runs.

Read-only: never connects to production services or starts a pipeline.
"""
import argparse
import json
from pathlib import Path


def read(path, pipeline):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"{path}: expected JSON object")
    for field in ("pipeline_id", "run_id", "input_ids", "stage_statuses"):
        if field not in obj:
            raise ValueError(f"{path}: missing {field}")
    if obj["pipeline_id"] != pipeline:
        raise ValueError(f"{path}: expected pipeline {pipeline}")
    if not isinstance(obj["run_id"], str) or not obj["run_id"].strip():
        raise ValueError(f"{path}: invalid run_id")
    ids = obj["input_ids"]
    if not isinstance(ids, list) or not all(isinstance(x, str) and x for x in ids):
        raise ValueError(f"{path}: invalid input_ids")
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate input ids")
    if not isinstance(obj["stage_statuses"], dict):
        raise ValueError(f"{path}: stage_statuses must be a mapping")
    return obj


def compare(current, legacy):
    if current["run_id"] == legacy["run_id"]:
        raise ValueError("Run identities must differ between pipeline versions")
    if set(current["input_ids"]) != set(legacy["input_ids"]):
        raise ValueError("Input sets differ; comparison is not valid")
    return {
        "input_ids": sorted(current["input_ids"]),
        "input_count": len(current["input_ids"]),
        "runs": {
            name: {
                "run_id": item["run_id"],
                "upstream_sha": item.get("upstream_sha"),
                "model": item.get("model"),
                "config_sha256": item.get("config_sha256"),
                "codebook_sha256": item.get("codebook_sha256"),
                "stage_statuses": item["stage_statuses"],
            }
            for name, item in (("ep24", current), ("ep24-legacy", legacy))
        },
        "validation_scope": "Offline manifest comparison only; no live scientific equivalence or storage isolation verified",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--legacy", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = compare(read(args.current, "ep24"), read(args.legacy, "ep24-legacy"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
