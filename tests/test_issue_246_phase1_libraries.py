from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from laclaugpt_data_analysis.analysis.phase1_baselines import (
    OptionalBaselineDependencyError,
    available_backends,
    keybert_keywords,
    textacy_terms,
    yake_keywords,
)


def test_phase1_baselines_are_explicit_and_descriptive():
    assert available_backends() == ("textacy", "yake", "keybert")


def test_yake_baseline_with_synthetic_module(monkeypatch):
    class FakeExtractor:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def extract_keywords(self, text):
            assert "AI policy" in text
            return [("AI policy", 0.01), ("regulation", 0.08)]

    monkeypatch.setitem(sys.modules, "yake", SimpleNamespace(KeywordExtractor=FakeExtractor))
    rows = yake_keywords("AI policy and regulation", top_n=2)
    assert [row.term for row in rows] == ["AI policy", "regulation"]
    assert all(row.interpretation_status == "DESCRIPTIVE_ONLY" for row in rows)


def test_keybert_requires_caller_supplied_model(monkeypatch):
    class FakeKeyBERT:
        def __init__(self, model):
            assert model == "already-loaded-model"

        def extract_keywords(self, text, **kwargs):
            assert kwargs["top_n"] == 1
            return [("public AI", 0.73)]

    monkeypatch.setitem(sys.modules, "keybert", SimpleNamespace(KeyBERT=FakeKeyBERT))
    rows = keybert_keywords("public AI debate", model="already-loaded-model", top_n=1)
    assert rows[0].backend == "keybert"
    assert rows[0].score == pytest.approx(0.73)


def test_textacy_uses_caller_prepared_doc(monkeypatch):
    def textrank(doc, topn):
        assert doc == "prepared-spacy-doc"
        assert topn == 1
        return [("governance", 0.5)]

    fake = SimpleNamespace(
        extract=SimpleNamespace(keyterms=SimpleNamespace(textrank=textrank))
    )
    monkeypatch.setitem(sys.modules, "textacy", fake)
    rows = textacy_terms("prepared-spacy-doc", top_n=1)
    assert rows[0].term == "governance"
    assert rows[0].backend == "textacy:textrank"


def test_missing_optional_dependency_has_actionable_error(monkeypatch):
    import laclaugpt_data_analysis.analysis.phase1_baselines as module

    real_import = module.import_module

    def fake_import(name):
        if name == "yake":
            raise ImportError("synthetic missing dependency")
        return real_import(name)

    monkeypatch.setattr(module, "import_module", fake_import)
    with pytest.raises(OptionalBaselineDependencyError, match="phase1-nlp"):
        yake_keywords("synthetic")
