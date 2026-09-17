# AI26 analysis pipeline

AI26 uses a layered analysis design in which descriptive work precedes stronger theory-specific interpretation. Each LLM layer is a provisional human-reviewable proposal, not ground truth.

```text
CanonicalRecord
  ↓
1. Multimodal summary / light sociological pre-analysis
   - multimodal frame analysis
   - multimodal item synthesis
   - light Castells-style Network Society context
  ↓
2. Laclaudian discourse analysis
   - articulations, demands, signifiers, subjects, frontiers, affects
   - equivalence/difference, candidate formations and sociotechnical imaginaries
  ↓
3. Optional DNA-compatible Discourse Network Analysis coding
   - actor × concept × stance/agreement statements
   - designed for DNA import/export compatibility
  ↓
4. Optional Critical AI Studies analysis
   - ideology shaping AI / reproduced through AI / contestation over AI
   - power and political economy
   - labour and hidden work
   - data, extraction and coloniality
   - material infrastructure and environment
   - governance, democracy and surveillance
   - subjectification, technological myths, distribution and alternatives
  ↓
periodic aggregation / visualization / RAG / human review
```

The Critical AI stage is disabled unless project settings explicitly enable it. This means ordinary canonical runs and projects for which Critical AI Studies is irrelevant do not receive another model call or another stage output.

Example AI26 settings:

```yaml
analysis:
  critical_ai:
    enabled: true
    provider: ollama
    model: gemma4:12b
    prompt_version: v1
    include_prior_laclau: true
    include_prior_dna: true
    include_rag: true
    include_periodic_context: true
    evidence_mode: strict
```

The runtime still receives an already configured provider object through the repository's provider abstraction. The Critical AI module never calls Ollama directly and does not make Gemma4 a global default. The stage-level `model` merely selects which configured model that provider should use.

Context is passed through the canonical prompt envelope and retains the distinction between current-source evidence, earlier pipeline proposals, project/codebook material, RAG material and periodic/situational context. Earlier Laclau and DNA results can be compared with Critical AI findings, but cannot silently become evidence for them.

See `docs/methods/critical_ai_studies.md` for the full method, schema, provenance contract, limitations, worked example and bibliography.