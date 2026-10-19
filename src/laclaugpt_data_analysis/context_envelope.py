"""Typed, inspectable prompt context for every LaclauGPT LLM stage.

The envelope keeps project/source/situational/memory/RAG/source-item/previous-stage
context separate so retrieved material is never confused with source evidence.

Since issue #372 the rendered envelope is also **bounded**: ``current_source`` and
``previous_analysis`` are lossless dumps of the record, so an ordinary prompt could
exceed the model's context window, and the server then truncated it silently — from
the front, i.e. from the system prompt and the task. :mod:`prompt_budget` reserves room
for the answer and the JSON shape, caps each section, marks truncation in band, and
reports the model-visible size of every section so an over-budget prompt is visible in
the log *before* the call. All eight section headers are always emitted, so the prompt
contract does not change; only the amount of each layer that fits does. Set
``LACLAUGPT_PROMPT_BUDGET_CHARS=0`` to disable the guard.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord
from .prompt_budget import Packet, Section, allocate, resolve_budget, summarise

EMPTY_CONTEXT = "(none available)"

#: Section order is the prompt contract: prompts refer to these eight names.
#: ``(attribute, header, priority, cap)`` — priority decides who keeps the budget when
#: the record does not fit, and the cap stops one field from starving the rest. The task
#: has the highest priority so the instruction the stage exists to give is never lost.
SECTION_PLAN: tuple[tuple[str, str, int, int | None], ...] = (
    ("project", "PROJECT CONTEXT", 40, 4_000),
    ("source", "SOURCE CONTEXT", 40, 4_000),
    ("situational", "SITUATIONAL CONTEXT", 30, 4_000),
    ("memory", "CONTEXT MEMORY", 20, 6_000),
    ("rag", "RAG CONTEXT", 10, 4_000),
    ("current_source", "CURRENT SOURCE ITEM", 90, 20_000),
    ("previous_analysis", "PREVIOUS ANALYSIS", 50, 12_000),
    ("task", "TASK", 100, 8_000),
)

_BY_NAME = {name: (header, priority, cap) for name, header, priority, cap in SECTION_PLAN}


class ContextFragment(BaseModel):
    text: str = ""
    provenance: list[str] = Field(default_factory=list)


class PromptEnvelope(BaseModel):
    project: ContextFragment = Field(default_factory=ContextFragment)
    source: ContextFragment = Field(default_factory=ContextFragment)
    situational: ContextFragment = Field(default_factory=ContextFragment)
    memory: ContextFragment = Field(default_factory=ContextFragment)
    rag: ContextFragment = Field(default_factory=ContextFragment)
    current_source: ContextFragment = Field(default_factory=ContextFragment)
    previous_analysis: ContextFragment = Field(default_factory=ContextFragment)
    task: ContextFragment = Field(default_factory=ContextFragment)
    prompt_version: str = "canonical-envelope-v1"
    #: Model-visible character budget. ``0`` renders the historical unbounded envelope.
    budget: int = 0
    reserve_output: int = 0
    reserve_schema: int = 0

    def _fragments(self) -> list[tuple[str, str, ContextFragment]]:
        return [
            (name, header, getattr(self, name))
            for name, header, _priority, _cap in SECTION_PLAN
        ]

    def _sections(self) -> list[Section]:
        sections: list[Section] = []
        for name, header, fragment in self._fragments():
            _header, priority, cap = _BY_NAME[name]
            provenance = ", ".join(fragment.provenance) or "none"
            body = fragment.text.strip() or EMPTY_CONTEXT
            sections.append(
                Section(
                    name=name,
                    header=f"[{header}]\nprovenance: {provenance}",
                    body=body,
                    priority=priority,
                    cap=cap,
                )
            )
        return sections

    def render(self) -> str:
        """Render the eight required sections in a stable, auditable order."""
        return self.render_with_report()[0]

    def render_with_report(self) -> tuple[str, dict[str, Any]]:
        """Render the prompt and return the model-visible accounting that goes with it.

        Stages record this report in their stage output and their model-run metadata, so
        a later reader can tell how much of the record the model actually saw.
        """
        packet: Packet = allocate(
            self._sections(),
            total=self.budget,
            reserve_output=self.reserve_output,
            reserve_schema=self.reserve_schema,
        )
        report = summarise(packet)
        report["prompt_version"] = self.prompt_version
        report["report_line"] = packet.render_report()
        return packet.text, report

    def provenance_snapshot(self) -> dict[str, list[str]]:
        return {
            "project": self.project.provenance,
            "source": self.source.provenance,
            "situational": self.situational.provenance,
            "memory": self.memory.provenance,
            "rag": self.rag.provenance,
            "current_source": self.current_source.provenance,
            "previous_analysis": self.previous_analysis.provenance,
            "task": self.task.provenance,
        }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, indent=2)


def source_item_text(record: CanonicalRecord) -> str:
    """Losslessly expose canonical source material plus raw collector payload."""
    source = record.source.model_dump(mode="json", exclude_none=False)
    content = record.content.model_dump(mode="json", exclude_none=False)
    raw_capture = record.raw_capture.model_dump(mode="json", exclude_none=False)
    return _json(
        {
            "source_url": record.source_url,
            "source_native_ids": record.source_native_ids,
            "source": source,
            "content": content,
            "raw_capture": raw_capture,
            "raw_metadata": record.source.raw_metadata,
        }
    )


def previous_analysis_text(record: CanonicalRecord) -> str:
    """Expose all earlier-stage researcher-visible outputs without flattening them."""
    return _json(
        {
            "asr": record.intermediate.asr,
            "ocr": record.intermediate.ocr,
            "frames": record.intermediate.frames,
            "frame_analysis": record.intermediate.frame_analysis,
            "translations": record.intermediate.translations,
            "stage_outputs": record.intermediate.stage_outputs,
            "human_readable": record.human_readable.model_dump(mode="json"),
            "existing_analysis": record.analysis.model_dump(mode="json", exclude_none=False),
            "legacy": record.legacy,
        }
    )


def build_prompt_envelope(
    record: CanonicalRecord,
    *,
    task: str,
    project_context: str = "",
    source_context: str = "",
    situational_context: str = "",
    memory_context: str = "",
    rag_context: str = "",
    context_provenance: dict[str, list[str]] | None = None,
    prompt_version: str = "canonical-envelope-v1",
    budget: int | None = None,
) -> PromptEnvelope:
    """Build the eight-section envelope, bounded by default (issue #372).

    ``budget=None`` resolves the model-visible character budget from the environment
    (``LACLAUGPT_PROMPT_BUDGET_CHARS``, default :data:`prompt_budget.DEFAULT_TOTAL`), so
    every caller inherits the guard without opting in. ``budget=0`` renders the
    historical unbounded envelope.
    """
    total, reserve_output, reserve_schema = resolve_budget(budget)
    provenance = context_provenance or {}
    return PromptEnvelope(
        project=ContextFragment(text=project_context, provenance=provenance.get("project", [])),
        source=ContextFragment(text=source_context, provenance=provenance.get("source", [])),
        situational=ContextFragment(
            text=situational_context or EMPTY_CONTEXT,
            provenance=provenance.get("situational", []),
        ),
        memory=ContextFragment(
            text=memory_context or EMPTY_CONTEXT,
            provenance=provenance.get("memory", []),
        ),
        rag=ContextFragment(
            text=rag_context or EMPTY_CONTEXT,
            provenance=provenance.get("rag", []),
        ),
        current_source=ContextFragment(
            text=source_item_text(record), provenance=[record.source_url]
        ),
        previous_analysis=ContextFragment(
            text=previous_analysis_text(record), provenance=[record.source_url]
        ),
        task=ContextFragment(text=task, provenance=provenance.get("task", [])),
        prompt_version=prompt_version,
        budget=total,
        reserve_output=reserve_output,
        reserve_schema=reserve_schema,
    )
