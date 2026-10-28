"""`laclaugpt-analysis pipelines ...` — list and inspect selectable pipelines (#399)."""
from __future__ import annotations

import argparse
import json
import sys

from .registry import UnknownPipeline, get_pipeline, list_pipelines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="laclaugpt-analysis")
    sub = parser.add_subparsers(dest="command", required=True)

    pipelines = sub.add_parser("pipelines", help="inspect the pipeline registry")
    pipelines.add_argument("action", choices=["list", "show"])
    pipelines.add_argument("pipeline_id", nargs="?", help="required for 'show'")
    pipelines.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.action == "list":
        specs = list_pipelines()
        if args.json:
            print(json.dumps([spec.pipeline_id for spec in specs], indent=2))
            return 0
        for spec in specs:
            print(f"{spec.pipeline_id:12s} {spec.label}")
            print(f"{'':12s} source: {spec.source_repository} @ {spec.source_ref} ({spec.source_sha[:12]})")
            print(f"{'':12s} stages: {', '.join(spec.stages)}")
        return 0

    if not args.pipeline_id:
        parser.error("'show' needs a pipeline id")
    try:
        spec = get_pipeline(args.pipeline_id)
    except UnknownPipeline as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    payload = {
        "pipeline_id": spec.pipeline_id,
        "label": spec.label,
        "package": spec.package,
        "stages": list(spec.stages),
        "source": {
            "repository": spec.source_repository,
            "ref": spec.source_ref,
            "sha": spec.source_sha,
        },
        "notes": spec.notes,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
