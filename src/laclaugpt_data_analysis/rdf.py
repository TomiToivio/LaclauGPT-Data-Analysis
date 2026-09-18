"""Optional RDF/Linked Data projection of canonical LaclauGPT records.

RDF is a semantic projection, never the canonical source of truth. Optional RDF
packages are imported only when RDF is explicitly enabled or an RDF API is called.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord

RDF_PROFILE_VERSION = "1.0"
LACLAUGPT = "https://w3id.org/laclaugpt/"
PROV = "http://www.w3.org/ns/prov#"
DCTERMS = "http://purl.org/dc/terms/"
SCHEMA = "https://schema.org/"
OA = "http://www.w3.org/ns/oa#"
SKOS = "http://www.w3.org/2004/02/skos/core#"


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


def graphrag_enabled(project_config: dict[str, Any] | None) -> bool:
    config = rdf_config(project_config)
    return config.enabled and config.graphrag.enabled


def _require_rdflib():
    try:
        import rdflib
    except ImportError as exc:  # pragma: no cover - optional dependency path
        raise RuntimeError("RDF support requires `pip install laclaugpt-data-analysis[rdf]`") from exc
    return rdflib


def _project_id(project_config: dict[str, Any] | None, fallback: str = "generic") -> str:
    root = project_config or {}
    value = root.get("project_id") or root.get("project") or root.get("id") or fallback
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(value).strip())
    return safe.strip("-") or "generic"


def _token(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    readable = urllib.parse.quote(value.strip()[:48], safe="-._~")
    return f"{readable}-{digest}" if readable else f"sha256-{digest}"


def stable_uri(base_uri: str, project_id: str, kind: str, stable_id: str) -> str:
    return "/".join(
        [base_uri.rstrip("/"), urllib.parse.quote(project_id, safe="-_"), kind, _token(stable_id)]
    )


def _language(value: str | None) -> str | None:
    return value.split("-")[0].lower() if value else None


def _review(value: str | None) -> str:
    allowed = {"PROVISIONAL", "ACCEPTED", "REJECTED", "REVISED", "CANONICAL", "SUPERSEDED"}
    return value if value in allowed else "PROVISIONAL"


def materialize_record(
    record: CanonicalRecord,
    *,
    project_id: str,
    base_uri: str = "https://data.example/laclaugpt",
    run_id: str | None = None,
):
    """Deterministically project a canonical record into one named RDF graph."""
    rdflib = _require_rdflib()
    dataset = rdflib.Dataset()
    graph_id = rdflib.URIRef(stable_uri(base_uri, project_id, "graph", run_id or record.source_url))
    graph = dataset.graph(graph_id)
    rdf = rdflib.namespace.RDF
    rdfs = rdflib.namespace.RDFS
    ns = rdflib.Namespace(LACLAUGPT)
    prov = rdflib.Namespace(PROV)
    dct = rdflib.Namespace(DCTERMS)
    schema = rdflib.Namespace(SCHEMA)
    oa = rdflib.Namespace(OA)
    skos = rdflib.Namespace(SKOS)
    for prefix, namespace in {
        "laclaugpt": ns,
        "prov": prov,
        "dcterms": dct,
        "schema": schema,
        "oa": oa,
        "skos": skos,
    }.items():
        dataset.bind(prefix, namespace)

    source = rdflib.URIRef(stable_uri(base_uri, project_id, "source", record.source_url))
    graph.add((source, rdf.type, prov.Entity))
    graph.add((source, rdf.type, schema.CreativeWork))
    graph.add((source, dct.identifier, rdflib.Literal(record.source_url)))
    if record.content.title:
        graph.add((source, dct.title, rdflib.Literal(record.content.title, lang=_language(record.content.language or record.source.language))))
    if record.source.language or record.content.language:
        graph.add((source, dct.language, rdflib.Literal(record.content.language or record.source.language)))
    if record.source.created_at:
        graph.add((source, dct.created, rdflib.Literal(record.source.created_at.isoformat())))
    if record.source.author:
        graph.add((source, dct.creator, rdflib.Literal(record.source.author)))
    for key, value in sorted(record.source_native_ids.items()):
        graph.add((source, dct.identifier, rdflib.Literal(f"{key}:{value}")))

    # Phase 1: record-level analytical summary text and the explicit uncertainty
    # record (issue #144). Uncertainty and abstentions are first-class research
    # output (abstention is a valid result), so they are projected rather than
    # dropped.
    if record.analysis.summary:
        graph.add((source, ns.analysisSummary, rdflib.Literal(record.analysis.summary, lang=_language(record.source.language))))
    for note in record.analysis.uncertainty:
        graph.add((source, ns.uncertainty, rdflib.Literal(note)))
    for note in record.analysis.abstentions:
        graph.add((source, ns.abstention, rdflib.Literal(note)))

    run_key = run_id or f"rdf:{record.source_url}:{record.schema_version}:{RDF_PROFILE_VERSION}"
    run = rdflib.URIRef(stable_uri(base_uri, project_id, "activity", run_key))
    graph.add((run, rdf.type, prov.Activity))
    graph.add((run, dct.identifier, rdflib.Literal(run_key)))
    graph.add((run, dct.hasVersion, rdflib.Literal(RDF_PROFILE_VERSION)))
    graph.add((run, prov.used, source))

    prov_uris: dict[str, Any] = {}
    for item in record.provenance:
        activity = rdflib.URIRef(stable_uri(base_uri, project_id, "activity", item.provenance_id))
        prov_uris[item.provenance_id] = activity
        graph.add((activity, rdf.type, prov.Activity))
        graph.add((activity, dct.identifier, rdflib.Literal(item.provenance_id)))
        graph.add((activity, dct.type, rdflib.Literal(item.method)))
        graph.add((activity, prov.used, source))
        if item.model:
            agent = rdflib.URIRef(stable_uri(base_uri, project_id, "agent", f"model:{item.model}"))
            graph.add((agent, rdf.type, prov.Agent))
            graph.add((agent, rdfs.label, rdflib.Literal(item.model)))
            graph.add((activity, prov.wasAssociatedWith, agent))

    evidence_uris: dict[str, Any] = {}
    for evidence in record.evidence:
        ev = rdflib.URIRef(stable_uri(base_uri, project_id, "evidence", evidence.evidence_id))
        evidence_uris[evidence.evidence_id] = ev
        graph.add((ev, rdf.type, oa.Annotation))
        graph.add((ev, dct.identifier, rdflib.Literal(evidence.evidence_id)))
        graph.add((ev, oa.hasSource, source))
        if evidence.quote is not None:
            body = rdflib.BNode()
            graph.add((ev, oa.hasBody, body))
            graph.add((body, rdf.value, rdflib.Literal(evidence.quote, lang=_language(record.source.language))))
        if evidence.start_offset is not None or evidence.end_offset is not None:
            target, selector = rdflib.BNode(), rdflib.BNode()
            graph.add((ev, oa.hasTarget, target))
            graph.add((target, oa.hasSource, source))
            graph.add((target, oa.hasSelector, selector))
            graph.add((selector, rdf.type, oa.TextPositionSelector))
            if evidence.start_offset is not None:
                graph.add((selector, oa.start, rdflib.Literal(evidence.start_offset)))
            if evidence.end_offset is not None:
                graph.add((selector, oa.end, rdflib.Literal(evidence.end_offset)))
        graph.add((ev, prov.wasGeneratedBy, prov_uris.get(evidence.provenance_id, run)))

    object_uris: dict[str, Any] = {}
    object_groups = [
        (record.analysis.formations, ns.DiscourseFormation),
        (record.analysis.signifiers, ns.Signifier),
        (record.analysis.nodal_points, ns.NodalPoint),
        (record.analysis.floating_signifiers, ns.FloatingSignifier),
        (record.analysis.empty_signifier_candidates, ns.EmptySignifier),
        (record.analysis.frontier, ns.DiscursiveFrontier),
        # Phase 1 analytical objects (issue #144). These are produced by the
        # default pipeline's discourse/postprocess stages and were previously
        # dropped from the RDF projection.
        (record.analysis.discourses, ns.Discourse),
        (record.analysis.imaginaries, ns.SociotechnicalImaginary),
        (record.analysis.us, ns.CollectiveSubject),
        (record.analysis.them, ns.Other),
        (record.analysis.affects, ns.Affect),
    ]
    for objects, rdf_type in object_groups:
        for obj in objects:
            node = rdflib.URIRef(stable_uri(base_uri, project_id, "concept", obj.object_id))
            object_uris[obj.object_id] = node
            graph.add((node, rdf.type, rdf_type))
            graph.add((node, rdf.type, skos.Concept))
            graph.add((node, dct.identifier, rdflib.Literal(obj.object_id)))
            graph.add((node, skos.prefLabel, rdflib.Literal(obj.label, lang=_language(record.source.language))))
            graph.add((node, ns.reviewState, rdflib.Literal(_review(obj.review_status))))
            if obj.confidence is not None:
                graph.add((node, ns.confidence, rdflib.Literal(obj.confidence)))
            if obj.uncertainty:
                graph.add((node, ns.uncertainty, rdflib.Literal(obj.uncertainty)))
            if obj.description:
                graph.add((node, dct.description, rdflib.Literal(obj.description, lang=_language(record.source.language))))
            # Corpus-level validation flags (e.g. floating/empty signifier
            # candidates) must survive projection so a consumer does not treat a
            # document-level candidate as a corpus-established finding.
            if obj.metadata.get("corpus_validation_required"):
                graph.add((node, ns.corpusValidationRequired, rdflib.Literal(True)))
            graph.add((node, prov.wasGeneratedBy, prov_uris.get(obj.provenance_id, run)))
            for evidence_id in obj.evidence_ids:
                if evidence_id in evidence_uris:
                    graph.add((node, ns.hasEvidence, evidence_uris[evidence_id]))

    for entity in record.analysis.entities:
        node = rdflib.URIRef(stable_uri(base_uri, project_id, "entity", entity.entity_id))
        object_uris[entity.entity_id] = node
        kind = (entity.entity_type or "Thing").casefold()
        rdf_type = schema.Person if kind in {"person", "per"} else schema.Organization if kind in {"organization", "org"} else schema.Thing
        graph.add((node, rdf.type, rdf_type))
        graph.add((node, dct.identifier, rdflib.Literal(entity.entity_id)))
        graph.add((node, schema.name, rdflib.Literal(entity.label, lang=_language(record.source.language))))
        graph.add((node, ns.reviewState, rdflib.Literal(_review(entity.review_status))))
        graph.add((node, prov.wasGeneratedBy, prov_uris.get(entity.provenance_id, run)))

    relations = list(record.analysis.relations) + list(record.analysis.antagonisms) + list(record.analysis.actor_entity_relations)
    for relation in relations:
        art = rdflib.URIRef(stable_uri(base_uri, project_id, "articulation", relation.relation_id))
        left = object_uris.get(relation.source_ref) or rdflib.URIRef(stable_uri(base_uri, project_id, "concept", relation.source_ref))
        right = object_uris.get(relation.target_ref) or rdflib.URIRef(stable_uri(base_uri, project_id, "concept", relation.target_ref))
        graph.add((art, rdf.type, ns.Articulation))
        graph.add((art, dct.identifier, rdflib.Literal(relation.relation_id)))
        graph.add((art, dct.type, rdflib.Literal(relation.relation_type)))
        graph.add((art, ns.articulates, left))
        graph.add((art, ns.articulates, right))
        graph.add((art, ns.reviewState, rdflib.Literal(_review(relation.review_status))))
        graph.add((art, prov.wasGeneratedBy, prov_uris.get(relation.provenance_id, run)))
        for evidence_id in relation.evidence_ids:
            if evidence_id in evidence_uris:
                graph.add((art, ns.hasEvidence, evidence_uris[evidence_id]))

    # Phase 1: equivalence / difference chains (issue #144). A chain is not a
    # single articulation: it groups heterogeneous members, so it is projected as
    # its own resource whose membership is preserved as explicit edges.
    for chain in list(record.analysis.equivalence_chains) + list(record.analysis.difference_chains):
        chain_node = rdflib.URIRef(stable_uri(base_uri, project_id, "chain", chain.chain_id))
        chain_type = ns.EquivalenceChain if chain.chain_type == "equivalence" else ns.DifferenceChain
        graph.add((chain_node, rdf.type, chain_type))
        graph.add((chain_node, rdf.type, ns.RelationChain))
        graph.add((chain_node, dct.identifier, rdflib.Literal(chain.chain_id)))
        graph.add((chain_node, dct.type, rdflib.Literal(chain.chain_type)))
        graph.add((chain_node, ns.reviewState, rdflib.Literal(_review(chain.review_status))))
        graph.add((chain_node, prov.wasGeneratedBy, prov_uris.get(chain.provenance_id, run)))
        for member_ref in chain.member_refs:
            member = object_uris.get(member_ref) or rdflib.URIRef(stable_uri(base_uri, project_id, "concept", member_ref))
            graph.add((chain_node, ns.hasMember, member))
        for evidence_id in chain.evidence_ids:
            if evidence_id in evidence_uris:
                graph.add((chain_node, ns.hasEvidence, evidence_uris[evidence_id]))

    # Phase 1: descriptive topics. These are descriptive computation, NOT
    # discourse-theoretical categories, so they are SKOS concepts typed
    # laclaugpt:Topic with no formation/articulation semantics (issue #144).
    for topic in record.analysis.topics:
        topic_id = getattr(topic, "topic_id", None) or getattr(topic, "id", None)
        label = getattr(topic, "canonical_label", None) or getattr(topic, "label", None)
        if not topic_id or not label:
            continue
        node = rdflib.URIRef(stable_uri(base_uri, project_id, "topic", topic_id))
        graph.add((node, rdf.type, ns.Topic))
        graph.add((node, rdf.type, skos.Concept))
        graph.add((node, dct.identifier, rdflib.Literal(topic_id)))
        graph.add((node, skos.prefLabel, rdflib.Literal(label, lang=_language(record.source.language))))
        graph.add((node, ns.descriptive, rdflib.Literal(True)))

    # Phase 1: sentiments and stances. Policy (issue #144): these ARE projected,
    # but explicitly typed as descriptive observations, never as affect or
    # antagonism. Sentiment polarity is not affective investment and must not be
    # readable as a discourse-theoretical claim in the graph.
    for kind, objects in (("sentiment", record.analysis.sentiments), ("stance", record.analysis.stances)):
        for obj in objects:
            node = rdflib.URIRef(stable_uri(base_uri, project_id, kind, obj.object_id))
            object_uris[obj.object_id] = node
            graph.add((node, rdf.type, ns.DescriptiveObservation))
            graph.add((node, rdf.type, skos.Concept))
            graph.add((node, dct.identifier, rdflib.Literal(obj.object_id)))
            graph.add((node, dct.type, rdflib.Literal(kind)))
            graph.add((node, skos.prefLabel, rdflib.Literal(obj.label, lang=_language(record.source.language))))
            graph.add((node, ns.descriptive, rdflib.Literal(True)))
            graph.add((node, ns.reviewState, rdflib.Literal(_review(obj.review_status))))
            if obj.confidence is not None:
                graph.add((node, ns.confidence, rdflib.Literal(obj.confidence)))
            if obj.uncertainty:
                graph.add((node, ns.uncertainty, rdflib.Literal(obj.uncertainty)))
            graph.add((node, prov.wasGeneratedBy, prov_uris.get(obj.provenance_id, run)))
            for evidence_id in obj.evidence_ids:
                if evidence_id in evidence_uris:
                    graph.add((node, ns.hasEvidence, evidence_uris[evidence_id]))

    # Phase 1: descriptive themes (issue #144). Projected as descriptive
    # observations for the same reason as sentiments/stances.
    for obj in record.analysis.themes:
        node = rdflib.URIRef(stable_uri(base_uri, project_id, "theme", obj.object_id))
        object_uris.setdefault(obj.object_id, node)
        graph.add((node, rdf.type, ns.DescriptiveObservation))
        graph.add((node, rdf.type, skos.Concept))
        graph.add((node, dct.identifier, rdflib.Literal(obj.object_id)))
        graph.add((node, dct.type, rdflib.Literal("theme")))
        graph.add((node, skos.prefLabel, rdflib.Literal(obj.label, lang=_language(record.source.language))))
        graph.add((node, ns.descriptive, rdflib.Literal(True)))
        graph.add((node, ns.reviewState, rdflib.Literal(_review(obj.review_status))))
        graph.add((node, prov.wasGeneratedBy, prov_uris.get(obj.provenance_id, run)))
        for evidence_id in obj.evidence_ids:
            if evidence_id in evidence_uris:
                graph.add((node, ns.hasEvidence, evidence_uris[evidence_id]))

    # Phase 1: formula of populism (issue #144). Projected as a structured
    # resource so the Us/Frontier components and the populist verdict survive;
    # only evidenced components present on the canonical record are emitted.
    formula = record.analysis.formula_of_populism
    if isinstance(formula, dict) and formula:
        formula_node = rdflib.URIRef(stable_uri(base_uri, project_id, "formula", record.source_url))
        graph.add((formula_node, rdf.type, ns.FormulaOfPopulism))
        graph.add((formula_node, dct.identifier, rdflib.Literal("formula_of_populism")))
        graph.add((formula_node, prov.wasGeneratedBy, run))
        if "populist" in formula and formula.get("populist") is not None:
            graph.add((formula_node, ns.populist, rdflib.Literal(bool(formula.get("populist")))))
        if formula.get("non_populist_reason"):
            graph.add((formula_node, ns.nonPopulistReason, rdflib.Literal(formula["non_populist_reason"])))
        for key, value in sorted(formula.items()):
            if key in {"populist", "non_populist_reason"} or value in (None, "", [], {}):
                continue
            graph.add((formula_node, ns.formulaComponent, rdflib.Literal(f"{key}:{value}")))
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
    """Validate the parent profile baseline, optionally using its SHACL file via PySHACL."""
    rdflib = _require_rdflib()
    if shapes_path:
        try:
            from pyshacl import validate
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError("SHACL validation requires pyshacl") from exc
        shapes = rdflib.Graph().parse(str(shapes_path), format="turtle")
        conforms, report_graph, report_text = validate(dataset, shacl_graph=shapes, advanced=True)
        sh = rdflib.Namespace("http://www.w3.org/ns/shacl#")
        issues = []
        for result in report_graph.subjects(rdflib.namespace.RDF.type, sh.ValidationResult):
            issues.append(
                ValidationIssue(
                    next((str(x) for x in report_graph.objects(result, sh.focusNode)), ""),
                    next((str(x) for x in report_graph.objects(result, sh.resultPath)), ""),
                    next((str(x) for x in report_graph.objects(result, sh.resultMessage)), "SHACL validation failure"),
                    next((str(x) for x in report_graph.objects(result, sh.resultSeverity)), "Violation"),
                )
            )
        return ValidationReport(bool(conforms), tuple(issues), str(report_text))

    ns = rdflib.Namespace(LACLAUGPT)
    prov = rdflib.Namespace(PROV)
    issues: list[ValidationIssue] = []
    for graph in dataset.graphs():
        for node in graph.subjects(rdflib.namespace.RDF.type, ns.Articulation):
            if len(set(graph.objects(node, ns.articulates))) < 2:
                issues.append(ValidationIssue(str(node), f"{LACLAUGPT}articulates", "An articulation must connect at least two articulated resources."))
            if not any(graph.objects(node, prov.wasGeneratedBy)):
                issues.append(ValidationIssue(str(node), f"{PROV}wasGeneratedBy", "An analytical articulation must retain generation provenance."))
            states = [str(x) for x in graph.objects(node, ns.reviewState)]
            if not states:
                issues.append(ValidationIssue(str(node), f"{LACLAUGPT}reviewState", "Articulation review state is required."))
            elif any(x not in {"PROVISIONAL", "ACCEPTED", "REJECTED", "REVISED", "CANONICAL", "SUPERSEDED"} for x in states):
                issues.append(ValidationIssue(str(node), f"{LACLAUGPT}reviewState", "Invalid articulation review state."))
        for rdf_type in (ns.EmptySignifier, ns.FloatingSignifier, ns.NodalPoint):
            for node in graph.subjects(rdflib.namespace.RDF.type, rdf_type):
                if not any(graph.objects(node, prov.wasGeneratedBy)):
                    issues.append(ValidationIssue(str(node), f"{PROV}wasGeneratedBy", "Theory-specific signifier-role claims must retain provenance."))
                if not any(graph.objects(node, ns.reviewState)):
                    issues.append(ValidationIssue(str(node), f"{LACLAUGPT}reviewState", "Theory-specific signifier-role claims must retain review state."))
        # Phase 1 analytical objects and relation chains (issue #144).
        phase1_classes = (
            ns.Discourse, ns.SociotechnicalImaginary, ns.CollectiveSubject, ns.Other,
            ns.Affect, ns.DiscourseFormation, ns.Signifier, ns.DiscursiveFrontier,
        )
        for rdf_type in phase1_classes:
            for node in graph.subjects(rdflib.namespace.RDF.type, rdf_type):
                if not any(graph.objects(node, prov.wasGeneratedBy)):
                    issues.append(ValidationIssue(str(node), f"{PROV}wasGeneratedBy", "A Phase 1 discourse-theoretical object must retain generation provenance."))
                if not any(graph.objects(node, ns.reviewState)):
                    issues.append(ValidationIssue(str(node), f"{LACLAUGPT}reviewState", "A Phase 1 discourse-theoretical object must retain review state."))
        for node in graph.subjects(rdflib.namespace.RDF.type, ns.RelationChain):
            if len(set(graph.objects(node, ns.hasMember))) < 2:
                issues.append(ValidationIssue(str(node), f"{LACLAUGPT}hasMember", "An equivalence/difference chain must retain at least two members."))
            if not any(graph.objects(node, prov.wasGeneratedBy)):
                issues.append(ValidationIssue(str(node), f"{PROV}wasGeneratedBy", "A relation chain must retain generation provenance."))
        for node in graph.subjects(rdflib.namespace.RDF.type, ns.FormulaOfPopulism):
            if not any(graph.objects(node, prov.wasGeneratedBy)):
                issues.append(ValidationIssue(str(node), f"{PROV}wasGeneratedBy", "The Formula of Populism projection must retain generation provenance."))
        # Descriptive observations must be explicitly marked descriptive so a
        # consumer cannot read polarity as affective investment.
        for rdf_type in (ns.DescriptiveObservation, ns.Topic):
            for node in graph.subjects(rdflib.namespace.RDF.type, rdf_type):
                if not any(graph.objects(node, ns.descriptive)):
                    issues.append(ValidationIssue(str(node), f"{LACLAUGPT}descriptive", "A descriptive observation must be explicitly marked descriptive."))
    return ValidationReport(not issues, tuple(issues), "\n".join(x.message for x in issues))


def _union_graph(dataset):
    rdflib = _require_rdflib()
    graph = rdflib.Graph()
    for context in dataset.graphs():
        for triple in context:
            graph.add(triple)
    for prefix, namespace in dataset.namespaces():
        graph.bind(prefix, namespace)
    return graph


def serialize_dataset(dataset, format_name: str) -> str:
    aliases = {
        "json-ld": "json-ld", "jsonld": "json-ld", "turtle": "turtle", "ttl": "turtle",
        "nquads": "nquads", "nq": "nquads", "ntriples": "nt", "n-triples": "nt", "nt": "nt",
        "trig": "trig", "rdfxml": "xml", "rdf/xml": "xml",
    }
    fmt = aliases.get(format_name.casefold())
    if fmt is None:
        raise ValueError(f"unsupported RDF format: {format_name}")
    target = dataset if fmt in {"nquads", "trig", "json-ld"} else _union_graph(dataset)
    value = target.serialize(format=fmt)
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
        suffix = {".jsonld": "json-ld", ".json": "json-ld", ".ttl": "turtle", ".nt": "nt", ".trig": "trig", ".rdf": "rdfxml"}.get(self.path.suffix.casefold(), "nquads")
        self.path.write_text(serialize_dataset(dataset, suffix), encoding="utf-8")
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
        self.dataset = _require_rdflib().Dataset()

    def healthcheck(self) -> dict[str, Any]:
        return {"ok": True, "backend": "rdflib", "query": True, "named_graphs": True}

    def add(self, dataset) -> dict[str, Any]:
        count = 0
        for context in dataset.graphs():
            target = self.dataset.graph(context.identifier)
            for triple in context:
                target.add(triple)
                count += 1
        return {"ok": True, "triples": count}

    def query(self, sparql: str, *, limits: dict[str, int] | None = None):
        return self.dataset.query(sparql)

    def export(self, format_name: str = "nquads") -> str:
        return serialize_dataset(self.dataset, format_name)


class SPARQLStore:
    """Generic authenticated SPARQL query/update adapter using the Python stdlib."""
    def __init__(self, *, query_endpoint: str, update_endpoint: str | None = None, token: str | None = None):
        self.query_endpoint, self.update_endpoint, self.token = query_endpoint, update_endpoint, token

    def _request(self, url: str, data: bytes, content_type: str, accept: str) -> bytes:
        headers = {"Content-Type": content_type, "Accept": accept}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read()

    def healthcheck(self) -> dict[str, Any]:
        try:
            self.query("ASK { ?s ?p ?o }")
            return {"ok": True, "backend": "sparql", "query": True, "update": bool(self.update_endpoint)}
        except Exception as exc:  # pragma: no cover - live network not used in CI
            return {"ok": False, "backend": "sparql", "error": type(exc).__name__}

    def add(self, dataset) -> dict[str, Any]:
        if not self.update_endpoint:
            raise RuntimeError("SPARQL update endpoint is not configured")
        update = f"INSERT DATA {{ {serialize_dataset(dataset, 'nquads')} }}".encode()
        self._request(self.update_endpoint, update, "application/sparql-update", "application/json")
        return {"ok": True}

    def query(self, sparql: str, *, limits: dict[str, int] | None = None) -> Any:
        text = sparql
        if limits and "limit" in limits and " limit " not in sparql.casefold():
            text = f"{sparql.rstrip()} LIMIT {int(limits['limit'])}"
        body = urllib.parse.urlencode({"query": text}).encode()
        raw = self._request(self.query_endpoint, body, "application/x-www-form-urlencoded", "application/sparql-results+json")
        return json.loads(raw.decode())

    def export(self, format_name: str = "nquads") -> str:
        body = urllib.parse.urlencode({"query": "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"}).encode()
        return self._request(self.query_endpoint, body, "application/x-www-form-urlencoded", "application/n-quads").decode()


def build_store(config: RDFStoreConfig) -> RDFStore:
    backend = config.backend.casefold()
    if backend == "file":
        return FileRDFStore(config.path or "rdf/laclaugpt.nq")
    if backend in {"local", "rdflib"}:
        return RDFLibStore()
    if backend == "sparql":
        endpoint = config.query_endpoint or config.endpoint
        if not endpoint:
            raise ValueError("SPARQL backend requires query_endpoint or endpoint")
        return SPARQLStore(query_endpoint=endpoint, update_endpoint=config.update_endpoint, token=config.token)
    if backend == "oxigraph":
        raise RuntimeError("Oxigraph is an optional future adapter behind the RDFStore contract")
    raise ValueError(f"unknown RDF store backend: {config.backend}")


@dataclass(frozen=True)
class RDFContext:
    text: str
    source_ids: tuple[str, ...]
    graph_paths: tuple[str, ...]
    provenance: dict[str, Any]


def retrieve_subgraph(dataset, *, project_id: str, seed: str, max_nodes: int = 40, max_edges: int = 80) -> RDFContext:
    """Return a bounded project-scoped subgraph with retrieval provenance."""
    rdflib = _require_rdflib()
    seed_cf = seed.casefold()
    triples: list[tuple[Any, Any, Any]] = []
    paths: list[str] = []
    nodes: set[str] = set()
    source_ids: set[str] = set()
    project_graphs = [g for g in dataset.graphs() if project_id.casefold() in str(g.identifier).casefold()]
    for graph in project_graphs:
        for triple in graph:
            if seed_cf in str(triple[0]).casefold() or seed_cf in str(triple[2]).casefold():
                triples.append(triple)
                paths.append(f"{graph.identifier} :: {triple[0]} -> {triple[1]} -> {triple[2]}")
                nodes.update((str(triple[0]), str(triple[2])))
                if len(triples) >= max_edges or len(nodes) >= max_nodes:
                    break
    frontier = [term for triple in triples for term in (triple[0], triple[2]) if isinstance(term, rdflib.URIRef)]
    for node in frontier:
        if len(triples) >= max_edges or len(nodes) >= max_nodes:
            break
        for graph in project_graphs:
            for triple in list(graph.triples((node, None, None))) + list(graph.triples((None, None, node))):
                if triple not in triples:
                    triples.append(triple)
                    paths.append(f"{graph.identifier} :: {triple[0]} -> {triple[1]} -> {triple[2]}")
                    nodes.update((str(triple[0]), str(triple[2])))
                if len(triples) >= max_edges or len(nodes) >= max_nodes:
                    break
    identifier = rdflib.URIRef(f"{DCTERMS}identifier")
    for graph in project_graphs:
        for value in graph.objects(None, identifier):
            if str(value).startswith(("http://", "https://")):
                source_ids.add(str(value))
    return RDFContext(
        text="\n".join(f"{s} | {p} | {o}" for s, p, o in triples),
        source_ids=tuple(sorted(source_ids)),
        graph_paths=tuple(paths[:max_edges]),
        provenance={"provider": "rdf-graphrag", "project_id": project_id, "seed": seed, "max_nodes": max_nodes, "max_edges": max_edges},
    )


def import_profile_dataset(dataset) -> list[dict[str, Any]]:
    """Import the portable source/articulation subset for semantic round-trip checks."""
    rdflib = _require_rdflib()
    dct, ns, prov = rdflib.Namespace(DCTERMS), rdflib.Namespace(LACLAUGPT), rdflib.Namespace(PROV)
    results: list[dict[str, Any]] = []
    for graph in dataset.graphs():
        for source in graph.subjects(rdflib.namespace.RDF.type, prov.Entity):
            ids = [str(x) for x in graph.objects(source, dct.identifier)]
            urls = [x for x in ids if x.startswith(("http://", "https://"))]
            if urls:
                results.append({"kind": "source", "source_url": urls[0], "identifiers": ids, "graph": str(graph.identifier)})
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
    """Project-gated materialization with required/optional failure semantics."""
    config = rdf_config(project_config)
    if not config.enabled:
        return record
    project_id = _project_id(project_config, project_profile)
    try:
        dataset = materialize_record(record, project_id=project_id, base_uri=config.base_uri)
        shapes = config.validation.shapes_path if config.validation.shacl else None
        report = validate_dataset(dataset, shapes_path=shapes) if config.validation.shacl else ValidationReport(True)
        if not report.conforms:
            raise ValueError("RDF SHACL validation failed: " + "; ".join(x.message for x in report.issues))
        serializations = {fmt: serialize_dataset(dataset, fmt) for fmt in config.formats}
        sink = store
        if sink is None and (config.store.backend.casefold() != "file" or config.store.path):
            sink = build_store(config.store)
        store_result = sink.add(dataset) if sink is not None else None
        record.analysis.plugin_results["rdf"] = {
            "schema": "laclaugpt-rdf-projection-v1",
            "project_id": project_id,
            "canonical_schema_version": record.schema_version,
            "rdf_profile_version": RDF_PROFILE_VERSION,
            "triple_count": sum(len(g) for g in dataset.graphs()),
            "named_graphs": sorted(str(g.identifier) for g in dataset.graphs()),
            "validation": {"conforms": report.conforms, "issues": [x.__dict__ for x in report.issues]},
            "serializations": serializations,
            "store": store_result,
            "graphrag_enabled": config.graphrag.enabled,
        }
    except Exception as exc:
        record.analysis.plugin_failures["rdf"] = {"error": type(exc).__name__, "message": str(exc), "required": config.required}
        if config.required:
            raise
    return record


class RDFMaterializationPlugin:
    """Adapter for the generic plugin runtime; callers still gate it with project settings."""
    @property
    def spec(self):
        from .plugin_pipeline import PluginSpec

        return PluginSpec(
            name="rdf_materialization",
            version=RDF_PROFILE_VERSION,
            method_id="rdf_interoperability_projection",
            method_version=RDF_PROFILE_VERSION,
            scope="record",
            requires=frozenset({"canonical_record"}),
            produces=frozenset({"rdf_projection"}),
            deterministic=True,
            config_schema_version="1",
        )

    def process(self, record: CanonicalRecord, context, config: Mapping[str, Any]) -> Mapping[str, Any]:
        project_config = {"project_id": context.project_id, "analysis": {"rdf": dict(config)}}
        run_optional_rdf_postprocess(record, project_config=project_config)
        if "rdf" in record.analysis.plugin_failures:
            raise RuntimeError(record.analysis.plugin_failures["rdf"]["message"])
        return record.analysis.plugin_results.get("rdf", {"enabled": False})
