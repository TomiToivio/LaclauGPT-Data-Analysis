# Phase 0 discourse ontology

Phase 0 models **Laclaudian Discourse Analysis only**. DNA and SNA are deliberately deferred.

MongoDB remains the operational store. RDF/JSON-LD is a lightweight semantic export generated from the existing `phase0_discourse` result.

## Namespace

`https://laclaugpt.org/ontology/` (`lg:`)

Standard vocabularies reused:

- RDF/RDFS
- SKOS labels
- PROV-O provenance

## Core Phase 0 classes

`Document`, `Actor`, `Signifier`, `EmptySignifier`, `FloatingSignifier`, `NodalPoint`, `Articulation`, `Equivalence`, `Difference`, `Antagonism`, `Frontier`, `Affect`, `AnalysisAssertion`, `AnalysisRun`.

## Principles

1. Discourse-analysis assertions stay traceable to their source document and analysis run.
2. Candidate structures remain candidates. RDF export does not turn an LLM interpretation into a theoretical fact.
3. Similar signifiers are not automatically merged.
4. Negative sentiment is not automatically antagonism.
5. Affect remains distinct from sentiment.
6. MongoDB is not replaced by a triple store.
7. DNA/SNA projections are later-phase extensions.

The exporter lives in `laclaugpt/laclaugpt_ontology.py` and stores both JSON-LD and Turtle under `phase0_ontology`.
