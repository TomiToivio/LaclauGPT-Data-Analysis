"""Small canonical LLM-assisted analysis orchestration."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord, DiscourseObject, Entity
from .memory.retrieval import context_block
from .models import ClassificationResult


class AnalysisProposal(BaseModel):
    summary: str | None = None
    entities: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    classifications: dict[str, str] = Field(default_factory=dict)
    formations: list[str] = Field(default_factory=list)
    signifiers: list[str] = Field(default_factory=list)
    nodal_points: list[str] = Field(default_factory=list)
    discourses: list[str] = Field(default_factory=list)
    imaginaries: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    abstentions: list[str] = Field(default_factory=list)


def analyze_record(record: CanonicalRecord, *, provider, memory_entries=None,
                   model: str | None = None, prompt_version: str = "analysis-v1") -> CanonicalRecord:
    """Enrich one canonical record while retaining source identity and review semantics."""
    memory_entries = memory_entries or []
    context = context_block(record.content.text, memory_entries) if memory_entries else ""
    system = (
        "You are a research analysis assistant. Distinguish descriptive observations from "
        "interpretive discourse candidates. Abstain when evidence is insufficient. "
        "Retrieved codebook/memory candidates are context, not evidence."
    )
    user = f"SOURCE URL: {record.source_url}\nTEXT:\n{record.content.text}\n"
    if context:
        user += f"\nRETRIEVED CANDIDATES (NOT EVIDENCE):\n{context}\n"
    result, response = provider.structured(
        AnalysisProposal,
        system_prompt=system,
        user_prompt=user,
        model=model,
    )
    now = datetime.now(UTC)
    record.analysis.status = "analyzed"
    record.analysis.started_at = record.analysis.started_at or now
    record.analysis.completed_at = now
    record.analysis.summary = result.summary
    record.analysis.entities = [
        Entity(entity_id=f"entity:{i}", label=label, review_status="PROVISIONAL")
        for i, label in enumerate(result.entities, start=1)
    ]
    record.analysis.classifications = [
        ClassificationResult(
            label=label,
            task=task,
            model=response.model,
            backend=response.provider,
            source_url=record.source_url,
        )
        for task, label in sorted(result.classifications.items())
    ]
    for field in ("formations", "signifiers", "nodal_points", "discourses", "imaginaries"):
        values = getattr(result, field)
        setattr(
            record.analysis,
            field,
            [DiscourseObject(object_id=f"{field}:{i}", label=label, kind=field.rstrip("s"))
             for i, label in enumerate(values, start=1)],
        )
    record.analysis.uncertainty = result.uncertainty
    record.analysis.abstentions = result.abstentions
    record.analysis.model_runs.append({
        "provider": response.provider,
        "model": response.model,
        "endpoint": response.endpoint,
        "prompt_version": prompt_version,
        "metadata": response.metadata,
    })
    provenance = record.append_analysis_provenance(
        method="llm-assisted-analysis",
        model=response.model,
        metadata={"provider": response.provider, "prompt_version": prompt_version,
                  "endpoint": response.endpoint},
    )
    record.analysis.memory_refs = [entry.entry_id for entry in memory_entries]
    for item in record.analysis.entities:
        item.provenance_id = provenance.provenance_id
    return record
