"""Run context and outcome vocabulary for the human-written pipeline.

This is agent-owned support code around the seven human-owned (locked) step modules
(issue #315 step 3: agents write code *around* these steps, not inside them).

Nothing in this file decides anything about the research method. It defines two
things a runner needs and a step should not have to invent:

* what a step is handed besides the record itself (``PipelineContext``);
* how a step's outcome is recorded (``StepStatus``, ``StepOutcome``).

The three-way distinction in ``StepStatus`` matters scientifically, not just
technically. A text-only record has nothing for frame analysis to read: that is
``SKIPPED``, a normal result. A step the evidence did not support is
``ABSTAINED``. Only an exception is ``FAILED``. Recording "nothing to do" as an
error would make a perfectly good text-only study look broken, and would hide a
real failure among the non-failures.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

# The seven steps of issue #315, in run order. The names are the vocabulary the
# run context, the storage layer and the runner share; the runner maps each name
# to the module and function it calls.
STEP_NAMES: tuple[str, ...] = (
    "preprocess",
    "frame",
    "summary",
    "postprocess",
    "laclau",
    "dna",
    "sna",
)

# The step whose absence of media makes a skip legitimate rather than a failure.
MEDIA_STEP = "frame"


class StepStatus:
    """Outcome of one step on one record.

    ``RAN``       the step did the work and produced output;
    ``SKIPPED``   the step had nothing to do for this record (frame analysis on
                  a text-only post). A normal result, never an error;
    ``ABSTAINED`` the step ran but the evidence did not support a conclusion.
                  Set by a step that reports abstention; also a valid result;
    ``FAILED``    the step raised. The record stays retryable.
    """

    RAN = "ran"
    SKIPPED = "skipped"
    ABSTAINED = "abstained"
    FAILED = "failed"

    ALL = (RAN, SKIPPED, ABSTAINED, FAILED)


@dataclass
class PipelineContext:
    """Everything a step needs that is not the record itself.

    Deliberately plain and optional: a step that needs only the record can ignore
    this entirely.

    ``llm`` is whatever provider object the deployment supplies. It is typed
    loosely and never constructed here, so importing this module cannot trigger an
    import-time model or network call (AGENTS.md).
    """

    project: str = ""
    project_prompt: str = ""
    model: str | None = None
    prompt_dir: str = ""
    codebook: dict[str, Any] = field(default_factory=dict)
    llm: Any = None
    options: dict[str, Any] = field(default_factory=dict)

    def option(self, name: str, default: Any = None) -> Any:
        """Read one run option without forcing a step to know the options dict."""
        return self.options.get(name, default)


class StepOutcome(BaseModel):
    """How one step's attempt on one record is recorded.

    ``output`` is the step's own result model, serialized. ``model`` and
    ``prompt`` carry provenance when the deployment knows it; both stay ``None``
    when it does not, rather than being invented (AGENTS.md: record the actual
    provider/model, and keep model output provisional until reviewed).
    """

    step: str
    status: str = StepStatus.RAN
    output: dict[str, Any] | None = None
    error: str | None = None
    notes: list[str] = Field(default_factory=list)
    at: str = ""
    model: str | None = None
    prompt: str | None = None
    review_status: str = "provisional"

    @property
    def ok(self) -> bool:
        """Whether the chain may continue past this step."""
        return self.status != StepStatus.FAILED


def now() -> str:
    """UTC timestamp for outcome records."""
    return datetime.now(timezone.utc).isoformat()


def outcome(
    step: str,
    status: str,
    *,
    output: BaseModel | dict[str, Any] | None = None,
    error: str | None = None,
    notes: list[str] | None = None,
    context: PipelineContext | None = None,
    prompt: str | None = None,
) -> StepOutcome:
    """Build a :class:`StepOutcome`, serializing a Pydantic output if given."""
    if isinstance(output, BaseModel):
        payload: dict[str, Any] | None = output.model_dump(mode="json")
    else:
        payload = output
    ctx = context or PipelineContext()
    return StepOutcome(
        step=step,
        status=status,
        output=payload,
        error=error,
        notes=list(notes or []),
        at=now(),
        model=ctx.model,
        prompt=prompt,
    )
