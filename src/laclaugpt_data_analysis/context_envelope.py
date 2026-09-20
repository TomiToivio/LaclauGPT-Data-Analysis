"""Typed, inspectable prompt context for every LaclauGPT LLM stage.

The envelope keeps project/source/situational/memory/RAG/source-item/previous-stage
context separate so retrieved material is never confused with source evidence.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord

EMPTY_CONTEXT = "(none available)"


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

    def render(self) -> str:
        """Render the eight required sections in a stable, auditable order."""
        sections = (
            ("PROJECT CONTEXT", self.project),
            ("SOURCE CONTEXT", self.source),
            ("SITUATIONAL CONTEXT", self.situational),
            ("CONTEXT MEMORY", self.memory),
            ("RAG CONTEXT", self.rag),
            ("CURRENT SOURCE ITEM", self.current_source),
            ("PREVIOUS ANALYSIS", self.previous_analysis),
            ("TASK", self.task),
        )
        chunks: list[str] = []
        for name, fragment in sections:
            body = fragment.text.strip() or EMPTY_CONTEXT
            provenance = ", ".join(fragment.provenance) or "none"
            chunks.append(f"[{name}]\nprovenance: {provenance}\n{body}")
        return "\n\n".join(chunks)

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
) -> PromptEnvelope:
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
    )
