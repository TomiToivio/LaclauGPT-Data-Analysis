"""Explicit Phase 2 publication of existing evidence-bearing AI26 network inputs.

Two input modes, one producer:

* ``--input`` publishes an explicit JSON object with ``statements`` and ``relations`` arrays.
* ``--from-store`` reads the same typed inputs from the canonical Analysis store: coded DNA
  statements the pipeline already stored under ``plugin_results.dna_statement_coding``, and
  observed actor ties that record metadata already carries.

Neither mode calls a model, codes a source, or changes the human-owned scientific steps. Reading a
stored code is not coding it: the projection keeps the recorded qualifier, evidence span, review
state and provenance, and never infers a tie from co-occurrence, labels or similar names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .canonical import ReviewStatus
from .interoperability import DiscourseStatement, Producer
from .knowledge_graph import (
    AnalyticalGraph,
    MongoGraphStore,
    SNARelation,
    merge_graphs,
    project_dna,
    project_sna,
)

PROJECT_ID = "ai26"

#: An explicitly addressed handle in the text. Deliberately narrow: a bare name that happens to
#: equal an author is not a mention, and treating it as one would manufacture ties from labels.
HANDLE = re.compile(r"(?<![\w@])@([A-Za-z0-9_.-]{2,64})")

#: The X collector rewrites a retweet body as ``RT @handle: text``. That address is a repost rather
#: than a mention, so the graph records the distinction instead of flattening both into one type.
RETWEET_PREFIX = re.compile(r"\s*RT @([A-Za-z0-9_.-]{2,64}):")

#: A DNA statement needs an explicit qualifier, evidence and provenance reference. The values below
#: are the recorded ones; ``unknown`` stance is published as recorded and counted, never upgraded.
_STANCE_UNKNOWN = "unknown"


def _digest(*parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _timestamp(value: Any) -> datetime | None:
    """Parse a stored ISO timestamp without inventing one when it is missing."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0.0 <= number <= 1.0 else None


def _review_status(validation_status: str) -> ReviewStatus:
    """Map a stored validation label onto the canonical review vocabulary.

    ``needs_review`` is still provisional: the coder asked for a human decision, so nothing here
    promotes it. Only an explicit acceptance in the stored record could do that.
    """
    if validation_status == "accepted":
        return "ACCEPTED"
    return "PROVISIONAL"


# --------------------------------------------------------------------------------------
# Store input: coded DNA statements the pipeline already stored
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class StoredStatements:
    """What the stored coding yields, including what had to be refused or counted."""

    statements: list[DiscourseStatement] = field(default_factory=list)
    invalid: int = 0
    duplicates: int = 0
    validation: Counter[str] = field(default_factory=Counter)
    stance: Counter[str] = field(default_factory=Counter)
    prompt_versions: Counter[str] = field(default_factory=Counter)
    run_ids: Counter[str] = field(default_factory=Counter)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "statements": len(self.statements),
            "invalid": self.invalid,
            "duplicates": self.duplicates,
            "validation": dict(self.validation),
            "stance": dict(self.stance),
            "prompt_versions": sorted(self.prompt_versions),
            "run_ids": sorted(self.run_ids),
            "notes": list(self.notes),
        }


def _coding(document: Mapping[str, Any]) -> Mapping[str, Any]:
    record = _mapping(document.get("result")) or document
    plugins = _mapping(_mapping(record.get("analysis")).get("plugin_results"))
    return _mapping(plugins.get("dna_statement_coding"))


