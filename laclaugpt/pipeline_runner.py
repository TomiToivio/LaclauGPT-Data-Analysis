"""Sequencing of the seven human-written analysis steps.

Agent-owned orchestration around the human-owned (locked) step modules (issue #315
step 3). This file decides *when* each step is called and *what is recorded*
about the attempt; it decides nothing about the analysis itself. Every step
function is imported from its own module and called as written.

The sequence the issue fixes:

    preprocess -> frame (only when media is attached) -> summary ->
    postprocess -> Laclau -> DNA -> SNA

Three rules are worth stating because they are scientific, not mechanical:

1. **A media step on a text-only record is skipped, not failed.** The issue makes
   frame analysis conditional on attached images/video; a text-only record is a
   valid record and must not be recorded as an error.
2. **A failed step stops that record's chain.** Running DNA or SNA on a record
   whose summary failed would build a network out of nothing, and would hide the
   original failure behind a plausible-looking later result.
3. **Everything a step produced is recorded with its status and provenance.**
   Later steps, and the researcher, read the same record of what happened.

Steps are injected through ``steps`` so the sequencing can be tested without the
scientific bodies being implemented, and so a test never needs to fake research
output.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline_context import (
    MEDIA_STEP,
    STEP_NAMES,
    PipelineContext,
    StepOutcome,
    StepStatus,
    outcome,
)
from pipeline_models import AnalysisBundle, HumanPipelineRecord

# The pipeline, in the issue's order: (step name, module, function). The module
# and function names are the guarded contract from
# tests/test_issue_315_human_pipeline.py; this tuple only wires them into a run.
STEP_ORDER: tuple[tuple[str, str, str], ...] = (
    ("preprocess", "step_01_preprocess", "preprocess"),
    ("frame", "step_02_frame", "analyze_frames"),
    ("summary", "step_03_summary", "summarize"),
    ("postprocess", "step_04_postprocess", "postprocess"),
    ("laclau", "step_05_laclau", "analyze_laclau"),
    ("dna", "step_06_dna", "analyze_dna"),
    ("sna", "step_07_sna", "analyze_sna"),
)


@dataclass
class PipelineRun:
    """One record's trip through the chain."""

    bundle: AnalysisBundle
    outcomes: list[StepOutcome] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        """Whether any step failed, i.e. the chain stopped early."""
        return any(item.status == StepStatus.FAILED for item in self.outcomes)

    def status_of(self, step: str) -> str | None:
        """The recorded status of ``step`` in this run, if it was attempted."""
        for item in self.outcomes:
            if item.step == step:
                return item.status
        return None


def resolve_steps() -> dict[str, Callable[..., Any]]:
    """Import the seven step functions by name.

    ``laclaugpt/`` is on pytest's ``pythonpath`` and is the script directory when
    the pipeline is run from the command line, so these are top-level modules.
    """
    directory = str(Path(__file__).resolve().parent)
    if directory not in sys.path:
        sys.path.insert(0, directory)

    resolved: dict[str, Callable[..., Any]] = {}
    for name, module_name, function_name in STEP_ORDER:
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
        if not callable(function):
            raise TypeError(f"{module_name}.{function_name} is not callable")
        resolved[name] = function
    return resolved


def _attempt(
    step: str,
    call: Callable[[], Any],
    *,
    context: PipelineContext,
) -> tuple[StepOutcome, Any]:
    """Call one step, converting an exception into a recorded failure."""
    try:
        value = call()
    except NotImplementedError:
        # The step is still the deliberate placeholder for the hand-written
        # method: an unfinished step must never look like a successful one.
        raise
    except Exception as exc:  # the step raised: record and stop this chain
        return outcome(
            step, StepStatus.FAILED, error=f"{type(exc).__name__}: {exc}", context=context
        ), None
    return outcome(step, StepStatus.RAN, output=_as_output(value), context=context), value


def _as_output(value: Any) -> Any:
    """Serialize a step result that is not a Pydantic model (a list of frames)."""
    if isinstance(value, list):
        return {
            "items": [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in value
            ]
        }
    return value if isinstance(value, dict) else None


