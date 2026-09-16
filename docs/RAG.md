# Optional Graph / Vector RAG

Data Analysis implements the shared LaclauGPT semantic-memory contract through `laclaugpt_data_analysis.rag.RetrievalBackend`. Neo4j is an optional index, not the source of truth. Canonical records remain authoritative and the semantic layer can be rebuilt from them.

RAG is **off by default**. Ordinary CSV/SQLite/filesystem analysis does not import the Neo4j driver, contact Ollama for embeddings, or require a graph database.

## Retrieval modes

`none`, `vector`, `graph`, and `hybrid` are supported. All calls accept bounded `top_k`, graph depth (1–5), and portable metadata filters for dataset, country, arena, platform, language, actor and source. Neo4j/Cypher details stay behind the backend interface so the same retrieval contract can be consumed later by agents, researcher Q&A and dashboards.

Every retrieval returns an audit record containing a request ID, method, filters, selected canonical IDs, scores, graph paths, embedding model, index version, timestamp and context size. The canonical pipeline wrapper stores this under `intermediate.stage_outputs.rag_retrieval` and adds request/source IDs to prompt-context provenance.

Retrieved material is **context, never source evidence**. `run_rag_pipeline()` retrieves context only after deterministic preprocessing and frame analysis, then exposes it to the summary and discourse-synthesis stages. This avoids contaminating source description with semantic-memory results. If retrieval fails, a visible `unavailable` audit is stored and ordinary analysis continues.

After successful canonical postprocessing, the analyzed record is upserted into the semantic layer. Index failures are recorded as warnings and do not invalidate the canonical analysis result.

## Configuration

Install the optional adapter with:

```bash
python -m pip install -e '.[rag,ollama]'
```

Example local laptop configuration:

```bash
export LACLAUGPT_RAG_ENABLED=true
export LACLAUGPT_RAG_BACKEND=neo4j
export LACLAUGPT_RAG_MODE=hybrid
export LACLAUGPT_RAG_TOP_K=12
export LACLAUGPT_RAG_GRAPH_DEPTH=2
export LACLAUGPT_NEO4J_URI=bolt://127.0.0.1:7687
export LACLAUGPT_NEO4J_USER=neo4j
export LACLAUGPT_NEO4J_PASSWORD='<private>'
export LACLAUGPT_NEO4J_DATABASE=neo4j
export LACLAUGPT_EMBEDDING_MODEL='<multilingual FI/PL/EN embedding model>'
export LACLAUGPT_EMBEDDING_ENDPOINT=http://127.0.0.1:11434
```

Never put credentials or restricted-study endpoints in tracked configuration. A remote Linux server or Roihu job uses the same variables with a remote/shared `LACLAUGPT_NEO4J_URI`. Several machines can safely target the same semantic index because records and derived nodes use `MERGE`-based idempotent upserts keyed by canonical source identity / stable labels.

For graph-only retrieval, an embedding model is not required:

```bash
export LACLAUGPT_RAG_MODE=graph
```

For `vector` or `hybrid`, `LACLAUGPT_EMBEDDING_MODEL` is required. The embedding model is intentionally independent of the chat/analysis model.

## Gemma4 routing

RAG does not introduce a separate hard-coded chat model. Any optional query rewriting, context synthesis or researcher-Q&A helper should use the same deployment/profile model policy as Analysis:

- low-resource laptop / edge: `gemma4:e2b` or `gemma4:e4b`
- workstation / capable laptop: `gemma4:12b`
- GPU Linux server / Roihu: `gemma4:26b`, with `gemma4:31b` when resources permit
- `gemma4:31b-cloud` only with explicit cloud opt-in

A RAG helper may deliberately select a smaller tier than full analysis, but effective model/profile/backend must remain provenance-visible. The old `gemma3:270m` assumption from the original architecture issue is superseded by the project Gemma4 routing policy. Embeddings remain separately configured.

## Semantic projection

The current Neo4j adapter projects canonical records and derived analysis objects as `Record`, `Source`, `Entity`, `Signifier`, `Frame`, `Topic` and generic `Concept` nodes. Relations are stored with source-record provenance and explicit review/inference status. LLM-derived relations remain provisional rather than becoming graph “truth”.

Indexing uses canonical `source_url` identity and `MERGE`, so retrying the same record is idempotent. `rebuild(records)` removes only nodes marked as RAG-managed and reconstructs the index from canonical records.

The vector index itself is operational Neo4j configuration. Create/configure it for the chosen embedding dimensionality in the private deployment; the public repository deliberately does not assume one embedding model or vector dimension.

## Failure and privacy rules

- `RAG_ENABLED=false`: explicit no-op backend; normal analysis unchanged.
- Neo4j unavailable: retrieval/index status is recorded, normal analysis continues.
- No silent fallback to another retrieval service.
- No credentials, private endpoint URLs, corpus contents or target lists are emitted in failure messages.
- Shared remote indexes must obey the same project/study privacy boundary as canonical data.
- Restricted studies should use an appropriately restricted Neo4j deployment or remain local-only.

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

This is the same interface intended for future agents, chatbots, dashboard Context Explorer and human-researcher tools.
