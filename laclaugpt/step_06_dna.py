"""STEP 6 - Discourse Network Analysis.

Optional Phase 2 projection of explicit, evidence-linked actor/concept coding.
The existing DNA coder or a human reviewer supplies the coded statements;
Laclaudian themes, demands and signifiers alone are not binary stances.
"""

# TOMI-LOCKED: changes to this step require Tomi's explicit authorization.
from pipeline_models import DNAResult, HumanPipelineRecord, LaclauResult

from laclaugpt_data_analysis.interoperability import DiscourseStatement
from laclaugpt_data_analysis.knowledge_graph import project_dna


def analyze_dna(record: HumanPipelineRecord, laclau: LaclauResult) -> DNAResult:
    """Validate and project explicitly coded statements; abstain if none exist."""
    statements = []
    seen = set()
    for raw in record.metadata.get("dna_statements", []):
        statement = DiscourseStatement.model_validate(raw)
        if statement.source_url != record.source_url:
            raise ValueError("DNA source identity mismatch")
        if statement.review_status in {"REJECTED", "SUPERSEDED"}:
            continue
        if not statement.qualifier or not statement.qualifier.strip():
            continue
        if not all(
            value and value.strip()
            for value in (
                statement.actor_id, statement.concept_id, statement.statement_id,
                statement.evidence_id, statement.provenance_id,
            )
        ):
            raise ValueError("DNA requires stable identities and evidence provenance")
        if statement.statement_id in seen:
            raise ValueError("Duplicate statement ID")
        seen.add(statement.statement_id)
        if statement.actor_id == statement.concept_id:
            raise ValueError("Actor and concept IDs must differ")
        statements.append(statement)

    graph = project_dna(statements, project_id=record.project)
    graph.validate_references()
    return DNAResult(
        claims=[statement.model_dump(mode="json") for statement in statements],
        edges=[edge.model_dump(mode="json") for edge in graph.edges],
    )
