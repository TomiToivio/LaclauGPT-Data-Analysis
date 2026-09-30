"""Issue #315 — the agent-owned support layer around the human-written steps.

The seven step modules are human-owned and locked (see AGENTS.md). This file tests the code
that runs *around* them, and it deliberately never implements a step body: every
step function here is a stand-in, so passing these tests says nothing about the
analysis method and cannot push the researcher's implementation in any direction.

What is worth pinning, because getting it wrong is silent rather than loud:

* a text-only record skips frame analysis and is **not** recorded as an error —
  otherwise a valid text-only study looks broken;
* a failed step stops that record's chain, so no network layer is ever built on
  a summary that failed;
* a step that already ran is not run again, and a media step is not offered a
  record that has no media;
* the runner does not swallow ``NotImplementedError`` — an unfinished step must
  never look like a successful one.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pipeline_context import STEP_NAMES, PipelineContext, StepStatus, outcome
from pipeline_models import (
    DNAResult,
    FrameObservation,
    HumanPipelineRecord,
    LaclauResult,
    MediaItem,
    PostprocessResult,
    SNAResult,
    SummaryResult,
)
from pipeline_runner import STEP_ORDER, plan, run_record
from pipeline_storage import SQLiteIncoming, SQLiteOutgoing

REPO = Path(__file__).resolve().parents[1]
PIPELINE = REPO / "laclaugpt"


def text_record(source_url: str = "https://example.invalid/1", project: str = "ai26"):
    return HumanPipelineRecord(
        source_url=source_url,
        project=project,
        source_text="A short synthetic post.",
    )


def media_record(source_url: str = "https://example.invalid/2", project: str = "ai26"):
    return HumanPipelineRecord(
        source_url=source_url,
        project=project,
        source_text="A post with a picture.",
        media=[MediaItem(kind="image", uri="file:///tmp/example.jpg")],
    )


def stub_steps(*, fail_at: str | None = None, calls: list[str] | None = None):
    """Seven stand-ins with the real step signatures, recording their own calls."""
    log = calls if calls is not None else []

    def check(step: str) -> None:
        log.append(step)
        if fail_at == step:
            raise RuntimeError(f"{step} exploded")

    def preprocess(record):
        check("preprocess")
        return record

    def frames(record):
        check("frame")
        return [FrameObservation(media_uri=record.media[0].uri, description="a picture")]

    def summary(record, observed):
        check("summary")
        return SummaryResult(summary="synthetic summary")

    def postprocess(record, made):
        check("postprocess")
        return PostprocessResult(entities=["an entity"], topics=["a topic"])

    def laclau(record, made, descriptive):
        check("laclau")
        return LaclauResult(analysis="synthetic reading", us=["us"], frontier=["them"])

    def dna(record, reading):
        check("dna")
        return DNAResult(claims=[{"claim": "synthetic"}])

    def sna(record, network):
        check("sna")
        return SNAResult(nodes=[{"actor": "synthetic"}])

    return {
        "preprocess": preprocess,
        "frame": frames,
        "summary": summary,
        "postprocess": postprocess,
        "laclau": laclau,
        "dna": dna,
        "sna": sna,
    }


# --------------------------------------------------------------------------
# Runner sequencing
# --------------------------------------------------------------------------


def test_text_only_record_skips_frame_analysis_without_failing() -> None:
    """A record with no media is a valid record, not a broken one."""
    calls: list[str] = []
    run = run_record(text_record(), steps=stub_steps(calls=calls))

    assert run.status_of("frame") == StepStatus.SKIPPED
    assert calls == ["preprocess", "summary", "postprocess", "laclau", "dna", "sna"]
    assert not run.failed, "a text-only record must not produce a failure"


def test_skipped_step_is_not_recorded_as_an_error() -> None:
    run = run_record(text_record(), steps=stub_steps())
    frame = next(item for item in run.outcomes if item.step == "frame")

    assert frame.status == StepStatus.SKIPPED
    assert frame.error is None
    assert frame.notes, "a skip should say why it was skipped"


def test_media_record_runs_frame_analysis_and_carries_frames_forward() -> None:
    run = run_record(media_record(), steps=stub_steps())

    assert run.status_of("frame") == StepStatus.RAN
    assert run.bundle.frames, "frame observations must reach the summary step"


def test_steps_run_in_the_issue_order() -> None:
    calls: list[str] = []
    run_record(media_record(), steps=stub_steps(calls=calls))

    assert calls == list(STEP_NAMES), "the run order is the scientific method, not a detail"


def test_a_failed_step_stops_the_chain_for_that_record() -> None:
    """DNA must never be built on a summary that failed."""
    calls: list[str] = []
    run = run_record(media_record(), steps=stub_steps(fail_at="summary", calls=calls))

    assert run.status_of("summary") == StepStatus.FAILED
    assert run.failed
    assert "laclau" not in calls and "dna" not in calls and "sna" not in calls
    assert run.bundle.dna is None and run.bundle.sna is None


def test_a_failure_keeps_the_results_of_the_steps_that_did_run() -> None:
    run = run_record(media_record(), steps=stub_steps(fail_at="laclau"))

    assert run.bundle.summary is not None, "completed upstream work must not be discarded"
    assert run.status_of("postprocess") == StepStatus.RAN
    assert run.bundle.laclau is None


def test_runner_does_not_swallow_notimplemented_on_unfinished_steps() -> None:
    """An unfinished step must be loud, not reported as a successful empty run."""
    with pytest.raises(NotImplementedError):
        run_record(text_record(), steps=None)


def test_every_outcome_records_when_it_happened() -> None:
    run = run_record(text_record(), steps=stub_steps())
    assert all(item.at for item in run.outcomes), "an outcome without a time is unauditable"


def test_plan_marks_the_media_step_without_calling_anything() -> None:
    assert dict(plan(text_record()))["frame"] == "skip"
    assert dict(plan(media_record()))["frame"] == "run"
    assert len(plan(text_record())) == len(STEP_NAMES)


# --------------------------------------------------------------------------
# The incoming/outgoing database boundary
# --------------------------------------------------------------------------


@pytest.fixture()
def databases(tmp_path: Path):
    incoming = SQLiteIncoming(tmp_path / "incoming.sqlite3")
    outgoing = SQLiteOutgoing(tmp_path / "outgoing.sqlite3")
    yield incoming, outgoing
    incoming.close()
    outgoing.close()


def test_records_round_trip_through_the_incoming_database(databases) -> None:
    incoming, _ = databases
    incoming.add(text_record())

    pending = list(incoming.pending("ai26"))
    assert [item.source_url for item in pending] == ["https://example.invalid/1"]
    assert pending[0].source_text == "A short synthetic post."


def test_pending_is_scoped_to_the_project(databases) -> None:
    incoming, _ = databases
    incoming.add(text_record(project="ai26"))
    incoming.add(text_record("https://example.invalid/3", project="other"))

    assert [item.source_url for item in incoming.pending("other")] == [
        "https://example.invalid/3"
    ]


def test_step_outcome_round_trips_with_provenance(databases) -> None:
    _, outgoing = databases
    item = outcome(
        "summary",
        StepStatus.RAN,
        output=SummaryResult(summary="synthetic summary"),
        context=PipelineContext(project="ai26", model="synthetic-model"),
        prompt="synthetic-prompt-id@1",
    )
    outgoing.save_outcome("https://example.invalid/1", item)

    stored = outgoing.outcome("https://example.invalid/1", "summary")
    assert stored["status"] == StepStatus.RAN
    assert stored["output"]["summary"] == "synthetic summary"
    assert stored["model"] == "synthetic-model"
    assert stored["prompt"] == "synthetic-prompt-id@1"
    assert stored["review_status"] == "provisional"


def test_ran_step_is_not_offered_again(databases) -> None:
    _, outgoing = databases
    document = text_record().model_dump(mode="json")
    outgoing.save_outcome(
        document["source_url"], outcome("preprocess", StepStatus.RAN)
    )

    assert outgoing.is_eligible(document, "preprocess") is False
    assert outgoing.is_eligible(document, "preprocess", retry_errors=True) is True


def test_text_only_record_is_not_offered_to_the_media_step(databases) -> None:
    _, outgoing = databases
    assert outgoing.is_eligible(text_record().model_dump(mode="json"), "frame") is False
    assert outgoing.is_eligible(media_record().model_dump(mode="json"), "frame") is True


def test_an_earlier_failure_blocks_later_steps(databases) -> None:
    """A record stuck at the summary must not be handed to DNA forever."""
    _, outgoing = databases
    document = text_record().model_dump(mode="json")
    outgoing.save_outcome(document["source_url"], outcome("summary", StepStatus.FAILED, error="boom"))

    assert outgoing.is_eligible(document, "laclau") is False
    assert outgoing.is_eligible(document, "dna") is False
    # ... until someone deliberately retries.
    assert outgoing.is_eligible(document, "laclau", retry_errors=True) is True


def test_skipped_is_a_result_not_a_failure(databases) -> None:
    _, outgoing = databases
    document = text_record().model_dump(mode="json")
    outgoing.save_outcome(document["source_url"], outcome("frame", StepStatus.SKIPPED))

    assert outgoing.is_eligible(document, "frame") is False
    assert outgoing.is_eligible(document, "summary") is True, "a skip must not block the chain"


def test_finished_bundle_is_written_with_source_url_identity(databases) -> None:
    incoming, outgoing = databases
    record = text_record()
    incoming.add(record)
    run = run_record(record, steps=stub_steps())
    outgoing.save(run.bundle)

    row = outgoing.connection.execute(
        "SELECT source_url, bundle FROM outgoing_bundles"
    ).fetchone()
    assert row["source_url"] == record.source_url
    assert record.source_url in row["bundle"], "source_url must survive persistence unchanged"


def test_the_runner_never_touches_a_real_database_by_itself(databases) -> None:
    """Running a record in memory writes nothing: persistence is the caller's call."""
    _, outgoing = databases
    run_record(text_record(), steps=stub_steps())

    count = outgoing.connection.execute("SELECT count(*) FROM outgoing_steps").fetchone()[0]
    assert count == 0


