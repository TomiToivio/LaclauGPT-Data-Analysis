"""The evidence gate for AI26 (#460): a coded field must be able to point at its evidence.

The audit measured coding that no evidence supports: records with no source text receive a
formation label 96.3 % of the time, and 957 records whose text is unusable were coded anyway.
The pipeline already knows which spans resolve — `stages/evidence.py` sets
`Evidence.metadata["exact"]` from `locate_quote()` against the stored source — but nothing
consumed that fact, so an object whose every quotation failed to locate was stored beside one
whose quotation resolved.

This module consumes it. An object or relation is kept only when at least one of its
`evidence_ids` resolves to an `Evidence` with `exact: True`; otherwise it is dropped and the
label is recorded in `analysis.uncertainty`, where a reader can see what was proposed and not
supported. The evidence records themselves are never deleted: the audit trail keeps the failed
quotation too, because "the model quoted this and it is not in the source" is a finding.

Off by default. Turning it on changes what the instrument emits, which is a decision recorded in
`docs/AI26_OPEN_DECISIONS.md` (D4), not a default an agent should choose. `dry_run=True` computes
exactly what the gate would drop without touching the record — that is how the decision can be
made against the live corpus instead of against an argument.
"""
from __future__ import annotations

import os
from typing import Any

from .canonical import CanonicalRecord

#: Env var read when a caller does not pass an explicit value.
ENV_FLAG = "LACLAUGPT_AI26_REQUIRE_EVIDENCE"

#: Coded fields that carry evidence-backed objects. `frontier`, `affects`, `sentiments` and the
#: summary projections are excluded because they are not evidence-annotated in this pipeline.
CODED_OBJECT_FIELDS = (
    "formations",
    "signifiers",
    "nodal_points",
    "floating_signifiers",
    "empty_signifier_candidates",
    "imaginaries",
    "us",
    "them",
)
CODED_RELATION_FIELDS = ("antagonisms", "equivalence_chains", "difference_chains")

#: How many dropped labels per field are named in `analysis.uncertainty`. The count is always exact;
#: the list is bounded so one bad record cannot bloat the canonical document.
MAX_NAMED_DROPS = 12


def evidence_gate_enabled(explicit: bool | None = None) -> bool:
    """Whether the gate is on: explicit argument, else the env flag, else off."""
    if explicit is not None:
        return explicit
    return os.environ.get(ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def _resolving_ids(record: CanonicalRecord) -> set[str]:
    return {
        evidence.evidence_id
        for evidence in record.evidence
        if bool((evidence.metadata or {}).get("exact"))
    }


def _label_of(item: Any) -> str:
    for attribute in ("label", "relation_type", "chain_type"):
        value = getattr(item, attribute, None)
        if value:
            return str(value)
    return getattr(item, "object_id", "") or getattr(item, "relation_id", "") or "?"


def apply_evidence_gate(
    record: CanonicalRecord, *, dry_run: bool = False
) -> dict[str, Any]:
    """Drop coded items with no resolving evidence span; report what happened.

    `dry_run=True` returns the same report and mutates nothing.
    """
    resolving = _resolving_ids(record)
    report: dict[str, Any] = {
        "enabled": True,
        "dry_run": dry_run,
        "resolving_evidence_spans": len(resolving),
        "fields": {},
        "dropped_total": 0,
        "kept_total": 0,
    }
    dropped_labels: list[str] = []

    for field_name in CODED_OBJECT_FIELDS + CODED_RELATION_FIELDS:
        items = getattr(record.analysis, field_name, None) or []
        if not isinstance(items, list) or not items:
            continue
        kept, dropped = [], []
        for item in items:
            ids = set(getattr(item, "evidence_ids", []) or [])
            if ids & resolving:
                kept.append(item)
            else:
                dropped.append(item)
        report["fields"][field_name] = {
            "total": len(items),
            "kept": len(kept),
            "dropped": len(dropped),
        }
        report["kept_total"] += len(kept)
        report["dropped_total"] += len(dropped)
        if dropped:
            dropped_labels.extend(f"{field_name}:{_label_of(item)}" for item in dropped[:MAX_NAMED_DROPS])
        if dropped and not dry_run:
            setattr(record.analysis, field_name, kept)

    if dropped_labels:
        note = (
            "evidence_gate: proposed without a resolvable evidence span and not stored: "
            + "; ".join(dropped_labels)
        )
        report["uncertainty_note"] = note
        if not dry_run:
            record.analysis.uncertainty = list(record.analysis.uncertainty) + [note]

    return report
