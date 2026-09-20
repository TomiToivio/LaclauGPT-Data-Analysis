"""MongoDB semantic-memory backend for canonical LaclauGPT analysis records.

MongoDB is used as an optional shared document, lightweight graph and vector layer.
The adapter keeps the public ``RetrievalBackend`` contract independent of Mongo query
syntax, supports native ``$vectorSearch`` when available, and degrades to bounded
client-side cosine search when the connected deployment has no vector index.
"""
from __future__ import annotations

import hashlib
import math
from collections import deque
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping, Sequence

from .canonical import CanonicalRecord, SCHEMA_VERSION
from .rag import (
    RAG_INDEX_VERSION,
    RAG_MODES,
    EmbeddingProvider,
    RetrievalContext,
    RetrievalItem,
    _context,
)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    lnorm = math.sqrt(sum(value * value for value in left))
    rnorm = math.sqrt(sum(value * value for value in right))
    return dot / (lnorm * rnorm) if lnorm and rnorm else 0.0


class MongoRetrievalBackend:
    """MongoDB implementation of the shared retrieval contract.

    ``database`` may be injected by tests. Production construction accepts a URI and
    creates a short-timeout client so ``auto`` mode can fail fast and fall back locally.
    """

    def __init__(
        self,
        *,
        uri: str | None = None,
        database_name: str = "laclaugpt",
        project_id: str = "default",
        embedding_provider: EmbeddingProvider | None = None,
        vector_index: str = "laclaugpt_record_embedding",
        database: Any | None = None,
        client: Any | None = None,
    ) -> None:
        if database is None:
            try:
                from pymongo import MongoClient
            except ImportError as exc:
                raise RuntimeError("MongoDB RAG requires: pip install '.[remote]'") from exc
            if not uri:
                raise ValueError("MongoDB RAG requires a configured MongoDB URI")
            client = client or MongoClient(uri, serverSelectionTimeoutMS=2500)
            database = client[database_name]
        self.client = client
        self.database = database
        self.project_id = project_id
        self.records = database[f"{project_id}__rag_records"]
        self.edges = database[f"{project_id}__rag_edges"]
        self.audits = database[f"{project_id}__rag_audits"]
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_provider.model if embedding_provider else ""
        self.vector_index = vector_index
        self.records.create_index("canonical_id", unique=True, name="canonical_id")
        self.records.create_index([("dataset", 1), ("arena", 1)], name="dataset_arena")
        self.edges.create_index([("source", 1), ("target", 1), ("relation_type", 1)], name="edge")

    def healthcheck(self) -> bool:
        try:
            self.database.command("ping")
            return True
        except Exception:
            return False

    @staticmethod
    def _text(record: CanonicalRecord) -> str:
        return (
            record.human_readable.markdown
            or record.human_readable.summary
            or record.content.text
        ).strip()

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
            "source": record.source_url,
            "created_at": record.source.created_at.isoformat() if record.source.created_at else "",
        }

    @staticmethod
    def _filter(filters: Mapping[str, Any] | None) -> dict[str, Any]:
        allowed = {"dataset", "country", "arena", "platform", "language", "actor", "source"}
        query: dict[str, Any] = {}
        for key, value in dict(filters or {}).items():
            if key in allowed and value not in (None, ""):
                query["canonical_id" if key == "source" else key] = value
        return query

    def native_vector_search_available(self) -> bool:
        """Detect vector-search support without requiring it for normal operation."""
        try:
            info = self.database.command({"listSearchIndexes": self.records.name})
            indexes = info.get("cursor", {}).get("firstBatch", [])
            return any(index.get("name") == self.vector_index for index in indexes)
        except Exception:
            return False

    def index_records(self, records: Sequence[CanonicalRecord]) -> int:
        now = datetime.now(UTC).isoformat()
        count = 0
        for record in records:
            text = self._text(record)
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            embedding = None
            if self.embedding_provider and text:
                embedding = self.embedding_provider.embed([text])[0]
            embedding_meta = {
                "model": self.embedding_model,
                "dimensions": len(embedding or []),
                "generated_at": now if embedding is not None else "",
                "source_text_sha256": text_hash,
                "index_version": RAG_INDEX_VERSION,
            }
            document = {
                "canonical_id": record.source_url,
                "text": text,
                "title": record.content.title or "",
                "summary": record.human_readable.summary,
                "embedding": embedding,
                "embedding_metadata": embedding_meta,
                "analysis_version": SCHEMA_VERSION,
                "rag_managed": True,
                **self._metadata(record),
                "entities": [item.label for item in record.analysis.entities],
                "signifiers": [item.label for item in record.analysis.signifiers],
                "frames": [item.label for item in record.analysis.themes],
                "imaginaries": [item.label for item in record.analysis.imaginaries],
                "topics": [item.label for item in record.analysis.topics],
            }
            self.records.update_one(
                {"canonical_id": record.source_url}, {"$set": document}, upsert=True
            )
            self.edges.delete_many({"source_record": record.source_url, "rag_managed": True})
            edges: list[dict[str, Any]] = []
            for kind, labels in (
                ("MENTIONS", document["entities"]),
                ("USES_SIGNIFIER", document["signifiers"]),
                ("USES_FRAME", document["frames"]),
                ("HAS_IMAGINARY", document["imaginaries"]),
                ("HAS_TOPIC", document["topics"]),
            ):
                for label in labels:
                    edges.append(
                        {
                            "source": record.source_url,
                            "target": f"{kind}:{label}",
                            "relation_type": kind,
                            "source_record": record.source_url,
                            "review_status": "PROVISIONAL",
                            "rag_managed": True,
                        }
                    )
            for relation in record.analysis.relations:
                edges.append(
                    {
                        "source": relation.source_ref,
                        "target": relation.target_ref,
                        "relation_type": relation.relation_type,
                        "source_record": record.source_url,
                        "review_status": relation.review_status,
                        "rag_managed": True,
                    }
                )
            if edges:
                self.edges.insert_many(edges)
            count += 1
        return count

    @staticmethod
    def _item(row: Mapping[str, Any], *, score: float | None = None, path=None) -> RetrievalItem:
        metadata = {
            key: row.get(key)
            for key in ("dataset", "country", "arena", "platform", "language", "actor", "created_at")
            if row.get(key) not in (None, "")
        }
        metadata["embedding_metadata"] = dict(row.get("embedding_metadata") or {})
        return RetrievalItem(
            canonical_id=str(row.get("canonical_id") or ""),
            text=str(row.get("text") or ""),
            score=score,
            metadata=metadata,
            graph_path=[str(value) for value in (path or [])],
        )

    def vector_search(self, query: str, filters=None, *, top_k: int = 20) -> list[RetrievalItem]:
        if not self.embedding_provider:
            raise RuntimeError("vector retrieval requires a configured embedding model")
        vector = self.embedding_provider.embed([query])[0]
        match = self._filter(filters)
        if self.native_vector_search_available():
            pipeline: list[dict[str, Any]] = [
                {
                    "$vectorSearch": {
                        "index": self.vector_index,
                        "path": "embedding",
                        "queryVector": vector,
                        "numCandidates": max(top_k * 4, top_k),
                        "limit": max(top_k * 2, top_k),
                    }
                },
            ]
            if match:
                pipeline.append({"$match": match})
            pipeline.extend(
                [
                    {"$set": {"_vector_score": {"$meta": "vectorSearchScore"}}},
                    {"$limit": max(1, top_k)},
                ]
            )
            rows = list(self.records.aggregate(pipeline))
            return [self._item(row, score=float(row.get("_vector_score", 0.0))) for row in rows]

        # Portable degradation path for Community/self-hosted deployments without
        # Atlas-style vector indexes. Bound candidate loading to avoid accidental dumps.
        query_filter = {**match, "embedding": {"$type": "array"}}
        rows = list(self.records.find(query_filter).limit(max(200, top_k * 20)))
        scored = [
            (row, _cosine(vector, [float(value) for value in row.get("embedding") or []]))
            for row in rows
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [self._item(row, score=score) for row, score in scored[: max(1, top_k)]]

    def _neighbor_records(self, canonical_id: str, *, depth: int) -> dict[str, list[str]]:
        bounded = max(1, min(int(depth), 5))
        queue = deque([(canonical_id, [canonical_id], 0)])
        seen = {canonical_id}
        found: dict[str, list[str]] = {}
        while queue:
            node, path, level = queue.popleft()
            if level >= bounded:
                continue
            for edge in self.edges.find({"$or": [{"source": node}, {"target": node}]}).limit(200):
                other = edge["target"] if edge.get("source") == node else edge.get("source")
                if not other or other in seen:
                    continue
                seen.add(str(other))
                new_path = path + [str(other)]
                queue.append((str(other), new_path, level + 1))
                if self.records.find_one({"canonical_id": other}) is not None:
                    found[str(other)] = new_path
        return found

    def graph_search(self, query: str, filters=None, *, top_k: int = 20, depth: int = 2) -> list[RetrievalItem]:
        match = self._filter(filters)
        terms = [term.casefold() for term in query.split() if len(term) >= 3][:12]
        candidates = list(self.records.find(match).limit(max(100, top_k * 10)))
        seeds = [
            row
            for row in candidates
            if not terms or any(term in str(row.get("text") or "").casefold() for term in terms)
        ][: max(1, top_k)]
        items: dict[str, RetrievalItem] = {}
        for seed in seeds:
            canonical_id = str(seed.get("canonical_id") or "")
            if canonical_id:
                items[canonical_id] = self._item(seed, path=[canonical_id])
            for neighbor, path in self._neighbor_records(canonical_id, depth=depth).items():
                row = self.records.find_one({"canonical_id": neighbor, **match})
                if row is not None:
                    items.setdefault(neighbor, self._item(row, path=path))
                if len(items) >= top_k:
                    break
        return list(items.values())[: max(1, top_k)]

    def hybrid_search(self, query: str, filters=None, *, top_k: int = 20, depth: int = 2) -> list[RetrievalItem]:
        vector = self.vector_search(query, filters, top_k=top_k)
        graph = self.graph_search(query, filters, top_k=top_k, depth=depth)
        merged: dict[str, RetrievalItem] = {item.canonical_id: item for item in vector}
        for item in graph:
            previous = merged.get(item.canonical_id)
            if previous is None:
                merged[item.canonical_id] = item
            else:
                merged[item.canonical_id] = RetrievalItem(
                    canonical_id=item.canonical_id,
                    text=previous.text or item.text,
                    score=previous.score,
                    metadata={**item.metadata, **previous.metadata},
                    graph_path=item.graph_path or previous.graph_path,
                )
        return list(merged.values())[: max(1, top_k)]

    def retrieve_context(self, query: str, filters=None, *, top_k: int = 20, depth: int = 2, mode: str = "hybrid") -> RetrievalContext:
        normalized = mode.casefold()
        if normalized not in RAG_MODES:
            raise ValueError(f"unsupported RAG mode: {mode}")
        filters = dict(filters or {})
        if normalized == "none":
            context = _context([], method="none", filters=filters, embedding_model=self.embedding_model, status="disabled")
        elif normalized == "vector":
            context = _context(self.vector_search(query, filters, top_k=top_k), method="vector", filters=filters, embedding_model=self.embedding_model)
        elif normalized == "graph":
            context = _context(self.graph_search(query, filters, top_k=top_k, depth=depth), method="graph", filters=filters, embedding_model=self.embedding_model)
        else:
            context = _context(self.hybrid_search(query, filters, top_k=top_k, depth=depth), method="hybrid", filters=filters, embedding_model=self.embedding_model)
        audit = context.audit.to_dict()
        if hasattr(self.audits, "insert_one"):
            self.audits.insert_one(audit)
        else:
            # Keep the injected lightweight collection contract used by tests
            # and offline adapters compatible without weakening production Mongo.
            self.audits.insert_many([audit])
        return context

    def rebuild(self, records: Iterable[CanonicalRecord]) -> int:
        self.records.delete_many({"rag_managed": True})
        self.edges.delete_many({"rag_managed": True})
        return self.index_records(list(records))

    def export_networkx(self, canonical_ids: Sequence[str], *, depth: int = 2):
        """Export a bounded subgraph for algorithms MongoDB should not implement."""
        try:
            import networkx as nx
        except ImportError as exc:
            raise RuntimeError("NetworkX export requires: pip install '.[analysis]'") from exc
        graph = nx.MultiDiGraph()
        seeds = [str(value) for value in canonical_ids]
        allowed = set(seeds)
        for seed in seeds:
            allowed.update(self._neighbor_records(seed, depth=depth))
        for edge in self.edges.find({"$or": [{"source": {"$in": list(allowed)}}, {"target": {"$in": list(allowed)}}]}):
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if source and target:
                graph.add_edge(
                    source,
                    target,
                    relation_type=str(edge.get("relation_type") or "RELATED_TO"),
                    source_record=str(edge.get("source_record") or ""),
                    review_status=str(edge.get("review_status") or "PROVISIONAL"),
                )
        return graph
