"""AI26 command line: read the pipeline, its prompts and its contracts without a model call.

Issue #341 asks that each step be understandable and reviewable, and specifically that the
*exact effective prompt* be inspectable at the CLI without calling a model. This module does
that and nothing else.

Read-only by construction:

* it claims no work, writes no research data and mutates no configuration;
* it imports no provider and never calls a model;
* every subcommand supports ``--json`` so a cron job or a human reads the same facts.

The step list is the module map in :mod:`laclaugpt_data_analysis.stages`, which is the
pipeline that actually runs. The 0-9 numbering in the issue is a *reading order* over the
same work; ``stages`` prints both so the mapping never has to be guessed.

Usage::

    python -m laclaugpt_data_analysis.ai26 stages
    python -m laclaugpt_data_analysis.ai26 stages --json
    python -m laclaugpt_data_analysis.ai26 render-prompt --stage discourse --profile ai26
    python -m laclaugpt_data_analysis.ai26 render-prompt --stage discourse --show --profile ai26
    python -m laclaugpt_data_analysis.ai26 contract --project-config config/projects/ai26.yaml
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parent
PROMPT_DIR = PACKAGE / "prompts"

#: The canonical pipeline, in reading order, as the modules that implement it.
CANONICAL_STEPS: tuple[str, ...] = (
    "preprocess",
    "frame",
    "summary",
    "laclau",
    "postprocess",
    "graph",
    "evidence",
)

#: The issue's proposed stage numbers, mapped onto those modules. Stages 7-9 are the
#: experimental Phase 2 tail and stage 0 is Collection's handoff, so neither is a module here.
STAGE_NUMBERS: dict[str, tuple[int, ...]] = {
    "handoff": (0,),
    "preprocess": (1,),
    "frame": (2,),
    "summary": (4,),
    "laclau": (6,),
    "postprocess": (5,),
    "graph": (9,),
    "evidence": (5,),
    "dna": (7,),
    "sna": (8,),
}

PHASE_STATUS = {
    "handoff": "Collection handoff (issue #271 contract)",
    "preprocess": "phase_1",
    "frame": "phase_1_optional_media",
    "summary": "phase_1",
    "laclau": "phase_1",
    "postprocess": "phase_1",
    "graph": "phase_1_export",
    "evidence": "phase_1_integrity",
    "dna": "experimental_phase_2",
    "sna": "experimental_phase_2",
}


def _first_docstring_line(module_name: str) -> str:
    """Return a stage module's own summary, or why it could not be read."""
    try:
        module = importlib.import_module(f"{__package__}.stages.{module_name}")
    except Exception as exc:  # pragma: no cover - depends on optional runtime deps
        return f"not importable here: {type(exc).__name__}"
    doc = (module.__doc__ or "").strip()
    return doc.splitlines()[0].strip() if doc else ""


def _prompt_record(stage: str, profile: str) -> dict[str, Any]:
    """Return the prompt ids for a stage, and the files behind them when they exist."""
    from laclaugpt_data_analysis.stages.prompt_map import prompt_ids_for_stage

    system_id, task_id = prompt_ids_for_stage(profile, stage)
    record: dict[str, Any] = {
        "stage": stage,
        "profile": profile,
        "system_prompt_id": system_id,
        "task_prompt_id": task_id,
        "files": [],
    }
    for prompt_id in (system_id, task_id):
        candidate = PROMPT_DIR / f"{prompt_id}.md"
        if candidate.exists():
            payload = candidate.read_bytes()
            record["files"].append(
                {
                    "prompt_id": prompt_id,
                    "path": str(candidate.relative_to(REPOSITORY_ROOT)),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "chars": len(payload),
                }
            )
    return record


def _read_prompt_text(prompt_id: str) -> str:
    candidate = PROMPT_DIR / f"{prompt_id}.md"
    if not candidate.exists():
        raise FileNotFoundError(candidate)
    return candidate.read_text(encoding="utf-8")


