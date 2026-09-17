# Analysis interoperability: DATS, DNA/rDNA, Python and R

This document implements the Analysis-side contract from `TomiToivio/LaclauGPT#35` and issue #57. The meta-repository owns the canonical theory/data contract; this repository owns executable analytical adapters.

## Core rule

External software produces **descriptive or method-specific analytical objects**. It does not directly produce Laclauian theoretical facts.

- DNA actor-concept agreement is not automatically equivalence.
- Network degree is not automatically nodal status.
- Community detection is not automatically an ideological formation.
- Semantic similarity is not automatically equivalence.
- Negative sentiment is not antagonism.
- Topic prevalence is not hegemony.
- Polysemy is not automatically empty/floating signification.
- LLM output remains provisional until human review.

Imported results belong under `CanonicalRecord.analysis.plugin_results[namespace]` and should use `interpretation_status: DESCRIPTIVE_ONLY` unless a separate evidence-grounded interpretive stage has been reviewed.

## DATS profile

`src/laclaugpt_data_analysis/interoperability.py` defines a normalized DATS interchange profile:

`DATS document <-> CanonicalRecord`

`DATS code <-> Code`

`DATS annotation <-> Evidence + Annotation`

`DATS human correction <-> HumanReview`

`DATS concept-over-time <-> TemporalSeries`

Machine-produced annotations must be exported as `PROVISIONAL` and `provisional_ai: true`. `dats_review.py` provides the explicit proposal/review bridge. Native DATS bundles may evolve; tool-specific readers should normalize them into this stable profile instead of coupling the core to DATS internals.

## DNA/rDNA profile

`DiscourseStatement` is the theory-neutral bridge. Stable statement, actor, concept, source, evidence, timestamp, producer, confidence, provenance, review status and external DNA IDs are preserved.

The portable table profile supports CSV and can be passed to rDNA. `graph_exchange.py` builds graph projections with graph-level metadata describing node semantics, edge semantics, projection method, weighting method, parameters and source statement IDs. GraphML and node/edge CSV are the preferred network exchange formats.

A downstream Laclau/Mouffe/Palonen interpretation is a **separate stage**:

```text
DNA statements -> descriptive graph/network result -> evidence retrieval
-> optional interpretive proposal -> human review
```

## Cross-language exchange

Preferred formats:

- JSON/JSONL for nested canonical records and plugin manifests
- Parquet/Apache Arrow for typed Python/R tables
- CSV for manual and legacy interchange
- GraphML for graphs
- node/edge CSV as universal graph fallback
- JSON manifests for producer/version/parameters/run/source IDs/uncertainty

Never make pickle or RDS the only exchange format.

## Method/software compatibility matrix

| Research question | Theoretical construct | Descriptive method | Software | Output object | Limitation | Validation |
| --- | --- | --- | --- | --- | --- | --- |
| Where does a researcher-defined concept occur? | sensitising/codebook concept | qualitative annotation / retrieval | DATS/COTA | `Annotation`, `Evidence` | code is a research construct | human review, intercoder checks |
| Can reviewed labels generalise? | operationalised category | supervised/few-shot classification | sklearn, Transformers, LLM | plugin result / provisional annotation | label reification, shift | held-out evaluation + review |
| What texts are semantically close? | none directly | embeddings | SentenceTransformers | embedding/plugin result | similarity != equivalence | retrieval inspection |
| Which actors/entities occur? | actors/entities | NER + entity resolution | spaCy, Transformers | entity/mention | resolution errors | sampled manual audit |
| What themes cluster? | none directly | BERTopic / LDA / NMF / CTM | BERTopic, gensim, sklearn | plugin result | topic != discourse/hegemony | stability + close reading |
| How do topics vary with covariates? | contextual thematic structure | STM | R `stm` | plugin result / Parquet tables | specification sensitivity | diagnostics + robustness |
| Which actors articulate which concepts? | discourse-network evidence | DNA | DNA/rDNA, NetworkX | `DiscourseStatement`, graph projection | agreement != equivalence | coding audit + construction metadata |
| What network structure exists? | structural relation | SNA | NetworkX, igraph | graph/plugin result | structure != political formation | sensitivity analysis |
| Which communities appear? | none directly | Leiden | igraph/leidenalg | plugin result | community != ideological formation | resolution/stability analysis |
| Which frames recur? | frame candidates | coding/classification | DATS, LLM, sklearn | annotation/plugin result | ontology dependent | human coding comparison |
| How does discourse change? | articulation/formation change candidates | temporal aggregation | pandas/R | `TemporalSeries` | volume/sampling confounds | normalized denominators + source audit |
| What social positions structure categories? | field/social space | MCA/GDA/correspondence | R/Python | plugin result | axes need substantive interpretation | contribution/quality diagnostics |
| Can an LLM assist close reading? | Laclauian interpretive proposal | structured coding/RAG | LLM | provisional objects | model error/bias | evidence links + human review |

## Python ecosystem

The repository already exposes thin optional backends for spaCy, Transformers, SentenceTransformers, scikit-learn, BERTopic, gensim and statsmodels. `analysis` extras provide pandas/numpy/scipy/statsmodels/scikit-learn/NetworkX; graph/Arrow extensions add python-igraph, leidenalg, polars and pyarrow. Optional packages must not become core runtime requirements.

## R integration

Standalone scripts under `scripts/r/` are optional modules runnable from RStudio, `Rscript`, Slurm or another R environment. They exchange open formats with Python and never require R for the core pipeline.

- `quanteda_interop.R`: corpus/docvars, DFM/KWIC-style workflow, table export
- `stm_interop.R`: STM with preserved seed/formula/settings, topic-proportion export
- `rdna_interop.R`: DNA statement-table normalization and result-manifest pattern
- `igraph_interop.R`: GraphML measures/community output with construction provenance

## Scientific sources

Canonical bibliography: `TomiToivio/LaclauGPT` sources and cross-tool compatibility contract.

Analysis-specific foundations include Grimmer & Stewart (2013) on text-as-data validation; Benoit et al. (2018) on quanteda; Roberts, Stewart, Tingley et al. on STM; Reimers & Gurevych (2019) on Sentence-BERT; Bianchi, Terragni & Hovy (2021) on contextualized topic models; Grootendorst (2022) on BERTopic; Traag, Waltman & van Eck (2019) on Leiden; Philip Leifeld's work on Discourse Network Analysis and rDNA; and DATS publications on COTA, Annotation Assistant and Whiteboards/human-in-the-loop discourse analysis.

The methodological principle across these sources is the same one enforced here: computational output is an instrument for research inference, not a substitute for construct validity, evidence inspection or human scholarly judgement.
