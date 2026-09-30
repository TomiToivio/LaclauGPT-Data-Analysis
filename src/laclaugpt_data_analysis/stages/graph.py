"""Stage 5 — graph: project the canonical analysis into a portable evidence graph.

Purpose
-------
Give the analysis an exportable topology: documents, the evidence found in them,
the analytical objects built from that evidence, and the relations between them.
GraphML/GEXF exports and the dashboard's network views read this projection.

Why it is a projection, not a second ontology
---------------------------------------------
Canonical object and relation ids remain the single source of truth; this module
only reshapes them. Introducing graph-specific identifiers would create a second
set of things to keep in sync, and the two would drift.

A note on relation ids
----------------------
Relation ids identify *edges*, not nodes. Do not emit an edge pointing at a
relation id: that creates a dangling reference, and GraphML/GEXF silently
materialise such references as phantom nodes on export. Relation evidence stays
attached to the relation edge through `evidence_ids`.

Inputs
------
* `record` — a record whose analysis surface has already been populated by
  postprocess; the graph reads that surface and adds nothing to it.

Outputs
-------
* a plain dict `{"schema", "source_url", "nodes", "edges"}` suitable for
  GraphML/GEXF export; the caller decides where it is persisted.
"""
from __future__ import annotations

from typing import Any

from ..canonical import CanonicalRecord

SCHEMA = "laclaugpt-discourse-graph-v1"


def build_discourse_graph(record: CanonicalRecord) -> dict[str, Any]:
    """Build the per-record evidence graph from the canonical analysis."""
    nodes: list[dict[str, Any]] = [
        {
            "id": record.source_url,
            "type": "document",
            "label": record.content.title or record.source_url,
        }
    ]
    edges: list[dict[str, Any]] = []

    # Evidence nodes: every proposed quotation, linked back to its document.
    for evidence in record.evidence:
        nodes.append(
            {
                "id": evidence.evidence_id,
                "type": "evidence",
                "label": evidence.quote or evidence.ref or evidence.evidence_id,
                "kind": evidence.kind,
                "provenance_id": evidence.provenance_id,
            }
        )
        edges.append(
            {
                "id": f"evidence-in:{evidence.evidence_id}",
                "source": evidence.evidence_id,
                "target": record.source_url,
                "type": "EVIDENCE_IN",
            }
        )

    # Analytical objects: each links to its document and to the evidence that
    # supports it, so a reader can always walk from a claim back to the source.
    object_groups = [
        record.analysis.entities,
        record.analysis.topics,
        record.analysis.signifiers,
        record.analysis.nodal_points,
        record.analysis.floating_signifiers,
        record.analysis.empty_signifier_candidates,
        record.analysis.formations,
        record.analysis.imaginaries,
        record.analysis.frontier,
        record.analysis.affects,
    ]
    for group in object_groups:
        for obj in group:
            object_id = getattr(obj, "object_id", None) or getattr(obj, "entity_id", None)
            if object_id is None:
                object_id = getattr(obj, "topic_id", None) or getattr(obj, "label", None)
            if object_id is None:
                continue
            label = getattr(obj, "label", None) or getattr(obj, "name", None) or str(object_id)
            kind = getattr(obj, "kind", None) or getattr(obj, "entity_type", None) or "topic"
            review_status = getattr(obj, "review_status", "PROVISIONAL")
            provenance_id = getattr(obj, "provenance_id", "")
            nodes.append(
                {
                    "id": str(object_id),
                    "type": str(kind),
                    "label": str(label),
                    "review_status": str(review_status),
                    "provenance_id": str(provenance_id),
                }
            )
            edges.append(
                {
                    "id": f"candidate-in:{object_id}",
                    "source": record.source_url,
                    "target": str(object_id),
                    "type": "CANDIDATE_IN",
                }
            )
            for evidence_id in getattr(obj, "evidence_ids", []):
                edges.append(
                    {
                        "id": f"evidence-for:{evidence_id}:{object_id}",
                        "source": str(evidence_id),
                        "target": str(object_id),
                        "type": "EVIDENCE_FOR",
                    }
                )

    relations = (
        list(record.analysis.relations)
        + list(record.analysis.antagonisms)
        + list(record.analysis.actor_entity_relations)
    )
    for relation in relations:
        edges.append(
            {
                "id": relation.relation_id,
                "source": relation.source_ref,
                "target": relation.target_ref,
                "type": relation.relation_type.upper(),
                "review_status": relation.review_status,
                "provenance_id": relation.provenance_id,
                "evidence_ids": list(relation.evidence_ids),
            }
        )
        # Relation evidence remains attached to the relation edge via
        # `evidence_ids`. Do not emit an edge to `relation.relation_id`:
        # relation IDs identify edges, not nodes, and using them as endpoints
        # creates dangling references that GraphML/GEXF silently materialize as
        # phantom nodes during export.

    for chain in record.analysis.equivalence_chains + record.analysis.difference_chains:
        relation_type = (
            "EQUIVALENT_TO" if chain.chain_type == "equivalence" else "DIFFERENTIATED_FROM"
        )
        for left, right in zip(chain.member_refs, chain.member_refs[1:], strict=False):
            edges.append(
                {
                    "id": f"{chain.chain_id}:{left}:{right}",
                    "source": left,
                    "target": right,
                    "type": relation_type,
                    "chain_id": chain.chain_id,
                    "evidence_ids": list(chain.evidence_ids),
                    "review_status": chain.review_status,
                    "provenance_id": chain.provenance_id,
                }
            )

    return {
        "schema": SCHEMA,
        "source_url": record.source_url,
        "nodes": nodes,
        "edges": edges,
    }
