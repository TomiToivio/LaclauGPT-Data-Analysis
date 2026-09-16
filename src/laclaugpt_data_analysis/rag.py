"""Optional backend-neutral retrieval and semantic-memory layer.

Neo4j is an index/semantic layer, never the canonical source of truth. The public
analysis pipeline talks only to ``RetrievalBackend``; Cypher and Neo4j driver types stay
inside ``Neo4jRetrievalBackend``. RAG failures degrade to ordinary analysis with an
explicit audit status rather than silently switching evidence sources.
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
    """Shared contract for pipelines, agents, chatbots and researcher interfaces."""

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
        del query, top_k, depth, mode
        return _context(
            [], method="none", filters=filters or {}, embedding_model="", status="disabled"
        )

    def rebuild(self, records: Iterable[CanonicalRecord]) -> int:
        del records
        return 0


class EmbeddingProvider(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OllamaEmbeddingProvider:
    """Small Ollama embedding client, deliberately separate from chat-model routing."""

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
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        embeddings = data.get("embeddings") or []
        if len(embeddings) != len(texts):
            raise RuntimeError("Ollama embedding response count did not match request")
        return [[float(value) for value in row] for row in embeddings]


def record_filters(record: CanonicalRecord, *, dataset: str = "") -> dict[str, Any]:
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
    return _context(
        [],
        method=method,
        filters=filters or {},
        embedding_model=embedding_model,
        status="unavailable",
        warning=f"{type(error).__name__}: retrieval backend unavailable",
    )


class Neo4jRetrievalBackend:
    """Neo4j adapter. Driver injection keeps normal CI offline and deterministic."""

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
            except ImportError as exc:
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
    def _metadata(record: CanonicalRecord) -> dict[str, str]:
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
        return (
            record.human_readable.markdown
            or record.human_readable.summary
            or record.content.text
        ).strip()

    def _run(self, cypher: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher, dict(params))
            return [dict(row) for row in result]

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
                "embedding": embedding,
                **metadata,
                "index_version": RAG_INDEX_VERSION,
                "entities": [entity.label for entity in record.analysis.entities],
                "signifiers": [obj.label for obj in record.analysis.signifiers],
                "frames": [obj.label for obj in record.analysis.themes],
                "topics": [topic.label for topic in record.analysis.topics],
            }
            self._run(
                """
                MERGE (r:Record {canonical_id:$source_url})
                SET r.text=$text, r.title=$title, r.summary=$summary, r.embedding=$embedding,
                    r.dataset=$dataset, r.arena=$arena, r.country=$country,
                    r.platform=$platform, r.language=$language, r.actor=$actor,
                    r.created_at=$created_at, r.analysis_version=$analysis_version,
                    r.index_version=$index_version, r.rag_managed=true
                MERGE (s:Source {canonical_id:$source_url}) SET s.rag_managed=true
                MERGE (r)-[:FROM_SOURCE]->(s)
                FOREACH (name IN $entities |
                  MERGE (e:Entity {label:name}) SET e.rag_managed=true
                  MERGE (r)-[:MENTIONS {status:'PROVISIONAL'}]->(e))
                FOREACH (name IN $signifiers |
                  MERGE (g:Signifier {label:name}) SET g.rag_managed=true
                  MERGE (r)-[:USES_SIGNIFIER {status:'PROVISIONAL'}]->(g))
                FOREACH (name IN $frames |
                  MERGE (f:Frame {label:name}) SET f.rag_managed=true
                  MERGE (r)-[:USES_FRAME {status:'PROVISIONAL'}]->(f))
                FOREACH (name IN $topics |
                  MERGE (t:Topic {label:name}) SET t.rag_managed=true
                  MERGE (r)-[:HAS_TOPIC {status:'PROVISIONAL'}]->(t))
                """,
                params,
            )
            for relation in record.analysis.relations:
                self._run(
                    """
                    MATCH (r:Record {canonical_id:$source_url})
                    MERGE (a:Concept {label:$source}) SET a.rag_managed=true
                    MERGE (b:Concept {label:$target}) SET b.rag_managed=true
                    MERGE (a)-[rel:RELATED_TO {
                      source_record:$source_url, relation_type:$relation_type
                    }]->(b)
                    SET rel.review_status=$review_status, rel.inference='analysis-output'
                    MERGE (r)-[:SUPPORTS_RELATION]->(a)
                    """,
                    {
                        "source_url": record.source_url,
                        "source": relation.source_ref,
                        "target": relation.target_ref,
                        "relation_type": relation.relation_type,
                        "review_status": relation.review_status,
                    },
                )
            count += 1
        return count

    @staticmethod
    def _filter_clause(
        filters: Mapping[str, Any], alias: str = "r"
    ) -> tuple[str, dict[str, Any]]:
        allowed = {"dataset", "country", "arena", "platform", "language", "actor", "source"}
        clauses: list[str] = []
        params: dict[str, Any] = {}
        for key, value in filters.items():
            if key not in allowed or value in (None, ""):
                continue
            param = f"filter_{key}"
            prop = "canonical_id" if key == "source" else key
            clauses.append(f"{alias}.{prop} = ${param}")
            params[param] = value
        return " AND ".join(clauses), params

    @staticmethod
    def _metadata_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: row.get(key)
            for key in ("dataset", "country", "arena", "platform", "language", "actor", "created_at")
            if row.get(key) not in (None, "")
        }

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
            RETURN r.canonical_id AS canonical_id, r.text AS text, score,
                   r.dataset AS dataset, r.country AS country, r.arena AS arena,
                   r.platform AS platform, r.language AS language, r.actor AS actor,
                   r.created_at AS created_at
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
                metadata=self._metadata_from_row(row),
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
        where_parts = ["any(term IN $terms WHERE toLower(coalesce(r.text,'')) CONTAINS term)"]
        if clause:
            where_parts.append(clause)
        bounded_depth = max(1, min(int(depth), 5))
        rows = self._run(
            f"""
            MATCH (r:Record)
            WHERE {' AND '.join(where_parts)}
            OPTIONAL MATCH p=(r)-[*1..{bounded_depth}]-(neighbor)
            RETURN r.canonical_id AS canonical_id, r.text AS text,
                   [n IN nodes(p) | coalesce(n.canonical_id, n.label, labels(n)[0])] AS path,
                   r.dataset AS dataset, r.country AS country, r.arena AS arena,
                   r.platform AS platform, r.language AS language, r.actor AS actor,
                   r.created_at AS created_at
            LIMIT $top_k
            """,
            {"terms": terms or [query.casefold()], "top_k": max(1, top_k), **params},
        )
        seen: set[str] = set()
        items: list[RetrievalItem] = []
        for row in rows:
            canonical_id = str(row.get("canonical_id") or "")
            if not canonical_id or canonical_id in seen:
                continue
            seen.add(canonical_id)
            items.append(
                RetrievalItem(
                    canonical_id=canonical_id,
                    text=str(row.get("text") or ""),
                    metadata=self._metadata_from_row(row),
                    graph_path=[str(value) for value in (row.get("path") or []) if value is not None],
                )
            )
        return items

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
            scores = [score for score in (previous.score, item.score) if score is not None]
            merged[item.canonical_id] = RetrievalItem(
                canonical_id=item.canonical_id,
                text=previous.text or item.text,
                score=max(scores) if scores else None,
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
            return _context(
                [],
                method="none",
                filters=filters,
                embedding_model=self.embedding_model,
                status="disabled",
            )
        if normalized == "vector":
            items = self.vector_search(query, filters, top_k=top_k)
        elif normalized == "graph":
            items = self.graph_search(query, filters, top_k=top_k, depth=depth)
        else:
            items = self.hybrid_search(query, filters, top_k=top_k, depth=depth)
        return _context(
            items,
            method=normalized,
            filters=filters,
            embedding_model=self.embedding_model,
        )

    def rebuild(self, records: Iterable[CanonicalRecord]) -> int:
        self._run("MATCH (n) WHERE n.rag_managed = true DETACH DELETE n", {})
        materialized = list(records)
        return self.index_records(materialized)


def backend_from_settings(settings: Any) -> RetrievalBackend:
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
