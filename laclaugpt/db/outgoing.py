"""Write a step's result back to storage.

Every step writes into one namespaced block on the record::

    step_outputs:
      preprocess:     {status, output, model, prompt, at, ...}
      frame_analysis: {status, ...}
      ...
      sna:            {status, ...}

Keeping one block per step is what makes the run order auditable and lets each
step be re-run without disturbing the others. The status vocabulary is the
``StepStatus`` one, so ``skipped`` and ``abstained`` are recorded as normal
results and only ``failed`` is an error.

Two rules from AGENTS.md are enforced here, because this is the write boundary:

- ``source_url`` is the canonical identity and is never replaced by a derived id;
- provisional, model-produced output keeps its provenance and stays reviewable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from steps import StepResult, StepStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def result_fields(
    step: str,
    result: StepResult,
    *,
    model: str | None = None,
    prompt_id: str | None = None,
    prompt_version: str | None = None,
) -> dict[str, Any]:
    """Build the document fields for one step's result.

    Returned as ``{"$set": ...}``-ready field paths so the caller can write them
    without knowing the namespace layout.
    """
    block: dict[str, Any] = {
        f"step_outputs.{step}.status": result.status,
        f"step_outputs.{step}.at": _now(),
    }
    if result.output is not None:
        block[f"step_outputs.{step}.output"] = result.output.model_dump(mode="json")
    if result.error:
        block[f"step_outputs.{step}.error"] = result.error
    if result.notes:
        block[f"step_outputs.{step}.notes"] = list(result.notes)
    # Provenance: which model and which prompt produced this, so a result can be
    # audited and reproduced. Model output is provisional until a human reviews it.
    if model:
        block[f"step_outputs.{step}.model"] = model
    if prompt_id:
        block[f"step_outputs.{step}.prompt_id"] = prompt_id
        block[f"step_outputs.{step}.prompt_version"] = prompt_version
    block[f"step_outputs.{step}.review_status"] = "provisional"
    return block


def write_result(
    record: dict[str, Any],
    step: str,
    result: StepResult,
    *,
    project_id: str | None = None,
    model: str | None = None,
    prompt_id: str | None = None,
    prompt_version: str | None = None,
) -> dict[str, Any]:
    """Persist one step's result. Returns the fields written.

    Failures are recorded through the existing failure helper so the attempt
    counter and first/last failure timestamps keep working as before.
    """
    from laclaugpt_mongo import record_stage_failure, update_document

    if result.status == StepStatus.FAILED:
        record_stage_failure(
            record,
            step,
            result.error or "step failed",
            project_id=project_id,
        )
        return {}

    fields = result_fields(
        step,
        result,
        model=model,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
    )
    update_document(record, fields, project_id=project_id)
    return fields


def step_output(document: dict[str, Any], step: str) -> dict[str, Any] | None:
    """Read back one step's block, for a later step or for a reviewer."""
    block = (document.get("step_outputs") or {}).get(step)
    return block if isinstance(block, dict) else None
