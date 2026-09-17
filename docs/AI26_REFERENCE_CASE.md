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

## AI26 staged analysis order

Multimodal AI26 records follow this theory-layered order:

```text
raw source evidence
  -> ASR / translation / OCR / frames / deterministic NLP
  -> per-frame multimodal semiotic description
  -> item-level multimodal synthesis + light Castells context
  -> Laclau/Mouffe/Palonen discourse analysis
  -> DNA / Critical AI Studies / other specialised stages when configured
```

The early multimodal stages build a reusable evidence layer. They must not jump directly from an image, transcript or chart to ideological formation, populism, hegemony, antagonism or Critical AI interpretation.

### Frame analysis

AI26 explicitly selects:

- `multimodal.system:v1`
- `multimodal.frame_analysis:v1`

The frame pass uses a Bateman/Wildfeuer/Hiippala-style problem-oriented multimodal approach with compatible social-semiotic concepts. It records material/canvas organisation, scene/participants, composition, text/symbol/interface cues, provenance/usage cues, semiotic contribution and uncertainty.

The AI26 project note may ask the model to notice, when present, AI/LLM interfaces and demos, labs/firms/researchers/investors/policy actors, compute/data centres/chips/energy, robots, generated media, benchmarks/charts, regulation/safety/labour/environmental material, protests/memes/online communities and quoted media. This note is a relevance guide only. It is not evidence and it does not classify ideology.

### Item synthesis and light Castells context

AI26 then selects:

- `multimodal.system:v1`
- `multimodal.summary_analysis:v1`

The item synthesis reconstructs narrative/temporal sequence and cross-modal relations across available transcript, OCR, frames, audio observations, metadata and deterministic NLP. It preserves reinforcement, elaboration, anchoring, contradiction, quotation/recontextualisation and substitution rather than flattening all modalities into one text field.

The same stage includes a deliberately light Castells-oriented context with separate fields for:

- actors / organisations / institutions;
- explicit or strongly implied networks and relations;
- flows;
- nodes / hubs / channels;
- space of places;
- space of flows;
- observable or explicitly claimed power/access/exclusion;
- uncertainty.

This is not formal SNA. Empty network fields are expected when the item does not establish a network relation. Centrality, brokerage, structural holes, institutional power or hidden ties must not be invented.

The structured summary contains no direct signifier, frontier or formation fields. It finishes with `Later analysis cues`, which are evidence-backed questions/candidates for downstream theory stages.

### Dedicated discourse stage

Only after the multimodal pre-analysis does AI26 run:

- `laclau.system:v1`
- `laclau.discourse_analysis:v1`

This later stage remains responsible for signifiers, articulation, equivalence/difference, collective subjects, frontiers, antagonism, populism, formations, imaginaries and other Laclau/Mouffe/Palonen concepts. DNA and Critical AI Studies remain separate later stages/plugins rather than being folded into the multimodal synthesis.

## Public codebooks

AI26 exposes two publication-safe codebook views:

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

## Current context, 2026-09-17

The public collection and analysis vocabulary currently emphasizes relations among `safety`, `pacing`, `competition`, `innovation`, `control`, `liability`, `independent evaluation`, `standards`, `open weights`, `labour`, `copyright`, `data centres` and `regulation`.

This should update **context/signifier vocabulary**, not expand the top-level formation taxonomy. The same organization can articulate safety, acceleration, competitive leadership and restraint in different texts or moments.

## Collection-to-analysis contract

The public AI26 demo in `TomiToivio/LaclauGPT-Data-Collection` prioritizes RSS/blog/web and scholarly sources, with bounded X, Bluesky and Mastodon samples and transcript-first YouTube collection. Analysis should therefore expect:

- rich attributable long-form text as the main stream;
- social posts with external links resolved to separate canonical `WEB` records where possible;
- `arena`, `source_family` and source provenance as sampling metadata only;
- ambiguous documents retained rather than pre-classified;
- source publication timestamps preserved so the analysis window can be enforced consistently;
- multimodal evidence retained as source/intermediate material before theoretical interpretation.

## Provenance requirements

For every model-assisted AI26 stage, preserve:

- exact prompt IDs and versions;
- source prompt SHA-256 hashes and rendered prompt hash;
- requested/resolved provider and model;
- configuration revision;
- codebook revision;
- context revision;
- project-configuration revision and deterministic project-config hash;
- stage name and run timestamp/provenance.

These are method provenance, not source evidence.

## Method safeguards

AI26 is especially useful for testing theory-sensitive failure modes:

- frequency != hegemony;
- polysemy != floating or empty signification;
- negativity/disagreement != antagonism;
- sentiment != affective investment;
- one speculative future != stabilized sociotechnical imaginary;
- actor identity/source family != formation membership;
- one document != a validated formation;
- a frame or summary cue != an ideological classification;
- a named platform or actor != evidence of network centrality or brokerage.

Every theory-facing candidate should retain source evidence, provenance, uncertainty and review state.

## Public/private boundary

Public:

- conceptual and machine-readable codebooks;
- project/arena semantics;
- bounded public demo source examples;
- synthetic fixtures and example prompts;
- current public context vocabulary;
- generic multimodal method prompts and schemas.

Private/ignored:

- row-level research corpus;
- unpublished researcher annotations;
- credentials, cookies, tokens and private endpoints;
- machine-specific runtime/deployment state;
- any source-selection notes that expose sensitive research operations.
