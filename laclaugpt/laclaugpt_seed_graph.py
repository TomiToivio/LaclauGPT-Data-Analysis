"""Phase 0 Wikipedia/Wikidata graph seeding for AI26.

The seeder creates background-knowledge and researcher-seed records only.
It never promotes a Wikipedia/Wikidata fact or a codebook seed into corpus evidence.
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import requests
import yaml
from pymongo import MongoClient

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "LaclauGPT-Phase0/1.0 (public research seeding)"
FORMATION_IDS = {
    "existential_risk",
    "accelerationist",
    "left_accelerationist",
    "ai_safety",
    "critical_ai",
    "anti_ai",
    "other",
    "unknown",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _db():
    """Open the Phase 0 MongoDB using the shared environment contract.

    Accepts both the legacy ``MONGO_URI``/``MONGO_DB_NAME`` pair and Collection's
    ``LACLAUGPT_MONGODB_URI``/``LACLAUGPT_MONGODB_DATABASE`` pair, so one cron
    environment configures Collection and every Phase 0 analysis entry point.
    """
    from laclaugpt_mongo import resolve_mongo_config

    uri, name = resolve_mongo_config()
    return MongoClient(uri)[name]


def load_codebook(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("codebook root must be a mapping")
    return data


def resolve_wikipedia(title: str, *, timeout: float = 10.0) -> dict[str, Any]:
    """Resolve an English Wikipedia title and optional Wikidata QID.

    Missing/ambiguous mappings are returned as unresolved rather than guessed.
    """
    params = {
        "action": "query",
        "format": "json",
        "redirects": 1,
        "prop": "pageprops|info",
        "inprop": "url",
        "titles": title,
    }
    response = requests.get(
        WIKIPEDIA_API,
        params=params,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    if page.get("missing") is not None or int(page.get("pageid", -1)) < 0:
        return {"resolved": False, "requested_title": title}

    canonical_title = str(page.get("title") or title)
    qid = str((page.get("pageprops") or {}).get("wikibase_item") or "")
    return {
        "resolved": True,
        "requested_title": title,
        "title": canonical_title,
        "wikipedia_url": page.get("fullurl")
        or f"https://en.wikipedia.org/wiki/{quote(canonical_title.replace(' ', '_'))}",
        "wikidata_id": qid or None,
        "wikidata_url": f"https://www.wikidata.org/wiki/{qid}" if qid else None,
    }


def _formation_documents(codebook: dict[str, Any]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for entry in codebook.get("entries", []):
        if entry.get("kind") != "formation":
            continue
        formation_id = str(entry.get("id") or entry.get("label") or "").strip()
        if formation_id not in FORMATION_IDS:
            continue
        docs.append(
            {
                "canonical_id": f"formation:{formation_id}",
                "node_type": "formation",
                "label": entry.get("display_label") or entry.get("label") or formation_id,
                "formation_id": formation_id,
                "aliases": list(entry.get("aliases") or []),
                "definition": str(entry.get("definition") or ""),
                "state": str((entry.get("metadata") or {}).get("state") or "PROVISIONAL"),
                "provenance_class": "researcher_seed",
                "rdf_types": ["skos:Concept", "laclaugpt:Formation"],
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
    return docs


def _entity_seeds(codebook: dict[str, Any]) -> list[dict[str, Any]]:
    return list((codebook.get("sections") or {}).get("entity_seeds") or [])


def _rag_chunks(codebook: dict[str, Any], entity_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()

    for entry in codebook.get("entries", []):
        kind = str(entry.get("kind") or "")
        label = str(entry.get("display_label") or entry.get("label") or "")
        if not kind or not label:
            continue
        chunk_id = f"codebook:{kind}:{_slug(str(entry.get('id') or label))}"
        chunks.append(
            {
                "canonical_id": chunk_id,
                "kind": kind,
                "label": label,
                "text": f"{label}. {str(entry.get('definition') or '').strip()}".strip(),
                "aliases": list(entry.get("aliases") or []),
                "provenance_class": "researcher_seed",
                "source": "public-codebook",
                "state": str((entry.get("metadata") or {}).get("state") or "PROVISIONAL"),
                "epistemic_role": "context_not_evidence",
                "updated_at": now,
            }
        )

    for entity in entity_docs:
        text = entity.get("label", "")
        if entity.get("description"):
            text += f". {entity['description']}"
        chunks.append(
            {
                "canonical_id": f"entity-card:{entity['canonical_id']}",
                "kind": "entity_card",
                "label": entity.get("label"),
                "text": text,
                "aliases": entity.get("aliases", []),
                "wikidata_id": entity.get("wikidata_id"),
                "wikipedia_url": entity.get("wikipedia_url"),
                "formation_hints": entity.get("formation_hints", []),
                "provenance_class": "background_knowledge",
                "seed_provenance_class": "researcher_seed",
                "epistemic_role": "context_not_evidence",
                "updated_at": now,
            }
        )

    for relation in (codebook.get("sections") or {}).get("current_watch_relations", []):
        if not isinstance(relation, list) or len(relation) != 2:
            continue
        left, right = map(str, relation)
        chunks.append(
            {
                "canonical_id": f"watch:{_slug(left)}:{_slug(right)}",
                "kind": "watch_relation",
                "label": f"{left} ↔ {right}",
                "text": f"Watch candidate articulation between {left} and {right}. This is retrieval context, not a validated discourse relation.",
                "provenance_class": "researcher_seed",
                "epistemic_role": "candidate_relation_not_evidence",
                "updated_at": now,
            }
        )
    return chunks


def seed(*, codebook_path: str, project_id: str = "ai26", no_network: bool = False) -> dict[str, int]:
    codebook = load_codebook(codebook_path)
    db = _db()
    nodes = db[f"{project_id}__graph_nodes"]
    edges = db[f"{project_id}__graph_edges"]
    rag = db[f"{project_id}__rag_codebook"]

    nodes.create_index("canonical_id", unique=True)
    edges.create_index([("source", 1), ("target", 1), ("relation_type", 1), ("provenance_class", 1)])
    rag.create_index("canonical_id", unique=True)
    rag.create_index([("kind", 1), ("provenance_class", 1)])

    formation_docs = _formation_documents(codebook)
    for doc in formation_docs:
        nodes.update_one({"canonical_id": doc["canonical_id"]}, {"$set": doc}, upsert=True)

    entity_docs: list[dict[str, Any]] = []
    for seed_entry in _entity_seeds(codebook):
        title = str(seed_entry.get("wikipedia_title") or seed_entry.get("label") or "").strip()
        if not title:
            continue
        resolved = {"resolved": False, "requested_title": title}
        if not no_network:
            try:
                resolved = resolve_wikipedia(title)
            except requests.RequestException as exc:
                resolved["resolution_error"] = type(exc).__name__

        qid = resolved.get("wikidata_id")
        local_id = f"actor:{qid}" if qid else f"actor:wp:{_slug(str(resolved.get('title') or title))}"
        doc = {
            "canonical_id": local_id,
            "node_type": str(seed_entry.get("entity_type") or "person"),
            "label": str(resolved.get("title") or seed_entry.get("label") or title),
            "aliases": list(seed_entry.get("aliases") or []),
            "description": str(seed_entry.get("description") or ""),
            "wikipedia_title": resolved.get("title") or title,
            "wikipedia_url": resolved.get("wikipedia_url"),
            "wikidata_id": qid,
            "wikidata_url": resolved.get("wikidata_url"),
            "formation_hints": list(seed_entry.get("formation_hints") or []),
            "provenance_class": "background_knowledge",
            "seed_provenance_class": "researcher_seed",
            "identity_status": "grounded" if resolved.get("resolved") else "unresolved",
            "rdf_types": list(seed_entry.get("rdf_types") or ["schema:Person", "prov:Agent"]),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if resolved.get("resolution_error"):
            doc["resolution_error"] = resolved["resolution_error"]
        nodes.update_one({"canonical_id": local_id}, {"$set": doc}, upsert=True)
        entity_docs.append(doc)

        edges.delete_many({"source": local_id, "relation_type": "seedFormation", "provenance_class": "researcher_seed"})
        for formation_id in doc["formation_hints"]:
            if formation_id not in FORMATION_IDS:
                raise ValueError(f"unknown formation hint: {formation_id}")
            edges.insert_one(
                {
                    "source": local_id,
                    "target": f"formation:{formation_id}",
                    "relation_type": "seedFormation",
                    "provenance_class": "researcher_seed",
                    "validation_state": "PROVISIONAL",
                    "epistemic_role": "retrieval_hint_not_corpus_evidence",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "extraction_method": "public_codebook_seed",
                }
            )

    chunks = _rag_chunks(codebook, entity_docs)
    for chunk in chunks:
        rag.update_one({"canonical_id": chunk["canonical_id"]}, {"$set": chunk}, upsert=True)

    return {
        "formations": len(formation_docs),
        "entities": len(entity_docs),
        "seed_edges": sum(len(doc.get("formation_hints", [])) for doc in entity_docs),
        "rag_chunks": len(chunks),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Phase 0 AI26 background graph from public codebook + English Wikipedia/Wikidata.")
    parser.add_argument("--codebook", default="codebooks/public/ai26_v2.yaml")
    parser.add_argument("--project-id", default=os.getenv("LACLAUGPT_PROJECT_ID", "ai26"))
    parser.add_argument("--no-network", action="store_true", help="Seed codebook structure without resolving Wikipedia/Wikidata.")
    args = parser.parse_args()
    stats = seed(codebook_path=args.codebook, project_id=args.project_id, no_network=args.no_network)
    print(" ".join(f"{key}={value}" for key, value in stats.items()))


if __name__ == "__main__":
    main()
