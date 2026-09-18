import json

import laclaugpt_discourse
import laclaugpt_process
import pytest


class FakeOllama:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return {"message": {"content": self.content}}


def _valid_discourse():
    return {
        "signifiers": [],
        "articulations": [],
        "demands": [],
        "chains_equivalence": [],
        "chains_difference": [],
        "collective_subjects": [],
        "frontiers": [],
        "affects": [],
        "nodal_point_candidates": [],
        "floating_signifier_candidates": [],
        "empty_signifier_candidates": [],
        "future_vision_candidates": [],
        "formation_evidence": [],
        "counter_evidence": [],
        "uncertainty_notes": [],
    }


def test_discourse_bounds_long_input_and_sets_context_options(monkeypatch):
    fake = FakeOllama(json.dumps(_valid_discourse()))
    monkeypatch.setattr(laclaugpt_discourse, "_ollama", lambda: fake)
    monkeypatch.setenv("LACLAUGPT_DISCOURSE_MAX_CHARS", "100")
    monkeypatch.setenv("LACLAUGPT_DISCOURSE_NUM_CTX", "4096")
    monkeypatch.setenv("LACLAUGPT_DISCOURSE_NUM_PREDICT", "512")

    raw, parsed = laclaugpt_discourse.analyze_discourse(
        {"document_id": "doc-long"},
        "x" * 1000,
        {"summary": "prior"},
    )

    assert raw
    call = fake.calls[0]
    assert call["options"]["num_ctx"] == 4096
    assert call["options"]["num_predict"] == 512
    assert "x" * 101 not in call["messages"][1]["content"]
    # input_metadata carries the full request record (the discourse stage stores it
    # verbatim as provenance), so assert the meaningful fields rather than exact equality.
    assert parsed["input_metadata"]["original_chars"] == 1000
    assert parsed["input_metadata"]["sent_chars"] == 100
    assert parsed["input_metadata"]["truncated"] is True
    assert parsed["input_metadata"]["max_chars"] == 100
    assert parsed["input_metadata"]["document_id"] == "doc-long"


def test_discourse_parse_error_keeps_raw_and_names_document(monkeypatch):
    fake = FakeOllama("")
    monkeypatch.setattr(laclaugpt_discourse, "_ollama", lambda: fake)

    with pytest.raises(laclaugpt_discourse.DiscourseParseError) as caught:
        laclaugpt_discourse.analyze_discourse(
            {"document_id": "doc-empty"},
            "text",
            {},
        )

    assert caught.value.raw_response == ""
    assert "doc-empty" in str(caught.value)
    assert "4 chars" in str(caught.value)


def test_process_persists_raw_response_on_discourse_parse_failure(monkeypatch):
    writes = []

    def fail_discourse(record, normalized_text, summary):
        raise laclaugpt_discourse.DiscourseParseError(
            "Discourse response parse failed for document doc-1 (12 chars, sent 12 chars)",
            raw_response="<bad-json>",
        )

    monkeypatch.setattr(laclaugpt_process, "analyze_discourse", fail_discourse)
    # The stage records failures through record_stage_failure (which also maintains the
    # attempt counters), not through a bare update_document call.
    monkeypatch.setattr(
        laclaugpt_process,
        "record_stage_failure",
        lambda source, stage, error, extra_fields=None, project_id=None: writes.append(
            {"stage": stage, "error": error, "extra_fields": extra_fields or {}}
        ),
    )

    laclaugpt_process.run_document(
        {
            "document_id": "doc-1",
            "normalized_text": "already here",
            "phase0_summary": {"summary": "existing"},
        },
        stage="discourse",
        project_id="ai26",
    )

    assert writes[-1]["stage"] == "discourse"
    assert writes[-1]["extra_fields"]["phase0_discourse_raw"] == "<bad-json>"
    assert "doc-1" in writes[-1]["error"]
