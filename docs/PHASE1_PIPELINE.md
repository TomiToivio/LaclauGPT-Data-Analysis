# Phase 1 default pipeline (legacy order)

This document defines the default LaclauGPT analysis path and its phase gating.
It implements issue #140. The machine-readable source of truth is
`src/laclaugpt_data_analysis/phases.py`; this document explains it.

## The default path

Running Data Analysis with default settings executes the **Phase 1** pipeline in
the conceptual order of the original legacy EP24 pipeline:

```text
preprocessing
  -> frame analysis (only when the record carries images/video/frames)
  -> summary analysis
  -> Laclaudian discourse analysis
  -> postprocessing
```

| Stage | Legacy ancestor | Default | Conditional |
| --- | --- | --- | --- |
| `preprocess` | `puhti_preprocess.py` | on | no |
| `frame` | `puhti_frame.py` | on | **yes** — skipped for text-only records |
| `summary` | `puhti_summary.py` | on | no |
| `discourse` | `puhti_populism.py` | on | no |
| `postprocess` | `puhti_postprocess.py` | on | no |

The modern implementation keeps its own architecture, schemas and evidence
handling; what descends from the legacy pipeline is the **stage order and the
responsibility of each stage**, not the old code.

## Stage responsibilities

- **Preprocessing** — media preprocessing, transcription, OCR where applicable,
  keyframe/frame extraction where applicable, and normalization of multimodal
  evidence for downstream stages.
- **Frame analysis** — a descriptive multimodal evidence pass over each frame.
  It runs only when frames exist. It does not classify ideology or discourse
  formations.
- **Summary analysis** — combines source material, metadata, transcript/OCR and
  frame outputs into a structured research-oriented summary. An intermediate
  layer, not the final Laclaudian interpretation.
- **Laclaudian discourse analysis** — theory-guided pre-analysis producing
  evidence-linked *candidates*: signifiers, nodal points, floating and
  tendentially empty signifiers, articulations, demands, collective subjects,
  chains of equivalence and difference, antagonistic frontiers, affects and
  sociotechnical imaginaries. Always provisional and human-reviewable.
- **Postprocessing** — derives compact, typed, auditable structured fields
  (topics, entities, affect targets, signifier roles, relations, uncertainty)
  from the summary and discourse outputs. It normalizes; it does not re-analyse.

## Phase 2 — experimental / optional, off by default

Phase 2 methods remain in the repository but **never run unless a study
explicitly enables them**:

| Capability | Status |
| --- | --- |
| `dna_statement_coding` (Discourse Network Analysis) | Phase 2, optional, default off |
| `critical_ai` (Critical AI Studies) | Phase 2, optional, default off |
| `sna` (Social Network Analysis) | Phase 2, not implemented as a canonical stage |
| `ant`, `valueflows` | Phase 2, not implemented as canonical stages |

Plugins declaring `phase=2` set `default_enabled=False` and are marked
`experimental`. `PluginSpec.validate()` **rejects** a Phase 2 plugin that tries
to be default-enabled, so this cannot silently regress.

Network measures are not substitutes for Laclaudian interpretation.

## Enabling Phase 2

Set the capability to `enabled: true` in the study's project config, e.g.:

```yaml
analysis:
  dna_statement_coding:
    enabled: true
```

Enabling a capability that has no implementation remains a fail-closed
configuration error.

## Project prompt profiles

Phase 1 LLM-assisted stages select prompts per project profile, and the profiles
are kept explicitly separate so project assumptions never leak between them:

| Profile | Frame | Summary | Discourse | Postprocess |
| --- | --- | --- | --- | --- |
| **AI26** | `ai26.frame_analysis` | `ai26.summary_analysis` | `ai26.discourse_analysis` | `ai26.postprocess` |
| **EP24** | `laclau.frame_analysis` | `laclau.summary_analysis` | `ep24.laclau_analysis` | `ep24.postprocess` |

All AI26 stages share `ai26.system`; the system layer carries stable
methodological rules, while project-specific assumptions live in the research
context layer. See `docs/PROMPT_LIBRARY.md` and
`src/laclaugpt_data_analysis/prompts/README.md`.

The AI26 prompts combine the current AI26 methodology (problem-oriented
multimodality, light Castells contextualisation, current evidence discipline and
schemas) with the explicitness of the legacy EP24 prompts. EP24 retains its
2024 election research context where methodologically appropriate.

## Where the gating lives

- `src/laclaugpt_data_analysis/phases.py` — stage order, phases, defaults.
- `src/laclaugpt_data_analysis/canonical_pipeline.py` — `run_canonical_pipeline`
  executes the order and gates Phase 2; each run records a `phase_manifest`
  stage output.
- `src/laclaugpt_data_analysis/plugin_pipeline.py` — `PluginSpec.phase`,
  `default_enabled`, `experimental` and their validation.
- `config/projects/ai26.yaml` — the shipped AI26 layer, with Phase 2 off.

## Tests

`tests/test_issue_140_phase_pipeline.py` covers: the default order, conditional
frame analysis for text-only records, Phase 2 not being invoked by default, the
shipped AI26 config remaining Phase 2-off, postprocessing ordering and typed
output, plugin phase metadata, and AI26/EP24 prompt-profile separation.
