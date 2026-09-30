"""Stage 4 — postprocess: turn proposals into the canonical analysis record.

Purpose
-------
Take the two model proposals (description + discourse analysis) and write them
into the canonical record's analysis surface as *structured, evidence-linked,
human-reviewable* objects. Nothing new is decided here; this stage is where the
pipeline's outputs become stable enough for export, dashboards and review.

Why it is a separate stage
--------------------------
It is the pipeline's schema boundary. Keeping it distinct means:

* the scientific output contract can be read in one place;
* the stages before it can be re-run without touching stored schema;
* the review semantics (every object `PROVISIONAL`) are applied uniformly rather
  than decided per model call.

Human-review semantics
----------------------
Every object this stage writes is `review_status="PROVISIONAL"`. That is not a
formality: it is the pipeline's statement that a model proposal is not a finding
until a researcher validates it. Objects whose validity depends on the wider
corpus rather than this one item (floating/empty signifiers, formations) are
additionally marked `corpus_validation_required`.

Inputs
------
* `record`, the `summary` proposal and the `discourse` proposal;
* `context` — to resolve which optional capability projections are switched on.

Outputs
-------
The record's `analysis` surface, populated and marked analysed; stage outputs
`postprocess` and `effective_analysis_stages`; research layers ensured. Returns
the record.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from ..canonical import (
    CanonicalRecord,
    DiscourseObject,
    Entity,
    Relation,
    RelationChain,
)
from ..models import Topic
from ..research_record import ensure_research_layers
from ..social_semiotic import UncertaintyObservation
from .evidence import evidence_ids
from .proposals import (
    DiscourseProposal,
    DiscursiveElement,
    DiscursiveRelation,
    SummaryResult,
)
from .shared import (
    PipelineContext,
    append_stage,
    effective_stage_set,
    enabled,
    project_config_sha256,
)


def _summary_uncertainty(summary: SummaryResult) -> list[str]:
    """Flatten the summary's uncertainty notes to plain strings."""
    values = getattr(summary, "uncertainty", [])
    return [
        item.description if isinstance(item, UncertaintyObservation) else str(item)
        for item in values
        if item
    ]


def _objects(
    record: CanonicalRecord, items: list[DiscursiveElement], kind: str
) -> list[DiscourseObject]:
    """Build canonical objects from proposed elements, attaching their evidence.

    Signifiers and formations are flagged `corpus_validation_required`: whether a
    signifier is genuinely floating, or empty, or a formation at all is a claim
    about the wider corpus, not about this item. Marking it here keeps a single
    document from asserting something only the collection can establish.
    """
    corpus_required = kind in {"floating_signifier", "empty_signifier", "formation"}
    return [
        DiscourseObject(
            object_id=f"{kind}:{index}",
            label=item.label,
            kind=kind,
            evidence_ids=evidence_ids(record, item.evidence, f"{kind}:{index}"),
            confidence=item.confidence,
            uncertainty=item.uncertainty,
            review_status="PROVISIONAL",
            metadata={"corpus_validation_required": corpus_required},
        )
        for index, item in enumerate(items, start=1)
    ]


def _relation_chains(
    record: CanonicalRecord,
    relations: list[DiscursiveRelation],
    chain_type: Literal["equivalence", "difference"],
) -> list[RelationChain]:
    """Build equivalence/difference chains, dropping self-relations.

    A relation from an element to itself carries no analytical content, so it is
    skipped rather than stored as a degenerate chain.
    """
    return [
        RelationChain(
            chain_id=f"{chain_type}_chain:{index}",
            chain_type=chain_type,
            member_refs=[item.source, item.target],
            evidence_ids=evidence_ids(record, item.evidence, f"{chain_type}_chain:{index}"),
            review_status="PROVISIONAL",
        )
        for index, item in enumerate(relations, start=1)
        if item.source and item.target and item.source != item.target
    ]


def _project_summary_capabilities(
    record: CanonicalRecord, summary: SummaryResult, context: PipelineContext
) -> None:
    """Project the descriptive pass onto the optional summary capabilities.

    Entities, topics and sentiment are separate capabilities a project may switch
    on. When on, they are projected from the *description* rather than re-derived,
    so the same text cannot yield two different topic sets.
    """
    if enabled(context, "entities"):
        record.analysis.entities = [
            Entity(entity_id=f"summary-entity:{i}", label=label, review_status="PROVISIONAL")
            for i, label in enumerate(summary.entities, start=1)
        ]
    if enabled(context, "topics"):
        record.analysis.topics = [
            Topic(
                topic_id=f"summary-topic:{i}",
                canonical_label=label,
                metadata={"source_stage": "summary", "review_status": "PROVISIONAL"},
            )
            for i, label in enumerate(summary.topics, start=1)
        ]
    if enabled(context, "sentiment"):
        record.analysis.sentiments = [
            DiscourseObject(
                object_id=f"summary-sentiment:{i}",
                label=label,
                kind="sentiment",
                review_status="PROVISIONAL",
                metadata={"source_stage": "summary"},
            )
            for i, label in enumerate(summary.sentiment_observations, start=1)
        ]


