"""Contract tests for the readable analysis-step framework (issue #315).

These pin the properties a researcher relies on when reading `laclaugpt/steps/`:

- the seven steps exist, in the documented order, and each is importable;
- every step exposes the same `run()` signature;
- each step declares an output model that is a real Pydantic model;
- the framework never silently claims to implement a step that is still to be
  hand-coded: an unimplemented step raises rather than returning placeholder data;
- a step with nothing to do reports `skipped` / `abstained`, which are valid
  research results, not failures.

They deliberately do not test any analysis method — that is the researcher's code.
"""
from __future__ import annotations

import importlib
import inspect

import pytest
from pydantic import BaseModel

import steps
from models.incoming import IncomingRecord
from steps import StepContext, StepStatus


def test_seven_steps_are_registered_in_order() -> None:
    assert steps.step_names() == (
        "preprocess",
        "frame_analysis",
        "summary",
        "postprocess",
        "discourse",
        "dna",
        "sna",
    )
    assert [s.order for s in steps.STEPS] == [1, 2, 3, 4, 5, 6, 7]


@pytest.mark.parametrize("registration", steps.STEPS, ids=lambda s: s.name)
def test_each_step_is_importable_and_exposes_run(registration) -> None:
    module = importlib.import_module(registration.module)
    assert callable(getattr(module, "run", None)), f"{registration.module} has no run()"


@pytest.mark.parametrize("registration", steps.STEPS, ids=lambda s: s.name)
def test_each_step_documents_its_purpose(registration) -> None:
    assert registration.purpose, f"{registration.name} has no declared purpose"
    module = importlib.import_module(registration.module)
    doc = module.__doc__ or ""
    # Every step file must carry the same readable sections so the pipeline can be
    # understood from any one of them.
    for heading in ("Purpose", "Inputs", "Outputs", "Model", "Provenance"):
        assert heading in doc, f"{registration.name} is missing the {heading!r} section"


@pytest.mark.parametrize("registration", steps.STEPS, ids=lambda s: s.name)
def test_each_step_run_takes_a_record_and_context(registration) -> None:
    module = importlib.import_module(registration.module)
    signature = inspect.signature(module.run)
    params = list(signature.parameters.values())
    assert params, f"{registration.name}.run() takes no arguments"
    assert params[0].name == "record"
    assert "context" in signature.parameters


def test_output_models_are_pydantic_models() -> None:
    from models import steps as step_models

    for name in (
        "Step1PreprocessOutput",
        "Step2FrameOutput",
        "Step3SummaryOutput",
        "Step4PostprocessOutput",
        "Step5DiscourseOutput",
        "Step6DnaOutput",
        "Step7SnaOutput",
    ):
        model = getattr(step_models, name)
        assert issubclass(model, BaseModel), f"{name} must be a Pydantic model"
        assert issubclass(model, BaseModel)


def test_unimplemented_step_raises_rather_than_faking_a_result() -> None:
    """A step still to be hand-coded must not return placeholder output.

    Silence here would be the worst outcome: the pipeline would appear to run while
    producing nothing of analytical value.
    """
    from models.incoming import MediaItem

    from steps import step1_preprocess

    record = IncomingRecord(
        source_url="https://example.invalid/v",
        media=[MediaItem(kind="video", url="https://example.invalid/v.mp4")],
    )
    with pytest.raises(NotImplementedError):
        step1_preprocess.run(record, context=StepContext(project_id="ai26"))


def test_text_only_record_is_skipped_not_failed() -> None:
    """A text-only record is valid; a media step reports `skipped`, never `failed`."""
    from steps import step1_preprocess

    record = IncomingRecord(source_url="https://example.invalid/text")
    result = step1_preprocess.run(record, context=StepContext(project_id="ai26"))

    assert result.status == StepStatus.SKIPPED
    assert result.ok, "a skipped step is not a failure"
    assert result.output is not None
    assert result.output.nothing_to_extract is True


def test_step_result_status_vocabulary_is_closed() -> None:
    assert StepStatus.ALL == ("ran", "skipped", "abstained", "failed")
    assert StepStatus.SKIPPED != StepStatus.FAILED
