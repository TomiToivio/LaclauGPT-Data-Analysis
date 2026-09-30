"""EP24 Phase 2 DNA/SNA/RDF extension."""
from __future__ import annotations
import csv, hashlib, json, sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any
import networkx as nx
from rdflib import Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import DCTERMS, PROV, XSD
from .hungary26_roihu import ollama_chat

LG = Namespace("https://w3id.org/laclaugpt/ep24/")
SCHEMA = Namespace("https://schema.org/")
PHASE2_PROMPT_VERSION = "ep24-phase2-dna.v1"
DNA_SYSTEM = """Code discourse-network statements from the supplied evidence.
Return JSON with key statements, a list. Each statement must describe one explicitly
evidenced actor-concept claim and contain actor, concept, stance
(support|reject|neutral|uncoded), evidence_ids, evidence_text, confidence.
Do not infer stance from actor identity, party, ideology, codebook membership, or mere
co-occurrence. Use uncoded when agreement/disagreement is not explicit."""

def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

def _slug(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]

def _parse_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == fence:
            lines = lines[:-1]
        text = "\n".join(lines)
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError("Phase 2 DNA response must be a JSON object")
    return obj

def _canonical_lookup(matches: list[dict[str, Any]], kind: str, label: str) -> str:
    folded = label.casefold().strip()
    wanted = {"entity", "actor"} if kind == "actor" else {"theme", "signifier", "concept"}
    for item in matches:
        if str(item.get("kind", "")).casefold() in wanted and folded in {
            str(item.get("label", "")).casefold().strip(),
            str(item.get("matched_surface", "")).casefold().strip(),
        }:
            return str(item.get("id") or "")
    return ""

def code_dna_statements(*, record_id: str, country: str, language: str,
                        row: dict[str, Any], preanalysis: dict[str, Any],
                        analysis: dict[str, Any], matches: list[dict[str, Any]],
                        model: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    source_url = next((str(row.get(k) or "").strip() for k in
        ("source_url", "url", "post_url", "video_url") if str(row.get(k) or "").strip()), "")
    raw = ollama_chat(
        model=model, system=DNA_SYSTEM,
        user=_stable({
            "record_id": record_id, "country": country, "language": language,
            "source_url": source_url,
            "phase1_preanalysis": preanalysis.get("parsed", preanalysis),
            "phase1_discourse_analysis": analysis.get("parsed", analysis),
            "codebook_matches_for_normalization_only": matches,
            "rules": {"identity_is_not_stance": True, "cooccurrence_is_not_statement": True},
        }),
        num_ctx=int(config.get("num_ctx", 32768)),
        num_predict=int(config.get("dna_num_predict", 3072)),
    )
    rows = _parse_object(raw).get("statements") or []
    if not isinstance(rows, list):
        raise ValueError("Phase 2 DNA statements must be a list")
    output = []
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            continue
        actor, concept = str(item.get("actor") or "").strip(), str(item.get("concept") or "").strip()
        if not actor or not concept:
            continue
        stance = str(item.get("stance") or "uncoded").casefold()
        if stance not in {"support", "reject", "neutral", "uncoded"}:
            stance = "uncoded"
        evidence_ids = item.get("evidence_ids") or []
        if isinstance(evidence_ids, str):
            evidence_ids = [evidence_ids]
        output.append({
            "statement_id": f"{record_id}:dna:{index + 1}:{_slug(actor + '|' + concept + '|' + stance)}",
            "record_id": record_id, "country": country, "language": language,
            "source_url": source_url, "actor": actor,
            "actor_id": _canonical_lookup(matches, "actor", actor) or f"actor:{_slug(actor.casefold())}",
            "concept": concept,
            "concept_id": _canonical_lookup(matches, "concept", concept) or f"concept:{_slug(concept.casefold())}",
            "stance": stance, "evidence_ids": [str(v) for v in evidence_ids if str(v).strip()],
            "evidence_text": str(item.get("evidence_text") or "").strip(),
            "confidence": item.get("confidence"), "coding_origin": "model",
            "review_state": "unreviewed", "prompt_version": PHASE2_PROMPT_VERSION,
            "phase1_relation": "downstream_of_laclau_analysis",
        })
    return output

def ensure_phase2_tables(db_path: str | Path) -> None:
    with sqlite3.connect(db_path) as db:
        for table in ("dna_statements", "dna_projections", "sna_graphs", "sna_metrics", "rdf_exports", "human_review"):
            db.execute(f"""CREATE TABLE IF NOT EXISTS {table}(
                record_id TEXT NOT NULL,item_id TEXT NOT NULL,payload_json TEXT NOT NULL,
                fingerprint TEXT NOT NULL,created_at REAL NOT NULL,
                PRIMARY KEY(record_id,item_id))""")

def persist_statements(db_path: str | Path, record_id: str, statements: list[dict[str, Any]],
                       fingerprint: str, created_at: float) -> None:
    ensure_phase2_tables(db_path)
    with sqlite3.connect(db_path) as db:
        db.execute("DELETE FROM dna_statements WHERE record_id=?", (record_id,))
        for row in statements:
            db.execute("INSERT INTO dna_statements VALUES(?,?,?,?,?)",
                       (record_id, row["statement_id"], _stable(row), fingerprint, created_at))

def load_statements(db_path: str | Path) -> list[dict[str, Any]]:
    ensure_phase2_tables(db_path)
    with sqlite3.connect(db_path) as db:
        rows = db.execute("SELECT payload_json FROM dna_statements ORDER BY record_id,item_id").fetchall()
    return [json.loads(row[0]) for row in rows]

def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row}) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if fields:
            writer.writeheader()
            for row in rows:
                writer.writerow({k: (_stable(v) if isinstance(v, (list, dict)) else v) for k, v in row.items()})

