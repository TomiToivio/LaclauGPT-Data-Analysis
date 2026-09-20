"""Optional accepted-memory normalization for canonical Phase 1 records.

This layer only substitutes accepted stable identifiers and records memory refs.
It never creates/promotes memory objects and never changes evidence/provenance.
"""
from __future__ import annotations

from .canonical import CanonicalRecord


def apply_accepted_memory(record: CanonicalRecord, store) -> CanonicalRecord:
    """Normalize labels to accepted stable IDs, abstaining on unknown/ambiguous aliases."""
    refs: set[str] = set(record.analysis.memory_refs)

    actor = (record.source.author_fullname or record.source.author).strip()
    if actor:
        resolved = store.resolve_accepted(actor, "actor")
        if resolved.decision == "EXISTING":
            refs.add(resolved.obj_id)

    for entity in record.analysis.entities:
        resolved = store.resolve_accepted(entity.label, "entity")
        if resolved.decision == "EXISTING":
            entity.entity_id = resolved.obj_id
            entity.label = resolved.label
            refs.add(resolved.obj_id)

    for topic in record.analysis.topics:
        resolved = store.resolve_accepted(topic.canonical_label, "topic")
        if resolved.decision == "EXISTING":
            topic.topic_id = resolved.obj_id
            topic.canonical_label = resolved.label
            refs.add(resolved.obj_id)

    for item in record.analysis.signifiers:
        resolved = store.resolve_accepted(item.label, "signifier")
        if resolved.decision == "EXISTING":
            item.object_id = resolved.obj_id
            item.label = resolved.label
            refs.add(resolved.obj_id)

    record.analysis.memory_refs = sorted(refs)
    return record
