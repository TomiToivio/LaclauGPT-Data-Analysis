"""Unified, inspectable context contract for LLM-assisted analysis stages.

This module composes existing ContextItem/ContextSnapshot, PromptEnvelope and
PipelineContext concepts without introducing a second memory or retrieval system.
Every fragment records trust, evidence role, source, size and a stable hash so a
model call has one inspectable answer to: what did this call know?
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord
from .codebooks import CodebookEntry
from .context_envelope import PromptEnvelope, build_prompt_envelope
from .context_runtime import ContextItem, ContextSnapshot, assemble_context

EvidenceRole = Literal["source_evidence", "context", "task_contract"]


class AnalysisContextFragment(BaseModel):
    kind: str
    text: str = ""
    source: str = ""
    revision: str = ""
    trust: str = "context"
    evidence_role: EvidenceRole = "context"
    record_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def provenance_token(self) -> str:
        bits = [self.kind]
        if self.source:
            bits.append(f"source={self.source}")
        if self.revision:
            bits.append(f"revision={self.revision}")
        bits.extend(
            (
                f"trust={self.trust}",
                f"role={self.evidence_role}",
                f"sha256={self.sha256}",
                f"chars={len(self.text)}",
            )
        )
        return ";".join(bits)


class AnalysisContextBundle(BaseModel):
    """One typed snapshot of everything available to an LLM-assisted stage."""

    project_background: AnalysisContextFragment
    theory_context: AnalysisContextFragment
    source_profile: AnalysisContextFragment
    codebook_context: AnalysisContextFragment
    situational_summary: AnalysisContextFragment
    memory_context: AnalysisContextFragment
    rag_context: AnalysisContextFragment
    current_source: AnalysisContextFragment
    previous_analysis: AnalysisContextFragment
    task_contract: AnalysisContextFragment
    profile: str = "balanced"
    provenance: dict[str, Any] = Field(default_factory=dict)

    def prompt_envelope(self, record: CanonicalRecord, *, prompt_version: str) -> PromptEnvelope:
        """Map the richer contract onto the repository's canonical eight-section envelope."""
        project = "\n\n".join(
            value for value in (self.project_background.text, self.theory_context.text) if value
        )
        source = "\n\n".join(
            value for value in (self.source_profile.text, self.codebook_context.text) if value
        )
        provenance = {
            "project": [
                self.project_background.provenance_token(),
                self.theory_context.provenance_token(),
            ],
            "source": [
                self.source_profile.provenance_token(),
                self.codebook_context.provenance_token(),
            ],
            "situational": [self.situational_summary.provenance_token()],
            "memory": [self.memory_context.provenance_token()],
            "rag": [self.rag_context.provenance_token()],
            "task": [self.task_contract.provenance_token()],
        }
        return build_prompt_envelope(
            record,
            task=self.task_contract.text,
            project_context=project,
            source_context=source,
            situational_context=self.situational_summary.text,
            memory_context=self.memory_context.text,
            rag_context=self.rag_context.text,
            context_provenance=provenance,
            prompt_version=prompt_version,
        )

    def audit_snapshot(self) -> dict[str, Any]:
        fragments = self.model_dump(mode="python", exclude={"provenance"})
        result: dict[str, Any] = {"profile": self.profile, "fragments": {}}
        for name, value in fragments.items():
            if name == "profile":
                continue
            text = str(value.get("text") or "")
            result["fragments"][name] = {
                "kind": value.get("kind"),
                "source": value.get("source"),
                "revision": value.get("revision"),
                "trust": value.get("trust"),
                "evidence_role": value.get("evidence_role"),
                "chars": len(text),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "record_ids": value.get("record_ids", []),
                "metadata": value.get("metadata", {}),
            }
        result["provenance"] = self.provenance
        return result