def _cmd_stages(args: argparse.Namespace) -> int:
    rows = []
    for name in CANONICAL_STEPS:
        rows.append(
            {
                "module": name,
                "stages": list(STAGE_NUMBERS.get(name, ())),
                "phase_status": PHASE_STATUS.get(name, "unknown"),
                "summary": _first_docstring_line(name),
            }
        )
    payload = {
        "canonical_steps": list(CANONICAL_STEPS),
        "stages": rows,
        "note": (
            "The module map is what runs. The stage numbers are the issue's reading order; "
            "experimental Phase 2 steps (dna, sna) are separate and never block Phase 1."
        ),
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print("AI26 canonical pipeline (read-only view; no model is called)")
    print()
    for row in rows:
        numbers = ",".join(str(n) for n in row["stages"]) or "-"
        print(f"  stage {numbers:>4}  {row['module']:<12} [{row['phase_status']}]")
        if row["summary"]:
            print(f"                 {row['summary']}")
    print()
    print(payload["note"])
    return 0


def _cmd_render_prompt(args: argparse.Namespace) -> int:
    try:
        record = _prompt_record(args.stage, args.profile)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.show:
        for prompt_id in (record["system_prompt_id"], record["task_prompt_id"]):
            print(f"### {prompt_id}")
            try:
                print(_read_prompt_text(prompt_id))
            except FileNotFoundError:
                print(f"(no prompt file at prompts/{prompt_id}.md)")
            print()
        return 0
    if args.json:
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0
    print(f"stage {record['stage']} (profile {record['profile']}):")
    print(f"  system prompt id: {record['system_prompt_id']}")
    print(f"  task prompt id:   {record['task_prompt_id']}")
    for item in record["files"]:
        print(f"  {item['path']}  sha256={item['sha256'][:16]}...  {item['chars']} chars")
    if not record["files"]:
        print("  (no prompt markdown found under prompts/; ids are still recorded in provenance)")
    return 0


def _cmd_contract(args: argparse.Namespace) -> int:
    path = Path(args.project_config)
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    if not path.exists():
        print(f"error: project config not found: {path}", file=sys.stderr)
        return 2
    import yaml

    from laclaugpt_data_analysis.stage_contract import resolve_stage_contract

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    contract = resolve_stage_contract(payload)
    if args.json:
        print(json.dumps(contract, indent=2, ensure_ascii=False, default=str))
        return 0
    print(f"stage contract resolved from {path.relative_to(REPOSITORY_ROOT)}:")
    for key, value in contract.items():
        print(f"  {key}: {value}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    configs = {
        "project": REPOSITORY_ROOT / "config/projects/ai26.yaml",
        "machine": REPOSITORY_ROOT / "config/machines/laskin.yaml",
        "execution": REPOSITORY_ROOT / "config/execution/laskin-cron.yaml",
    }
    payload = {
        "read_only": True,
        "calls_a_model": False,
        "configs": {
            name: {"path": str(path.relative_to(REPOSITORY_ROOT)), "present": path.exists()}
            for name, path in configs.items()
        },
        "canonical_steps": list(CANONICAL_STEPS),
        "phase2_steps": ["dna", "sna"],
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print("AI26 status (read-only; claims no work, calls no model)")
    for name, item in payload["configs"].items():
        print(f"  {name:<9} {'present' if item['present'] else 'MISSING'}  {item['path']}")
    print(f"  steps     {len(CANONICAL_STEPS)} canonical; Phase 2 separate: {', '.join(payload['phase2_steps'])}")
    print()
    print("Run `ai26 stages` for the map, `ai26 render-prompt --stage <s>` to review a prompt.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m laclaugpt_data_analysis.ai26",
        description=(
            "Read the AI26 pipeline, its prompt mapping and its stage contract. "
            "Read-only: no work is claimed, no research data is written and no model is called."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    stages = subparsers.add_parser("stages", help="the canonical step map with phase status")
    stages.add_argument("--json", action="store_true", help="machine-readable output")
    stages.set_defaults(func=_cmd_stages)

    prompts = subparsers.add_parser(
        "render-prompt", help="the prompt ids for a stage, with hashes; --show prints the text"
    )
    prompts.add_argument("--stage", required=True, help="frame, summary or discourse")
    prompts.add_argument("--profile", default="ai26", help="corpus profile (default: ai26)")
    prompts.add_argument("--show", action="store_true", help="print the prompt text itself")
    prompts.add_argument("--json", action="store_true", help="machine-readable output")
    prompts.set_defaults(func=_cmd_render_prompt)

    contract = subparsers.add_parser("contract", help="resolve the stage contract for a project")
    contract.add_argument(
        "--project-config", default="config/projects/ai26.yaml", help="path to a project config"
    )
    contract.add_argument("--json", action="store_true", help="machine-readable output")
    contract.set_defaults(func=_cmd_contract)

    status = subparsers.add_parser("status", help="which configs exist, and what is read-only")
    status.add_argument("--json", action="store_true", help="machine-readable output")
    status.set_defaults(func=_cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
