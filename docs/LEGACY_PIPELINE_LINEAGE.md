# Legacy pipeline lineage: EP24 `puhti_*` to the modern Phase 1 pipeline

This document records how the modern LaclauGPT analysis pipeline relates to the
original legacy multimodal pipeline, as required by issue #140.

## The legacy pipeline

The predecessor implementation
(`TomiToivio/LaclauGPT-Multimodal-Analysis`, used in the 2024 European
Parliament election study — "EP24") ran as a sequence of CSC Puhti batch
scripts:

```text
puhti_preprocess.py -> puhti_frame.py -> puhti_summary.py
    -> puhti_populism.py -> puhti_postprocess.py
```

Its strengths, which the modern pipeline deliberately preserves:

- a clear, explicit **stage order** with one responsibility per stage;
- highly explicit, step-by-step **system prompts** that a researcher can read
  and audit directly;
- a descriptive **frame-analysis** pass kept separate from political
  interpretation;
- a **summary** layer that is explicitly intermediate;
- theory-guided Laclaudian analysis expressed through Palonen's Formula of
  Populism;
- a final **normalization** stage producing machine-readable fields.

Its limitations, which the current implementation addresses:

- prompts and schemas mixed project-specific (EP24 election) assumptions with
  reusable method;
- no evidence-span verification, no structured provenance, no abstention
  discipline;
- monolithic scripts coupling collection, analysis and storage;
- one project's assumptions baked into the method.

## The modern Phase 1 pipeline

The modern default path (`docs/PHASE1_PIPELINE.md`) keeps the legacy stage order
and per-stage responsibility, but:

- uses versioned, inspectable prompt resources per project profile;
- verifies evidence quotes against the source and records `exact=True/False`;
- separates descriptive computation from interpretive candidates;
- records full model/prompt/config/codebook provenance;
- treats abstention as valid and every theoretical output as provisional;
- marks Phase 2 (DNA, SNA, Critical AI) as experimental and off by default.

| Legacy script | Modern stage | Modern location |
| --- | --- | --- |
| `puhti_preprocess.py` | preprocessing | `preprocess_record` |
| `puhti_frame.py` | frame analysis | `analyze_frames` |
| `puhti_summary.py` | summary analysis | `summarize_record` |
| `puhti_populism.py` | Laclaudian discourse analysis | `discourse_analysis` |
| `puhti_postprocess.py` | postprocessing | `postprocess_record` |
| — | orchestration | `run_canonical_pipeline` |

## Preserved vs. replaced

**Preserved as lineage:** stage order; per-stage separation of descriptive vs.
interpretive work; the explicitness benchmark for prompts.

**Not carried forward:** the EP24 election framing as a method assumption, the
monolithic script structure, unverified evidence handling, and free-form output
parsing.

The legacy prompt texts are archived verbatim for reference in
`docs/legacy_ep24_prompts/`. The current EP24 prompt resources live under
`src/laclaugpt_data_analysis/prompts/ep24/`; the AI26 profile is separate under
`prompts/ai26/`.

## Non-goals

The modern pipeline does not reproduce the legacy code, does not reintroduce
numbered OCR/frame columns as canonical fields, and does not let network
measures substitute for Laclaudian interpretation.
