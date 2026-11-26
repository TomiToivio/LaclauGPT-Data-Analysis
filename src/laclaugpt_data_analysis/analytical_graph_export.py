"""Publish the stored AI26 analysis as an AnalyticalGraph (#578, #579).

The pipeline already produces the two things the dashboard's DNA and SNA layers need: every stored
result carries coded DNA statements, and canonical records carry the author and parent references
from which observed replies can be read. What was missing is the step that projects them into the
graph product the Visualization adapter reads (`kg_meta` / `kg_nodes` / `kg_edges`).

This module is that producer, and it deliberately does one narrow job:

* it **projects** existing objects through the repository's own ``knowledge_graph`` contract — it
  does not code anything, re-run a model, or invent a relation;
* SNA ties are only ever **observed**: a reply is a stored ``parent_source_url`` that resolves to a
  known author, a mention is an ``@handle`` in the text that matches an author in the same window.
  Co-occurrence is not a tie and is never written;
* every node and edge keeps ``source_url`` provenance, so a researcher can walk from the graph back
  to the record that justifies it.

Run it read-mostly first (``--dry-run`` prints the counts it would write), then for real. Writes are
upserts keyed by ``project_id`` + ``id``, so a second run over the same corpus is idempotent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .canonical import CanonicalRecord
from .discourse_network.models import DiscourseStatement
from .knowledge_graph import (
    AnalyticalGraph,
    MongoGraphStore,
    SNARelation,
    merge_graphs,
    project_dna,
    project_laclau_record,
    project_sna,
)

DEFAULT_PROJECT_ID = "ai26"
DEFAULT_BASE_URI = "https://data.laclaugpt.local/graph"

#: An explicit handle in the text. Deliberately narrow: a bare word that happens to equal a name is
#: not a mention, and treating it as one would manufacture ties from label similarity.
HANDLE = re.compile(r"(?<![\w@])@([A-Za-z0-9_.-]{2,64})")


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return digest


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
    return cleaned or _stable_id(value)


def actor_id(name: str) -> str:
    """A stable actor identity for an author string, so the same author is one node."""
    return f"actor:{_slug(name)}"


def stored_result(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """The canonical record a result document holds, whichever nesting the store used."""
    result = document.get("result")
    return result if isinstance(result, Mapping) else document


def statements_from_result(document: Mapping[str, Any]) -> list[DiscourseStatement]:
    """Read the coded DNA statements the pipeline already stored, and validate them.

    A statement that no longer validates against the current model is skipped rather than repaired:
    silently coercing it would put a guess into the graph.
    """
    record = stored_result(document)
    analysis = record.get("analysis") if isinstance(record.get("analysis"), Mapping) else {}
    plugins = (
        analysis.get("plugin_results")
        if isinstance(analysis.get("plugin_results"), Mapping)
        else {}
    )
    coding = (
        plugins.get("dna_statement_coding")
        if isinstance(plugins.get("dna_statement_coding"), Mapping)
        else {}
    )
    proposal = coding.get("proposal") if isinstance(coding.get("proposal"), Mapping) else {}
    statements: list[DiscourseStatement] = []
    for raw in proposal.get("statements") or ():
        if not isinstance(raw, Mapping):
            continue
        try:
            statements.append(DiscourseStatement.model_validate(dict(raw)))
        except Exception:  # noqa: BLE001 - a stale statement must not stop the export
            continue
    return statements


@dataclass(slots=True)
class SnaScan:
    relations: list[SNARelation] = field(default_factory=list)
    records: int = 0
    replies: int = 0
    mentions: int = 0
    unresolved_parents: int = 0
    parents_without_author: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "records": self.records,
            "relations": len(self.relations),
            "replies": self.replies,
            "mentions": self.mentions,
            "unresolved_parents": self.unresolved_parents,
            "parents_without_author": self.parents_without_author,
            "notes": list(self.notes),
        }


def sna_relations(documents: Sequence[Mapping[str, Any]]) -> SnaScan:
    """Observed communication ties: stored replies and explicit ``@handles``.

    The window is the documents passed in. A reply whose parent is outside the window is counted as
    unresolved and **not** written, because the graph cannot cite an actor it did not read.
    """
    scan = SnaScan()
    by_source: dict[str, Mapping[str, Any]] = {}
    authors: dict[str, str] = {}
    for document in documents:
        record = stored_result(document)
        source = record.get("source") if isinstance(record.get("source"), Mapping) else {}
        url = str(record.get("source_url") or document.get("source_url") or "")
        if not url:
            continue
        by_source[url] = record
        author = str(source.get("author") or source.get("author_fullname") or "").strip()
        if author:
            authors.setdefault(author.casefold(), author)

    seen: set[str] = set()
    for url, record in by_source.items():
        scan.records += 1
        source = record.get("source") if isinstance(record.get("source"), Mapping) else {}
        author = str(source.get("author") or source.get("author_fullname") or "").strip()
        parent = str(source.get("parent_source_url") or "").strip()
        if not author:
            # A reply with no readable author cannot produce a tie whose source actor we can name.
            # It is counted rather than dropped silently.
            if parent:
                scan.parents_without_author += 1
            continue
        platform = str(source.get("platform") or "")
        stamp = _timestamp(source.get("created_at"))

        if parent:
            parent_record = by_source.get(parent)
            parent_source = (
                parent_record.get("source")
                if isinstance(parent_record, Mapping)
                and isinstance(parent_record.get("source"), Mapping)
                else {}
            )
            target = str(
                parent_source.get("author") or parent_source.get("author_fullname") or ""
            ).strip()
            if target and target.casefold() != author.casefold():
                relation_id = f"sna:reply:{_stable_id(url, parent)}"
                if relation_id not in seen:
                    seen.add(relation_id)
                    scan.relations.append(
                        SNARelation(
                            relation_id=relation_id,
                            source_actor_id=actor_id(author),
                            target_actor_id=actor_id(target),
                            relation_type="reply",
                            source_url=url,
                            timestamp=stamp,
                            platform=platform or None,
                            weight=1.0,
                            properties={
                                "evidence": "parent_source_url",
                                "parent_source_url": parent,
                            },
                        )
                    )
                    scan.replies += 1
            else:
                scan.unresolved_parents += 1

        text = _text(record)
        if not text:
            continue
        own = author.casefold()
        for handle in {match.group(1).casefold() for match in HANDLE.finditer(text)}:
            known = authors.get(handle)
            if not known or handle == own:
                continue
            relation_id = f"sna:mention:{_stable_id(url, known)}"
            if relation_id in seen:
                continue
            seen.add(relation_id)
            scan.relations.append(
                SNARelation(
                    relation_id=relation_id,
                    source_actor_id=actor_id(author),
                    target_actor_id=actor_id(known),
                    relation_type="mention",
                    source_url=url,
                    timestamp=stamp,
                    platform=platform or None,
                    weight=1.0,
                    properties={"evidence": "@handle", "handle": known},
                )
            )
            scan.mentions += 1

    if scan.parents_without_author:
        scan.notes.append(
            f"{scan.parents_without_author} reply record(s) carry a parent link but no author, so no "
            "tie was written for them."
        )
    if scan.unresolved_parents:
        scan.notes.append(
            f"{scan.unresolved_parents} reply record(s) name a parent outside the exported window; "
            "no tie was written for them."
        )
    return scan


def _text(record: Mapping[str, Any]) -> str:
    content = record.get("content") if isinstance(record.get("content"), Mapping) else {}
    return str(content.get("text") or "")


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(slots=True)
class ExportReport:
    graph: AnalyticalGraph
    statements: int
    invalid_statements: int
    records: int
    sna: dict[str, Any]
    duplicate_statements: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        by_layer: dict[str, int] = {}
        for edge in self.graph.edges:
            by_layer[edge.layer] = by_layer.get(edge.layer, 0) + 1
        return {
            "project_id": self.graph.project_id,
            "schema_version": self.graph.schema_version,
            "nodes": len(self.graph.nodes),
            "edges": len(self.graph.edges),
            "edges_by_layer": by_layer,
            "records": self.records,
            "statements": self.statements,
            "invalid_statements": self.invalid_statements,
            "duplicate_statements": self.duplicate_statements,
            "sna": self.sna,
            "notes": self.notes,
        }


def build_graph(
    documents: Sequence[Mapping[str, Any]],
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    base_uri: str = DEFAULT_BASE_URI,
    run_id: str | None = None,
    include_laclau: bool = True,
) -> ExportReport:
    """Project records, coded statements and observed ties into one graph for a project."""
    # A statement id is stable per (source, actor, concept), and a re-analysed source produces the
    # same id with differently worded text. One id may only enter the graph once: two nodes with the
    # same identity and different content is exactly what the graph contract rejects.
    by_id: dict[str, DiscourseStatement] = {}
    invalid = 0
    duplicates = 0
    for document in documents:
        try:
            for statement in statements_from_result(document):
                if statement.statement_id in by_id:
                    duplicates += 1
                    continue
                by_id[statement.statement_id] = statement
        except Exception:  # noqa: BLE001
            invalid += 1
    statements = list(by_id.values())
    graph_parts: list[AnalyticalGraph] = []
    notes: list[str] = []

    if include_laclau:
        for document in documents:
            try:
                record = CanonicalRecord.model_validate(dict(stored_result(document)))
            except Exception:  # noqa: BLE001 - a record that no longer validates is skipped, not patched
                invalid += 1
                continue
            graph_parts.append(
                project_laclau_record(
                    record, project_id=project_id, base_uri=base_uri, run_id=run_id
                )
            )

    if statements:
        graph_parts.append(
            project_dna(statements, project_id=project_id, base_uri=base_uri, run_id=run_id)
        )
    else:
        notes.append("No coded DNA statements were found in the requested window.")

    scan = sna_relations(documents)
    if scan.relations:
        graph_parts.append(
            project_sna(scan.relations, project_id=project_id, base_uri=base_uri, run_id=run_id)
        )
    else:
        notes.append(
            "No observed SNA relations (stored replies or explicit handles) exist in the window."
        )

    if not graph_parts:
        graph_parts.append(
            AnalyticalGraph(
                project_id=project_id, base_uri=base_uri, metadata={"projection": "empty"}
            )
        )
    graph = merge_graphs(*graph_parts) if len(graph_parts) > 1 else graph_parts[0]
    graph.metadata = {
        **dict(graph.metadata),
        "producer": "laclaugpt_data_analysis.analytical_graph_export",
        "produced_at": datetime.now(UTC).isoformat(),
        "run_id": run_id or "",
        "window_records": len(documents),
        "dna_statements": len(statements),
        "sna_relations": len(scan.relations),
    }
    return ExportReport(
        graph=graph,
        statements=len(statements),
        invalid_statements=invalid,
        duplicate_statements=duplicates,
        records=len(documents),
        sna=scan.summary(),
        notes=[
            *notes,
            *(
                [
                    f"{duplicates} statement id(s) repeated across re-analysed sources; the first was kept."
                ]
                if duplicates
                else []
            ),
        ],
    )


def read_documents(
    database: Any,
    *,
    collection: str = "ai26__analysis_results",
    limit: int | None = None,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read stored results, newest last, bounded on purpose."""
    query: dict[str, Any] = {}
    if since is not None:
        query["created_at"] = {"$gte": since}
    cursor = database[collection].find(query, {"_id": 0}).sort("created_at", 1)
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)


