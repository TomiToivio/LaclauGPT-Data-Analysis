"""`laclaugpt-analysis-pipelines` — list, inspect and check registered pipelines (#399).

Selection must be explicit and inspectable. This CLI is deliberately read-only: it does
not run a pipeline, so asking "what is registered?" can never start work by accident.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import check_pipeline, get_pipeline, list_pipelines, pipeline_namespace, snapshot_digest


def _cmd_list(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps([
            {
                "pipeline_id": s.pipeline_id,
                "display_name": s.display_name,
                "version": s.version,
                "stages": len(s.stages),
                "source_ref": s.source_ref,
            }
            for s in list_pipelines()
        ], indent=2))
        return 0
    width = max(len(s.pipeline_id) for s in list_pipelines())
    for spec in list_pipelines():
        print(f"{spec.pipeline_id:<{width}}  {spec.display_name:<32} "
              f"{len(spec.stages):>2} stages  {spec.version[:12]}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    spec = get_pipeline(args.pipeline_id)
    payload = {
        "pipeline_id": spec.pipeline_id,
        "display_name": spec.display_name,
        "version": spec.version,
        "source_repository": spec.source_repository,
        "source_ref": spec.source_ref,
        "license": spec.license,
        "snapshot_digest": snapshot_digest(spec.pipeline_id),
        "stages": list(spec.stages),
        "requires": list(spec.requires),
        "entry_module": spec.entry_module,
        "notes": spec.notes,
    }
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    report = check_pipeline(args.pipeline_id)
    print(json.dumps(report, indent=2))
    if args.strict:
        return 0 if report["selectable"] else 1
    return 0


def _cmd_namespace(args: argparse.Namespace) -> int:
    print(json.dumps(pipeline_namespace(args.pipeline_id, args.run_id), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="laclaugpt-analysis-pipelines", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list registered pipelines")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="show one pipeline's identity and provenance")
    p_show.add_argument("pipeline_id")
    p_show.set_defaults(func=_cmd_show)

    p_check = sub.add_parser("check", help="verify stages exist and the entry module imports")
    p_check.add_argument("pipeline_id")
    p_check.add_argument("--strict", action="store_true", help="exit non-zero unless selectable")
    p_check.set_defaults(func=_cmd_check)

    p_ns = sub.add_parser("namespace", help="show the durable keys for a pipeline and run")
    p_ns.add_argument("pipeline_id")
    p_ns.add_argument("--run-id", required=True)
    p_ns.set_defaults(func=_cmd_namespace)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