def postprocess_record(
    record: CanonicalRecord,
    summary: SummaryResult,
    discourse: DiscourseProposal,
    context: PipelineContext | None = None,
) -> CanonicalRecord:
    """Write both proposals into the canonical analysis record."""
    ctx = context or PipelineContext()
    record.analysis.status = "analyzed"
    record.analysis.summary = summary.summary or None
    _project_summary_capabilities(record, summary, ctx)

    # Signifiers: floating and empty candidates are stored separately, then
    # combined, so a reviewer can tell which kind the model proposed.
    record.analysis.floating_signifiers = _objects(
        record, discourse.floating_signifier_candidates, "floating_signifier"
    )
    record.analysis.empty_signifier_candidates = _objects(
        record, discourse.empty_signifier_candidates, "empty_signifier"
    )
    record.analysis.signifiers = list(record.analysis.floating_signifiers) + list(
        record.analysis.empty_signifier_candidates
    )
    record.analysis.nodal_points = _objects(record, discourse.nodal_point_candidates, "nodal_point")
    record.analysis.formations = _objects(record, discourse.formation_candidates, "formation")
    record.analysis.imaginaries = (
        _objects(record, discourse.imaginary_candidates, "imaginary")
        if enabled(ctx, "sociotechnical_imaginaries")
        else []
    )
    record.analysis.us = _objects(record, discourse.collective_subjects, "collective_subject")
    record.analysis.frontier = _objects(record, discourse.frontiers, "frontier")
    record.analysis.affects = _objects(record, discourse.affects, "affect")
    record.analysis.formula_of_populism = {
        "populist": discourse.populist,
        "non_populist_reason": discourse.non_populist_reason,
        **discourse.formula_of_populism,
    }
    record.analysis.uncertainty = list(
        dict.fromkeys(_summary_uncertainty(summary) + discourse.uncertainty)
    )
    record.analysis.abstentions = discourse.abstentions
    record.analysis.equivalence_chains = _relation_chains(
        record, discourse.equivalences, "equivalence"
    )
    record.analysis.difference_chains = _relation_chains(
        record, discourse.differences, "difference"
    )
    record.analysis.antagonisms = [
        Relation(
            relation_id=f"antagonism:{i}",
            relation_type=item.relation_type,
            source_ref=item.source,
            target_ref=item.target,
            evidence_ids=evidence_ids(record, item.evidence, f"antagonism:{i}"),
            review_status="PROVISIONAL",
        )
        for i, item in enumerate(discourse.antagonisms, start=1)
    ]

    # The combined relation list keeps every relation kind together for export and
    # graphing; the per-kind lists above remain the authoritative typed views.
    relations = (
        discourse.articulations
        + discourse.equivalences
        + discourse.differences
        + discourse.antagonisms
    )
    record.analysis.relations = [
        Relation(
            relation_id=f"relation:{i}",
            relation_type=item.relation_type,
            source_ref=item.source,
            target_ref=item.target,
            evidence_ids=evidence_ids(record, item.evidence, f"relation:{i}"),
            review_status="PROVISIONAL",
        )
        for i, item in enumerate(relations, start=1)
    ]

    append_stage(
        record,
        "postprocess",
        {
            "created_at": datetime.now(UTC).isoformat(),
            "schema": "canonical-analysis-v1",
            "validated": True,
            "source_stages": ["summary", "discourse"],
            "topics": [item.canonical_label for item in record.analysis.topics],
            "entities": [item.label for item in record.analysis.entities],
            "sentiments": [item.label for item in record.analysis.sentiments],
            "uncertainty": record.analysis.uncertainty,
        },
    )
    # Record which optional stages were actually in force for this run, so the
    # result does not have to be interpreted by guessing from its shape.
    append_stage(
        record,
        "effective_analysis_stages",
        {
            "stages": effective_stage_set(ctx),
            "project_config_revision": ctx.project_config_revision,
            "project_config_sha256": project_config_sha256(ctx),
        },
    )
    record.analysis.completed_at = datetime.now(UTC)
    return ensure_research_layers(record)