def run_record(
    record: HumanPipelineRecord,
    *,
    context: PipelineContext | None = None,
    steps: dict[str, Callable[..., Any]] | None = None,
    on_outcome: Callable[[HumanPipelineRecord, StepOutcome], None] | None = None,
) -> PipelineRun:
    """Run the seven steps for one record and record what happened.

    ``steps`` defaults to the real step functions; tests pass stand-ins.
    ``on_outcome`` is called after each step so a caller can persist progress; a
    record that fails at step 3 keeps the results of steps 1 and 2.
    """
    ctx = context or PipelineContext()
    functions = steps if steps is not None else resolve_steps()
    run = PipelineRun(bundle=AnalysisBundle(record=record))

    def emit(item: StepOutcome) -> None:
        run.outcomes.append(item)
        if on_outcome is not None:
            on_outcome(record, item)

    # 1. preprocess
    item, value = _attempt("preprocess", lambda: functions["preprocess"](run.bundle.record), context=ctx)
    emit(item)
    if value is not None:
        run.bundle.record = value
        record = value
    if not item.ok:
        return run

    # 2. frame analysis, only when the record actually carries media
    if run.bundle.record.media:
        item, frames = _attempt("frame", lambda: functions["frame"](run.bundle.record), context=ctx)
    else:
        item, frames = (
            outcome(
                "frame",
                StepStatus.SKIPPED,
                notes=["text-only record: nothing for frame analysis to read"],
                context=ctx,
            ),
            [],
        )
    run.bundle.frames = list(frames or [])
    emit(item)
    if not item.ok:
        return run

    # 3. summary
    item, summary = _attempt(
        "summary", lambda: functions["summary"](run.bundle.record, run.bundle.frames), context=ctx
    )
    run.bundle.summary = summary
    emit(item)
    if not item.ok:
        return run

    # 4. descriptive postprocess
    item, descriptive = _attempt(
        "postprocess", lambda: functions["postprocess"](run.bundle.record, summary), context=ctx
    )
    run.bundle.postprocess = descriptive
    emit(item)
    if not item.ok:
        return run

    # 5. Laclaudian discourse analysis
    item, laclau = _attempt(
        "laclau",
        lambda: functions["laclau"](run.bundle.record, summary, descriptive),
        context=ctx,
    )
    run.bundle.laclau = laclau
    emit(item)
    if not item.ok:
        return run

    # 6. Discourse Network Analysis
    item, dna = _attempt("dna", lambda: functions["dna"](run.bundle.record, laclau), context=ctx)
    run.bundle.dna = dna
    emit(item)
    if not item.ok:
        return run

    # 7. Social Network Analysis
    item, sna = _attempt("sna", lambda: functions["sna"](run.bundle.record, dna), context=ctx)
    run.bundle.sna = sna
    emit(item)
    return run


def run_records(
    records: Iterable[HumanPipelineRecord],
    *,
    context: PipelineContext | None = None,
    steps: dict[str, Callable[..., Any]] | None = None,
    on_outcome: Callable[[HumanPipelineRecord, StepOutcome], None] | None = None,
) -> Iterator[PipelineRun]:
    """Run the chain for each record, yielding each run as it finishes."""
    functions = steps if steps is not None else resolve_steps()
    for record in records:
        yield run_record(
            record,
            context=context,
            steps=functions,
            on_outcome=on_outcome,
        )


def plan(record: HumanPipelineRecord) -> list[tuple[str, str]]:
    """What a record's run would do, without calling any step.

    Used by ``--dry-run`` so the sequencing can be inspected before anything
    expensive or model-backed happens.
    """
    return [
        (name, "skip" if name == MEDIA_STEP and not record.media else "run")
        for name in STEP_NAMES
    ]


def _project_prompt(project: str, data_dir: Path) -> str:
    """Load a project's system prompt from runtime/private data, if present."""
    path = data_dir / "projects" / project / "system_prompt.md"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _default_paths() -> tuple[str, str]:
    """Default databases, anchored at the repository root rather than the CWD.

    The pipeline is usually launched from ``laclaugpt/`` (that is how the rest of
    this directory is run), so relative defaults would land in the wrong place.
    The default location is ``data/database/`` — the runtime data tree, which is
    git-ignored (AGENTS.md).
    """
    root = Path(__file__).resolve().parent.parent
    return (
        str(root / "data" / "database" / "pipeline_incoming.sqlite3"),
        str(root / "data" / "database" / "pipeline_outgoing.sqlite3"),
    )


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point: run the pipeline from a local database.

    Deliberately the same style as the rest of this directory: a script you can
    read, run directly and put in cron.
    """
    from pipeline_storage import SQLiteIncoming, SQLiteOutgoing

    default_incoming, default_outgoing = _default_paths()
    parser = argparse.ArgumentParser(description="Run the human-readable Phase 2 pipeline.")
    parser.add_argument("--project", required=True, help="project id, e.g. ai26")
    parser.add_argument(
        "--incoming",
        default=default_incoming,
        help="incoming database (runtime data; never committed)",
    )
    parser.add_argument(
        "--outgoing",
        default=default_outgoing,
        help="outgoing database (runtime data; never committed)",
    )
    parser.add_argument("--limit", type=int, default=None, help="process at most N records")
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="re-run steps whose previous attempt failed",
    )
    parser.add_argument("--model", default=None, help="model id recorded in provenance")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan; call no step and write nothing",
    )
    args = parser.parse_args(argv)

    incoming = SQLiteIncoming(Path(args.incoming), outgoing_path=Path(args.outgoing))
    outgoing = SQLiteOutgoing(Path(args.outgoing))
    context = PipelineContext(
        project=args.project,
        project_prompt=_project_prompt(args.project, Path("data")),
        model=args.model,
    )

    records = list(
        incoming.pending(args.project, limit=args.limit, retry_errors=args.retry_errors)
    )
    if not records:
        print(f"no pending records for project {args.project!r}")
        return 0

    if args.dry_run:
        print(f"{len(records)} pending record(s); no step called, nothing written:")
        for record in records:
            print(f"  {record.source_url}")
            for name, action in plan(record):
                print(f"    {name:<12} {action}")
        return 0

    def record_outcome(record: HumanPipelineRecord, item: StepOutcome) -> None:
        outgoing.save_outcome(record.source_url, item)

    processed = 0
    for run in run_records(
        records,
        context=context,
        on_outcome=record_outcome,
    ):
        outgoing.save(run.bundle)
        statuses = ", ".join(f"{item.step}={item.status}" for item in run.outcomes)
        print(f"{run.bundle.record.source_url}: {statuses}")
        processed += 1

    print(f"processed {processed} record(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    raise SystemExit(main())
