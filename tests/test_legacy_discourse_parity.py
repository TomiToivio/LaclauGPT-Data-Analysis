from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.codebooks import CodebookEntry
from laclaugpt_data_analysis.llm.base import ChatRequest, LLMCallProvenance, LLMResponse
from laclaugpt_data_analysis.pipeline import (
    AnalysisProposal,
    ChainProposal,
    EvidenceLinkedCandidate,
    RelationProposal,
    analyze_record,
)


class ParityProvider:
    def chat(self, request: ChatRequest) -> LLMResponse:
        assert "RETRIEVED CODEBOOK CANDIDATES (NOT EVIDENCE)" in request.user
        proposal = AnalysisProposal(
            summary="Synthetic parity summary",
            entities=["Synthetic Lab", "Researcher A"],
            topics=[
                EvidenceLinkedCandidate(
                    label="AI governance",
                    evidence=["AI should be governed democratically."],
                    confidence=0.8,
                )
            ],
            themes=[
                EvidenceLinkedCandidate(
                    label="democratic control",
                    evidence=["AI should be governed democratically."],
                    confidence=0.8,
                )
            ],
            sentiments=[
                EvidenceLinkedCandidate(
                    label="concerned",
                    evidence=["Unregulated systems worry us."],
                    confidence=0.7,
                )
            ],
            stances=[
                EvidenceLinkedCandidate(
                    label="supports democratic AI governance",
                    evidence=["AI should be governed democratically."],
                    confidence=0.9,
                )
            ],
            signifiers=["AI"],
            nodal_points=["democracy"],
            floating_signifiers=[
                EvidenceLinkedCandidate(
                    label="AI",
                    evidence=["AI should be governed democratically."],
                    confidence=0.5,
                    uncertainty="Requires cross-document comparison.",
                )
            ],
            empty_signifier_candidates=[
                EvidenceLinkedCandidate(
                    label="progress",
                    evidence=["Progress means AI that serves everyone."],
                    confidence=0.4,
                    uncertainty="Candidate only.",
                )
            ],
            formations=["democratic AI project"],
            discourses=["democratic technology discourse"],
            imaginaries=["democratically governed AI future"],
            equivalence_chains=[
                ChainProposal(
                    chain_type="equivalence",
                    members=["democracy", "accountability", "public control"],
                    evidence=["Democracy, accountability and public control belong together."],
                )
            ],
            difference_chains=[
                ChainProposal(
                    chain_type="difference",
                    members=["public control", "private ownership"],
                    evidence=["Public control differs from private ownership."],
                )
            ],
            antagonisms=[
                RelationProposal(
                    relation_type="antagonism",
                    source="democratic public",
                    target="unaccountable monopoly",
                    evidence=["An unaccountable monopoly blocks democratic control."],
                )
            ],
            actor_entity_relations=[
                RelationProposal(
                    relation_type="ADVOCATES",
                    source="Researcher A",
                    target="democratic control",
                    evidence=["Researcher A calls for democratic control."],
                )
            ],
            uncertainty=["Formation requires corpus validation."],
            abstentions=["No hegemonic finding from one document."],
        )
        return LLMResponse(
            content=proposal.model_dump_json(),
            provenance=LLMCallProvenance(
                requested_mode="local",
                requested_model="fake-model",
                resolved_model="fake-model",
                actual_mode="local",
                actual_model="fake-model",
                endpoint="fake",
            ),
        )


def test_expanded_discourse_fields_survive_pipeline_serialization_and_rendering():
    source_url = "https://example.invalid/parity/1"
    record = CanonicalRecord(
        source_url=source_url,
        content={
            "text": (
                "AI should be governed democratically. Unregulated systems worry us. "
                "Progress means AI that serves everyone."
            )
        },
    )
    codebook = [
        CodebookEntry(
            kind="signifier",
            label="AI",
            aliases=["artificial intelligence"],
            definition="Synthetic public fixture",
        )
    ]

    result = analyze_record(
        record,
        provider=ParityProvider(),
        codebook_entries=codebook,
        model="fake-model",
    )

    assert result.source_url == source_url
    assert result.analysis.topics[0].canonical_label == "AI governance"
    assert result.analysis.themes[0].label == "democratic control"
    assert result.analysis.sentiments[0].label == "concerned"
    assert result.analysis.stances[0].label.startswith("supports")
    assert result.analysis.floating_signifiers[0].label == "AI"
    assert result.analysis.floating_signifiers[0].metadata["corpus_validation_required"] is True
    assert result.analysis.empty_signifier_candidates[0].label == "progress"
    assert result.analysis.equivalence_chains[0].member_refs == [
        "democracy",
        "accountability",
        "public control",
    ]
    assert result.analysis.difference_chains[0].member_refs == [
        "public control",
        "private ownership",
    ]
    assert result.analysis.antagonisms[0].target_ref == "unaccountable monopoly"
    assert result.analysis.actor_entity_relations[0].source_ref == "Researcher A"

    assert result.evidence
    assert all(item.source_url == source_url for item in result.evidence)
    assert result.analysis.themes[0].evidence_ids
    assert result.analysis.antagonisms[0].evidence_ids
    assert result.analysis.themes[0].review_status == "PROVISIONAL"
    assert result.analysis.antagonisms[0].review_status == "PROVISIONAL"
    assert result.analysis.themes[0].provenance_id
    assert result.analysis.equivalence_chains[0].provenance_id
    assert result.provenance[-1].metadata["stage"] == "analysis"

    payload = result.model_dump_json()
    restored = CanonicalRecord.model_validate_json(payload)
    assert restored.analysis.empty_signifier_candidates[0].label == "progress"
    assert restored.analysis.actor_entity_relations[0].target_ref == "democratic control"

    report = result.human_readable.markdown
    assert "## Sentiment and stance" in report
    assert "Floating signifiers: AI" in report
    assert "Empty-signifier candidates: progress" in report
    assert "Equivalence chains: democracy ≡ accountability ≡ public control" in report
    assert "unaccountable monopoly" in report
    assert "Researcher A" in report


def test_text_only_parity_does_not_manufacture_multimodal_evidence():
    record = CanonicalRecord(
        source_url="https://example.invalid/text-only",
        content={"text": "AI should be governed democratically."},
    )
    result = analyze_record(record, provider=ParityProvider(), model="fake-model")
    assert result.content.frames == []
    assert result.content.ocr == []
    assert result.content.transcripts == []
    assert result.intermediate.frames == []
    assert result.intermediate.ocr == []
    assert result.intermediate.asr == []