def _statement(
    raw: Mapping[str, Any], coding: Mapping[str, Any], source_url: str
) -> DiscourseStatement:
    """Validate one stored statement before it can enter a projection.

    A statement that no longer satisfies the contract is refused rather than repaired: coercing it
    would put a guess into the graph. The evidence span and the recorded model/prompt identity are
    what make the projected edge traceable back to a source and a run.
    """
    statement_id = _text(raw.get("statement_id"))
    actor_id = _text(raw.get("actor_id"))
    concept_id = _text(raw.get("concept_id"))
    if not all((statement_id, actor_id, concept_id, source_url)):
        raise ValueError("statement without stable identities or a source")
    if actor_id == concept_id:
        raise ValueError("actor and concept IDs must be distinct")
    evidence = _mapping(raw.get("evidence"))
    quote = _text(evidence.get("quote"))
    if not quote:
        raise ValueError("statement without a verbatim evidence quote")
    prompt_version = (
        _text(raw.get("prompt_version")) or _text(coding.get("prompt_version")) or "unknown"
    )
    model = _text(raw.get("model_version")) or _text(raw.get("coder_id_or_model")) or "unknown"
    metadata = _mapping(raw.get("metadata"))
    return DiscourseStatement(
        statement_id=statement_id,
        actor_id=actor_id,
        actor_label=_text(raw.get("actor_name")) or actor_id,
        concept_id=concept_id,
        concept_label=_text(raw.get("concept_label"))
        or _text(raw.get("proposition"))
        or concept_id,
        qualifier=_text(raw.get("stance")) or _STANCE_UNKNOWN,
        source_url=source_url,
        source_document_id=_text(raw.get("source_record_id")) or source_url,
        evidence_id="evidence:"
        + _digest(source_url, quote, evidence.get("start_char"), evidence.get("end_char")),
        evidence_text=quote,
        timestamp=_timestamp(raw.get("timestamp")),
        document_attributes={
            "platform": _text(raw.get("platform")),
            "coder_type": _text(raw.get("coder_type")),
            "validation_status": _text(raw.get("validation_status")),
            "abstained": raw.get("abstained") is True,
        },
        producer=Producer(type="model", id=model, version=prompt_version),
        confidence=_confidence(raw.get("confidence")),
        uncertainty=_text(metadata.get("notes")) or None,
        provenance_id="prov:" + _digest(source_url, statement_id, prompt_version, model),
        review_status=_review_status(_text(raw.get("validation_status"))),
    )


def statements_from_results(documents: Iterable[Mapping[str, Any]]) -> StoredStatements:
    """Project stored DNA coding proposals into the publication contract.

    Documents are expected in a stable order (the caller sorts by ``created_at``), because a
    re-analysed source repeats the same statement ID with differently worded text: the first one
    wins and the repetition is counted, so one identity never enters the graph twice.
    """
    stored = StoredStatements()
    by_id: set[str] = set()
    for document in documents:
        result = _mapping(document.get("result")) or document
        run_id = _text(document.get("run_id")) or _text(result.get("run_id"))
        if run_id:
            stored.run_ids[run_id] += 1
        coding = _coding(document)
        fallback_source = _text(result.get("source_url")) or _text(document.get("source_url"))
        for raw in _rows(_mapping(coding.get("proposal")).get("statements")):
            try:
                statement = _statement(
                    _mapping(raw), coding, _text(raw.get("source_url")) or fallback_source
                )
            except ValueError:
                stored.invalid += 1
                continue
            if statement.statement_id in by_id:
                stored.duplicates += 1
                continue
            by_id.add(statement.statement_id)
            stored.statements.append(statement)
            stored.stance[statement.qualifier or _STANCE_UNKNOWN] += 1
            validation = _text(_mapping(raw).get("validation_status")) or "unknown"
            stored.validation[validation] += 1
            stored.prompt_versions[_text(_mapping(raw).get("prompt_version")) or "unknown"] += 1
    if stored.duplicates:
        stored.notes.append(
            f"{stored.duplicates} repeated statement ID(s) across re-analysed sources; "
            "the first coded instance was kept."
        )
    if stored.invalid:
        stored.notes.append(
            f"{stored.invalid} stored statement(s) no longer satisfy the contract and were refused."
        )
    if stored.stance.get(_STANCE_UNKNOWN):
        stored.notes.append(
            f"{stored.stance[_STANCE_UNKNOWN]} statement(s) carry no recorded stance; they are "
            "published with qualifier 'unknown' rather than assigned a position."
        )
    return stored


