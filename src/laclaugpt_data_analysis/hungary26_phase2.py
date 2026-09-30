"""Hungary26 Phase 2 post-processing: DNA -> SNA -> RDF.

This module deliberately starts after the preserved Hungary26 Phase 1 multimodal /
Laclaudian runner. It turns evidence-linked source rows into DNA statements, conventional
NetworkX projections and an RDF research graph while preserving stage/provenance labels.

Real source rows and outputs stay under the private Hungary26 runtime root.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Callable

from .discourse_network.models import (
    AgreementStatus,
    DiscourseStatement,
    EvidenceSpan,
    Stance,
    ValidationStatus,
)
from .discourse_network.network import (
    dna_actor_projection,
    dna_binary_actor_concept,
    dna_concept_projection,
)

DNA_PROMPT_VERSION = "hungary26-dna-v1"
DNA_SYSTEM = """Code evidence-linked Discourse Network Analysis statements for Hungary26.
Return one JSON object with key statements, a list. Each item must contain:
concept_label, agreement (true/false/null), agreement_status
(coded/ambiguous/not_applicable/abstain), evidence_text, confidence, uncertainty_reason.
Use only claims attributable to the source actor. Prefer proposition-like concepts.
Do not infer ideology, party alignment, equivalence, antagonism or stance from identity.
Evidence must be copied from the supplied caption or clearly marked multimodal evidence.
If no defensible statement exists, return an empty list."""


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.strip().casefold().encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _parse_json_output(value: str) -> dict[str, Any]:
    raw = json.loads(value)
    if not isinstance(raw, dict):
        raise ValueError("Phase 2 model output must be a JSON object")
    return raw


def _stage_payload(row: dict[str, Any], stage: str) -> dict[str, Any]:
    raw = row.get(f"{stage}_output") or ""
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _evidence_span(caption: str, evidence: str) -> EvidenceSpan:
    evidence = str(evidence or "").strip()
    if not evidence:
        return EvidenceSpan()
    start = caption.find(evidence)
    if start >= 0:
        return EvidenceSpan(
            quote=evidence,
            start_char=start,
            end_char=start + len(evidence),
            exact=True,
        )
    return EvidenceSpan(quote=evidence, exact=False)


def code_row_to_statements(
    row: dict[str, Any],
    *,
    model: str,
    codebook_version: str,
    ollama_chat: Callable[..., str],
) -> list[DiscourseStatement]:
    """Code DNA statements from one completed Phase 1 row."""
    if row.get("discourse_status") != "ok":
        return []
    actor_name = str(row.get("author") or row.get("author_fullname") or "").strip()
    if not actor_name:
        return []

    caption = str(row.get("caption") or "")
    summary = _stage_payload(row, "summary").get("parsed", {})
    discourse = _stage_payload(row, "discourse").get("parsed", {})
    vision = _stage_payload(row, "vision").get("observations", [])
    prompt = stable_json(
        {
            "source_record_id": row.get("document_id"),
            "actor": actor_name,
            "caption_hu": caption,
            "multimodal_summary": summary,
            "visual_observations": vision,
            "prior_laclau_analysis": discourse,
            "boundary_note": (
                "Summary/visual/Laclau fields are prior analytical context. "
                "DNA evidence must remain traceable to source or explicit multimodal anchors."
            ),
        }
    )
    parsed = _parse_json_output(
        ollama_chat(model=model, system=DNA_SYSTEM, user=prompt, num_predict=1536)
    )
    candidates = parsed.get("statements") or []
    if not isinstance(candidates, list):
        raise ValueError("DNA output statements must be a list")

    actor_id = _stable_id("actor", actor_name)
    document_id = str(row.get("document_id") or "")
    source_url = str(row.get("source_url") or f"urn:hungary26:{document_id}")
    output: list[DiscourseStatement] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        concept_label = str(candidate.get("concept_label") or "").strip()
        if not concept_label:
            continue
        agreement = candidate.get("agreement")
        status_raw = str(candidate.get("agreement_status") or "abstain")
        try:
            status = AgreementStatus(status_raw)
        except ValueError:
            status = AgreementStatus.ABSTAIN
        if not isinstance(agreement, bool):
            agreement = None
        if status == AgreementStatus.CODED and agreement is None:
            status = AgreementStatus.AMBIGUOUS
        if status != AgreementStatus.CODED:
            agreement = None
        stance = (
            Stance.SUPPORT
            if agreement is True
            else Stance.OPPOSE
            if agreement is False
            else Stance.UNKNOWN
        )
        evidence_text = str(candidate.get("evidence_text") or "").strip()
        concept_id = _stable_id("concept", concept_label)
        statement_material = f"{document_id}|{actor_id}|{concept_id}|{agreement}|{index}"
        statement_id = "hu26-dna:" + hashlib.sha256(statement_material.encode()).hexdigest()[:20]
        confidence = candidate.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None
        if confidence_value is not None:
            confidence_value = max(0.0, min(1.0, confidence_value))
        span = _evidence_span(caption, evidence_text)
        output.append(
            DiscourseStatement(
                statement_id=statement_id,
                source_url=source_url,
                source_record_id=document_id,
                actor_id=actor_id,
                actor_name=actor_name,
                concept_id=concept_id,
                concept_label=concept_label,
                proposition=concept_label,
                concept_type="issue_position",
                stance=stance,
                agreement=agreement,
                agreement_status=status,
                platform=str(row.get("platform") or "") or None,
                coder_type="llm",
                coder_id_or_model=model,
                model_version=model,
                prompt_version=DNA_PROMPT_VERSION,
                confidence=confidence_value,
                codebook_version=codebook_version,
                validation_status=(
                    ValidationStatus.PROVISIONAL
                    if span.exact
                    else ValidationStatus.NEEDS_REVIEW
                ),
                abstained=status != AgreementStatus.CODED,
                abstention_reason=str(candidate.get("uncertainty_reason") or "") or None,
                evidence=span,
                metadata={
                    "project": "hungary26",
                    "evidence_anchor_type": (
                        "caption_exact" if span.exact else "multimodal_or_nonexact"
                    ),
                },
                provenance={
                    "workbook": row.get("workbook"),
                    "sheet": row.get("sheet"),
                    "row_number": row.get("row_number"),
                    "source_fingerprint": row.get("source_fingerprint"),
                    "prompt_version": DNA_PROMPT_VERSION,
                },
            )
        )
    return output


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        if fieldnames:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def _statement_rows(statements: list[DiscourseStatement]) -> list[dict[str, Any]]:
    rows = []
    for statement in statements:
        payload = statement.model_dump(mode="json")
        payload["evidence"] = stable_json(payload["evidence"])
        payload["metadata"] = stable_json(payload["metadata"])
        payload["provenance"] = stable_json(payload["provenance"])
        rows.append(payload)
    return rows


def _matrix_rows(statements: list[DiscourseStatement]) -> list[dict[str, Any]]:
    matrix = dna_binary_actor_concept(statements)
    rows: list[dict[str, Any]] = []
    for actor_id, concepts in sorted(matrix.items()):
        for concept_id, values in sorted(concepts.items()):
            rows.append(
                {
                    "actor_id": actor_id,
                    "concept_id": concept_id,
                    "support_count": values[True],
                    "oppose_count": values[False],
                }
            )
    return rows


def _projection_rows(
    projection: dict[tuple[str, str], dict[str, Any]],
    *,
    left_name: str,
    right_name: str,
) -> list[dict[str, Any]]:
    rows = []
    for (left, right), data in sorted(projection.items()):
        rows.append(
            {
                left_name: left,
                right_name: right,
                "weight": data.get("weight", 0.0),
                "kind": data.get("kind", ""),
                "projection_method": data.get("projection_method", ""),
                "matches": stable_json(
                    data.get("shared_concepts") or data.get("shared_actors") or []
                ),
            }
        )
    return rows


def _build_graphs(
    statements: list[DiscourseStatement],
    *,
    graphs_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Hungary26 Phase 2 requires networkx") from exc

    graphs_dir.mkdir(parents=True, exist_ok=True)
    matrix = dna_binary_actor_concept(statements)
    congruence = dna_actor_projection(statements)
    conflict = dna_actor_projection(statements, conflict=True)
    concept = dna_concept_projection(statements)

    graph_objects: dict[str, Any] = {}

    actor_concept = nx.Graph(name="dna_actor_concept")
    for actor_id, concepts in sorted(matrix.items()):
        actor_node = f"actor:{actor_id}"
        actor_concept.add_node(actor_node, bipartite="actor", layer="dna", project="hungary26")
        for concept_id, values in sorted(concepts.items()):
            concept_node = f"concept:{concept_id}"
            actor_concept.add_node(
                concept_node, bipartite="concept", layer="dna", project="hungary26"
            )
            actor_concept.add_edge(
                actor_node,
                concept_node,
                support_count=int(values[True]),
                oppose_count=int(values[False]),
                weight=int(values[True]) + int(values[False]),
                kind="actor_concept",
            )
    graph_objects["dna_actor_concept"] = actor_concept

    for name, projection in {
        "dna_actor_congruence": congruence,
        "dna_actor_conflict": conflict,
        "dna_concept_congruence": concept,
    }.items():
        graph = nx.Graph(name=name)
        for (left, right), data in projection.items():
            attrs = {
                key: stable_json(value) if isinstance(value, (list, dict)) else value
                for key, value in data.items()
            }
            graph.add_edge(left, right, **attrs)
        for node in graph.nodes:
            graph.nodes[node]["layer"] = "dna"
            graph.nodes[node]["project"] = "hungary26"
        graph_objects[name] = graph

    node_rows: list[dict[str, Any]] = []
    edge_rows: list[dict[str, Any]] = []
    outputs: dict[str, str] = {}
    for name, graph in graph_objects.items():
        for node, attrs in graph.nodes(data=True):
            node_rows.append({"graph": name, "node_id": node, **attrs})
        for left, right, attrs in graph.edges(data=True):
            edge_rows.append({"graph": name, "source": left, "target": right, **attrs})
        graphml = graphs_dir / f"{name}.graphml"
        gexf = graphs_dir / f"{name}.gexf"
        nx.write_graphml(graph, graphml)
        nx.write_gexf(graph, gexf)
        outputs[f"{name}_graphml"] = str(graphml)
        outputs[f"{name}_gexf"] = str(gexf)

    graph = graph_objects["dna_actor_congruence"]
    metrics: list[dict[str, Any]] = []
    if graph.number_of_nodes():
        degree = dict(graph.degree(weight="weight"))
        betweenness = nx.betweenness_centrality(graph, weight="weight")
        closeness = nx.closeness_centrality(graph)
        pagerank = (
            nx.pagerank(graph, weight="weight")
            if graph.number_of_edges()
            else {node: 1.0 / graph.number_of_nodes() for node in graph}
        )
        clustering = nx.clustering(graph, weight="weight")
        for node in sorted(graph.nodes):
            metrics.append(
                {
                    "graph": "dna_actor_congruence",
                    "node_id": node,
                    "weighted_degree": degree.get(node, 0.0),
                    "betweenness": betweenness.get(node, 0.0),
                    "closeness": closeness.get(node, 0.0),
                    "pagerank": pagerank.get(node, 0.0),
                    "clustering": clustering.get(node, 0.0),
                    "interpretation_guardrail": (
                        "network measurement, not a political/theoretical verdict"
                    ),
                }
            )
    return node_rows, edge_rows, metrics, outputs

def _write_rdf(
    *,
    phase1_rows: list[dict[str, Any]],
    statements: list[DiscourseStatement],
    node_rows: list[dict[str, Any]],
    edge_rows: list[dict[str, Any]],
    target: Path,
) -> dict[str, Any]:
    try:
        import rdflib
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Hungary26 Phase 2 RDF export requires rdflib") from exc

    RDF = rdflib.RDF
    PROV = rdflib.Namespace("http://www.w3.org/ns/prov#")
    LG = rdflib.Namespace("https://w3id.org/laclaugpt/")
    DCT = rdflib.namespace.DCTERMS
    graph = rdflib.Graph()
    graph.bind("lg", LG)
    graph.bind("prov", PROV)
    graph.bind("dcterms", DCT)

    for row in phase1_rows:
        record_id = str(row.get("document_id") or "")
        if not record_id:
            continue
        source = rdflib.URIRef(f"https://w3id.org/laclaugpt/hungary26/source/{record_id}")
        graph.add((source, RDF.type, LG.SourceRecord))
        graph.add((source, LG.layer, rdflib.Literal("source")))
        graph.add((source, DCT.identifier, rdflib.Literal(record_id)))
        if row.get("platform"):
            graph.add((source, LG.platform, rdflib.Literal(str(row["platform"]))))
        if row.get("source_fingerprint"):
            graph.add(
                (source, LG.sourceFingerprint, rdflib.Literal(str(row["source_fingerprint"])))
            )
        for stage, rdf_type, layer in (
            ("vision", LG.MultimodalRepresentation, "source"),
            ("summary", LG.DescriptiveSummary, "source"),
            ("discourse", LG.LaclauAnalysis, "laclau"),
        ):
            if row.get(f"{stage}_status") != "ok":
                continue
            analysis = rdflib.URIRef(
                f"https://w3id.org/laclaugpt/hungary26/{stage}/{record_id}"
            )
            graph.add((analysis, RDF.type, rdf_type))
            graph.add((analysis, LG.layer, rdflib.Literal(layer)))
            graph.add((analysis, PROV.wasDerivedFrom, source))
            graph.add((analysis, LG.stage, rdflib.Literal(stage)))

    for statement in statements:
        sid = rdflib.URIRef(f"https://w3id.org/laclaugpt/hungary26/dna/{statement.statement_id}")
        actor = rdflib.URIRef(f"https://w3id.org/laclaugpt/hungary26/actor/{statement.actor_id}")
        concept = rdflib.URIRef(f"https://w3id.org/laclaugpt/hungary26/concept/{statement.concept_id}")
        source = rdflib.URIRef(
            f"https://w3id.org/laclaugpt/hungary26/source/{statement.source_record_id}"
        )
        graph.add((sid, RDF.type, LG.DNAStatement))
        graph.add((sid, LG.layer, rdflib.Literal("dna")))
        graph.add((sid, LG.actor, actor))
        graph.add((sid, LG.concept, concept))
        graph.add((sid, PROV.wasDerivedFrom, source))
        graph.add((actor, RDF.type, PROV.Agent))
        graph.add((concept, RDF.type, LG.DNAConcept))
        graph.add((concept, rdflib.namespace.RDFS.label, rdflib.Literal(statement.concept_label)))
        if statement.agreement is not None:
            graph.add((sid, LG.agreement, rdflib.Literal(statement.agreement)))
        if statement.evidence.quote:
            graph.add((sid, LG.evidenceText, rdflib.Literal(statement.evidence.quote)))
        graph.add((sid, LG.validationStatus, rdflib.Literal(statement.validation_status.value)))

    for row in node_rows:
        node = rdflib.URIRef(
            f"https://w3id.org/laclaugpt/hungary26/sna/{row['graph']}/{row['node_id']}"
        )
        graph.add((node, RDF.type, LG.SNANode))
        graph.add((node, LG.layer, rdflib.Literal("sna")))
        graph.add((node, LG.graphName, rdflib.Literal(str(row["graph"]))))
    for index, row in enumerate(edge_rows):
        edge = rdflib.URIRef(f"https://w3id.org/laclaugpt/hungary26/sna/edge/{index}")
        graph.add((edge, RDF.type, LG.SNAEdge))
        graph.add((edge, LG.layer, rdflib.Literal("sna")))
        graph.add((edge, LG.graphName, rdflib.Literal(str(row["graph"]))))
        graph.add((edge, LG.sourceNode, rdflib.Literal(str(row["source"]))))
        graph.add((edge, LG.targetNode, rdflib.Literal(str(row["target"]))))
        if row.get("weight") is not None:
            graph.add((edge, LG.weight, rdflib.Literal(float(row["weight"]))))

    target.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=str(target), format="turtle")
    dna_nodes = set(graph.subjects(RDF.type, LG.DNAStatement))
    valid = all(
        (node, PROV.wasDerivedFrom, None) in graph
        and (node, LG.actor, None) in graph
        and (node, LG.concept, None) in graph
        for node in dna_nodes
    )
    layers = sorted({str(value) for value in graph.objects(None, LG.layer)})
    return {
        "triples": len(graph),
        "dna_statements": len(dna_nodes),
        "layers": layers,
        "valid": valid and {"source", "laclau", "dna", "sna"}.issubset(set(layers)),
    }

def _persist_sqlite(
    db_path: Path,
    *,
    statements: list[DiscourseStatement],
    metrics: list[dict[str, Any]],
    rdf_report: dict[str, Any],
) -> None:
    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS dna_statements (
                statement_id TEXT PRIMARY KEY,
                source_record_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                concept_id TEXT NOT NULL,
                agreement INTEGER,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sna_metrics (
                graph TEXT NOT NULL,
                node_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (graph, node_id)
            );
            CREATE TABLE IF NOT EXISTS rdf_exports (
                export_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            );
            """
        )
        db.executemany(
            "INSERT OR REPLACE INTO dna_statements VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    item.statement_id,
                    item.source_record_id or "",
                    item.actor_id,
                    item.concept_id,
                    None if item.agreement is None else int(item.agreement),
                    stable_json(item.model_dump(mode="json")),
                )
                for item in statements
            ],
        )
        db.executemany(
            "INSERT OR REPLACE INTO sna_metrics VALUES (?, ?, ?)",
            [
                (str(row["graph"]), str(row["node_id"]), stable_json(row))
                for row in metrics
            ],
        )
        db.execute(
            "INSERT OR REPLACE INTO rdf_exports VALUES (?, ?)",
            ("hungary26-phase2", stable_json(rdf_report)),
        )


