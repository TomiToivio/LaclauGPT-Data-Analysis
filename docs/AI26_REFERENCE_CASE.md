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

## Arenas

The paper compares:

- `elites`: frontier-AI labs, researchers, entrepreneurs, intellectuals and adjacent movements;
- `grassroots`: mobilisation around employment, creative work, surveillance, data extraction, data centres, environment, safety and opposition/support;
- `parliamentary`: parliamentary, electoral, government, party and policy discourse.

Arena is sampling provenance. It must never be used as evidence for ideological classification.

## Canonical formation vocabulary

For stable aggregation, the AI26 public codebook currently exposes six provisional formation labels:

- accelerationism
- doomerism
- left-wing accelerationism
- ai safety
- ai critical
- anti-ai

These are sensitising concepts, not a closed ontology. The paper explicitly requires claims/relations to be analysed before documents are put into ideological boxes. Multi-label outputs, uncertainty and abstention are expected.

## Current context, 2026-09-16

The live frontier-AI debate currently makes the relation among `safety`, `pacing`, `competition`, `innovation`, `China`, `control`, `liability`, `independent evaluation`, `standards` and `regulation` particularly useful for AI26.

The public situation report in the meta-repository notes that Dario Amodei has argued for coordinated pacing and third-party evaluation, while Mark Zuckerberg and Jensen Huang have publicly rejected coordinated slowdown logic and emphasized competition/company responsibility. Public reporting also describes OpenAI, Anthropic and Google DeepMind discussing forms of AI-safety coordination.

This should update **context/signifier vocabulary**, not expand the top-level formation taxonomy. The same organization can articulate safety, acceleration, competitive leadership and restraint in different texts or moments.

Public background sources used for this update:

- Dario Amodei, `We Must Pace the Frontier`: https://darioamodei.com/post/we-must-pace-the-frontier
- OpenAI, `The AI policy window is open. We need to act.` (2026-09-09): https://openai.com/index/ai-policy-window/
- Reuters (2026-09-16), reporting Mark Zuckerberg's rejection of coordinated slowdown logic: https://www.reuters.com/business/metas-zuckerberg-says-ai-labs-have-enough-incentive-build-safely-2026-09-16/
- Reuters (2026-09-15), reporting OpenAI/Anthropic/Google safety discussions: https://www.reuters.com/technology/openai-is-working-with-anthropic-google-ai-safety-bloomberg-news-reports-2026-09-15/

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

- conceptual codebooks and formation normalization;
- project/arena semantics;
- public entity/source examples;
- synthetic fixtures and example prompts;
- situation-report-derived context vocabulary.

Private/ignored:

- row-level research corpus;
- private watch lists and target selection notes;
- unpublished researcher annotations;
- credentials, tokens and private endpoints;
- machine-specific runtime/deployment state.
