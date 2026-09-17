from __future__ import annotations

from typing import Any

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.codebooks import CodebookEntry
from laclaugpt_data_analysis.llm.base import ChatRequest, ChatResponse, LLMProvider
from laclaugpt_data_analysis.pipeline import analyze_record


class ParityProvider(LLMProvider):
    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        user = request.user
        if "Return JSON with keys: summary" in user:
            return ChatResponse(
                content='{"summary":"AI governance summary","themes":["democratic control"],"sentiment":"concerned","stance":"supports democratic control"}',
                model=request.model,
            )
        if "Return JSON with keys: signifiers" in user:
            return ChatResponse(
                content='{"signifiers":[{"label":"AI","kind":"floating_signifier","description":"contested meaning","evidence_quotes":["AI should be governed democratically."],"confidence":0.8},{"label":"progress","kind":"empty_signifier_candidate","description":"broadly available horizon","evidence_quotes":["Progress means AI that serves everyone."],"confidence":0.7}],"relations":[],"equivalence_chains":[{"members":["democracy","accountability","public control"],"evidence_quotes":["AI should be governed democratically."],"confidence":0.8}],"difference_chains":[{"members":["public control","unregulated systems"],"evidence_quotes":["Unregulated systems worry us."],"confidence":0.8}],"antagonisms":[],"us":[],"them":[],"frontier":[],"affects":[],"formula_of_populism":null}',
                model=request.model,
            )
        if "Return JSON with keys: canonical_label" in user:
            return ChatResponse(
                content='{"canonical_label":"AI governance","keywords":["AI","governance"],"confidence":0.9}',
                model=request.model,
            )
        if "Return JSON with keys: entities" in user:
            return ChatResponse(content='{"entities":[]}', model=request.model)
        if "Return JSON with keys: frames" in user:
            return ChatResponse(content='{"frames":[]}', model=request.model)
        if "Return JSON with keys: stances" in user:
            return ChatResponse(
                content='{"stances":[{"label":"supports democratic control","target":"AI","evidence_quotes":["AI should be governed democratically."],"confidence":0.8}]}',
                model=request.model,
            )
        if "Return JSON with keys: sentiments" in user:
            return ChatResponse(
                content='{"sentiments":[{"label":"concerned","target":"unregulated systems","evidence_quotes":["Unregulated systems worry us."],"confidence":0.8}]}',
                model=request.model,
            )
        return ChatResponse(content="{}", model=request.model)


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
    provider = ParityProvider()

    result = analyze_record(
        record,
        provider=provider,
        codebook_entries=codebook,
        model="fake-model",
    )

    assert any(
        "RETRIEVED CODEBOOK CANDIDATES (NOT EVIDENCE)" in request.user
        for request in provider.requests
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
        "unregulated systems",
    ]
    serialized = result.canonical_dict()
    assert serialized["analysis"]["floating_signifiers"][0]["label"] == "AI"
    assert serialized["analysis"]["empty_signifier_candidates"][0]["label"] == "progress"