def run_phase2(
    *,
    rows: list[dict[str, Any]],
    private_root: Path,
    db_path: Path,
    model: str,
    codebook_version: str,
    ollama_chat: Callable[..., str],
) -> dict[str, Any]:
    """Run the complete Phase 2 projection/export chain over completed Phase 1 rows."""
    data_dir = private_root / "data"
    graphs_dir = private_root / "graphs"
    outputs_dir = private_root / "outputs"
    data_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    statements: list[DiscourseStatement] = []
    coding_failures: list[dict[str, str]] = []
    for row in rows:
        if row.get("discourse_status") != "ok":
            continue
        try:
            statements.extend(
                code_row_to_statements(
                    row,
                    model=model,
                    codebook_version=codebook_version,
                    ollama_chat=ollama_chat,
                )
            )
        except Exception as exc:
            coding_failures.append(
                {"document_id": str(row.get("document_id") or ""), "error": str(exc)}
            )

    statement_rows = _statement_rows(statements)
    matrix_rows = _matrix_rows(statements)
    actor_congruence = _projection_rows(
        dna_actor_projection(statements),
        left_name="actor_left",
        right_name="actor_right",
    )
    actor_conflict = _projection_rows(
        dna_actor_projection(statements, conflict=True),
        left_name="actor_left",
        right_name="actor_right",
    )
    concept_congruence = _projection_rows(
        dna_concept_projection(statements),
        left_name="concept_left",
        right_name="concept_right",
    )

    csv_targets = {
        "dna_statements": data_dir / "dna_statements.csv",
        "dna_actor_concept": data_dir / "dna_actor_concept.csv",
        "dna_actor_congruence": data_dir / "dna_actor_congruence.csv",
        "dna_actor_conflict": data_dir / "dna_actor_conflict.csv",
        "dna_concept_congruence": data_dir / "dna_concept_congruence.csv",
    }
    for key, target in csv_targets.items():
        payload = {
            "dna_statements": statement_rows,
            "dna_actor_concept": matrix_rows,
            "dna_actor_congruence": actor_congruence,
            "dna_actor_conflict": actor_conflict,
            "dna_concept_congruence": concept_congruence,
        }[key]
        _write_csv(target, payload)

    node_rows, edge_rows, metrics, graph_outputs = _build_graphs(
        statements, graphs_dir=graphs_dir
    )
    _write_csv(data_dir / "sna_nodes.csv", node_rows)
    _write_csv(data_dir / "sna_edges.csv", edge_rows)
    _write_csv(data_dir / "sna_metrics.csv", metrics)

    rdf_target = graphs_dir / "hungary26.ttl"
    rdf_report = _write_rdf(
        phase1_rows=rows,
        statements=statements,
        node_rows=node_rows,
        edge_rows=edge_rows,
        target=rdf_target,
    )
    _persist_sqlite(
        db_path,
        statements=statements,
        metrics=metrics,
        rdf_report=rdf_report,
    )

    qa = {
        "schema_version": "hungary26-phase2-qa-v1",
        "prompt_version": DNA_PROMPT_VERSION,
        "phase1_rows": len(rows),
        "dna_statements": len(statements),
        "dna_coding_failures": coding_failures,
        "actor_congruence_edges": len(actor_congruence),
        "actor_conflict_edges": len(actor_conflict),
        "concept_congruence_edges": len(concept_congruence),
        "sna_nodes": len(node_rows),
        "sna_edges": len(edge_rows),
        "sna_metric_rows": len(metrics),
        "rdf": rdf_report,
        "stage_boundary": "source/multimodal -> Phase1 Laclau -> DNA -> SNA -> RDF",
    }
    qa_target = outputs_dir / f"phase2-qa-{os.getenv('SLURM_JOB_ID', 'local')}.json"
    qa_target.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        **qa,
        "csvs": {key: str(value) for key, value in csv_targets.items()},
        "sna_nodes_csv": str(data_dir / "sna_nodes.csv"),
        "sna_edges_csv": str(data_dir / "sna_edges.csv"),
        "sna_metrics_csv": str(data_dir / "sna_metrics.csv"),
        "graphs": graph_outputs,
        "rdf_turtle": str(rdf_target),
        "qa_report": str(qa_target),
    }
