"""Canonical LLM-assisted analysis orchestration."""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord, DiscourseObject, Entity
from .codebooks import CodebookEntry
from .llm.structured_output import chat_structured
from .memory.retrieval import context_block
from .models import ClassificationResult


class AnalysisProposal(BaseModel):
    summary: str = ""
    entities: list[str] = Field(default_factory=list)
    classifications: dict[str, str] = Field(default_factory=dict)
    formations: list[str] = Field(default_factory=list)
    signifiers: list[str] = Field(default_factory=list)
    nodal_points: list[str] = Field(default_factory=list)
    discourses: list[str] = Field(default_factory=list)
    imaginaries: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    abstentions: list[str] = Field(default_factory=list)


def analyze_record(
    record: CanonicalRecord,
    *,
    provider,
    codebook_entries: list[CodebookEntry] | None = None,
    model: str = "auto",
    prompt_version: str = "analysis-v1",
    allow_cloud_fallback: bool | None = None,
) -> CanonicalRecord:
    """Enrich one canonical record without changing its source identity."""
    entries = codebook_entries or []
    retrieved = context_block(record.content.text, entries) if entries else ""
    system = (
        "You are a research analysis assistant. Distinguish descriptive observations from "
        "interpretive discourse candidates. Abstain when evidence is insufficient. "
        "Codebook candidates are context, not evidence."
    )
    user = f"SOURCE URL: {record.source_url}\nTEXT:\n{record.content.text}\n"
    if retrieved:
        user += f"\nRETRIEVED CODEBOOK CANDIDATES (NOT EVIDENCE):\n{retrieved}\n"
    proposal, response = chat_structured(
        provider,
        AnalysisProposal,
        model=model,
        system_prompt=system,
        user_prompt=user,
        allow_cloud_fallback=allow_cloud_fallback,
    )

    now = datetime.now(UTC)
    record.analysis.status = "analyzed"
    record.analysis.started_at = record.analysis.started_at or now
    record.analysis.completed_at = now
    record.analysis.summary = proposal.summary or None
    record.analysis.entities = [
        Entity(entity_id=f"entity:{index}", label=label, review_status="PROVISIONAL")
        for index, label in enumerate(proposal.entities, start=1)
    ]
    record.analysis.classifications = [
        ClassificationResult(
            label=label,
            task=task,
            model=response.provenance.actual_model,
            backend="ollama" if response.provenance.actual_mode in {"local", "cloud", "external"} else response.provenance.actual_mode,
            source_url=record.source_url,
        )
        for task, label in sorted(proposal.classifications.items())
    ]
    for field in ("formations", "signifiers", "nodal_points", "discourses", "imaginaries"):
        values = getattr(proposal, field)
        setattr(
            record.analysis,
            field,
            [
                DiscourseObject(
                    object_id=f"{field}:{index}",
                    label=label,
                    kind=field.rstrip("s"),
                    review_status="PROVISIONAL",
                )
                for index, label in enumerate(values, start=1)
            ],
        )
    record.analysis.uncertainty = proposal.uncertainty
    record.analysis.abstentions = proposal.abstentions
    record.analysis.codebook_refs = sorted({entry.label for entry in entries})
    record.analysis.model_runs.append(
        {
            **response.provenance.to_dict(),
            "prompt_version": prompt_version,
        }
    )
    provenance = record.append_analysis_provenance(
        method="llm-assisted-analysis",
        model=response.provenance.actual_model,
        metadata={
            "provider": "ollama" if response.provenance.actual_mode in {"local", "cloud", "external"} else response.provenance.actual_mode,
            "prompt_version": prompt_version,
            "endpoint": response.provenance.endpoint,
            "fallback_used": response.provenance.fallback_used,
        },
    )
    for item in record.analysis.entities:
        item.provenance_id = provenance.provenance_id
    return record
