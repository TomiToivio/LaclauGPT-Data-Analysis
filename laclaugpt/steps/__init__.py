"""The shared contract every analysis step follows.

A step is a small module in this directory that exposes one function:

    run(record: IncomingRecord, *, context: StepContext) -> StepResult

Everything else in this file exists so the step files can stay short and readable.
Nothing here decides anything about the research method: it only defines what a
step is given and what it must return.

The seven steps, in order, are registered in ``STEPS`` below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from models.incoming import IncomingRecord
from pydantic import BaseModel, Field


class StepStatus:
    """Outcome of one step on one record.

    ``RAN``      the step did work and wrote output;
    ``SKIPPED``  the step had nothing to do for this record (for example frame
                 analysis on a text-only post). This is a normal result, not a
                 failure, and it must not be recorded as an error.
    ``ABSTAINED`` the step ran but the evidence did not support a conclusion
                 (INV_ABSTAIN). Also a valid result.
    ``FAILED``   the step raised. The record stays eligible for retry.
    """

    RAN = "ran"
    SKIPPED = "skipped"
    ABSTAINED = "abstained"
    FAILED = "failed"

    ALL = (RAN, SKIPPED, ABSTAINED, FAILED)


class StepResult(BaseModel):
    """What a step returns to the runner.

    ``output`` is the step's structured result and must be an instance of the
    step's declared ``output_model``. ``fields`` carries anything the step wants
    written to the outgoing record that is not part of that model; normally it is
    empty, because the output model should already describe the result.
    """

    status: str = StepStatus.RAN
    output: BaseModel | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    notes: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status != StepStatus.FAILED


@dataclass
class StepContext:
    """Everything a step needs that is not the record itself.

    Deliberately plain: a project id, the project's prompt directory, and the
    helpers for reading and writing. A step that needs nothing but the record can
    ignore this entirely.
    """

    project_id: str
    prompt_dir: str = ""
    db: Any = None
    llm: Any = None
    codebook: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)

    def option(self, name: str, default: Any = None) -> Any:
        return self.options.get(name, default)


class Step(Protocol):
    """The shape each step module provides."""

    name: str
    order: int
    purpose: str
    output_model: type[BaseModel]

    def run(self, record: IncomingRecord, *, context: StepContext) -> StepResult: ...


@dataclass(frozen=True)
class StepRegistration:
    """A step's entry in the registry, kept next to the step it describes."""

    name: str
    order: int
    module: str
    purpose: str
    needs_media: bool = False


# The seven steps, in run order. This tuple is the pipeline: if a step is missing
# here it does not run, and the order here is the order of execution.
STEPS: tuple[StepRegistration, ...] = (
    StepRegistration(
        name="preprocess",
        order=1,
        module="steps.step1_preprocess",
        purpose="Extract frames, OCR, transcript and translation from incoming media.",
        needs_media=True,
    ),
    StepRegistration(
        name="frame_analysis",
        order=2,
        module="steps.step2_frame_analysis",
        purpose="Read images / sampled video frames. Skipped when a record has none.",
        needs_media=True,
    ),
    StepRegistration(
        name="summary",
        order=3,
        module="steps.step3_summary",
        purpose="Summarise the record, text-only or multimodal.",
    ),
    StepRegistration(
        name="postprocess",
        order=4,
        module="steps.step4_postprocess",
        purpose="Turn the summary into structured fields.",
    ),
    StepRegistration(
        name="discourse",
        order=5,
        module="steps.step5_discourse",
        purpose="Laclaudian discourse analysis (Laclau, Mouffe, Palonen).",
    ),
    StepRegistration(
        name="dna",
        order=6,
        module="steps.step6_dna",
        purpose="Discourse Network Analysis: statements, actors, concepts.",
    ),
    StepRegistration(
        name="sna",
        order=7,
        module="steps.step7_sna",
        purpose="Social Network Analysis over the discourse network.",
    ),
)

STEPS_BY_NAME: dict[str, StepRegistration] = {step.name: step for step in STEPS}


def step_names() -> tuple[str, ...]:
    return tuple(step.name for step in STEPS)


def resolve_runner(module_name: str) -> Callable[..., StepResult]:
    """Import a step module and return its ``run`` function."""
    from importlib import import_module

    module = import_module(module_name)
    return module.run
