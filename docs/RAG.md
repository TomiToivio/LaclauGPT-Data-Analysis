# MongoDB-first graph / vector RAG

Data Analysis exposes semantic memory through `laclaugpt_data_analysis.rag.RetrievalBackend`. MongoDB is now the preferred shared backend when configured because the same deployment can hold canonical/enriched documents, portable edge records, embeddings and retrieval audits. CSV/local files remain the minimum contract, and Neo4j remains an optional specialized graph backend.

RAG is **off by default**. Local CSV analysis does not require MongoDB, Redis, S3, Neo4j or an embedding service.

## Storage modes

`LACLAUGPT_STORAGE_BACKEND` accepts:

- `auto`: use MongoDB only when a MongoDB URI was explicitly configured and the server is reachable; otherwise use local CSV.
- `mongodb`: require MongoDB and fail clearly when unavailable.
- `csv`: never contact MongoDB.
- `sqlite`: retain the existing local SQLite option.

Example minimum laptop mode:

```bash
export LACLAUGPT_STORAGE_BACKEND=csv
export LACLAUGPT_DATA_DIR=./data
```

Shared mode:

```bash
export LACLAUGPT_STORAGE_BACKEND=mongodb
export LACLAUGPT_MONGODB_URI='mongodb+srv://<private>'
export LACLAUGPT_MONGO_DATABASE=laclaugpt
```

`MongoStore.write()` performs source-identity upserts instead of deleting and replacing the project collection, so analysis enrichments do not erase fields owned by Collection.

## Retrieval modes

`none`, `vector`, `graph`, and `hybrid` are supported. Calls accept bounded `top_k`, graph depth (1–5), and metadata filters for dataset, country, arena, platform, language, actor and canonical source.

Every retrieval returns an audit record with request ID, method, filters, selected canonical IDs, scores, graph paths, embedding model/index version, timestamp and context size. The MongoDB adapter also persists these audits for research reproducibility.

Retrieved material is context, never source evidence. Canonical source IDs and source provenance remain visible throughout analysis.

## MongoDB semantic projection

`MongoRetrievalBackend` stores one semantic record per canonical `source_url` plus explicit edge-like documents. Current projections cover entities, signifiers, frames, imaginaries, topics and evidence-linked analysis relations. This representation is deliberately simple and exportable rather than pretending MongoDB is a full graph engine.

Embeddings persist:

- embedding vector;
- model name;
- dimensionality;
- generation timestamp;
- source-text SHA-256;
- RAG index version.

The backend checks for a configured native MongoDB vector-search index. When native `$vectorSearch` is unavailable, retrieval gracefully uses a bounded client-side cosine search instead of making vector support a deployment requirement.

Graph traversal is bounded. For specialized algorithms such as centrality, community detection or shortest paths, `MongoRetrievalBackend.export_networkx()` exports a bounded subgraph to NetworkX.

## Configuration

Install remote support plus an embedding runtime when desired:

```bash
python -m pip install -e '.[remote,ollama,analysis]'
```

MongoDB RAG example:

```bash
export LACLAUGPT_RAG_ENABLED=true
export LACLAUGPT_RAG_BACKEND=mongodb
export LACLAUGPT_RAG_MODE=hybrid
export LACLAUGPT_RAG_TOP_K=12
export LACLAUGPT_RAG_GRAPH_DEPTH=2
export LACLAUGPT_MONGODB_URI='mongodb+srv://<private>'
export LACLAUGPT_MONGO_DATABASE=laclaugpt
export LACLAUGPT_MONGO_VECTOR_INDEX=laclaugpt_record_embedding
export LACLAUGPT_EMBEDDING_MODEL='<multilingual FI/PL/EN embedding model>'
export LACLAUGPT_EMBEDDING_ENDPOINT=http://127.0.0.1:11434
```

For graph-only retrieval, no embedding model is required. For `vector` or `hybrid`, the embedding model is intentionally configured separately from the LLM used for analysis.

Neo4j remains available with `LACLAUGPT_RAG_BACKEND=neo4j` and the existing `LACLAUGPT_NEO4J_*` settings.

## Practical deployment shapes

```text
Laptop / minimum:
CSV -> Data Analysis -> CSV/local outputs

Remote/shared:
MongoDB -> Data Analysis
            |- enrichments
            |- graph relations
            |- embeddings / optional native vector index
            `- auditable RAG context

Degraded/auto:
configured MongoDB unavailable -> CSV/local fallback
```

No remote endpoint is auto-discovered. Credentials, hostnames and restricted research data must stay in private runtime configuration. Use authenticated TLS MongoDB deployments for shared/remote work.

## Programmatic use

```python
from laclaugpt_data_analysis.rag import backend_from_settings

rag = backend_from_settings(settings)
context = rag.retrieve_context(
    "AI regulation and democratic control",
    filters={"dataset": "AI26", "country": "FI", "arena": "parliamentary"},
    top_k=12,
    depth=2,
    mode="hybrid",
)
print(context.audit.to_dict())
```

The retrieval interface stays backend-independent so dashboards, agents, researcher Q&A and future dedicated graph/vector stores do not need MongoDB query syntax.