from laclaugpt_preprocess import preprocess_record
from laclaugpt_postprocess import validate_summary


def test_phase0_text_smoke():
    source = {
        "source_url": "https://example.org/ai",
        "source_date": "2026-09-18",
        "source_text": "  AI   regulation should protect workers.  ",
        "actor_name": "Example Actor",
        "arena": "parliamentary",
        "ai_formation": "critical_ai",
        "title": "Example",
    }
    processed = preprocess_record(source)
    assert processed["normalized_text"] == "AI regulation should protect workers."
    assert processed["metadata"]["ai_formation"] == "critical_ai"

    raw_summary = {
        "summary": "The actor argues for worker-protective AI regulation.",
        "claims": ["AI regulation should protect workers."],
        "actors": ["Example Actor"],
        "entities": [],
        "topics": ["AI governance", "labour"],
        "signifiers": ["AI regulation", "workers"],
        "future_visions": [],
        "governance_positions": ["worker protection"],
        "evidence": ["AI regulation should protect workers."],
        "uncertainty_notes": ["Formation seed is contextual only."],
        "model_metadata": {"provider": "fake", "model": "fake"},
        "prompt_version": "test",
    }
    working = {**source, **processed}
    validated = validate_summary(working, raw_summary)
    assert validated.source_url == source["source_url"]
    assert validated.document_id == processed["document_id"]


def test_phase0_postprocess_normalises_scalar_list_fields():
    source = {
        "source_url": "https://example.org/ai-risk",
        "source_text": "Superhuman AI could create catastrophic outcomes.",
        "title": "AI risk",
    }
    processed = preprocess_record(source)
    working = {**source, **processed}
    raw_summary = {
        "summary": "The document warns about catastrophic outcomes from superhuman AI.",
        "claims": ["Superhuman AI could create catastrophic outcomes."],
        "actors": [],
        "entities": [],
        "topics": ["AI risk"],
        "signifiers": ["superhuman AI"],
        "future_visions": "A catastrophic outcome from superhuman AI.",
        "governance_positions": "Restrict development of superhuman AI.",
        "evidence": "Superhuman AI could create catastrophic outcomes.",
        "uncertainty_notes": "Short source document.",
        "model_metadata": {"provider": "fake", "model": "fake"},
        "prompt_version": "test",
    }

    validated = validate_summary(working, raw_summary)

    assert validated.future_visions == ["A catastrophic outcome from superhuman AI."]
    assert validated.governance_positions == ["Restrict development of superhuman AI."]
    assert validated.evidence == ["Superhuman AI could create catastrophic outcomes."]
    assert validated.uncertainty_notes[0] == "Short source document."
    assert "future_visions" in validated.uncertainty_notes[-1]
    assert "governance_positions" in validated.uncertainty_notes[-1]
    assert "evidence" in validated.uncertainty_notes[-1]
    assert "uncertainty_notes" in validated.uncertainty_notes[-1]
