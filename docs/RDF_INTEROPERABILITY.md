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
| relations / antagonisms | explicit `laclaugpt:Articulation` resources |
| analyses summary, uncertainty, abstentions | `laclaugpt:analysisSummary`, `laclaugpt:uncertainty`, `laclaugpt:abstention` on the source |

### Phase 1 analytical objects (issue #144)

The default Phase 1 pipeline populates additional typed fields. These are all
projected, with evidence links, `prov:wasGeneratedBy`, `laclaugpt:reviewState`,
`laclaugpt:confidence` and `laclaugpt:uncertainty` preserved where the canonical
object carries them:

| Canonical Phase 1 object | RDF representation |
| --- | --- |
| `discourses` | `laclaugpt:Discourse` + `skos:Concept` |
| `imaginaries` | `laclaugpt:SociotechnicalImaginary` + `skos:Concept` |
| `us` | `laclaugpt:CollectiveSubject` + `skos:Concept` |
| `them` | `laclaugpt:Other` + `skos:Concept` |
| `affects` | `laclaugpt:Affect` + `skos:Concept` |
| `equivalence_chains` | `laclaugpt:EquivalenceChain` + `laclaugpt:RelationChain`, members via `laclaugpt:hasMember` |
| `difference_chains` | `laclaugpt:DifferenceChain` + `laclaugpt:RelationChain`, members via `laclaugpt:hasMember` |
| `formula_of_populism` | `laclaugpt:FormulaOfPopulism` with `laclaugpt:populist`, `laclaugpt:nonPopulistReason`, `laclaugpt:formulaComponent` |
| candidate objects flagged for corpus validation | `laclaugpt:corpusValidationRequired true` |

A chain is projected as its own resource rather than collapsed into pairwise
articulations, because a chain groups heterogeneous members and its membership is
analytical content. Objects whose canonical `metadata.corpus_validation_required`
is set keep that flag in RDF, so a consumer cannot mistake a document-level
candidate for a corpus-established finding.

### Descriptive computation: explicit typing policy

Topics, sentiments, stances and themes come from descriptive computation, not
discourse theory. They **are** projected — but deliberately typed as
`laclaugpt:DescriptiveObservation` (or `laclaugpt:Topic`) and marked
`laclaugpt:descriptive true`, and never as `laclaugpt:Affect`,
`laclaugpt:DiscursiveFrontier` or a formation.

This is the encoding of the project rule that **sentiment polarity is not
affective investment**: a consumer can retrieve polarity as an observation but
cannot read it as a theory-facing claim, because the node lacks the
theory-specific type. `topic_assignments` and `representations` are not
projected; they are document-processing bookkeeping rather than analytical
objects, and this omission is recorded here rather than left silent.

Analytical edges are reified as `laclaugpt:Articulation` resources so evidence, review state, relation type and generation provenance remain attachable without requiring RDF-star.

## Deterministic identity and graph boundaries

`stable_uri()` generates `{base}/{project}/{kind}/{readable-prefix}-{sha256-prefix}` identifiers. The project is present in every minted URI and named graph boundary. This prevents accidental cross-project collisions. Source URLs are preserved as literals and therefore round-trip even when they are not used directly as RDF subjects.

Lexical strings, SKOS/discourse concepts and source occurrences are never equated. Multilingual labels use RDF language tags when source language is available.

## Validation

`validate_dataset()` implements the parent baseline constraints offline and can also execute the parent SHACL shapes through PySHACL when `validation.shapes_path` points to the copied/current shapes file. Baseline checks require:

- at least two endpoints for every articulation;
- `prov:wasGeneratedBy` for articulations;
- allowed review states;
- generation provenance and review state for theory-specific signifier-role claims;
- generation provenance and review state for Phase 1 discourse-theoretical objects (`Discourse`, `SociotechnicalImaginary`, `CollectiveSubject`, `Other`, `Affect`, `DiscourseFormation`, `Signifier`, `DiscursiveFrontier`);
- at least two members, generation provenance and review state for every `RelationChain`;
- generation provenance for the `FormulaOfPopulism` projection;
- `laclaugpt:descriptive true` on every `DescriptiveObservation` and `Topic`, so polarity cannot be read as a theory-facing claim.

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