# --------------------------------------------------------------------------------------
# Store input: observed actor ties that record metadata already carries
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class StoredRelations:
    """Observed ties only, plus the coverage this corpus could not provide."""

    relations: list[SNARelation] = field(default_factory=list)
    structured_mentions: int = 0
    text_mentions: int = 0
    reposts: int = 0
    unresolved_handles: int = 0
    thread_pointers: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "relations": len(self.relations),
            "structured_mentions": self.structured_mentions,
            "text_mentions": self.text_mentions,
            "reposts": self.reposts,
            "unresolved_handles": self.unresolved_handles,
            "thread_pointers": self.thread_pointers,
            "notes": list(self.notes),
        }


def _actor_id(platform: str, handle: str) -> str:
    """A platform-scoped actor identity.

    The same handle on two platforms is two different actors, so the platform is part of the ID. A
    display label is never part of an identity, and no cross-platform merge is attempted.
    """
    return f"actor:{platform}:{handle.strip().casefold()}"


def relations_from_records(
    records: Iterable[Mapping[str, Any]], *, project_id: str = PROJECT_ID
) -> StoredRelations:
    """Read observed actor ties from record metadata.

    A tie exists only where a source explicitly addresses another actor: a structured ``mentions``
    entry, an addressed ``@handle`` in the text, or a retweet prefix. A stored ``parent_document_id``
    is *not* used as a reply edge: for X it is the conversation root of a reply (the immediate
    parent is not stored), and for web captures it is the post that linked to the page. Neither is
    a reply between the two authors, and writing one would invent a tie.
    """
    found = StoredRelations()
    observed = list(records)
    authors: dict[tuple[str, str], str] = {}
    for record in observed:
        source = _mapping(record.get("source"))
        platform = _text(source.get("platform"))
        author = _text(source.get("author")) or _text(source.get("author_fullname"))
        if platform and author:
            authors.setdefault((platform, author.casefold()), author)

    seen: set[str] = set()
    for record in observed:
        source = _mapping(record.get("source"))
        platform = _text(source.get("platform"))
        author = _text(source.get("author")) or _text(source.get("author_fullname"))
        source_url = _text(record.get("source_url"))
        if not (platform and author and source_url):
            if _text(_mapping(source.get("raw_metadata")).get("parent_document_id")):
                found.thread_pointers += 1
            continue
        if _text(_mapping(source.get("raw_metadata")).get("parent_document_id")):
            found.thread_pointers += 1
        own = author.casefold()
        text = _text(_mapping(record.get("content")).get("text"))
        retweeted = RETWEET_PREFIX.match(text)
        retweeted_handle = retweeted.group(1).casefold() if retweeted else ""
        structured = [
            handle
            for handle in _mapping(source.get("raw_metadata")).get("mentions") or []
            if isinstance(handle, str) and handle.strip()
        ]
        candidates = [(handle, "raw_metadata.mentions") for handle in structured]
        if not structured:
            candidates = [(match.group(1), "@handle") for match in HANDLE.finditer(text)]
        for handle, basis in candidates:
            key = handle.strip().casefold()
            if key == own:
                continue
            target = authors.get((platform, key))
            if not target:
                found.unresolved_handles += 1
                continue
            kind = "repost" if key == retweeted_handle else "mention"
            relation_id = f"sna:{kind}:{_digest(source_url, platform, key)}"
            if relation_id in seen:
                continue
            seen.add(relation_id)
            found.relations.append(
                SNARelation(
                    relation_id=relation_id,
                    source_actor_id=_actor_id(platform, author),
                    target_actor_id=_actor_id(platform, target),
                    relation_type=kind,
                    source_url=source_url,
                    timestamp=_timestamp(source.get("created_at")),
                    platform=platform,
                    weight=1.0,
                    evidence_ids=["evidence:" + _digest(source_url, kind, key)],
                    provenance_id="prov:" + _digest(source_url, relation_id),
                    properties={"evidence": basis, "handle": target, "project_id": project_id},
                )
            )
            if kind == "repost":
                found.reposts += 1
            elif basis == "raw_metadata.mentions":
                found.structured_mentions += 1
            else:
                found.text_mentions += 1
    if found.thread_pointers:
        found.notes.append(
            f"{found.thread_pointers} record(s) carry a parent_document_id; that field is a "
            "conversation root or discovery link, not an immediate reply target, so no reply tie "
            "was written for them."
        )
    if found.unresolved_handles:
        found.notes.append(
            f"{found.unresolved_handles} addressed handle(s) did not resolve to an author inside "
            "this corpus; no tie was written for them."
        )
    return found


