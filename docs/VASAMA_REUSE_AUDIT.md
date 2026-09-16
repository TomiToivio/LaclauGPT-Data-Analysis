# VASAMA-OSINT reuse audit for Data Analysis

Issue #18 audits historical `TomiToivio/vasama-osint` mechanics without importing its OSINT prompts, geopolitical classifications, private runtime settings or analytical assumptions.

## Historical window checked

GitHub history contains no commits between **2026-02-01 and 2026-04-01**, so there is no literal March 2026 snapshot to audit. The closest preceding main-line work is the **2026-01-31 shared-context/RAG series**, especially commit `c1b1ee3e2538d9d788d59c4afdf7ca13542decc4`. The older `rag` branch was also inspected at `94ec36d6b0a3137d45da0be3c747eeb31b562589`.

The audit is architectural. Historical credentials, session files, target lists and domain prompts are explicitly excluded.

## Audit table

| VASAMA path | branch/commit | capability | decision | target Analysis component | reason |
| --- | --- | --- | --- | --- | --- |
| `cron.sh`, `cron_*.{py,sh}` | `rag` / `94ec36d` | one-machine stage chain | **adapt** | `deployment.render_cron`, cron/systemd profiles | Sequential scheduled stages are useful. Reject hard-coded cwd, implicit interpreter, missing locking/checkpoints and Mongo-only assumptions. Current Analysis keeps local CSV/SQLite/filesystem first-class and uses `flock` in generated cron entries. |
| `osint_vector.py`, `osint_chroma.py` | `rag` / `94ec36d` | persistent vector memory, separate embeddings | **adapt** | `rag.py` | Persistent semantic memory and a dedicated embedding model are useful. Reject Chroma-specific pipeline coupling, hard-coded model names and unprovenanced history IDs. Current target is optional Neo4j graph/vector retrieval with a backend-neutral contract. |
| `VasamaQuery.py`, `VasamaAgent.py`, chatbot/query helpers | `rag` / `94ec36d` | bounded retrieval before synthesis | **adapt** | `RetrievalBackend`, `run_rag_pipeline` | Reuse bounded `top_k` retrieval and explicit context assembly. Reject VASAMA personas/prompts, global LlamaIndex settings and fixed Gemma3 assumptions. Current Gemma4 routing and retrieval provenance remain authoritative. |
| shared-context/RAG changes | main / `c1b1ee3` (2026-01-31) | shared context, message history, RAG citations | **adapt** | RAG audit/context envelope | Useful idea: retrieval consumers share one context layer and retain source identity. Reject geopolitical prompt text and treating conversational memory as source evidence. |
| `osint_geocode.py` | `rag` / `94ec36d` | event locations, map/timeline materialization | **adapt** | `derived_structures.py` | Keep named location, coordinates, source URL and event linkage. Reject hard-coded Mapbox token, direct DB writes, `eval()`, truthy-coordinate bugs and loss of distinction between source, inferred and geocoded location. |
| `osint_geocode.py` network loop | `rag` / `94ec36d` | generic source→target edges | **adapt** | `project_network_relations`, Neo4j semantic graph | The edge mechanics are reusable, but relation meaning must come from canonical LaclauGPT discourse analysis. No second network database is introduced. |
| `osint_report.py` + recent-report context | main historical series | previous reports as memory | **adapt** | RAG/context sources and reporting | Prior summaries can be retrieval context when explicitly configured and provenance-linked. They are not source evidence or ground truth. |
| OSINT system prompts/classifications | all historical branches | geopolitical/military interpretation | **reject** | none | Outside LaclauGPT theory/codebook scope and would contaminate the academic analysis contract. |
| committed session files / historical auth material | `rag` | runtime authentication | **reject** | none | Never copy credentials, sessions, tokens or private endpoints into the public module. |

## Implemented reusable structures

`laclaugpt_data_analysis.derived_structures` provides rebuildable, storage-neutral projections for downstream Visualization and semantic indexing:

- `LocationEntity`: named and normalized location, optional coordinates, country/region, canonical `source_url`, evidence IDs, confidence, extraction/geocoder provenance and review state.
- `TimelineEvent`: stable event ID, source, time text, actors, location references, evidence, confidence, entity/signifier references and review state.
- `NetworkRelation`: discourse/network edge with canonical source identity, relation type, evidence, review state and provenance.
- `build_visualization_projection(record)`: one export payload containing locations, events and network relations.

Direct source-provided location is represented independently from an LLM-inferred event location. Optional geocoding creates a third `origin="geocoded"` record linked back to the inferred location; it never overwrites the source/inferred observation.

No external geocoder is enabled by default. A deployment may inject a `Geocoder` implementation privately.

## Network / Neo4j compatibility

The canonical Analysis model already contains evidence-linked discourse relations and actor/entity relations. Issue #17's Neo4j RAG adapter indexes the same canonical records, entities, signifiers, topics and discourse relations. The new visualization network projection uses those same canonical IDs and relation semantics rather than inventing an OSINT graph or separate database.

This means Visualization can use `build_visualization_projection()` in local CSV/JSON workflows, while a Neo4j-enabled deployment continues to populate/query the shared semantic graph from canonical analysis results.

## Local scheduled processing

The useful VASAMA cron idea is the **small, restartable stage chain**, not its hard-coded scripts. Current Analysis already supports:

- `DeploymentProfile` local laptop/Linux-server execution,
- `render_cron()` with `flock` concurrency protection,
- `render_systemd()` for timer/service operation,
- local `data/` directories and SQLite/CSV/filesystem defaults,
- explicit optional remote MongoDB/Redis/S3/Neo4j adapters rather than requirements.

A normal local run therefore does not require MongoDB, Redis, S3 or Neo4j. Distributed and local modes operate on the same canonical record semantics.

## Security notes

The historical `rag` branch contains material that must not be copied into a public module, including session files and a hard-coded geocoding token. This audit intentionally ports no such values. Only generic mechanics and data-shape lessons are represented here.
