# RDF / Linked Data interoperability

This module implements the Data Analysis responsibilities of the meta-repository RDF application profile (`TomiToivio/LaclauGPT/docs/RDF_APPLICATION_PROFILE.md`). The canonical `CanonicalRecord` remains authoritative. RDF is an optional semantic projection and is disabled unless `analysis.rdf.enabled: true`.

## Configuration

```yaml
analysis:
  rdf:
    enabled: false
    required: false
    base_uri: https://data.example/laclaugpt
    formats: [json-ld, turtle, nquads]
    store:
      backend: file
      path: null
    validation:
      shacl: true
      shapes_path: null
    graphrag:
      enabled: false
      max_nodes: 40
      max_edges: 80
```

Omitting `analysis.rdf` is identical to `enabled: false`. Machine settings may provide endpoints and paths but must not silently enable RDF. `required: false` isolates materialization/validation/store failures in `analysis.plugin_failures.rdf`; `required: true` raises the failure.

RDFLib and PySHACL are optional dependencies: install `.[rdf]`. The disabled path never imports them.

## Mapping

The implementation follows the parent profile rather than defining a second ontology. Generic metadata uses DCTERMS, sources and runs use PROV-O, generic entities use Schema.org, concepts use SKOS, and evidence spans use Web Annotation. LaclauGPT vocabulary is reserved for discourse-theoretical classes and properties.

| Canonical object | RDF representation |
| --- | --- |
| `source_url` | deterministic project-scoped source URI + `dcterms:identifier` preserving the original URL |
| `source.*` | DCTERMS / Schema.org |
| `provenance[]` | `prov:Activity`, `prov:Agent`, `prov:used`, `prov:wasAssociatedWith` |
| `evidence[]` | `oa:Annotation`, `oa:TextPositionSelector`, exact quote body |
| entities | `schema:Person`, `schema:Organization`, or `schema:Thing` |
| formations | `laclaugpt:DiscourseFormation` + `skos:Concept` |
| signifiers | `laclaugpt:Signifier` + `skos:Concept` |
| nodal/floating/empty signifiers | corresponding LaclauGPT theory-specific class + provenance/review state |
| discourses | `laclaugpt:Discourse` + SKOS concept |
| sociotechnical imaginaries | `laclaugpt:SociotechnicalImaginary` + SKOS concept |
| Us / Them | `laclaugpt:CollectiveSubject` / `laclaugpt:OpposingSubject` |
| frontier | `laclaugpt:DiscursiveFrontier` |
| affects | `laclaugpt:Affect` |
| equivalence / difference chains | ordered `laclaugpt:EquivalenceChain` / `laclaugpt:DifferenceChain` with `hasMember` plus RDF container-order predicates |
| Formula of Populism | `laclaugpt:PopulismFormula` with typed component resources retaining canonical component names and values |
| relations / antagonisms | explicit `laclaugpt:Articulation` resources |

Analytical edges are reified as `laclaugpt:Articulation` resources so evidence, review state, relation type and generation provenance remain attachable without requiring RDF-star. Phase 1 discourse objects also retain confidence, uncertainty, evidence links, review state and generation provenance when the canonical object carries them. Formula-of-Populism metadata keys (`evidence_ids`, `provenance_id`, `review_status`, `confidence`, `uncertainty`) are projected onto the formula resource; the remaining canonical keys become named component resources.

### Phase 1 projection audit

RDF is deliberately loss-aware rather than lossless. `CanonicalRecord` remains authoritative, and fields are only promoted into RDF when their semantics are stable enough to be portable across projects.

| Phase 1 canonical field | RDF decision |
| --- | --- |
| formations, signifiers, nodal/floating/empty signifiers | mapped |
| discourses | mapped |
| imaginaries | mapped |
| equivalence_chains / difference_chains | mapped, preserving explicit member order |
| us / them / frontier | mapped |
| affects | mapped |
| formula_of_populism | mapped as formula + components |
| entities | mapped; evidence/provenance/review state retained |
| relations / antagonisms / actor_entity_relations | mapped as articulations |
| topics / topic_assignments | **canonical-only for now**: topic-model identity, probability semantics and corpus scope are model/project dependent |
| sentiments | **canonical-only for now**: label spaces and scoring semantics vary by classifier/codebook |
| stances | **canonical-only for now**: target, label space and entailment semantics need an explicit portable profile first |
| summary, uncertainty, abstentions | canonical analysis/reporting state, not promoted as first-class RDF analytical objects |
| plugin results, embeddings, representations, model runs | implementation/runtime artifacts; remain canonical/plugin data unless a dedicated profile is defined |

