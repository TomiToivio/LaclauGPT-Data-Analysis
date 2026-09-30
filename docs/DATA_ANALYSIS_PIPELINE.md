# LaclauGPT Data Analysis Pipeline

This is the canonical human-readable guide to the Phase 1 analysis path.

The design goal is simple: a researcher should be able to answer **what happens to one post, in what order, with which prompt, and where the result goes** without reverse-engineering the software framework.

The executable version of this document lives in:

```text
src/laclaugpt_data_analysis/phase1_pipeline/
    preprocess.py
    frame.py
    summary.py
    laclau.py
    postprocess.py
    runner.py
```

The older `canonical_pipeline.py` remains the compatibility engine for validated schemas, evidence/provenance handling, and established helper functions. New readers should start with `phase1_pipeline/runner.py`.

## Pipeline at a glance

```text
source record
    |
    v
1. PREPROCESS
    |
    v
2. FRAME / MULTIMODAL ANALYSIS
   only when usable visual media exists
    |
    v
3. DESCRIPTIVE SUMMARY
   all available modalities
    |
    v
4. LACLAU DISCOURSE ANALYSIS
    |
    v
5. POSTPROCESS
    |
    v
persist / export / visualize
```

The five steps are deliberately separate. Technical infrastructure such as storage, LLM providers, caches, configuration, and provenance helpers is shared rather than duplicated inside every stage.

## 1. Preprocess

File: `phase1_pipeline/preprocess.py`

Purpose: preserve the source and prepare derived material needed by later stages.

Possible inputs include:

- post text or caption;
- title and platform metadata;
- image/video/audio references;
- existing OCR;
- existing ASR/transcripts;
- already extracted frames;
- project-specific preprocessing output.

The stage preserves the original source and legacy fields. Optional project preprocessors may add ASR, OCR, frames, translations, or compatibility material.

Preprocessing is not discourse analysis. It prepares evidence.

## 2. Frame / multimodal analysis

File: `phase1_pipeline/frame.py`

Routing is **record-by-record**.

```text
usable image/video frames present?
    yes -> run visual frame analysis
    no  -> skip visual analysis cleanly
```

Materialized still images are represented as canonical timestamp-zero frames so they can use the same audited visual-analysis path as sampled video frames.

The default rule is capability-driven:

- supported usable media present -> use the multimodal path;
- text/caption + metadata only -> use the text path;
- mixed datasets may therefore contain both routes in the same project;
- missing modalities do not make the record fail;
- a remote reference alone is not treated as visual evidence until the media layer says it is materialized.

The modality plan is written into `intermediate.stage_outputs["modality_plan"]` for auditability.

## 3. Descriptive summary

File: `phase1_pipeline/summary.py`

This stage creates the evidence-preserving descriptive first pass.

It can integrate whatever is actually available:

- post text/caption;
- metadata;
- transcript / ASR;
- OCR / visible text;
- frame analyses;
- image/video-derived observations.

Text-only records use the same stage without inventing missing visual or auditory evidence.

This stage is intentionally **before Laclauian discourse interpretation**. It follows the social-semiotic pre-analysis boundary and should preserve cross-modal disagreement, uncertainty, source wording, and missing-modality information.

Prompts:

- `prompts/multimodal/system_v2.md`
- `prompts/multimodal/summary_analysis_v2.md`

## 4. Laclau discourse analysis

File: `phase1_pipeline/laclau.py`

This is the Phase 1 discourse-theoretical stage.

It may propose evidence-supported:

- demands;
- articulations;
- equivalence and difference relations;
- collective subjects;
- antagonistic frontiers;
- affective investments;
- nodal-point candidates;
- floating/empty-signifier candidates;
- ideological-formation candidates;
- sociotechnical-imaginary candidates where enabled.

Document-level outputs remain provisional. Corpus-level validation is required where the theory/method contract requires it. Abstention is valid.

Prompts:

- `prompts/laclau/system_v1.md`
- `prompts/laclau/discourse_analysis_v1.md`

Project-specific prompt context may be added without changing the canonical methodological boundary.

## 5. Postprocess

File: `phase1_pipeline/postprocess.py`

Postprocessing converts the summary and discourse proposals into the canonical analysis schema.

It:

- validates and projects structured results;
- preserves evidence links;
- preserves uncertainty and provenance;
- marks outputs provisional for human review;
- creates the legacy multimodal compatibility projection;
- prepares the record for storage, graph export, vector indexing, and visualization.

Postprocessing does not introduce a new theoretical interpretation.

## Prompt layout

Prompts are research instruments and are kept as readable Markdown files under:

```text
src/laclaugpt_data_analysis/prompts/
```

The prompt architecture is:

```text
SYSTEM / METHODOLOGICAL CONSTITUTION
    stable methodological rules

RESEARCH CONTEXT
    project, codebook, memory, RAG, researcher context + provenance

CURRENT TASK / DATA
    what to analyze now + the evidence bundle
```

See `src/laclaugpt_data_analysis/prompts/README.md`.

Prompt files are versioned and prompt provenance hashes are retained in model-run metadata.

## Project settings

Project settings belong in configuration, not scattered through scientific stage files.

Different projects may vary in:

- model choice;
- source/platform context;
- codebook context;
- enabled optional capabilities;
- media availability;
- cloud/local inference permissions;
- storage backend.

These differences must not change the canonical meaning of Phase 1 fields.

## Codebooks, memory, and RAG

These are context, not automatic source evidence.

- **Codebooks** provide researcher-defined conceptual context.
- **Memory** supports stable-ID continuity and previously accepted mappings.
- **RAG** retrieves relevant research material.

The source record remains the evidentiary basis for claims about the item being analyzed unless a method explicitly defines another source.

## Storage and databases

Storage is intentionally outside the scientific stage logic.

The same analysis path can be used with local files/SQLite or distributed MongoDB/Redis/S3-style deployments. Backend choice must not change the canonical schema or scientific interpretation.

## Human review

Every LLM-generated interpretation is provisional.

Human review is not a cosmetic final approval step. Researchers remain responsible for:

- checking source evidence;
- rejecting hallucinated or weak proposals;
- evaluating uncertainty;
- resolving ambiguous signifiers and relations;
- validating corpus-level theoretical claims;
- deciding what can be reported as a research finding.

## Legacy compatibility

The readability model comes from the legacy repository:

https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis

Its visible sequence was roughly:

```text
puhti_preprocess.py
puhti_frame.py
puhti_summary.py
puhti_populism.py
puhti_postprocess.py
```

The modern implementation keeps the useful idea that the scientific pipeline should be visible as separate steps, while retaining canonical records, provider-neutral inference, provenance, project configuration, and modern storage adapters.

Legacy EP24-style fields are translated through compatibility adapters/projections rather than being spread through every scientific stage.

## Reading the code

For the fastest route through the implementation, read these files in order:

1. `phase1_pipeline/runner.py`
2. `phase1_pipeline/preprocess.py`
3. `phase1_pipeline/frame.py`
4. `phase1_pipeline/summary.py`
5. `phase1_pipeline/laclau.py`
6. `phase1_pipeline/postprocess.py`
7. the referenced Markdown prompts

Only then descend into `canonical_pipeline.py`, storage adapters, LLM provider code, or schema helpers when you need implementation details.

That separation is intentional: **readability is part of the research software contract.**