def _actor_concept_rows(statements):
    counts = defaultdict(int)
    for row in statements:
        counts[(row["actor_id"], row["concept_id"], row["stance"])] += 1
    return [{"actor_id": a, "concept_id": c, "stance": s, "weight": w}
            for (a, c, s), w in sorted(counts.items())]

def _pair_projection(statements, dimension):
    other = "concept_id" if dimension == "actor_id" else "actor_id"
    by_other = defaultdict(lambda: defaultdict(set))
    for row in statements:
        if row["stance"] != "uncoded":
            by_other[row[other]][row[dimension]].add(row["stance"])
    weights = defaultdict(int)
    for groups in by_other.values():
        ids = sorted(groups)
        for i, left in enumerate(ids):
            for right in ids[i + 1:]:
                kind = "congruence" if groups[left] & groups[right] else "conflict"
                weights[(left, right, kind)] += 1
    return [{"source": a, "target": b, "relation": kind, "weight": w}
            for (a, b, kind), w in sorted(weights.items())]

def _graph(name, rows):
    graph = nx.Graph(name=name, graph_kind="analytical_derived")
    for row in rows:
        source, target = row.get("source") or row.get("actor_id"), row.get("target") or row.get("concept_id")
        if source and target:
            graph.add_edge(str(source), str(target), **{k: v for k, v in row.items()
                if k not in {"source", "target", "actor_id", "concept_id"}})
    return graph

def _metrics(graph):
    if not graph.number_of_nodes():
        return []
    degree = dict(graph.degree(weight="weight"))
    between = nx.betweenness_centrality(graph, weight="weight")
    close = nx.closeness_centrality(graph)
    pagerank = nx.pagerank(graph, weight="weight") if graph.number_of_edges() else {n: 0.0 for n in graph}
    components = {}
    for i, comp in enumerate(nx.connected_components(graph)):
        for node in comp:
            components[node] = i
    return [{"node_id": n, "degree": degree.get(n, 0), "betweenness": between.get(n, 0.0),
             "closeness": close.get(n, 0.0), "pagerank": pagerank.get(n, 0.0),
             "component": components.get(n, 0)} for n in graph.nodes]

