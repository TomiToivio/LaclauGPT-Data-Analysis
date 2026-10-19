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

#: The machine-readable stage registry is the single source of truth for the step list
#: (issue #341). Everything below is a derived view of it, so the map the CLI prints cannot
#: drift from the map the repository declares.
REGISTRY_PATH = PACKAGE / "stages" / "registry.json"


def load_stage_registry() -> dict[str, Any]:
    """Read the stage registry. Raises if the packaged file is missing or malformed."""
    with open(REGISTRY_PATH, encoding="utf-8") as stream:
        registry = json.load(stream)
    if registry.get("format") != "laclaugpt.ai26.stage_registry":
        raise ValueError("Unsupported stage registry format")
    if not registry.get("canonical_stages"):
        raise ValueError("Stage registry declares no canonical stages")
    return registry


_REGISTRY = load_stage_registry()
_ALL_STAGES: tuple[dict[str, Any], ...] = tuple(
    [*_REGISTRY["canonical_stages"], *_REGISTRY.get("phase_2_stages", [])]
)

#: The canonical pipeline, in reading order, as the modules that implement it.
CANONICAL_STEPS: tuple[str, ...] = tuple(
    stage["id"] for stage in _REGISTRY["canonical_stages"] if stage.get("in_canonical_list")
)

#: The issue's reading-order numbers, as declared in the registry.
STAGE_NUMBERS: dict[str, tuple[int, ...]] = {
    stage["id"]: tuple(stage.get("reading_order") or ()) for stage in _ALL_STAGES
}

PHASE_STATUS: dict[str, str] = {stage["id"]: stage["phase_status"] for stage in _ALL_STAGES}

#: Steps that are explicitly experimental Phase 2 and must never block Phase 1.
PHASE_2_STEPS: tuple[str, ...] = tuple(
    stage["id"] for stage in _REGISTRY.get("phase_2_stages", [])
)

_REGISTRY_BY_ID: dict[str, dict[str, Any]] = {stage["id"]: stage for stage in _ALL_STAGES}


def _first_docstring_line(module_name: str) -> str:
    """Return a stage module's own summary, or why it could not be read."""
    try:
        module = importlib.import_module(f"{__package__}.stages.{module_name}")
    except Exception as exc:  # pragma: no cover - depends on optional runtime deps
        return f"not importable here: {type(exc).__name__}"
    doc = (module.__doc__ or "").strip()
    return doc.splitlines()[0].strip() if doc else ""


def prompt_files(prompt_id: str) -> list[Path]:
    """Every file behind a prompt id.

    A prompt id is ``<family>.<name>`` and its text lives at ``prompts/<family>/<name>_v<n>.md``.
    Versions are research instruments, so all of them are returned rather than one: an
    analysis can be traced to the exact wording that produced it, and a later version never
    erases the record of an earlier run.
    """
    family, _, name = prompt_id.partition(".")
    directory = PROMPT_DIR / family if family else PROMPT_DIR
    if not directory.is_dir():
        return []
    matches = sorted(directory.glob(f"{name}_v*.md"))
    if not matches:
        matches = sorted(directory.glob(f"{name}*.md"))
    return matches


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
        for candidate in prompt_files(prompt_id):
            payload = candidate.read_bytes()
            record["files"].append(
                {
                    "prompt_id": prompt_id,
                    "version": candidate.stem,
                    "path": str(candidate.relative_to(REPOSITORY_ROOT)),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "chars": len(payload),
                }
            )
    return record


