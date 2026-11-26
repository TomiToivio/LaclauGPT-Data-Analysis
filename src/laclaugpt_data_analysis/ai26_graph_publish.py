"""Explicit Phase 2 publication of existing evidence-bearing AI26 network inputs.

No model calls, source coding, or changes to the human-owned scientific steps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from .interoperability import DiscourseStatement
from .knowledge_graph import (
    AnalyticalGraph,
    MongoGraphStore,
    SNARelation,
    merge_graphs,
    project_dna,
    project_sna,
)


def build_graph(
    statements: list[DiscourseStatement],
    relations: list[SNARelation],
    *,
    run_id: str,
    codebook_version: str,
    prompt_version: str,
) -> AnalyticalGraph:
    """Reject incomplete provenance and publish only explicit typed inputs."""
    if not all(value.strip() for value in (run_id, codebook_version, prompt_version)):
        raise ValueError("Run, codebook and prompt versions are required")
    if not statements and not relations:
        raise ValueError("No network inputs: do not publish an empty success")
    if len({s.statement_id for s in statements}) != len(statements):
        raise ValueError("Duplicate DNA statement IDs")
    if len({r.relation_id for r in relations}) != len(relations):
        raise ValueError("Duplicate SNA relation IDs")
    for s in statements:
        if s.review_status in {"REJECTED", "SUPERSEDED"}:
            raise ValueError("Rejected or superseded statement is not publishable")
        if not all(
            (
                s.actor_id.strip(),
                s.concept_id.strip(),
                s.statement_id.strip(),
                (s.qualifier or "").strip(),
                (s.evidence_id or "").strip(),
                (s.provenance_id or "").strip(),
            )
        ):
            raise ValueError("DNA requires explicit identities, stance and evidence provenance")
        if s.actor_id == s.concept_id:
            raise ValueError("Actor and concept IDs must be distinct")
    for r in relations:
        if not all(
            (
                r.relation_id.strip(),
                r.source_actor_id.strip(),
                r.target_actor_id.strip(),
                r.source_url.strip(),
                (r.provenance_id or "").strip(),
            )
        ) or not any(value.strip() for value in r.evidence_ids):
            raise ValueError("SNA requires observed identities and source evidence provenance")
        if r.relation_type == "co-occurrence":
            raise ValueError("Co-occurrence is not an observed social tie")
    # The existing projector deduplicates by raw ID; reject role collisions before it can.
    actors = {s.actor_id for s in statements} | {
        actor for r in relations for actor in (r.source_actor_id, r.target_actor_id)
    }
    concepts = {s.concept_id for s in statements}
    statement_ids = {s.statement_id for s in statements}
    sources = {f"source:{s.source_url}" for s in statements} | {
        f"source:{r.source_url}" for r in relations
    }
    roles = (actors, concepts, statement_ids, sources)
    if any(left & right for i, left in enumerate(roles) for right in roles[i + 1 :]):
        raise ValueError("Conflicting typed identities in graph inputs")
    dna = project_dna(
        sorted(statements, key=lambda s: s.statement_id), project_id="ai26", run_id=run_id
    )
    sna = project_sna(
        sorted(relations, key=lambda r: r.relation_id), project_id="ai26", run_id=run_id
    )
    review = {s.statement_id: s.review_status for s in statements}
    for edge in dna.edges:
        statement_id = edge.id.rsplit(":", 1)[0]
        edge.properties["review_status"] = review[statement_id]
    graph = merge_graphs(dna, sna)
    for element in [*graph.nodes, *graph.edges]:
        element.provenance.codebook_refs = [codebook_version]
    graph.metadata.update(
        {
            "run_id": run_id,
            "codebook_version": codebook_version,
            "prompt_version": prompt_version,
            "experimental": True,
            "dna_statements": len(statements),
            "sna_relations": len(relations),
        }
    )
    graph.validate_references()
    return graph


def write_json(graph: AnalyticalGraph, path: Path) -> None:
    """Atomically write the private uploadable graph; never expose a partial file."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(graph.model_dump_json(indent=2) + "\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def publish_mongo(graph: AnalyticalGraph, database) -> dict:
    """Idempotent initial/same-snapshot publish; refuse stale mixed generations."""
    digest = hashlib.sha256(graph.model_dump_json().encode()).hexdigest()
    current = database["kg_meta"].find_one({"project_id": "ai26"})
    if current and current.get("metadata", {}).get("snapshot_sha256") != digest:
        raise ValueError("Different existing graph: coordinate snapshot replacement with consumer")
    if database["kg_meta"].find_one({"project_id": "AI26"}):
        raise ValueError("Conflicting uppercase AI26 graph already exists")
    # Refuse orphan rows from an unrelated or interrupted publication.
    for collection, elements in (("kg_nodes", graph.nodes), ("kg_edges", graph.edges)):
        expected = {element.id for element in elements}
        actual = {row["id"] for row in database[collection].find({"project_id": "ai26"}, {"id": 1})}
        if actual - expected:
            raise ValueError("Existing graph contains stale IDs; no rows removed")
    payload = graph.model_copy(deep=True)
    payload.metadata["snapshot_sha256"] = digest
    payload.metadata["nodes"] = len(graph.nodes)
    payload.metadata["edges"] = len(graph.edges)
    return MongoGraphStore(database).write(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="private JSON with statements and relations arrays",
    )
    parser.add_argument("--output", type=Path, required=True, help="private JSON graph output")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--codebook-version", required=True)
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument(
        "--mongo", action="store_true", help="explicitly publish to configured private DB"
    )
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    statements = data.get("statements", [])
    if "records" in data:
        from .ai26_dna_graph_input import convert_coded_record

        for record in data["records"]:
            statements.extend(convert_coded_record(record, data["identities"]))
    graph = build_graph(
        [DiscourseStatement.model_validate(s) for s in statements],
        [SNARelation.model_validate(r) for r in data["relations"]],
        run_id=args.run_id,
        codebook_version=args.codebook_version,
        prompt_version=args.prompt_version,
    )
    write_json(graph, args.output)
    if args.mongo:
        from pymongo import MongoClient

        uri = os.environ["LACLAUGPT_MONGODB_URI"]
        database = os.environ["LACLAUGPT_MONGODB_DATABASE"]
        with MongoClient(uri) as client:
            publish_mongo(graph, client[database])
    print(json.dumps({"nodes": len(graph.nodes), "edges": len(graph.edges), **graph.metadata}))


if __name__ == "__main__":
    main()