# --------------------------------------------------------------------------
# The support layer is not allowed to drift away from the locked step names
# --------------------------------------------------------------------------


def test_support_layer_names_match_the_locked_step_files() -> None:
    """The runner's step names must keep pointing at the seven locked step files."""
    assert tuple(name for name, _, _ in STEP_ORDER) == STEP_NAMES
    for _, module_name, _ in STEP_ORDER:
        assert (PIPELINE / f"{module_name}.py").is_file(), (
            f"{module_name}.py is a locked step file and must keep existing"
        )


def test_support_layer_does_not_implement_or_replace_a_step() -> None:
    """Agents write around the steps; this layer must not contain the method.

    While a step is hand-coding material it still raises ``NotImplementedError``.
    When Tomi implements one, this expectation is updated deliberately rather than
    discovered by a silent green run.
    """
    for _, module_name, _ in STEP_ORDER:
        source = (PIPELINE / f"{module_name}.py").read_text(encoding="utf-8")
        assert "NotImplementedError" in source, (
            f"{module_name}.py no longer raises NotImplementedError: either Tomi has "
            "hand-coded the step (fine) or an agent has written the method (not fine)."
        )


def test_outgoing_database_creates_the_expected_tables(tmp_path: Path) -> None:
    """A step's block is addressed as (source_url, step) so the run order is readable."""
    database = tmp_path / "schema.sqlite3"
    outgoing = SQLiteOutgoing(database)
    try:
        tables = {
            row[0]
            for row in outgoing.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        outgoing.close()

    assert {"incoming_records", "outgoing_steps", "outgoing_bundles"} <= tables


def test_incoming_reads_eligibility_from_the_outgoing_database(tmp_path: Path) -> None:
    """The reader must not look for step statuses in the incoming database."""
    incoming = SQLiteIncoming(tmp_path / "incoming.sqlite3", tmp_path / "outgoing.sqlite3")
    outgoing = SQLiteOutgoing(tmp_path / "outgoing.sqlite3")
    try:
        incoming.add(text_record())
        assert [item.source_url for item in incoming.pending("ai26")], "unrun record is pending"

        outgoing.save_outcome("https://example.invalid/1", outcome("preprocess", StepStatus.RAN))
        # preprocess is done, but the later steps are not, so it is still pending.
        assert [item.source_url for item in incoming.pending("ai26")]

        for step in STEP_NAMES:
            outgoing.save_outcome("https://example.invalid/1", outcome(step, StepStatus.RAN))
        assert list(incoming.pending("ai26")) == [], "a fully analysed record is not pending"
    finally:
        incoming.close()
        outgoing.close()


# --------------------------------------------------------------------------
# The command-line entry point
# --------------------------------------------------------------------------


def test_cli_defaults_are_anchored_at_the_repository_root() -> None:
    """Launched from laclaugpt/ (as the rest of the directory is), defaults still land in data/."""
    from pipeline_runner import _default_paths

    for path in _default_paths():
        assert path.startswith(str(REPO)), f"{path} is not anchored at the repository root"
        assert "data" in Path(path).parts, f"{path} is outside the runtime data tree"


def test_cli_dry_run_lists_records_and_writes_nothing(tmp_path: Path, capsys) -> None:
    from pipeline_runner import main

    incoming_path = tmp_path / "incoming.sqlite3"
    outgoing_path = tmp_path / "outgoing.sqlite3"
    incoming = SQLiteIncoming(incoming_path, outgoing_path)
    incoming.add(text_record())
    incoming.close()

    code = main(
        [
            "--project",
            "ai26",
            "--incoming",
            str(incoming_path),
            "--outgoing",
            str(outgoing_path),
            "--dry-run",
        ]
    )
    printed = capsys.readouterr().out

    assert code == 0
    assert "https://example.invalid/1" in printed
    assert "frame" in printed and "skip" in printed, "the plan should show the media decision"

    outgoing = SQLiteOutgoing(outgoing_path)
    try:
        assert (
            outgoing.connection.execute("SELECT count(*) FROM outgoing_steps").fetchone()[0] == 0
        ), "a dry run must write nothing"
    finally:
        outgoing.close()


def test_cli_reports_when_there_is_nothing_to_do(tmp_path: Path, capsys) -> None:
    from pipeline_runner import main

    code = main(
        [
            "--project",
            "ai26",
            "--incoming",
            str(tmp_path / "incoming.sqlite3"),
            "--outgoing",
            str(tmp_path / "outgoing.sqlite3"),
        ]
    )
    assert code == 0
    assert "no pending records" in capsys.readouterr().out


def test_resolve_steps_wires_the_seven_locked_step_functions() -> None:
    """The real wiring resolves, and each entry is that locked module's callable."""
    from pipeline_runner import resolve_steps

    functions = resolve_steps()
    assert tuple(functions) == STEP_NAMES
    for name, module_name, function_name in STEP_ORDER:
        assert functions[name].__name__ == function_name
        assert functions[name].__module__ == module_name