def export_phase2(db_path: str | Path, paths: dict[str, Path], *, fingerprint: str) -> dict[str, str]:
    statements = load_statements(db_path)
    data = Path(paths["data"])
    graphs_dir = Path(paths.get("graphs") or (Path(paths["root"]) / "graphs"))
    graphs_dir.mkdir(parents=True, exist_ok=True)
    outputs, all_graphs = {}, []
    groups = {"combined": statements,
              "finland": [r for r in statements if r.get("country") == "FI"],
              "poland": [r for r in statements if r.get("country") == "PL"]}
    for scope, rows in groups.items():
        suffix = "" if scope == "combined" else f"_{scope}"
        p = data / f"dna_statements{suffix}.csv"; _write_csv(p, rows); outputs[f"dna_statements_{scope}"] = str(p)
        ac, actor, concept = _actor_concept_rows(rows), _pair_projection(rows, "actor_id"), _pair_projection(rows, "concept_id")
        for key, values in (("dna_actor_concept", ac), ("dna_actor_projection", actor), ("dna_concept_projection", concept)):
            p = data / f"{key}{suffix}.csv"; _write_csv(p, values); outputs[f"{key}_{scope}"] = str(p)
        for key, values in (("actor_concept", ac), ("actor", actor), ("concept", concept)):
            graph = _graph(f"ep24_{scope}_{key}", values); all_graphs.append((f"{scope}_{key}", graph))
            gml, gexf = graphs_dir / f"{scope}_{key}.graphml", graphs_dir / f"{scope}_{key}.gexf"
            nx.write_graphml(graph, gml); nx.write_gexf(graph, gexf)
            outputs[f"graphml_{scope}_{key}"], outputs[f"gexf_{scope}_{key}"] = str(gml), str(gexf)
            mp = data / f"sna_metrics_{scope}_{key}.csv"; _write_csv(mp, _metrics(graph)); outputs[f"sna_metrics_{scope}_{key}"] = str(mp)
    rdf = Graph(); rdf.bind("lg", LG); rdf.bind("prov", PROV); rdf.bind("schema", SCHEMA)
    for row in statements:
        s = URIRef(LG[row["statement_id"]]); rdf.add((s, RDF.type, LG.DNAStatement))
        rdf.add((s, DCTERMS.identifier, Literal(row["statement_id"])))
        rdf.add((s, LG.record, URIRef(LG[row["record_id"]]))); rdf.add((s, LG.actor, URIRef(LG[row["actor_id"]])))
        rdf.add((s, LG.concept, URIRef(LG[row["concept_id"]]))); rdf.add((s, LG.stance, Literal(row["stance"])))
        rdf.add((s, PROV.wasDerivedFrom, URIRef(LG[row["record_id"]])))
        if row.get("source_url"): rdf.add((s, SCHEMA.url, Literal(row["source_url"])))
        for eid in row.get("evidence_ids") or []: rdf.add((s, LG.evidence, URIRef(LG[str(eid)])))
    for name, graph in all_graphs:
        g = URIRef(LG[f"graph:{name}"]); rdf.add((g, RDF.type, LG.SNAGraph))
        rdf.add((g, LG.graphKind, Literal("analytical_derived"))); rdf.add((g, LG.fingerprint, Literal(fingerprint)))
        rdf.add((g, LG.nodeCount, Literal(graph.number_of_nodes(), datatype=XSD.integer)))
        rdf.add((g, LG.edgeCount, Literal(graph.number_of_edges(), datatype=XSD.integer)))
    ttl = graphs_dir / "ep24.ttl"; rdf.serialize(ttl, format="turtle")
    check = Graph(); check.parse(ttl, format="turtle")
    outputs["rdf"], outputs["rdf_validation"] = str(ttl), "passed"
    with sqlite3.connect(db_path) as db:
        db.execute("DELETE FROM rdf_exports WHERE record_id='__run__'")
        db.execute("INSERT INTO rdf_exports VALUES('__run__','ep24-rdf',?,?,strftime('%s','now'))",
                   (_stable({"path": str(ttl), "triples": len(check), "validation": "passed"}), fingerprint))
    return outputs