# --------------------------------------------------------------------------------------
# Projection, publication and CLI
# --------------------------------------------------------------------------------------


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


def publish_mongo(graph: AnalyticalGraph, database: Any, *, replace_snapshot: bool = False) -> dict:
    """Idempotent initial/same-snapshot publish; refuse stale mixed generations.

    ``replace_snapshot`` is the operator's explicit decision to replace a *different* existing
    graph. The store only upserts, so the previous projection must be removed first or its nodes
    and edges would survive into the new snapshot. Nothing is removed unless that flag is given.
    """
    digest = hashlib.sha256(graph.model_dump_json().encode()).hexdigest()
    current = database["kg_meta"].find_one({"project_id": PROJECT_ID})
    replaced: dict[str, int] = {}
    if current and _mapping(current.get("metadata")).get("snapshot_sha256") != digest:
        if not replace_snapshot:
            raise ValueError(
                "Different existing graph: coordinate snapshot replacement with consumer"
            )
        for collection in ("kg_nodes", "kg_edges", "kg_meta"):
            replaced[collection] = (
                database[collection].delete_many({"project_id": PROJECT_ID}).deleted_count
            )
    if database["kg_meta"].find_one({"project_id": "AI26"}):
        raise ValueError("Conflicting uppercase AI26 graph already exists")
    # Refuse orphan rows from an unrelated or interrupted publication.
    for collection, elements in (("kg_nodes", graph.nodes), ("kg_edges", graph.edges)):
        expected = {element.id for element in elements}
        actual = {
            row["id"] for row in database[collection].find({"project_id": PROJECT_ID}, {"id": 1})
        }
        if actual - expected:
            raise ValueError("Existing graph contains stale IDs; no rows removed")
    payload = graph.model_copy(deep=True)
    payload.metadata["snapshot_sha256"] = digest
    payload.metadata["nodes"] = len(graph.nodes)
    payload.metadata["edges"] = len(graph.edges)
    result = MongoGraphStore(database).write(payload)
    return {**result, "replaced": replaced}


def read_collection(database: Any, collection: str, *, sort_field: str) -> list[Mapping[str, Any]]:
    """Read a whole collection in a stable order.

    The store has no portable time field: analysis results carry an epoch float in ``created_at``
    while records only carry an RFC-2822 string under ``source.created_at``. Rather than pretend a
    common time filter exists, the snapshot is the whole store and the metadata reports its counts.
    """
    return list(database[collection].find({}, {"_id": 0}).sort(sort_field, 1))


def store_inputs(
    documents: Iterable[Mapping[str, Any]],
    records: Iterable[Mapping[str, Any]],
    *,
    project_id: str = PROJECT_ID,
) -> tuple[list[DiscourseStatement], list[SNARelation], dict[str, Any]]:
    """The typed inputs and the honest report of what the store did and did not provide."""
    stored = statements_from_results(documents)
    observed = relations_from_records(records, project_id=project_id)
    return (
        stored.statements,
        observed.relations,
        {
            "statements": stored.summary(),
            "relations": observed.summary(),
            "notes": [*stored.notes, *observed.notes],
        },
    )