def _cmd_stages(args: argparse.Namespace) -> int:
    rows = []
    for name in CANONICAL_STEPS:
        declared = _REGISTRY_BY_ID.get(name, {})
        rows.append(
            {
                "module": name,
                "stages": list(STAGE_NUMBERS.get(name, ())),
                "phase_status": PHASE_STATUS.get(name, "unknown"),
                "requires_media": bool(declared.get("requires_media")),
                "conditional": bool(declared.get("conditional")),
                "prompt_stage": declared.get("prompt_stage"),
                "summary": _first_docstring_line(name) or str(declared.get("summary") or ""),
            }
        )
    payload = {
        "canonical_steps": list(CANONICAL_STEPS),
        "stages": rows,
        "phase_2_steps": list(PHASE_2_STEPS),
        "registry": {
            "path": str(REGISTRY_PATH.relative_to(REPOSITORY_ROOT)),
            "version": _REGISTRY.get("version"),
        },
        "note": _REGISTRY.get("reading_order_note", ""),
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print("AI26 canonical pipeline (read-only view; no model is called)")
    print()
    for row in rows:
        numbers = ",".join(str(n) for n in row["stages"]) or "-"
        flags = " media-optional" if row["conditional"] and row["requires_media"] else ""
        print(f"  stage {numbers:>4}  {row['module']:<12} [{row['phase_status']}]{flags}")
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
    if args.show and args.json:
        # Preserve JSON output even when the researcher requests prompt bodies.
        # This exposes static resource text, not a fully rendered model invocation.
        for item in record["files"]:
            item["text"] = (REPOSITORY_ROOT / item["path"]).read_text(encoding="utf-8")
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0
    if args.show:
        for prompt_id in (record["system_prompt_id"], record["task_prompt_id"]):
            candidates = prompt_files(prompt_id)
            if not candidates:
                print(f"### {prompt_id}\n(no prompt file under prompts/)")
                continue
            for candidate in candidates:
                print(f"### {prompt_id}  [{candidate.stem}]")
                print(candidate.read_text(encoding="utf-8"))
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
        print("  (no prompt markdown under prompts/ for this id; the id is still in provenance)")
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
        "phase2_steps": list(PHASE_2_STEPS),
        "stage_registry": {
            "path": str(REGISTRY_PATH.relative_to(REPOSITORY_ROOT)),
            "version": _REGISTRY.get("version"),
        },
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print("AI26 status (read-only; claims no work, calls no model)")
    for name, item in payload["configs"].items():
        print(f"  {name:<9} {'present' if item['present'] else 'MISSING'}  {item['path']}")
    print(
        f"  steps     {len(CANONICAL_STEPS)} canonical; Phase 2 separate: "
        f"{', '.join(payload['phase2_steps'])}"
    )
    print(f"  registry  {payload['stage_registry']['path']} (v{payload['stage_registry']['version']})")
    print()
    print("Run `ai26 stages` for the map, `ai26 render-prompt --stage <s>` to review a prompt.")
    return 0



def _cmd_step(args: argparse.Namespace) -> int:
    """Inspect one logical step without claiming a task or executing research code.

    A dry-run is intentionally a contract inspection, not a simulation of execution.
    Some logical numbers map to multiple modules, or no executable module at all.
    """
    matches = [
        stage for stage in _ALL_STAGES
        if args.number in stage.get("reading_order", [])
    ]
    if not matches:
        print(f"error: unknown logical AI26 step {args.number}", file=sys.stderr)
        return 2
    if args.limit < 1:
        print("error: --limit must be positive", file=sys.stderr)
        return 2
    payload = {
        "logical_step": args.number,
        "mode": "contract_inspection_only",
        "read_only": True,
        "executed": False,
        "claimed_tasks": 0,
        "project": args.project,
        "machine": args.machine,
        "limit": args.limit,
        "stages": [
            {
                "id": stage["id"],
                "module": stage.get("module"),
                "phase_status": stage["phase_status"],
                "conditional": bool(stage.get("conditional", False)),
                "requires_media": bool(stage.get("requires_media", False)),
                "inputs": stage.get("inputs", []),
                "outputs": stage.get("outputs", []),
            }
            for stage in matches
        ],
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"AI26 logical step {args.number}: dry-run contract inspection only")
        print("No records inspected or claimed; no provider invoked; no outputs written.")
        for stage in payload["stages"]:
            print(f"  {stage['id']} [{stage['phase_status']}] module={stage['module'] or 'none'}")
            if stage["conditional"]:
                print("    conditional: media/handoff applicability is not evaluated")
        print("To execute bounded worker claims, use scripts/ai26_run_next.sh --apply explicitly.")
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

    step = subparsers.add_parser(
        "step",
        help="inspect one logical step without execution (requires --dry-run)",
    )
    step.add_argument("number", type=int, choices=range(10), metavar="{0..9}")
    step.add_argument("--project", choices=("ai26",), default="ai26")
    step.add_argument("--machine", choices=("laskin",), default="laskin")
    step.add_argument("--limit", type=int, default=10)
    step.add_argument("--dry-run", action="store_true", required=True,
                      help="mandatory safety flag: contract inspection, not execution")
    step.add_argument("--json", action="store_true")
    step.set_defaults(func=_cmd_step)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
