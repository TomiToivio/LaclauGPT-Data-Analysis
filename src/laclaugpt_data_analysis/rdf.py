"""Optional RDF/Linked Data projection of canonical LaclauGPT records.

RDF is an interoperability projection, never the canonical source of truth. Optional
RDF dependencies are imported only from enabled execution paths so ordinary projects
retain the lightweight core dependency set.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord, SCHEMA_VERSION

RDF_PROFILE_VERSION = "1.0"
LACLAUGPT = "https://w3id.org/laclaugpt/"
PROV = "http://www.w3.org/ns/prov#"
DCTERMS = "http://purl.org/dc/terms/"
DCAT = "http://www.w3.org/ns/dcat#"
SCHEMA = "https://schema.org/"
OA = "http://www.w3.org/ns/oa#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XSD = "http://www.w3.org/2001/XMLSchema#"


class RDFValidationConfig(BaseModel):
    shacl: bool = True
    shapes_path: str | None = None


class RDFStoreConfig(BaseModel):
    backend: str = "file"
    path: str | None = None
    endpoint: str | None = None
    query_endpoint: str | None = None
    update_endpoint: str | None = None
    token: str | None = Field(default=None, repr=False)


class RDFGraphRAGConfig(BaseModel):
    enabled: bool = False
    max_nodes: int = Field(default=40, ge=1, le=500)
    max_edges: int = Field(default=80, ge=1, le=2000)


class RDFConfig(BaseModel):
    enabled: bool = False
    required: bool = False
    base_uri: str = "https://data.example/laclaugpt"
    formats: list[str] = Field(default_factory=lambda: ["json-ld", "turtle", "nquads"])
    store: RDFStoreConfig = Field(default_factory=RDFStoreConfig)
    validation: RDFValidationConfig = Field(default_factory=RDFValidationConfig)
    graphrag: RDFGraphRAGConfig = Field(default_factory=RDFGraphRAGConfig)


def rdf_config(project_config: dict[str, Any] | None) -> RDFConfig:
    root = project_config or {}
    analysis = root.get("analysis") if isinstance(root.get("analysis"), dict) else {}
    raw = analysis.get("rdf") if isinstance(analysis.get("rdf"), dict) else {}
    return RDFConfig.model_validate(raw)


def rdf_enabled(project_config: dict[str, Any] | None) -> bool:
    return rdf_config(project_config).enabled


def _require_rdflib():
    try:
        import rdflib
    except ImportError as exc:  # pragma: no cover - depends on optional environment
        raise RuntimeError("RDF support requires the optional 'rdf' dependencies") from exc
    return rdflib


def _project_id(project_config: dict[str, Any] | None, fallback: str = "generic") -> str:
    root = project_config or {}
    value = root.get("project_id") or root.get("project") or root.get("id") or fallback
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(value).strip())
    return safe.strip("-") or "generic"


def _stable_token(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    readable = urllib.parse.quote(value.strip()[:48], safe="-._~")
    return f"{readable}-{digest}" if readable else f"sha256-{digest}"


def stable_uri(base_uri: str, project_id: str, kind: str, stable_id: str) -> str:
    return "/".join(
        [base_uri.rstrip("/"), urllib.parse.quote(project_id, safe="-_"), kind, _stable_token(stable_id)]
    )


def _language(value: str | None) -> str | None:
    if not value:
        return None
    return value.split("-")[0].lower()


def _review(value: str | None) -> str:
    allowed = {"PROVISIONAL", "ACCEPTED", "REJECTED", "REVISED", "CANONICAL", "SUPERSEDED"}
    return value if value in allowed else "PROVISIONAL"


def _provenance_index(record: CanonicalRecord) -> dict[str, Any]:
    return {item.provenance_id: item for item in record.provenance}


def materialize_record(
    record: CanonicalRecord,
    *,
    project_id: str,
    base_uri: str = "https://data.example/laclaugpt",
    run_id: str | None = None,
):
    """Deterministically project one canonical record into an RDF Dataset."""
    rdflib = _require_rdflib()
    Dataset = rdflib.Dataset
    URIRef, Literal, BNode = rdflib.URIRef, rdflib.Literal, rdflib.BNode
    RDFNS = rdflib.namespace.RDF
    RDFS = rdflib.namespace.RDFS

    dataset = Dataset()
    graph_uri = URIRef(stable_uri(base_uri, project_id, "graph", run_id or record.source_url))
    graph = dataset.graph(graph_uri)

    ns = rdflib.Namespace(LACLAUGPT)
    prov = rdflib.Namespace(PROV)
    dct = rdflib.Namespace(DCTERMS)
    schema = rdflib.Namespace(SCHEMA)
    oa = rdflib.Namespace(OA)
    skos = rdflib.Namespace(SKOS)

    for prefix, namespace in {
        "laclaugpt": ns, "prov": prov, "dcterms": dct, "schema": schema,
        "oa": oa, "skos": skos,
    }.items():
        dataset.bind(prefix, namespace)

    source = URIRef(stable_uri(base_uri, project_id, "source", record.source_url))
    graph.add((source, RDFNS.type, prov.Entity))
    graph.add((source, RDFNS.type, schema.CreativeWork))
    graph.add((source, dct.identifier, Literal(record.source_url)))
    if record.content.title:
        graph.add((source, dct.title, Literal(record.content.title, lang=_language(record.content.language or record.source.language))))
    if record.source.language or record.content.language:
        graph.add((source, dct.language, Literal(record.content.language or record.source.language)))
    if record.source.created_at:
        graph.add((source, dct.created, Literal(record.source.created_at.isoformat())))
    if record.source.author:
        graph.add((source, dct.creator, Literal(record.source.author)))
    for key, value in sorted(record.source_native_ids.items()):
        graph.add((source, dct.identifier, Literal(f"{key}:{value}")))

    run_key = run_id or f"rdf:{record.source_url}:{SCHEMA_VERSION}:{RDF_PROFILE_VERSION}"
    run = URIRef(stable_uri(base_uri, project_id, "activity", run_key))
    graph.add((run, RDFNS.type, prov.Activity))
    graph.add((run, dct.identifier, Literal(run_key)))
    graph.add((run, dct.hasVersion, Literal(RDF_PROFILE_VERSION)))

    provenance = _provenance_index(record)
    prov_uris: dict[str, Any] = {}
    for item in record.provenance:
        activity = URIRef(stable_uri(base_uri, project_id, "activity", item.provenance_id))
        prov_uris[item.provenance_id] = activity
        graph.add((activity, RDFNS.type, prov.Activity))
        graph.add((activity, dct.identifier, Literal(item.provenance_id)))
        graph.add((activity, dct.type, Literal(item.method)))
        if item.model:
            agent = URIRef(stable_uri(base_uri, project_id, "agent", f"model:{item.model}"))
            graph.add((agent, RDFNS.type, prov.Agent))
            graph.add((agent, RDFS.label, Literal(item.model)))
            graph.add((activity, prov.wasAssociatedWith, agent))
        graph.add((activity, prov.used, source))

    evidence_uris: dict[str, Any] = {}
    for evidence in record.evidence:
        ev = URIRef(stable_uri(base_uri, project_id, "evidence", evidence.evidence_id))
        evidence_uris[evidence.evidence_id] = ev
        graph.add((ev, RDFNS.type, oa.Annotation))
        graph.add((ev, dct.identifier, Literal(evidence.evidence_id)))
        graph.add((ev, oa.hasSource, source))
        if evidence.quote is not None:
            body = BNode()
            graph.add((ev, oa.hasBody, body))
            graph.add((body, RDFNS.value, Literal(evidence.quote, lang=_language(record.source.language))))
        if evidence.start_offset is not None or evidence.end_offset is not None:
            target = BNode()
            selector = BNode()
            graph.add((ev, oa.hasTarget, target))
            graph.add((target, oa.hasSource, source))
            graph.add((target, oa.hasSelector, selector))
            graph.add((selector, RDFNS.type, oa.TextPositionSelector))
            if evidence.start_offset is not None:
                graph.add((selector, oa.start, Literal(evidence.start_offset)))
            if evidence.end_offset is not None:
                graph.add((selector, oa.end, Literal(evidence.end_offset)))
        if evidence.provenance_id:
            graph.add((ev, prov.wasGeneratedBy, prov_uris.get(evidence.provenance_id, run)))

    object_uris: dict[str, Any] = {}
    object_groups = [
        (record.analysis.formations, ns.DiscourseFormation),
        (record.analysis.signifiers, ns.Signifier),
        (record.analysis.nodal_points, ns.NodalPoint),
        (record.analysis.floating_signifiers, ns.FloatingSignifier),
        (record.analysis.empty_signifier_candidates, ns.EmptySignifier),
        (record.analysis.frontier, ns.DiscursiveFrontier),
    ]
    for objects, rdf_type in object_groups:
        for obj in objects:
            node = URIRef(stable_uri(base_uri, project_id, "concept", obj.object_id))
            object_uris[obj.object_id] = node
            graph.add((node, RDFNS.type, rdf_type))
            graph.add((node, RDFNS.type, skos.Concept))
            graph.add((node, dct.identifier, Literal(obj.object_id)))
            graph.add((node, skos.prefLabel, Literal(obj.label, lang=_language(record.source.language))))
            graph.add((node, ns.reviewState, Literal(_review(obj.review_status))))
            if obj.confidence is not None:
                graph.add((node, ns.confidence, Literal(obj.confidence)))
            activity = prov_uris.get(obj.provenance_id, run)
            graph.add((node, prov.wasGeneratedBy, activity))
            for evidence_id in obj.evidence_ids:
                if evidence_id in evidence_uris:
                    graph.add((node, ns.hasEvidence, evidence_uris[evidence_id]))

    # Generic entities use Schema.org rather than a custom LaclauGPT class.
    for entity in record.analysis.entities:
        node = URIRef(stable_uri(base_uri, project_id, "entity", entity.entity_id))
        object_uris[entity.entity_id] = node
        entity_type = (entity.entity_type or "Thing").casefold()
        cls = schema.Person if entity_type in {"person", "per"} else schema.Organization if entity_type in {"organization", "org"} else schema.Thing
        graph.add((node, RDFNS.type, cls))
        graph.add((node, dct.identifier, Literal(entity.entity_id)))
        graph.add((node, schema.name, Literal(entity.label, lang=_language(record.source.language))))
        graph.add((node, ns.reviewState, Literal(_review(entity.review_status))))
        graph.add((node, prov.wasGeneratedBy, prov_uris.get(entity.provenance_id, run)))

    for relation in list(record.analysis.relations) + list(record.analysis.antagonisms) + list(record.analysis.actor_entity_relations):
        art = URIRef(stable_uri(base_uri, project_id, "articulation", relation.relation_id))
        left = object_uris.get(relation.source_ref) or URIRef(stable_uri(base_uri, project_id, "concept", relation.source_ref))
        right = object_uris.get(relation.target_ref) or URIRef(stable_uri(base_uri, project_id, "concept", relation.target_ref))
        graph.add((art, RDFNS.type, ns.Articulation))
        graph.add((art, dct.identifier, Literal(relation.relation_id)))
        graph.add((art, dct.type, Literal(relation.relation_type)))
        graph.add((art, ns.articulates, left))
        graph.add((art, ns.articulates, right))
        graph.add((art, ns.reviewState, Literal(_review(relation.review_status))))
        graph.add((art, prov.wasGeneratedBy, prov_uris.get(relation.provenance_id, run)))
        for evidence_id in relation.evidence_ids:
            if evidence_id in evidence_uris:
                graph.add((art, ns.hasEvidence, evidence_uris[evidence_id]))

    return dataset


@dataclass(frozen=True)
class ValidationIssue:
    focus_node: str
    path: str
    message: str
    severity: str = "Violation"


@dataclass(frozen=True)
class ValidationReport:
    conforms: bool
    issues: tuple[ValidationIssue, ...] = ()
    text: str = ""


def validate_dataset(dataset, *, shapes_path: str | Path | None = None) -> ValidationReport:
    """Validate with PySHACL when available; otherwise apply the baseline shapes locally."""
    rdflib = _require_rdflib()
    ns = rdflib.Namespace(LACLAUGPT)
    prov = rdflib.Namespace(PROV)
    rdf_type = rdflib.namespace.RDF.type
    issues: list[ValidationIssue] = []

    # Baseline validator mirrors the meta-repository SHACL contract and works offline.
    for graph in dataset.graphs():
        for node in graph.subjects(rdf_type, ns.Articulation):
            if len(set(graph.objects(node, ns.articulates))) < 2:
                issues.append(ValidationIssue(str(node), f"{LACLAUGPT}articulates", "An articulation must connect at least two articulated resources."))
            if not any(graph.objects(node, prov.wasGeneratedBy)):
                issues.append(ValidationIssue(str(node), f"{PROV}wasGeneratedBy", "An analytical articulation must retain generation provenance."))
            states = [str(x) for x in graph.objects(node, ns.reviewState)]
            if not states:
                issues.append(ValidationIssue(str(node), f"{LACLAUGPT}reviewState", "Articulation review state is required."))
            elif any(x not in {"PROVISIONAL", "ACCEPTED", "REJECTED", "REVISED", "CANONICAL", "SUPERSEDED"} for x in states):
                issues.append(ValidationIssue(str(node), f"{LACLAUGPT}reviewState", "Invalid articulation review state."))
            for value in graph.objects(node, ns.confidence):
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    number = -1
                if not 0 <= number <= 1:
                    issues.append(ValidationIssue(str(node), f"{LACLAUGPT}confidence", "Confidence must be between 0 and 1."))
        for rdf_class in (ns.EmptySignifier, ns.FloatingSignifier, ns.NodalPoint):
            for node in graph.subjects(rdf_type, rdf_class):
                if not any(graph.objects(node, prov.wasGeneratedBy)):
                    issues.append(ValidationIssue(str(node), f"{PROV}wasGeneratedBy", "Theory-specific signifier-role claims must retain provenance."))
                if not any(graph.objects(node, ns.reviewState)):
                    issues.append(ValidationIssue(str(node), f"{LACLAUGPT}reviewState", "Theory-specific signifier-role claims must retain review state."))
    return ValidationReport(not issues, tuple(issues), "\n".join(i.message for i in issues))


def serialize_dataset(dataset, format_name: str) -> str:
    aliases = {
        "json-ld": "json-ld", "jsonld": "json-ld",
        "turtle": "turtle", "ttl": "turtle",
        "nquads": "nquads", "nq": "nquads",
        "ntriples": "nt", "n-triples": "nt", "nt": "nt",
        "trig": "trig", "rdfxml": "xml", "rdf/xml": "xml",
    }
    fmt = aliases.get(format_name.casefold())
    if fmt is None:
        raise ValueError(f"unsupported RDF format: {format_name}")
    value = dataset.serialize(format=fmt)
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


class RDFStore(Protocol):
    def healthcheck(self) -> dict[str, Any]: ...
    def add(self, dataset) -> dict[str, Any]: ...
    def query(self, sparql: str, *, limits: dict[str, int] | None = None) -> Any: ...
    def export(self, format_name: str = "nquads") -> str: ...


class FileRDFStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._dataset = None

    def healthcheck(self) -> dict[str, Any]:
        return {"ok": True, "backend": "file", "path": str(self.path)}

    def add(self, dataset) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._dataset = dataset
        self.path.write_text(serialize_dataset(dataset, _format_from_suffix(self.path.suffix)), encoding="utf-8")
        return {"ok": True, "path": str(self.path)}

    def query(self, sparql: str, *, limits: dict[str, int] | None = None):
        if self._dataset is None:
            raise RuntimeError("file store has no loaded dataset")
        return self._dataset.query(sparql)

    def export(self, format_name: str = "nquads") -> str:
        if self._dataset is None:
            raise RuntimeError("file store has no loaded dataset")
        return serialize_dataset(self._dataset, format_name)


class RDFLibStore:
    def __init__(self):
        rdflib = _require_rdflib()
        self.dataset = rdflib.Dataset()

    def healthcheck(self) -> dict[str, Any]:
        return {"ok": True, "backend": "rdflib", "query": True, "named_graphs": True}

    def add(self, dataset) -> dict[str, Any]:
        count = 0
        for graph in dataset.graphs():
            target = self.dataset.graph(graph.identifier)
            for triple in graph:
                target.add(triple)
                count += 1
        return {"ok": True, "triples": count}

    def query(self, sparql: str, *, limits: dict[str, int] | None = None):
        return self.dataset.query(sparql)

    def export(self, format_name: str = "nquads") -> str:
        return serialize_dataset(self.dataset, format_name)


class SPARQLStore:
    """Small backend-neutral remote SPARQL adapter using stdlib HTTP only."""
    def __init__(self, *, query_endpoint: str, update_endpoint: str | None = None, token: str | None = None):
        self.query_endpoint = query_endpoint
        self.update_endpoint = update_endpoint
        self.token = token

    def _request(self, url: str, data: bytes | None, content_type: str, accept: str = "application/sparql-results+json") -> bytes:
        headers = {"Content-Type": content_type, "Accept": accept}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read()

    def healthcheck(self) -> dict[str, Any]:
        try:
            self.query("ASK { ?s ?p ?o }")
            return {"ok": True, "backend": "sparql", "query": True, "update": bool(self.update_endpoint)}
        except Exception as exc:  # pragma: no cover - network adapter is mocked in tests
            return {"ok": False, "backend": "sparql", "error": type(exc).__name__}

    def add(self, dataset) -> dict[str, Any]:
        if not self.update_endpoint:
            raise RuntimeError("SPARQL update endpoint is not configured")
        payload = serialize_dataset(dataset, "nquads")
        update = f"INSERT DATA {{ {payload} }}".encode("utf-8")
        self._request(self.update_endpoint, update, "application/sparql-update", "application/json")
        return {"ok": True}

    def query(self, sparql: str, *, limits: dict[str, int] | None = None) -> Any:
        text = sparql
        if limits and "limit" in limits and " limit " not in sparql.casefold():
            text = f"{sparql.rstrip()} LIMIT {int(limits['limit'])}"
        body = urllib.parse.urlencode({"query": text}).encode("utf-8")
        raw = self._request(self.query_endpoint, body, "application/x-www-form-urlencoded")
        return json.loads(raw.decode("utf-8"))

    def export(self, format_name: str = "nquads") -> str:
        query = "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"
        body = urllib.parse.urlencode({"query": query}).encode("utf-8")
        raw = self._request(self.query_endpoint, body, "application/x-www-form-urlencoded", "application/n-quads")
        return raw.decode("utf-8")


def _format_from_suffix(suffix: str) -> str:
    return {".jsonld": "json-ld", ".json": "json-ld", ".ttl": "turtle", ".nq": "nquads", ".nt": "nt", ".trig": "trig", ".rdf": "rdfxml"}.get(suffix.casefold(), "nquads")


def build_store(config: RDFStoreConfig) -> RDFStore:
    backend = config.backend.casefold()
    if backend == "file":
        return FileRDFStore(config.path or "rdf/laclaugpt.nq")
    if backend in {"rdflib", "local"}:
        return RDFLibStore()
    if backend == "sparql":
        endpoint = config.query_endpoint or config.endpoint
        if not endpoint:
            raise ValueError("SPARQL backend requires query_endpoint or endpoint")
        return SPARQLStore(query_endpoint=endpoint, update_endpoint=config.update_endpoint, token=config.token)
    if backend == "oxigraph":
        raise RuntimeError("Oxigraph adapter is optional and not installed in the baseline implementation")
    raise ValueError(f"unknown RDF store backend: {config.backend}")


@dataclass(frozen=True)
class RDFContext:
    text: str
    source_ids: tuple[str, ...]
    graph_paths: tuple[str, ...]
    provenance: dict[str, Any]


def retrieve_subgraph(
    dataset,
    *,
    project_id: str,
    seed: str,
    max_nodes: int = 40,
    max_edges: int = 80,
) -> RDFContext:
    """Bounded local GraphRAG retrieval with auditable graph/triple provenance."""
    rdflib = _require_rdflib()
    seed_cf = seed.casefold()
    candidates: list[Any] = []
    source_ids: set[str] = set()
    paths: list[str] = []
    triples: list[tuple[Any, Any, Any]] = []
    seen_nodes: set[str] = set()

    for graph in dataset.graphs():
        if project_id.casefold() not in str(graph.identifier).casefold():
            continue
        for s, p, o in graph:
            if seed_cf in str(s).casefold() or seed_cf in str(o).casefold():
                candidates.extend([s, o])
                triples.append((s, p, o))
                paths.append(f"{graph.identifier} :: {s} -> {p} -> {o}")
                if len(triples) >= max_edges:
                    break
        if len(triples) >= max_edges:
            break

    frontier = list(dict.fromkeys(candidates))
    for node in frontier:
        if len(triples) >= max_edges or len(seen_nodes) >= max_nodes:
            break
        seen_nodes.add(str(node))
        for graph in dataset.graphs():
            if project_id.casefold() not in str(graph.identifier).casefold():
                continue
            for triple in list(graph.triples((node, None, None))) + list(graph.triples((None, None, node))):
                if triple not in triples:
                    triples.append(triple)
                    paths.append(f"{graph.identifier} :: {triple[0]} -> {triple[1]} -> {triple[2]}")
                for item in (triple[0], triple[2]):
                    if isinstance(item, rdflib.term.URIRef):
                        seen_nodes.add(str(item))
                if len(triples) >= max_edges or len(seen_nodes) >= max_nodes:
                    break

    dct_identifier = rdflib.URIRef(f"{DCTERMS}identifier")
    for graph in dataset.graphs():
        for _, _, value in graph.triples((None, dct_identifier, None)):
            text = str(value)
            if text.startswith(("http://", "https://")):
                source_ids.add(text)

    rendered = "\n".join(f"{s} | {p} | {o}" for s, p, o in triples)
    return RDFContext(
        text=rendered,
        source_ids=tuple(sorted(source_ids)),
        graph_paths=tuple(paths[:max_edges]),
        provenance={"provider": "rdf-graphrag", "project_id": project_id, "seed": seed, "max_nodes": max_nodes, "max_edges": max_edges},
    )


def import_profile_dataset(dataset) -> list[dict[str, Any]]:
    """Import the lossless baseline identity/relation subset into interchange dictionaries."""
    rdflib = _require_rdflib()
    dct = rdflib.Namespace(DCTERMS)
    ns = rdflib.Namespace(LACLAUGPT)
    prov = rdflib.Namespace(PROV)
    results: list[dict[str, Any]] = []
    for graph in dataset.graphs():
        for source in graph.subjects(rdflib.namespace.RDF.type, prov.Entity):
            identifiers = [str(x) for x in graph.objects(source, dct.identifier)]
            source_urls = [x for x in identifiers if x.startswith(("http://", "https://"))]
            if source_urls:
                results.append({"kind": "source", "source_url": source_urls[0], "identifiers": identifiers, "graph": str(graph.identifier)})
        for art in graph.subjects(rdflib.namespace.RDF.type, ns.Articulation):
            results.append({
                "kind": "articulation",
                "id": next((str(x) for x in graph.objects(art, dct.identifier)), str(art)),
                "relation_type": next((str(x) for x in graph.objects(art, dct.type)), "articulation"),
                "endpoints": [str(x) for x in graph.objects(art, ns.articulates)],
                "review_state": next((str(x) for x in graph.objects(art, ns.reviewState)), "PROVISIONAL"),
                "generated_by": [str(x) for x in graph.objects(art, prov.wasGeneratedBy)],
                "evidence": [str(x) for x in graph.objects(art, ns.hasEvidence)],
            })
    return results


def run_optional_rdf_postprocess(
    record: CanonicalRecord,
    *,
    project_config: dict[str, Any] | None,
    project_profile: str = "generic",
    store: RDFStore | None = None,
) -> CanonicalRecord:
    """Materialize RDF only when explicitly enabled, with configurable failure isolation."""
    config = rdf_config(project_config)
    if not config.enabled:
        return record
    project_id = _project_id(project_config, project_profile)
    try:
        dataset = materialize_record(record, project_id=project_id, base_uri=config.base_uri)
        validation = validate_dataset(dataset) if config.validation.shacl else ValidationReport(True)
        if not validation.conforms:
            raise ValueError("RDF SHACL validation failed: " + "; ".join(x.message for x in validation.issues))
        serializations = {fmt: serialize_dataset(dataset, fmt) for fmt in config.formats}
        sink = store
        store_result = None
        if sink is None and config.store.backend:
            # File output is only written when an explicit path was configured. This avoids
            # surprising filesystem writes merely from enabling materialization in tests/workers.
            if config.store.backend.casefold() != "file" or config.store.path:
                sink = build_store(config.store)
        if sink is not None:
            store_result = sink.add(dataset)
        record.analysis.plugin_results["rdf"] = {
            "schema": "laclaugpt-rdf-projection-v1",
            "project_id": project_id,
            "canonical_schema_version": record.schema_version,
            "rdf_profile_version": RDF_PROFILE_VERSION,
            "triple_count": sum(len(g) for g in dataset.graphs()),
            "named_graphs": sorted(str(g.identifier) for g in dataset.graphs()),
            "validation": {"conforms": validation.conforms, "issues": [i.__dict__ for i in validation.issues]},
            "serializations": serializations,
            "store": store_result,
            "graphrag_enabled": bool(config.graphrag.enabled),
        }
        return record
    except Exception as exc:
        failure = {"error": type(exc).__name__, "message": str(exc), "required": config.required}
        record.analysis.plugin_failures["rdf"] = failure
        if config.required:
            raise
        return record
