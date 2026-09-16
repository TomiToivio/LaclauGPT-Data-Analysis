from datetime import UTC, datetime

import pytest

from laclaugpt_data_analysis.canonical import CanonicalRecord, ContentSection, SourceSection
from laclaugpt_data_analysis.claims import claim_from_canonical


def _record() -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.org/ai26/item-1",
        source_native_ids={"id": "item-1"},
        source=SourceSection(
            platform="rss",
            author="Example Actor",
            created_at=datetime(2026, 9, 16, tzinfo=UTC),
        ),
        content=ContentSection(text="AI development should proceed rapidly but with worker protections."),
    )


def test_claim_from_canonical_binds_exact_evidence_and_stable_id():
    record = _record()
    quote = "AI development should proceed rapidly"
    first = claim_from_canonical(
        record,
        {
            "actor_id": "actor-example",
            "actor_name": "Example Actor",
            "concept_id": "rapid-development",
            "concept_label": "rapid AI development",
            "proposition": "Rapid AI development should proceed",
            "stance": "support",
            "evidence_quote": quote,
            "confidence": 0.9,
        },
        project_id="ai26",
        arena="elite",
        codebook_version="ai26-test-v1",
    )
    second = claim_from_canonical(
        record,
        {
            "actor_id": "actor-example",
            "actor_name": "Example Actor",
            "concept_id": "rapid-development",
            "concept_label": "rapid AI development",
            "proposition": "Rapid AI development should proceed",
            "stance": "support",
            "evidence_quote": quote,
            "confidence": 0.9,
        },
        project_id="ai26",
        arena="elite",
        codebook_version="ai26-test-v1",
    )
    assert first.statement_id == second.statement_id
    assert first.source_record_id == "item-1"
    assert first.evidence.exact is True
    assert first.platform == "rss"
    assert first.project_id == "ai26"


def test_claim_from_canonical_rejects_mismatched_offsets():
    record = _record()
    with pytest.raises(ValueError, match="does not match"):
        claim_from_canonical(
            record,
            {
                "actor_id": "a",
                "concept_id": "x",
                "proposition": "unsupported normalization",
                "evidence_quote": "wrong text",
                "evidence_start": 0,
                "evidence_end": 5,
            },
            project_id="ai26",
        )
