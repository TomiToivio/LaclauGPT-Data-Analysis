"""STEP 7 - Social Network Analysis.

Optional Phase 2 projection of observed communication relations supplied by
source metadata or reviewed coding. Shared topics, DNA agreement and semantic
similarity do not establish social ties.
"""

# TOMI-LOCKED: changes to this step require Tomi's explicit authorization.
from pipeline_models import DNAResult, HumanPipelineRecord, SNAResult

from laclaugpt_data_analysis.knowledge_graph import SNARelation, project_sna


def analyze_sna(record: HumanPipelineRecord, dna: DNAResult) -> SNAResult:
    """Project only explicit observed ties, preserving provenance and direction."""
    relations = []
    seen = set()
    for raw in record.metadata.get("sna_relations", []):
        relation = SNARelation.model_validate(raw)
        if relation.source_url != record.source_url:
            raise ValueError("SNA source identity mismatch")
        if relation.relation_type == "co-occurrence":
            raise ValueError("Co-occurrence is not an observed communication tie")
        if not all(
            value and value.strip()
            for value in (
                relation.relation_id, relation.source_actor_id,
                relation.target_actor_id, relation.provenance_id,
            )
        ) or not relation.evidence_ids or not all(
            value.strip() for value in relation.evidence_ids
        ):
            raise ValueError("SNA requires stable identities and evidence provenance")
        if relation.relation_id in seen:
            raise ValueError("Duplicate relation ID")
        seen.add(relation.relation_id)
        relations.append(relation)

    graph = project_sna(relations, project_id=record.project)
    graph.validate_references()
    return SNAResult(
        nodes=[node.model_dump(mode="json") for node in graph.nodes],
        edges=[edge.model_dump(mode="json") for edge in graph.edges],
    )
