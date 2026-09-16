# AI26 analysis reference case

AI26 (`Ideological contestation over AI`) is the canonical public example for LaclauGPT Data Analysis. It connects the reusable analysis machinery to the current public paper without making the pipeline study-specific.

## Public project profile

The publication-safe profile adapted from the working study is:

```yaml
project: ai26
dataset:
  title: Ideological contestation over AI
  languages: [en, fi]
  relevance:
    mode: retain_unjudged
analysis:
  laclau: true
  palonen: true
  sociotechnical_imaginaries: true
  sentiment: true
  topics: true
  entities: true
  context_memory: true
  temporal: true
  multimodal: true
  sna: false
  ant: false
  valueflows: false
```

The switches describe the reference research design, not global defaults for every study.

## Public codebooks

AI26 now exposes two publication-safe codebook views:

- `codebooks/public/seed_ai_formations.md`: human-readable methodological guide;
- `codebooks/public/ai26_v2.yaml`: machine-readable codebook that can be loaded by `laclaugpt_data_analysis.codebooks.load_codebook()` and seeded into context memory.

The machine-readable codebook contains provisional formation anchors, candidate signifiers and cross-cutting topics derived from the public paper. It intentionally contains no corpus-derived labels or private annotations.

## Arenas

The paper compares:

- `elites`: frontier-AI labs, researchers, entrepreneurs, intellectuals and adjacent movements;
- `grassroots`: mobilisation around employment, creative work, surveillance, data extraction, data centres, environment, safety and opposition/support;
- `parliamentary`: parliamentary, electoral, government, party and policy discourse.

Arena is sampling provenance. It must never be used as evidence for ideological classification.

## Canonical formation vocabulary

For stable aggregation, the AI26 public codebook exposes six provisional formation labels:

- accelerationism
- doomerism
- left-wing accelerationism
- ai safety
- ai critical
- anti-ai

These are sensitising concepts, not a closed ontology. The paper explicitly requires claims and relations to be analysed before documents are put into ideological boxes. Multi-label outputs, uncertainty and abstention are expected.

The collection repository uses the same vocabulary only to maintain discursive coverage. It does **not** stamp source records with ideological labels.

## Cross-cutting analytical dimensions

To avoid forcing every record into one of six buckets, AI26 also tracks reusable dimensions across formations:

- political economy: ownership, labour, concentration, redistribution and public infrastructure;
- governance: regulation, liability, audits, standards, evaluation and democratic control;
- capability risk: alignment, catastrophic risk, loss of control and autonomous agents;
- techno-optimism: abundance, growth, innovation, human flourishing and post-work futures;
- rights and harms: discrimination, surveillance, copyright, creator rights and data extraction;
- infrastructure: compute, chips, data centres, energy, water and open weights;
- geopolitics: AI race, sovereignty, national security, China and export controls.

These dimensions are context for analysis, not ideological classes.

## Current context, 2026-09-16

The public collection and analysis vocabulary currently emphasizes relations among `safety`, `pacing`, `competition`, `innovation`, `control`, `liability`, `independent evaluation`, `standards`, `open weights`, `labour`, `copyright`, `data centres` and `regulation`.

This should update **context/signifier vocabulary**, not expand the top-level formation taxonomy. The same organization can articulate safety, acceleration, competitive leadership and restraint in different texts or moments.

## Collection-to-analysis contract

The public AI26 demo in `TomiToivio/LaclauGPT-Data-Collection` prioritizes RSS/blog/web and scholarly sources, with bounded X, Bluesky and Mastodon samples and transcript-first YouTube collection. Analysis should therefore expect:

- rich attributable long-form text as the main stream;
- social posts with external links resolved to separate canonical `WEB` records where possible;
- `arena`, `source_family` and source provenance as sampling metadata only;
- ambiguous documents retained rather than pre-classified;
- source publication timestamps preserved so the analysis window can be enforced consistently.

## Method safeguards

AI26 is especially useful for testing theory-sensitive failure modes:

- frequency != hegemony;
- polysemy != floating or empty signification;
- negativity/disagreement != antagonism;
- sentiment != affective investment;
- one speculative future != stabilized sociotechnical imaginary;
- actor identity/source family != formation membership;
- one document != a validated formation.

Every theory-facing candidate should retain source evidence, provenance, uncertainty and review state.

## Public/private boundary

Public:

- conceptual and machine-readable codebooks;
- project/arena semantics;
- bounded public demo source examples;
- synthetic fixtures and example prompts;
- current public context vocabulary.

Private/ignored:

- row-level research corpus;
- unpublished researcher annotations;
- credentials, cookies, tokens and private endpoints;
- machine-specific runtime/deployment state;
- any source-selection notes that expose sensitive research operations.
