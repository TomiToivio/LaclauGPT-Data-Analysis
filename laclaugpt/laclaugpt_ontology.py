"""Minimal RDF/JSON-LD export for Phase 0 Laclaudian discourse analysis."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

LG = "https://laclaugpt.org/ontology/"
PROV = "http://www.w3.org/ns/prov#"
SKOS = "http://www.w3.org/2004/02/skos/core#"


def _slug(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    text = re.sub(r"[^a-z0-9 _-]+", "", text)
    return quote(text.replace(" ", "_")) or "unknown"


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _label(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("label", "name", "signifier", "element", "actor", "subject", "value"):
            if value.get(key):
                return str(value[key]).strip()
    return str(value).strip()


def _resource(kind: str, label: str) -> str:
    return f"{LG}{kind}/{_slug(label)}"


def build_jsonld(record: dict[str, Any], discourse: dict[str, Any]) -> dict[str, Any]:
    document_id = str(record.get("document_id") or record.get("source_url") or "document")
    doc_uri = _resource("document", document_id)
    run_id = str(discourse.get("generated_at") or document_id)
    run_uri = _resource("analysis-run", run_id)

    graph: list[dict[str, Any]] = [
        {
            "@id": doc_uri,
            "@type": "lg:Document",
            "skos:prefLabel": document_id,
        },
        {
            "@id": run_uri,
            "@type": "lg:AnalysisRun",
            "lg:analysisMethod": "Laclau/Mouffe/Palonen-inspired discourse analysis",
            "lg:model": (discourse.get("model_metadata") or {}).get("model"),
            "lg:promptVersion": discourse.get("prompt_version"),
            "prov:wasDerivedFrom": {"@id": doc_uri},
        },
    ]

    type_fields = {
        "signifiers": ("signifier", "lg:Signifier"),
        "collective_subjects": ("actor", "lg:Actor"),
        "nodal_point_candidates": ("nodal-point", "lg:NodalPoint"),
        "floating_signifier_candidates": ("floating-signifier", "lg:FloatingSignifier"),
        "empty_signifier_candidates": ("empty-signifier", "lg:EmptySignifier"),
        "affects": ("affect", "lg:Affect"),
        "frontiers": ("frontier", "lg:Frontier"),
    }

    seen: set[str] = set()
    for field, (kind, rdf_type) in type_fields.items():
        for raw in _items(discourse.get(field)):
            label = _label(raw)
            if not label:
                continue
            uri = _resource(kind, label)
            if uri in seen:
                continue
            seen.add(uri)
            node: dict[str, Any] = {
                "@id": uri,
                "@type": rdf_type,
                "skos:prefLabel": label,
                "prov:wasGeneratedBy": {"@id": run_uri},
            }
            if isinstance(raw, dict):
                if raw.get("confidence") is not None:
                    node["lg:confidence"] = raw["confidence"]
                if raw.get("evidence"):
                    node["lg:surfaceForm"] = str(raw["evidence"])
            graph.append(node)

    relation_fields = {
        "articulations": "lg:articulates",
        "chains_equivalence": "lg:equivalentTo",
        "chains_difference": "lg:differentFrom",
        "antagonisms": "lg:antagonisticTo",
        "frontiers": "lg:constructsFrontier",
        "affects": "lg:expressesAffect",
    }

    assertion_index = 0
    for field, relation in relation_fields.items():
        for raw in _items(discourse.get(field)):
            if not isinstance(raw, dict):
                continue
            subject = _label(raw.get("subject") or raw.get("actor") or raw.get("us") or raw.get("source"))
            obj = _label(raw.get("object") or raw.get("signifier") or raw.get("frontier") or raw.get("affect") or raw.get("target"))
            if not subject or not obj:
                continue
            assertion_index += 1
            assertion: dict[str, Any] = {
                "@id": _resource("assertion", f"{document_id}-{assertion_index}"),
                "@type": "lg:AnalysisAssertion",
                "lg:subject": {"@id": _resource("resource", subject)},
                "lg:relation": {"@id": relation.replace("lg:", LG)},
                "lg:object": {"@id": _resource("resource", obj)},
                "lg:sourceDocument": {"@id": doc_uri},
                "prov:wasGeneratedBy": {"@id": run_uri},
            }
            if raw.get("confidence") is not None:
                assertion["lg:confidence"] = raw["confidence"]
            if raw.get("evidence"):
                assertion["lg:surfaceForm"] = str(raw["evidence"])
            if raw.get("validated") is not None:
                assertion["lg:validated"] = bool(raw["validated"])
            if raw.get("correction_of"):
                assertion["prov:wasRevisionOf"] = {"@id": str(raw["correction_of"])}
            graph.append(assertion)

    return {
        "@context": {
            "lg": LG,
            "prov": PROV,
            "skos": SKOS,
            "sourceDocument": {"@id": "lg:sourceDocument", "@type": "@id"},
        },
        "@graph": graph,
    }


def to_turtle(jsonld: dict[str, Any]) -> str:
    lines = [
        "@prefix lg: <https://laclaugpt.org/ontology/> .",
        "@prefix prov: <http://www.w3.org/ns/prov#> .",
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "",
    ]
    for node in jsonld.get("@graph", []):
        subject = f"<{node['@id']}>"
        predicates: list[str] = []
        rdf_type = node.get("@type")
        if rdf_type:
            predicates.append(f"a {rdf_type}")
        for key, value in node.items():
            if key.startswith("@"):
                continue
            pred = key if ":" in key else f"lg:{key}"
            values = value if isinstance(value, list) else [value]
            rendered = []
            for item in values:
                if isinstance(item, dict) and item.get("@id"):
                    rendered.append(f"<{item['@id']}>")
                elif isinstance(item, bool):
                    rendered.append("true" if item else "false")
                elif isinstance(item, (int, float)):
                    rendered.append(str(item))
                elif item is not None:
                    escaped = str(item).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                    rendered.append(f'"{escaped}"')
            if rendered:
                predicates.append(f"{pred} " + ", ".join(rendered))
        if predicates:
            lines.append(subject + " " + " ;\n    ".join(predicates) + " .\n")
    return "\n".join(lines)


def export_discourse(record: dict[str, Any], discourse: dict[str, Any]) -> dict[str, Any]:
    jsonld = build_jsonld(record, discourse)
    return {"jsonld": jsonld, "turtle": to_turtle(jsonld)}
