from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "laclaugpt" / "laclaugpt_seed_graph.py"

spec = importlib.util.spec_from_file_location("laclaugpt_seed_graph", MODULE)
seed_graph = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(seed_graph)


def _codebook():
    return {
        "entries": [
            {
                "id": "ai_safety",
                "kind": "formation",
                "label": "ai_safety",
                "display_label": "AI safety",
                "aliases": ["AI safety discourse"],
                "definition": "Provisional safety formation.",
                "metadata": {"state": "PROVISIONAL"},
            },
            {
                "id": "alignment",
                "kind": "signifier",
                "label": "alignment",
                "definition": "Candidate signifier.",
            },
        ],
        "sections": {
            "entity_seeds": [
                {
                    "label": "Nick Srnicek",
                    "wikipedia_title": "Nick Srnicek",
                    "entity_type": "person",
                    "formation_hints": ["left_accelerationist"],
                }
            ],
            "current_watch_relations": [["AI safety", "pacing"]],
        },
    }


def test_formation_documents_use_canonical_ids():
    docs = seed_graph._formation_documents(_codebook())
    assert docs[0]["canonical_id"] == "formation:ai_safety"
    assert docs[0]["provenance_class"] == "researcher_seed"
    assert "laclaugpt:Formation" in docs[0]["rdf_types"]


def test_rag_chunks_are_explicitly_context_not_evidence():
    entity = {
        "canonical_id": "actor:Q1",
        "label": "Nick Srnicek",
        "aliases": [],
        "description": "",
        "wikidata_id": "Q1",
        "wikipedia_url": "https://en.wikipedia.org/wiki/Nick_Srnicek",
        "formation_hints": ["left_accelerationist"],
    }
    chunks = seed_graph._rag_chunks(_codebook(), [entity])
    assert chunks
    assert all("evidence" in chunk["epistemic_role"] for chunk in chunks)
    assert any(chunk["kind"] == "watch_relation" for chunk in chunks)


def test_public_codebook_has_required_issue_174_sections():
    data = yaml.safe_load((REPO / "codebooks/public/ai26_v2.yaml").read_text(encoding="utf-8"))
    ids = {entry.get("id") or entry.get("label") for entry in data["entries"] if entry.get("kind") == "formation"}
    assert {
        "existential_risk",
        "accelerationist",
        "left_accelerationist",
        "ai_safety",
        "critical_ai",
        "anti_ai",
    } <= ids
    assert data["sections"]["entity_seeds"]
    assert data["sections"]["bibliography"]
    assert data["sections"]["rdf_mapping"]["identity"]["external_identity"] == "wikidata_qid_when_available"
