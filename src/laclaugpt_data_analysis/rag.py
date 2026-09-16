"""Optional backend-neutral retrieval and semantic-memory layer.

Neo4j is an index/semantic layer, never the canonical source of truth.  The public
analysis pipeline talks only to ``RetrievalBackend``; Cypher and Neo4j driver types are
kept inside ``Neo4jRetrievalBackend``.  RAG failures are designed to degrade to ordinary
analysis with an explicit audit status rather than silently changing evidence sources.
"""
from __future__ import annotations

import json
import math
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .canonical import CanonicalRecord, SCHEMA_VERSION

RAG_INDEX_VERSION = "laclaugpt-rag-v1"
RAG_MODES = {"none", "vector", "graph", "hybrid"}


@dataclass(frozen=True, slots=True)
class RetrievalItem:
    """One auditable context item returned by any retrieval backend."""

    canonical_id: str
    text: str
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    graph_path: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RetrievalAudit:
    request_id: str
    method: str
    filters: dict[str, Any]
    selected_canonical_ids: list[str]
    scores: dict[str, float]
    graph_paths: dict[str, list[str]]
    embedding_model: str
    index_version: str
    timestamp: str
    context_size: int
    status: str = "ok"
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "method": self.method,
            "filters": dict(self.filters),
            "selected_canonical_ids": list(self.selected_canonical_ids),
            "scores": dict(self.scores),
            "graph_paths": {key: list(value) for key, value in self.graph_paths.items()},
            "embedding_model": self.embedding_model,
            "index_version": self.index_version,
            "timestamp": self.timestamp,
            "context_size": self.context_size,
            "status": self.status,
            "warning": self.warning,
        }


@dataclass(frozen=True, slots=True)
class RetrievalContext:
    items: list[RetrievalItem]
    audit: RetrievalAudit

    def render(self, *, max_chars: int = 16_000) -> str:
        """Render bounded context for prompts without changing item provenance."""
        chunks: list[str] = []
        used = 0
        for item in self.items:
            header = f"[RAG source={item.canonical_id}"
            if item.score is not None:
                header += f" score={item.score:.4f}"
            header += "]\n"
            chunk = header + item.text.strip() + "\n"
            remaining = max_chars - used
            if remaining <= 0:
                break
            chunks.append(chunk[:remaining])
            used += min(len(chunk), remaining)
        return "\n".join(chunks).strip()


class RetrievalBackend(Protocol):
    """Shared backend-independent contract consumed by pipeline/tools/agents."""

    def healthcheck(self) -> bool: ...

    def index_records(self, records: Sequence[CanonicalRecord]) -> int: ...

    def vector_search(
        self,
        query: str,
        filters: Mapping[str, Any] | None = None,
        *,
        top_k: int = 20,
    ) -> list[RetrievalItem]: ...

    def graph_search(
        self,
        query: str,
        filters: Mapping[str, Any] | None = None,
        *,
        top_k: int = 20,
        depth: int = 2,
    ) -> list[RetrievalItem]: ...

    def hybrid_search(
        self,
        query: str,
        filters: Mapping[str, Any] | None = None,
        *,
        top_k: int = 20,
        depth: int = 2,
    ) -> list[RetrievalItem]: ...

    def retrieve_context(
        self,
        query: str,
        filters: Mapping[str, Any] | None = None,
        *,
        top_k: int = 20,
        depth: int = 2,
        mode: str = "hybrid",
    ) -> RetrievalContext: ...

    def rebuild(self, records: Iterable[CanonicalRecord]) -> int: ...


class NullRetrievalBackend:
    """Explicit no-RAG backend, useful for callers that want one stable interface."""

    embedding_model = ""

    def healthcheck(self) -> bool:
        return True

    def index_records(self, records: Sequence[CanonicalRecord]) -> int:
        del records
        return 0

    def vector_search(self, query: str, filters=None, *, top_k: int = 20):
        del query, filters, top_k
        return []

    def graph_search(self, query: str, filters=None, *, top_k: int = 20, depth: int = 2):
        del query, filters, top_k, depth
        return []

    def hybrid_search(self, query: str, filters=None, *, top_k: int = 20, depth: int = 2):
        del query, filters, top_k, depth
        return []

    def retrieve_context(
        self, query: str, filters=None, *, top_k: int = 20, depth: int = 2, mode: str = "none"
    ) -> RetrievalContext:
        del query, top_k, depth
        return _context([], method="none", filters=filters or {}, embedding_model="", status="disabled")

    def rebuild(self, records: Iterable[CanonicalRecord]) -> int:
        del records
        return 0