This omission policy is intentional: an absent RDF mapping must be documented here rather than silently interpreted as semantic equivalence or data loss from the canonical record.

## Deterministic identity and graph boundaries

`stable_uri()` generates `{base}/{project}/{kind}/{readable-prefix}-{sha256-prefix}` identifiers. The project is present in every minted URI and named graph boundary. This prevents accidental cross-project collisions. Source URLs are preserved as literals and therefore round-trip even when they are not used directly as RDF subjects.

Lexical strings, SKOS/discourse concepts and source occurrences are never equated. Multilingual labels use RDF language tags when source language is available.

## Validation

`validate_dataset()` implements the parent baseline constraints offline and can also execute the parent SHACL shapes through PySHACL when `validation.shapes_path` points to the copied/current shapes file. Baseline checks require:

- at least two endpoints for every articulation;
- `prov:wasGeneratedBy` for articulations;
- allowed review states;
- generation provenance and review state for theory-specific signifier-role claims;
- generation provenance and review state for mapped Phase 1 discourse concepts;
- at least two members for equivalence/difference chains;
- at least one component for a Formula of Populism.

Validation reports contain focus node, path, message and severity. Persistent store writes occur only after validation passes.

## Export

`serialize_dataset()` supports JSON-LD, Turtle, N-Quads, N-Triples, TriG and RDF/XML. Turtle/N-Triples are generated from a deterministic union graph; N-Quads/TriG preserve named-graph boundaries.

The plugin result stores the selected serialized forms together with canonical schema version, RDF profile version, project ID, named graphs and validation metadata. Large production workflows may instead direct the dataset to an `RDFStore` and retain only export references.

## Stores

The `RDFStore` protocol exposes `healthcheck`, `add`, `query` and `export`.

- `FileRDFStore`: local serialization.
- `RDFLibStore`: local named-graph dataset and SPARQL query.
- `SPARQLStore`: generic authenticated HTTP query/update adapter.
- `oxigraph` is reserved behind the same contract and intentionally not a baseline dependency.

No external store is required for CI.

## GraphRAG

RDF GraphRAG is independently gated by both `analysis.rdf.enabled` and `analysis.rdf.graphrag.enabled`. `retrieve_subgraph()` returns a bounded project-scoped neighborhood with source identifiers, named-graph/triple paths and retrieval parameters for auditability. It is an additional context provider, not a replacement for Mongo/vector/full-text retrieval.

The local implementation deliberately avoids arbitrary full-graph prompt injection. Production remote adapters should implement the same bounded contract using SPARQL `CONSTRUCT`/`SELECT` with explicit project/time/source/entity/review filters.

## Plugin runtime

`RDFMaterializationPlugin` implements the generic `PluginSpec`/`AnalysisPlugin` contract. Register it in a `PluginRegistry` and select it only when project configuration has enabled RDF. Direct canonical-pipeline integrations may call `run_optional_rdf_postprocess(record, project_config=...)`; the function itself re-checks the project gate, so omitted/disabled configuration is a no-op.

## Round-trip

`import_profile_dataset()` imports the portable source/articulation subset. The synthetic round-trip guarantees recovery of canonical source identity, relation IDs/types/endpoints, review state, generation activity and evidence links. Byte-for-byte equality is not promised because RDF blank-node layout and serialization ordering are not semantic.

## Privacy and publication

The materializer does not serialize `raw_capture`, legacy blobs, project context, credentials, private codebooks or researcher notes. RDF does not imply publication. Store credentials belong in private/machine configuration. Publication/de-identification policy must be applied before exporting any graph derived from restricted sources.

## Parent references

Normative definitions remain in the meta-repository:

- `docs/RDF_APPLICATION_PROFILE.md`
- `schemas/laclaugpt-rdf-profile.ttl`
- `schemas/laclaugpt-rdf.shacl.ttl`
- `schemas/rdf-project-settings.v1.schema.json`

When this implementation and the parent profile differ, the parent profile is authoritative.