# Experimental Luhmann / Social Systems analysis layer

Status: **optional, experimental, disabled by default**.

This layer asks a different question from the default Laclau/Mouffe/Palonen discourse analysis. Instead of treating articulation, antagonism and signifiers as the primary object, it examines communication in relation to functional differentiation, system/environment distinctions, communication codes/programmes, structural couplings and cross-system translation.

It must not replace or silently modify the default discourse pipeline.

## Theoretical starting points

Primary sources:

- Niklas Luhmann, *Social Systems* (1984; English trans. 1995).
- Niklas Luhmann, *The Reality of the Mass Media* (English trans. 2000).
- Niklas Luhmann, *Law as a Social System* (English ed. 2004).
- Niklas Luhmann, *Theory of Society*, Vols. 1–2 (English eds. 2012/2013).

The implementation follows an important caution: functional systems and their codes/programmes are theory-laden analytical constructions. The software therefore supports `unknown`, multiple references and mixed/organization-mediated cases, and it treats code/programme assignments as candidates with confidence/evidence rather than fixed universal labels.

## Empirical/computational operationalization

The prototype is informed by work that attempts to operationalize communication and meaning without claiming that computational measures are identical to Luhmannian concepts:

- Loet Leydesdorff (1996), “Luhmann's Sociological Theory: Its Operationalization and Future Perspectives,” *Social Science Information* 35(2), 283–306. DOI 10.1177/053901896035002007.
- Loet Leydesdorff (2011), “‘Meaning’ as a Sociological Concept: A Review of the Modeling, Mapping and Simulation of the Communication of Knowledge and Meaning,” *Social Science Information* 50(3–4), 391–413. DOI 10.1177/0539018411411021.
- Loet Leydesdorff, Alexander M. Petersen & Inga Ivanova (2017), “Self-organization of Meaning and the Reflexive Communication of Information,” *Social Science Information* 56(1), 4–27. DOI 10.1177/0539018416675074.
- “Network analysis as an alternative way to interpret constitutions,” *PLOS ONE* (2021), DOI 10.1371/journal.pone.0259461.
- “Communicating science addressing contentious environmental issues: utilizing Luhmann's social systems theory,” *Frontiers in Communication* (2024), DOI 10.3389/fcomm.2024.1348078.

The code includes Shannon entropy, mutual information and contingency-matrix helpers because these are useful empirical descriptors inspired by this operationalization literature. They must be reported as measured information-theoretic features, not automatically labeled “autopoiesis”, “self-organization” or “meaning”.

## Data model

`SystemsAnalysis` contains:

- `primary_system`
- `referenced_systems[]`
- `organization_context`
- `system_environment_distinction`
- `communication_code_candidates[]`
- `programme_or_criterion_candidates[]`
- `structural_couplings[]`
- `cross_system_translations[]`
- `observations_of_other_systems[]`
- `evidence_spans[]`
- `confidence`
- `model_method`
- `provenance`
- `human_validation`

The public codebook is versioned at `codebooks/public/luhmann_social_systems_v1.yaml`.

## Structured LLM extraction

`build_structured_extraction_prompt()` creates a conservative prompt for an existing structured-output LLM adapter. It explicitly permits unknown/mixed cases and requires evidence spans. `parse_structured_analysis()` validates returned JSON with Pydantic.

This module deliberately does not hard-wire one model provider. It can later be wrapped by the generic analysis-plugin/runtime architecture.

## Non-LLM baseline

`prototype_classify()` is a transparent normalized prototype-term-overlap baseline. It is intentionally simple and reproducible. Its purpose is comparison, calibration and tests, not substantive validation of Luhmannian theory.

A later benchmark should compare at least:

- this transparent baseline;
- sentence-transformer prototype/centroid similarity;
- supervised multilabel scikit-learn classifier;
- zero-shot/NLI transformer baseline;
- structured LLM extraction.

## Human validation

Use `evaluation/luhmann_validation_template.csv` for a small human-coded sample. At minimum record:

- source record ID;
- text/evidence reference;
- one or more system labels;
- ambiguity/unknown state;
- code/programme candidates if justified;
- annotator and notes.

For multilabel evaluation report precision, recall and F1. Also report disagreement/ambiguity rather than hiding it behind majority labels.

## Cross-system graph

`translation_edges()` converts structured `cross_system_translations` into evidence-preserving rows suitable for NetworkX, igraph, a knowledge graph or downstream visualization.

Example conceptual sequence:

```text
science capability result
  -> competitiveness framing in economy/politics
  -> regulatory-risk framing in politics/law
  -> headline selection in mass media
```

Useful downstream products include:

- system × system flow matrix;
- Sankey/alluvial flow;
- temporal system shares;
- functional-system reference network;
- system × signifier / system × imaginary table.

These outputs are empirical projections. Brokerage, centrality and transition counts are graph measures, not inherently Luhmannian concepts.

## Feature flag

The feature is disabled by default:

```text
LACLAUGPT_LUHMANN_ENABLED=false
```

When enabled, the default public codebook path is:

```text
codebooks/public/luhmann_social_systems_v1.yaml
```

The current implementation is a prototype library layer. It does not automatically insert itself into the canonical pipeline. Integration should happen through the generic analysis-plugin interface when that architecture is implemented.

## AI26

AI26 is a useful future validation case because AI communications frequently cross science, economy, politics, law and mass media. Do not activate this layer in the default AI26 pipeline until a human-coded validation set exists and the experimental labels have been evaluated.