class EmbeddingProvider(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OllamaEmbeddingProvider:
    """Minimal Ollama embedding client; embeddings stay separate from chat-model routing."""

    def __init__(self, *, base_url: str, model: str, timeout: float = 30.0):
        if not model.strip():
            raise ValueError("a separate embedding model is required for vector RAG")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        payload = json.dumps({"model": self.model, "input": list(texts)}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
        embeddings = data.get("embeddings") or []
        if len(embeddings) != len(texts):
            raise RuntimeError("Ollama embedding response count did not match request")
        return [[float(value) for value in row] for row in embeddings]


def record_filters(record: CanonicalRecord, *, dataset: str = "") -> dict[str, Any]:
    """Build portable metadata filters from canonical fields and Collection metadata."""
    raw = record.source.raw_metadata
    filters = {
        "dataset": dataset or raw.get("collection_id") or raw.get("study") or "",
        "country": record.source.country,
        "arena": raw.get("arena") or "",
        "platform": record.source.platform,
        "language": record.content.language or record.source.language,
        "actor": record.source.author,
        "source": record.source_url,
    }
    return {key: value for key, value in filters.items() if value not in (None, "")}


def _context(
    items: list[RetrievalItem],
    *,
    method: str,
    filters: Mapping[str, Any],
    embedding_model: str,
    status: str = "ok",
    warning: str = "",
) -> RetrievalContext:
    scores = {
        item.canonical_id: float(item.score)
        for item in items
        if item.score is not None and math.isfinite(float(item.score))
    }
    paths = {item.canonical_id: list(item.graph_path) for item in items if item.graph_path}
    audit = RetrievalAudit(
        request_id=str(uuid.uuid4()),
        method=method,
        filters=dict(filters),
        selected_canonical_ids=[item.canonical_id for item in items],
        scores=scores,
        graph_paths=paths,
        embedding_model=embedding_model,
        index_version=RAG_INDEX_VERSION,
        timestamp=datetime.now(UTC).isoformat(),
        context_size=sum(len(item.text) for item in items),
        status=status,
        warning=warning,
    )
    return RetrievalContext(items=items, audit=audit)


def failed_context(
    *, method: str, filters: Mapping[str, Any] | None, embedding_model: str, error: Exception
) -> RetrievalContext:
    """Produce a researcher-visible failure audit without leaking credentials/endpoints."""
    return _context(
        [],
        method=method,
        filters=filters or {},
        embedding_model=embedding_model,
        status="unavailable",
        warning=f"{type(error).__name__}: retrieval backend unavailable",
    )


class Neo4jRetrievalBackend:
    """Neo4j graph/vector adapter implementing the shared retrieval contract.

    The driver is injectable for offline tests.  Callers never receive driver-specific
    records or write Cypher themselves.
    """

    def __init__(
        self,
        *,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        embedding_provider: EmbeddingProvider | None = None,
        vector_index: str = "laclaugpt_record_embedding",
        driver: Any | None = None,
    ) -> None:
        if driver is None:
            try:
                from neo4j import GraphDatabase
            except ImportError as exc:  # pragma: no cover - exercised in optional installs
                raise RuntimeError("Neo4j RAG requires: pip install '.[rag]'") from exc
            driver = GraphDatabase.driver(uri, auth=(user, password))
        self.driver = driver
        self.database = database
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_provider.model if embedding_provider else ""
        self.vector_index = vector_index

    def healthcheck(self) -> bool:
        try:
            self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    @staticmethod
    def _metadata(record: CanonicalRecord) -> dict[str, Any]:
        raw = record.source.raw_metadata
        return {
            "dataset": str(raw.get("collection_id") or raw.get("study") or ""),
            "arena": str(raw.get("arena") or ""),
            "country": record.source.country,
            "platform": record.source.platform,
            "language": record.content.language or record.source.language or "",
            "actor": record.source.author,
            "created_at": record.source.created_at.isoformat() if record.source.created_at else "",
            "analysis_version": SCHEMA_VERSION,
        }

    @staticmethod
    def _record_text(record: CanonicalRecord) -> str:
        return (record.human_readable.markdown or record.human_readable.summary or record.content.text).strip()

    def index_records(self, records: Sequence[CanonicalRecord]) -> int:
        count = 0
        for record in records:
            text = self._record_text(record)
            metadata = self._metadata(record)
            embedding = None
            if self.embedding_provider and text:
                embedding = self.embedding_provider.embed([text])[0]
            params = {
                "source_url": record.source_url,
                "text": text,
                "title": record.content.title or "",
                "summary": record.human_readable.summary,
                "metadata": metadata,
                "embedding": embedding,
                "entities": [entity.label for entity in record.analysis.entities],
                "signifiers": [obj.label for obj in record.analysis.signifiers],
                "frames": [obj.label for obj in record.analysis.themes],
                "topics": [topic.label for topic in record.analysis.topics],
                "relations": [
                    {
                        "source": rel.source_ref,
                        "target": rel.target_ref,
                        "type": rel.relation_type,
                        "review_status": rel.review_status,
                    }
                    for rel in record.analysis.relations
                ],
            }
            cypher = """
            MERGE (r:Record {canonical_id: $source_url})
            SET r.text=$text, r.title=$title, r.summary=$summary, r.metadata=$metadata,
                r.analysis_version=$metadata.analysis_version, r.index_version=$index_version,
                r.embedding=$embedding
            MERGE (s:Source {canonical_id: $source_url})
            MERGE (r)-[:FROM_SOURCE]->(s)
            FOREACH (name IN $entities |
              MERGE (e:Entity {label:name}) MERGE (r)-[:MENTIONS {status:'PROVISIONAL'}]->(e))
            FOREACH (name IN $signifiers |
              MERGE (g:Signifier {label:name}) MERGE (r)-[:USES_SIGNIFIER {status:'PROVISIONAL'}]->(g))
            FOREACH (name IN $frames |
              MERGE (f:Frame {label:name}) MERGE (r)-[:USES_FRAME {status:'PROVISIONAL'}]->(f))
            FOREACH (name IN $topics |
              MERGE (t:Topic {label:name}) MERGE (r)-[:HAS_TOPIC {status:'PROVISIONAL'}]->(t))
            """
            self._run(cypher, {**params, "index_version": RAG_INDEX_VERSION})
            # Relations use a fixed generic edge so user/LLM relation labels remain data,
            # not executable Cypher. Human validation status is preserved explicitly.
            for relation in params["relations"]:
                self._run(
                    """
                    MATCH (r:Record {canonical_id:$source_url})
                    MERGE (a:Concept {label:$source})
                    MERGE (b:Concept {label:$target})
                    MERGE (a)-[rel:RELATED_TO {source_record:$source_url, relation_type:$type}]->(b)
                    SET rel.review_status=$review_status, rel.inference='analysis-output'
                    MERGE (r)-[:SUPPORTS_RELATION]->(a)
                    """,
                    {"source_url": record.source_url, **relation},
                )
            count += 1
        return count

    def _run(self, cypher: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher, dict(params))
            return [dict(row) for row in result]

    @staticmethod
    def _filter_clause(filters: Mapping[str, Any], alias: str = "r") -> tuple[str, dict[str, Any]]:
        allowed = {"dataset", "country", "arena", "platform", "language", "actor", "source"}
        clauses: list[str] = []
        params: dict[str, Any] = {}
        for key, value in filters.items():
            if key not in allowed or value in (None, ""):
                continue
            param = f"filter_{key}"
            if key == "source":
                clauses.append(f"{alias}.canonical_id = ${param}")
            else:
                clauses.append(f"{alias}.metadata.{key} = ${param}")
            params[param] = value
        return (" AND ".join(clauses), params)

    def vector_search(
        self, query: str, filters: Mapping[str, Any] | None = None, *, top_k: int = 20
    ) -> list[RetrievalItem]:
        if not self.embedding_provider:
            raise RuntimeError("vector retrieval requires a configured embedding model")
        filters = dict(filters or {})
        vector = self.embedding_provider.embed([query])[0]
        clause, params = self._filter_clause(filters)
        where = f"WHERE {clause}" if clause else ""
        rows = self._run(
            f"""
            CALL db.index.vector.queryNodes($index, $candidate_k, $embedding)
            YIELD node AS r, score
            {where}
            RETURN r.canonical_id AS canonical_id, r.text AS text, r.metadata AS metadata, score
            ORDER BY score DESC LIMIT $top_k
            """,
            {
                "index": self.vector_index,
                "candidate_k": max(top_k * 4, top_k),
                "embedding": vector,
                "top_k": max(1, top_k),
                **params,
            },
        )
        return [
            RetrievalItem(
                canonical_id=str(row.get("canonical_id") or ""),
                text=str(row.get("text") or ""),
                score=float(row["score"]) if row.get("score") is not None else None,
                metadata=dict(row.get("metadata") or {}),
            )
            for row in rows
            if row.get("canonical_id")
        ]

    def graph_search(
        self,
        query: str,
        filters: Mapping[str, Any] | None = None,
        *,
        top_k: int = 20,
        depth: int = 2,
    ) -> list[RetrievalItem]:
        filters = dict(filters or {})
        clause, params = self._filter_clause(filters)
        terms = [term.casefold() for term in query.split() if len(term) >= 3][:12]
        query_clause = "any(term IN $terms WHERE toLower(coalesce(r.text,'')) CONTAINS term)"
        where_parts = [query_clause]
        if clause:
            where_parts.append(clause)
        bounded_depth = max(1, min(int(depth), 5))
        rows = self._run(
            f"""
            MATCH (r:Record)
            WHERE {' AND '.join(where_parts)}
            OPTIONAL MATCH p=(r)-[*1..{bounded_depth}]-(neighbor)
            WITH r, [n IN nodes(p) | coalesce(n.canonical_id, n.label, labels(n)[0])] AS path
            RETURN r.canonical_id AS canonical_id, r.text AS text, r.metadata AS metadata,
                   path
            LIMIT $top_k
            """,
            {"terms": terms or [query.casefold()], "top_k": max(1, top_k), **params},
        )
        return [
            RetrievalItem(
                canonical_id=str(row.get("canonical_id") or ""),
                text=str(row.get("text") or ""),
                score=None,
                metadata=dict(row.get("metadata") or {}),
                graph_path=[str(value) for value in (row.get("path") or []) if value is not None],
            )
            for row in rows
            if row.get("canonical_id")
        ]

    def hybrid_search(
        self,
        query: str,
        filters: Mapping[str, Any] | None = None,
        *,
        top_k: int = 20,
        depth: int = 2,
    ) -> list[RetrievalItem]:
        vector = self.vector_search(query, filters, top_k=top_k)
        graph = self.graph_search(query, filters, top_k=top_k, depth=depth)
        merged: dict[str, RetrievalItem] = {}
        for item in vector + graph:
            previous = merged.get(item.canonical_id)
            if previous is None:
                merged[item.canonical_id] = item
                continue
            merged[item.canonical_id] = RetrievalItem(
                canonical_id=item.canonical_id,
                text=previous.text or item.text,
                score=max(
                    [score for score in (previous.score, item.score) if score is not None],
                    default=None,
                ),
                metadata={**item.metadata, **previous.metadata},
                graph_path=previous.graph_path or item.graph_path,
            )
        ranked = sorted(
            merged.values(),
            key=lambda item: (item.score is not None, item.score or 0.0, bool(item.graph_path)),
            reverse=True,
        )
        return ranked[: max(1, top_k)]

    def retrieve_context(
        self,
        query: str,
        filters: Mapping[str, Any] | None = None,
        *,
        top_k: int = 20,
        depth: int = 2,
        mode: str = "hybrid",
    ) -> RetrievalContext:
        normalized = mode.casefold()
        if normalized not in RAG_MODES:
            raise ValueError(f"unsupported RAG mode: {mode}")
        filters = dict(filters or {})
        if normalized == "none":
            return _context([], method="none", filters=filters, embedding_model=self.embedding_model, status="disabled")
        if normalized == "vector":
            items = self.vector_search(query, filters, top_k=top_k)
        elif normalized == "graph":
            items = self.graph_search(query, filters, top_k=top_k, depth=depth)
        else:
            items = self.hybrid_search(query, filters, top_k=top_k, depth=depth)
        return _context(items, method=normalized, filters=filters, embedding_model=self.embedding_model)

    def rebuild(self, records: Iterable[CanonicalRecord]) -> int:
        """Rebuild semantic data from canonical records; canonical storage remains authoritative."""
        self._run(
            "MATCH (n) WHERE n.index_version = $index_version DETACH DELETE n",
            {"index_version": RAG_INDEX_VERSION},
        )
        materialized = list(records)
        return self.index_records(materialized)


def backend_from_settings(settings: Any) -> RetrievalBackend:
    """Construct the configured backend without making RAG a hard dependency."""
    if not getattr(settings, "rag_enabled", False):
        return NullRetrievalBackend()
    backend = str(getattr(settings, "rag_backend", "neo4j") or "neo4j").casefold()
    if backend != "neo4j":
        raise ValueError(f"unsupported RAG backend: {backend}")
    embedding_model = str(getattr(settings, "embedding_model", "") or "")
    embedding_provider = None
    if embedding_model:
        embedding_provider = OllamaEmbeddingProvider(
            base_url=str(getattr(settings, "embedding_endpoint", "") or settings.llm_endpoint),
            model=embedding_model,
        )
    return Neo4jRetrievalBackend(
        uri=str(settings.neo4j_uri),
        user=str(settings.neo4j_user),
        password=str(settings.neo4j_password),
        database=str(settings.neo4j_database),
        embedding_provider=embedding_provider,
        vector_index=str(settings.neo4j_vector_index),
    )