def _fragment(
    kind: str,
    text: str = "",
    *,
    source: str = "",
    revision: str = "",
    trust: str = "context",
    evidence_role: EvidenceRole = "context",
    record_ids: Iterable[str] = (),
    metadata: Mapping[str, Any] | None = None,
) -> AnalysisContextFragment:
    return AnalysisContextFragment(
        kind=kind,
        text=text.strip(),
        source=source,
        revision=revision,
        trust=trust,
        evidence_role=evidence_role,
        record_ids=list(record_ids),
        metadata=dict(metadata or {}),
    )


def codebook_context(entries: Iterable[CodebookEntry], *, limit: int = 80) -> AnalysisContextFragment:
    """Render bounded codebook priors explicitly as context, never source evidence."""
    values = list(entries)[: max(0, limit)]
    lines = [
        "Codebook entries are researcher/context priors, not proof that the current item expresses a label or formation.",
        "Contradiction, hybridity and abstention are valid outputs.",
    ]
    for entry in values:
        aliases = ", ".join(entry.aliases)
        line = f"- {entry.kind}: {entry.label}"
        if aliases:
            line += f"; aliases={aliases}"
        lines.append(line)
    return _fragment(
        "codebook_context",
        "\n".join(lines),
        source="codebook",
        trust="researcher_context",
        metadata={"entry_count": len(values)},
    )


def context_items_fragment(
    kind: str,
    items: Iterable[ContextItem],
    *,
    profile: str = "balanced",
    trust: str = "context",
) -> tuple[AnalysisContextFragment, ContextSnapshot]:
    """Bound arbitrary memory/RAG items through the existing context-profile runtime."""
    values = tuple(items)
    kwargs: dict[str, Any] = {"profile": profile}
    if kind == "rag_context":
        kwargs["rag_context"] = values
    elif kind == "theory_context":
        kwargs["theory_context"] = values
    elif kind == "situational_summary":
        kwargs["previous_summary"] = values
    else:
        kwargs["previous_records"] = values
    snapshot = assemble_context(**kwargs)
    fragment = _fragment(
        kind,
        snapshot.text,
        source="context_runtime",
        revision=snapshot.sha256,
        trust=trust,
        record_ids=[item.record_id for item in snapshot.items if item.record_id],
        metadata=dict(snapshot.provenance),
    )
    return fragment, snapshot


def build_analysis_context_bundle(
    record: CanonicalRecord,
    *,
    task: str,
    project_background: str = "",
    theory_context: str = "",
    source_profile: str = "",
    codebook_entries: Iterable[CodebookEntry] = (),
    situational_summary: str = "",
    memory_context: str = "",
    rag_context: str = "",
    profile: str = "balanced",
    provenance: Mapping[str, Any] | None = None,
) -> AnalysisContextBundle:
    """Build a context bundle without network access or hidden global state."""
    from .context_envelope import previous_analysis_text, source_item_text

    return AnalysisContextBundle(
        project_background=_fragment(
            "project_background", project_background, source="project_context"
        ),
        theory_context=_fragment(
            "theory_context", theory_context, source="method_context", trust="method"
        ),
        source_profile=_fragment(
            "source_profile", source_profile, source="source_profile", trust="researcher_context"
        ),
        codebook_context=codebook_context(codebook_entries),
        situational_summary=_fragment(
            "historical_summary_context",
            situational_summary,
            source="periodic_summary",
            trust="context_not_evidence",
        ),
        memory_context=_fragment(
            "memory_context", memory_context, source="context_memory", trust="context_not_evidence"
        ),
        rag_context=_fragment(
            "rag_context", rag_context, source="retrieval", trust="context_not_evidence"
        ),
        current_source=_fragment(
            "current_source",
            source_item_text(record),
            source=record.source_url,
            trust="source",
            evidence_role="source_evidence",
            record_ids=[record.source_url],
        ),
        previous_analysis=_fragment(
            "previous_analysis",
            previous_analysis_text(record),
            source=record.source_url,
            trust="provisional_analysis",
            record_ids=[record.source_url],
        ),
        task_contract=_fragment(
            "task_contract", task, source="prompt_library", trust="instruction", evidence_role="task_contract"
        ),
        profile=profile,
        provenance=dict(provenance or {}),
    )