def _single(values: Iterable[str], name: str, override: str | None) -> str:
    """Derive one provenance identifier, and refuse to guess when the store disagrees."""
    if override and override.strip():
        return override.strip()
    cleaned = sorted({value for value in values if value and value != "unknown"})
    if len(cleaned) == 1:
        return cleaned[0]
    raise ValueError(f"cannot derive a single {name} from the store; pass it explicitly")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--input", type=Path, help="private JSON with statements and relations arrays"
    )
    source.add_argument(
        "--from-store",
        action="store_true",
        help="read coded statements and observed ties from the configured store",
    )
    parser.add_argument("--output", type=Path, required=True, help="private JSON graph output")
    parser.add_argument("--collection", default="ai26__analysis_results")
    parser.add_argument("--records", default="ai26__records")
    parser.add_argument("--run-id")
    parser.add_argument("--codebook-version")
    parser.add_argument("--prompt-version")
    parser.add_argument("--dry-run", action="store_true", help="report counts without writing")
    parser.add_argument(
        "--mongo", action="store_true", help="explicitly publish to configured private DB"
    )
    parser.add_argument(
        "--replace-snapshot",
        action="store_true",
        help="replace a different existing graph instead of refusing it",
    )
    args = parser.parse_args(argv)

    report: dict[str, Any] = {}
    if args.from_store:
        from pymongo import MongoClient

        uri = os.environ["LACLAUGPT_MONGODB_URI"]
        database = os.environ["LACLAUGPT_MONGODB_DATABASE"]
        with MongoClient(uri) as client:
            db = client[database]
            documents = read_collection(db, args.collection, sort_field="created_at")
            records = read_collection(db, args.records, sort_field="source_url")
            statements, relations, report = store_inputs(documents, records)
            run_id = _single((_text(d.get("run_id")) for d in documents), "run ID", args.run_id)
            prompt_versions = report["statements"]["prompt_versions"]
            prompt_version = _single(prompt_versions, "prompt version", args.prompt_version)
            codebook_version = (args.codebook_version or "").strip() or "not-recorded"
            graph = build_graph(
                statements,
                relations,
                run_id=run_id,
                codebook_version=codebook_version,
                prompt_version=prompt_version,
            )
            graph.metadata.update(
                {
                    "producer": "laclaugpt_data_analysis.ai26_graph_publish",
                    "input_mode": "store",
                    "produced_at": datetime.now(UTC).isoformat(),
                    "window": {
                        "analysis_results": len(documents),
                        "records": len(records),
                        "collection": args.collection,
                        "records_collection": args.records,
                    },
                    "statement_report": report["statements"],
                    "relation_report": report["relations"],
                    "coverage_notes": report["notes"],
                }
            )
            if not args.dry_run:
                write_json(graph, args.output)
            if args.mongo and not args.dry_run:
                report["published"] = publish_mongo(
                    graph, db, replace_snapshot=args.replace_snapshot
                )
    else:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        graph = build_graph(
            [DiscourseStatement.model_validate(s) for s in data["statements"]],
            [SNARelation.model_validate(r) for r in data["relations"]],
            run_id=args.run_id or "",
            codebook_version=args.codebook_version or "",
            prompt_version=args.prompt_version or "",
        )
        write_json(graph, args.output)
        if args.mongo:
            from pymongo import MongoClient

            uri = os.environ["LACLAUGPT_MONGODB_URI"]
            database = os.environ["LACLAUGPT_MONGODB_DATABASE"]
            with MongoClient(uri) as client:
                report["published"] = publish_mongo(
                    graph, client[database], replace_snapshot=args.replace_snapshot
                )
    report.update(
        {
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "edges_by_layer": dict(Counter(edge.layer for edge in graph.edges)),
            "metadata": graph.metadata,
        }
    )
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
