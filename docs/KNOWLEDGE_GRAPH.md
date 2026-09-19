# Analytical knowledge graph contract

Issue: #249

This document defines the analysis-side graph contract for LaclauGPT. The graph is an **optional projection** of canonical analysis results. It does not replace the canonical record, MongoDB documents, CSV/SQLite outputs, or the Phase-0/Phase-1 pipeline.

## Status and activation

- Phase 0/1 behavior is unchanged by default.
- Laclau projection is available now through `project_laclau_record()`.
- DNA and SNA schemas are implemented as dormant Phase-2 projection helpers. Their existence does not enable those analysis stages.
- RDF remains optional and lazy-loaded.
- MongoDB and ArangoDB adapters accept already configured client/database objects and add no mandatory service dependency.

Schema version: `1.0.0`.

## Common semantic contract

Every graph object has:

- stable project-scoped `id` and RDF-compatible `uri`
- `layer`: `source`, `laclau`, `dna`, `sna`, or `cross-layer`
- `assertion_kind`: `empirical`, `coded`, `model-derived`, or `graph-statistical`
- source identity
- run/provenance identity where available
- method/model metadata where available
- codebook references where available
- exact evidence IDs where available
- optional temporal validity and snapshot ID

This separation prevents source facts, discourse coding, model-derived interpretation and graph statistics from being silently collapsed into one kind of claim.

## Stable identity

Actor identity is shared across layers:

```text
{base}/{project}/actor/{stable-token}
```

The same actor ID therefore receives the same URI in Laclau, DNA and SNA projections. DNA concepts reuse the common concept namespace so they can link to Laclau signifiers without duplicating concept identity.

Source objects keep the canonical collection `source_url` as their semantic source identity.

## Laclau projection

`project_laclau_record()` maps the current canonical record to:

- source
- actors/entities
- signifiers
- nodal points
- floating signifiers
- empty-signifier candidates
- themes
- discourse formations
- discourses
- sociotechnical imaginaries
- collective subject / other
- frontier
- affect
- equivalence/difference and other articulations
- equivalence/difference chains

Relations and chains retain review state, evidence IDs, codebook refs and generation provenance.

The graph does not infer new theoretical claims. Missing relation endpoints are represented only as reference placeholders so graph integrity is preserved.

## DNA Phase-2 contract

`project_dna()` projects the existing `DiscourseStatement` interoperability object as:

```text
Actor -> Statement -> Concept
             |
             -> Source
```

Statement properties retain:

- qualifier / agreement-disagreement stance
- timestamp
- confidence
- review status
- provenance
- evidence ID

The DNA import/export path remains the existing `import_dna_rows()`, `export_dna_rows()` and DNA CSV adapters. Stable actor/concept IDs allow DNA software results to reconnect to Laclau and SNA objects.

Temporal slicing uses statement timestamps and may be performed before projection or by filtering `valid_from`.

## SNA Phase-2 contract

`SNARelation` supports:

- reply
- mention
- repost
- share
- hyperlink
- co-occurrence
- follow
- membership

Each relation records directedness, weight, timestamp, platform/source context, evidence and provenance.

`SNADerivedResult` supports:

- centrality
- components
- communities
- roles
- positions

Derived results are always `graph-statistical` assertions and require a `snapshot_id`. Window start/end values scope the result in time. Community membership is therefore a property of an analytical snapshot, never a timeless actor attribute.

## Cross-layer graph

`merge_graphs()` merges projections only when they share `project_id` and `base_uri`. Shared semantic identity is deduplicated. Conflicting edge identities fail loudly.

This supports queries such as:

- SNA communities amplifying a Laclau discourse formation
- actors connecting DNA concepts
- high-centrality actors associated with particular signifiers
- discourse/DNA/SNA changes by temporal window
- provenance path from a derived graph relation to source object and evidence

## Local / CSC Roihu

### CSV

`CSVGraphStore` writes:

- `nodes.csv`
- `edges.csv`
- `manifest.json`

The files are backend-neutral and suitable for DuckDB reads.

### SQLite

`SQLiteGraphStore` writes:

- `kg_meta`
- `kg_nodes`
- `kg_edges`

Indexes cover project/source/target/type traversal. SQLite requires no service and is the recommended persistent local graph representation for Roihu jobs.

DuckDB does not require a dedicated adapter because it can query the CSV files or SQLite export through its normal readers/extensions without changing the graph contract.

## MongoDB

`MongoGraphStore` writes canonical node/edge documents to three collections:

- `kg_nodes`
- `kg_edges`
- `kg_meta`

Indexes are created for:

- project + stable ID
- project + type
- project + source
- project + target
- project + time

The adapter intentionally accepts a pymongo Database-like object rather than constructing credentials/connections.

## ArangoDB

`ArangoGraphStore` is optional. It derives vertex and edge documents from the exact same `AnalyticalGraph` model and preserves the canonical graph `id` and RDF-compatible `uri`.

Arango `_key` values are storage keys only and are deterministic hashes of project + canonical ID. They are not semantic identifiers.

AQL may therefore traverse the native edge collection without changing application-level graph semantics.

## RDF / JSON-LD

`graph_to_rdf()` converts the common contract into RDFLib using:

- LaclauGPT namespace for project-specific graph terms
- PROV-O `prov:wasDerivedFrom` and `prov:wasGeneratedBy`
- DCTERMS identifiers

`serialize_graph_rdf()` supports the RDFLib formats including JSON-LD, Turtle and N-Quads.

The existing richer canonical-record RDF exporter remains valid. The common graph RDF export exists to guarantee parity for DNA/SNA/storage-neutral projections.

## SHACL

`schemas/knowledge-graph.shacl.ttl` validates the common graph relation minimum:

- identifier
- source
- target
- layer
- assertion kind
- directedness

The existing canonical RDF SHACL validation continues to apply to the current Laclau RDF profile.

## Backend parity rule

Backends may add physical indexes, document keys or database-specific metadata, but must not change:

- canonical `id`
- semantic `uri`
- relation source/target
- assertion kind
- temporal window
- provenance
- evidence links

The analysis API should deal in `AnalyticalGraph`, `GraphNode` and `GraphEdge`, not backend-native objects.

## Example cross-layer workflow

```python
laclau = project_laclau_record(record, project_id="AI26", run_id="laclau-run")
dna = project_dna(statements, project_id="AI26", run_id="dna-run")
sna = project_sna(relations, derived_results, project_id="AI26", run_id="sna-run")

graph = merge_graphs(laclau, dna, sna)
SQLiteGraphStore("ai26.sqlite3").write(graph)
jsonld = serialize_graph_rdf(graph, "json-ld")
```

## Migration policy

Graph schema changes must:

1. increment `KG_SCHEMA_VERSION`
2. document changed fields/semantics here
3. preserve stable semantic URIs whenever the represented entity/relation is unchanged
4. add or update round-trip tests
5. update SHACL constraints when required

No graph schema migration is allowed to silently reinterpret existing analytical assertions.
