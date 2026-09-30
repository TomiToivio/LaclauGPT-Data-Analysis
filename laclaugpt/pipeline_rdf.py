"""Transparent RDF projection helpers for human-readable Phase 2 output."""

from __future__ import annotations

from typing import Any

LACLAUGPT = "https://w3id.org/laclaugpt/"
SCHEMA = "https://schema.org/"
PROV = "http://www.w3.org/ns/prov#"


def record_triples(source_url: str, project: str) -> list[tuple[str, str, Any]]:
    """Return plain triples before any rdflib/storage-specific serialization."""
    return [
        (source_url, f"{SCHEMA}url", source_url),
        (source_url, f"{LACLAUGPT}project", project),
    ]


def relation_triple(subject: str, predicate: str, object_: str) -> tuple[str, str, str]:
    """Make an explicit graph relation with no hidden ontology inference."""
    if ":" not in predicate and not predicate.startswith("http"):
        predicate = f"{LACLAUGPT}{predicate}"
    return subject, predicate, object_
