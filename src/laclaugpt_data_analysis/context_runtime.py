"""Bounded, inspectable context assembly for analysis stages.

The runtime never performs network access itself. Callers provide already-loaded
or retrieved context records, making the module deterministic in CI and usable
without memory/RAG services.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .context_profiles import ContextProfile, load_context_profile


@dataclass(frozen=True)
class ContextItem:
    kind: str
    text: str
    source: str
    record_id: str = ""
    trust: str = "context"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextSnapshot:
    profile: str
    text: str
    sha256: str
    items: tuple[ContextItem, ...]
    provenance: Mapping[str, Any]


def load_text_context(path: str | Path, *, kind: str, trust: str = "context") -> ContextItem:
    source = Path(path)
    raw = source.read_text(encoding="utf-8")
    if source.suffix.casefold() == ".json":
        value = json.loads(raw)
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    else:
        text = raw.strip()
    return ContextItem(
        kind=kind,
        text=text,
        source=source.name,
        trust=trust,
        metadata={"sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()},
    )


def assemble_context(
    *,
    profile: str | ContextProfile = "balanced",
    codebook_items: Iterable[ContextItem] = (),
    previous_summary: Iterable[ContextItem] = (),
    corpus_context: Iterable[ContextItem] = (),
    previous_records: Iterable[ContextItem] = (),
    researcher_validation: Iterable[ContextItem] = (),
    theory_context: Iterable[ContextItem] = (),
    rag_context: Iterable[ContextItem] = (),
) -> ContextSnapshot:
    """Assemble one deterministic context block under an explicit policy."""
    policy = load_context_profile(profile) if isinstance(profile, str) else profile
    selected: list[ContextItem] = []

    if policy.context_memory:
        selected.extend(list(codebook_items)[: policy.glossary_top_k])
        selected.extend(list(previous_records)[: policy.max_records])
    if policy.inject_previous_batch_summary:
        selected.extend(previous_summary)
    if policy.inject_corpus_stats:
        selected.extend(corpus_context)
    if policy.inject_researcher_validation:
        selected.extend(researcher_validation)
    if policy.inject_theory_context:
        selected.extend(theory_context)
    if policy.vector_rag:
        selected.extend(rag_context)

    if policy.fail_on_missing_codebook and policy.inject_codebook and not tuple(codebook_items):
        raise RuntimeError("selected validation context profile requires a codebook")

    selected = selected[: policy.max_records]
    rendered: list[str] = []
    kept: list[ContextItem] = []
    used = 0
    for item in selected:
        header = f"[{item.kind}] source={item.source} trust={item.trust}"
        if item.record_id:
            header += f" id={item.record_id}"
        block = f"{header}\n{item.text.strip()}".strip()
        if not block:
            continue
        remaining = policy.max_context_chars - used
        if remaining <= 0:
            break
        clipped = block[:remaining]
        rendered.append(clipped)
        kept.append(item)
        used += len(clipped)

    text = "\n\n".join(rendered)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    provenance = {
        "profile": policy.name,
        "sha256": digest,
        "chars": len(text),
        "item_count": len(kept),
        "max_context_chars": policy.max_context_chars,
        "max_records": policy.max_records,
        "max_tokens_hint": policy.max_tokens_hint,
        "vector_rag": policy.vector_rag,
        "sources": [
            {
                "kind": item.kind,
                "source": item.source,
                "record_id": item.record_id,
                "trust": item.trust,
                "metadata": dict(item.metadata),
            }
            for item in kept
        ],
    }
    return ContextSnapshot(
        profile=policy.name,
        text=text,
        sha256=digest,
        items=tuple(kept),
        provenance=provenance,
    )