def export(
    database: Any,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    limit: int | None = None,
    since: datetime | None = None,
    dry_run: bool = False,
    prefix: str = "kg",
    include_laclau: bool = True,
) -> dict[str, Any]:
    documents = read_documents(database, limit=limit, since=since)
    report = build_graph(documents, project_id=project_id, include_laclau=include_laclau)
    summary = report.summary()
    if dry_run:
        summary["written"] = False
        return summary
    summary["written"] = MongoGraphStore(database, prefix=prefix).write(report.graph)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish the AI26 AnalyticalGraph (DNA and SNA layers)"
    )
    parser.add_argument("--uri", default=os.environ.get("LACLAUGPT_MONGODB_URI", ""))
    parser.add_argument(
        "--database", default=os.environ.get("LACLAUGPT_MONGODB_DATABASE", "laclaugpt")
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--collection", default="ai26__analysis_results")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--since", default=None, help="ISO date; only results created at or after it"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-laclau", action="store_true", help="project DNA and SNA only")
    args = parser.parse_args(argv)
    if not args.uri:
        print("error: no MongoDB URI; set LACLAUGPT_MONGODB_URI or pass --uri", file=sys.stderr)
        return 2
    from pymongo import MongoClient

    since = _timestamp(args.since) if args.since else None
    client = MongoClient(args.uri, serverSelectionTimeoutMS=8000)
    try:
        summary = export(
            client[args.database],
            project_id=args.project,
            limit=args.limit,
            since=since,
            dry_run=args.dry_run,
            include_laclau=not args.skip_laclau,
        )
    finally:
        client.close()
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
