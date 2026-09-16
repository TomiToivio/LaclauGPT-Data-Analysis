# Pipeline context audit

This document answers the operational question: **what did each LLM-assisted model call know, where did that information come from, and was it source evidence or contextual memory?**

Issue #55 establishes `AnalysisContextBundle` as the typed context contract, `context_orchestration.py` as the production selector/policy layer, and the existing `PromptEnvelope` as the canonical rendered model-call surface. The implementation composes the existing `ContextItem` / `ContextSnapshot`, `PipelineContext`, periodic-summary and RAG mechanisms rather than creating a parallel memory system.

## Context contract

| Fragment | Evidence role | Typical source | Rule |
|---|---|---|---|
| project background | context | versioned project resource/private overlay | study prior, never proof of a current document |
| theory/method | context | versioned theory resource | selected by task, not dumped into every stage |
| source profile | context | source metadata/researcher profile | may guide interpretation but may be contradicted |
| codebook | context | public/private project codebook | researcher prior, not source evidence |
| situational summary | context | preceding compatible periodic summary | `context_not_evidence`; must precede the item/window |
| memory | context | reviewed/corpus context | bounded by context profile; rejected memory excluded |
| RAG | context | MongoDB/Neo4j/vector/graph retrieval | bounded, audited, self-retrieval removed |
| current source | **source evidence** | canonical record | source metadata/content/raw capture |
| multimodal attachment | **source evidence** | readable local frame media | actual pixels only when attached to provider request |
| previous analysis | provisional context | ASR/OCR/frame analysis/translations/stage outputs | visible as previous analysis, not raw source evidence |
| task contract | instruction | versioned prompt library | explicit task + structured output contract |

`AnalysisContextFragment` records kind, source, revision, trust, evidence role, record IDs, metadata, size and SHA-256. `AnalysisContextBundle.audit_snapshot()` gives one machine-readable answer to “what did this call know?”

## Audited baseline before issue #55

| Stage/runtime | Baseline state | Main problem |
|---|---|---|
| old `pipeline.py::analyze_record()` | text + URL + codebook relevance block | bypassed canonical envelope and omitted richer context classes |
| canonical frame | canonical envelope + frame metadata | provider contract had no image attachment field, so pixels were not demonstrably visible |
| canonical summary/discourse | good eight-section envelope | project/theory/RAG/periodic context depended on caller-populated strings |
| reprocessing / Roihu | `PipelineContext(project_context=<project id>)` | production context population too thin |
| distributed worker | minimal/static project context | same scientific call could see less context than local/manual paths |
| periodic summary | structured temporal context already separated from evidence | needed systematic injection into later analysis |
| RAG | retrieval abstraction and audit existed | stage policy/self-retrieval/rejected-memory rules were not centralized |

## After issue #55

| Stage/runtime | Context assembly | Retrieval/time/evidence policy | Provenance |
|---|---|---|---|
| compatibility `analyze_record()` | `AnalysisContextBundle` -> canonical `PromptEnvelope` | current source is evidence; project/theory/codebook/summary/memory/RAG are contextual | context audit, profile, prompt/envelope hashes and model provenance recorded |
| production reprocessing + worker entrypoints | `contextual_entrypoints.py` -> `run_contextual_canonical_pipeline()` | same staged scientific runner for local/batch/distributed entrypoints | existing queue/storage behavior preserved; stage audits added |
| frame analysis | stage-specific bundle + `FrameAwareProvider` | no RAG/theory by default; readable local `media_ref` is attached as actual pixels; remote refs require materialization first | audit says `direct_image_pixels` only when an image was attached and records frame ID/path; otherwise `textual_derivatives_only` |
| summary/discourse | stage-specific bundle | `high_accuracy` enables theory, periodic context and bounded RAG; self/current record and rejected retrieval memory excluded | per-stage context hashes and retrieval audit retained |
| periodic summary | existing `PeriodicDiscourseSummary` repository | selected with `before=record_timestamp`, so historical EP24/Hungary26 runs cannot receive future summaries | summary ID/hash/window retained and rendered as `context_not_evidence` |
| project resources | public-safe versioned resources + explicit private overlay path | AI26/EP24/Hungary26 are configuration, not generic-engine hard-coding | resource path/revision can be recorded with context audit |
| theory | `contexts/theory/evidence_first_v1.md` | high-accuracy/validation include method context; `fast_local` is an intentional ablation | theory fragment hash/revision recorded |

## Project and theory resources

Public-safe project resources live under `contexts/projects/`:

- `ai26_v1.md`
- `ep24_generic_v1.md`
- `hungary26_generic_v1.md`

Private source lists, researcher annotations, private codebooks and operational settings remain outside the public repository and may be supplied with `LACLAUGPT_PROJECT_CONTEXT_PATH` or other approved private configuration. The generic context engine contains no mandatory AI26 formation labels.

`contexts/theory/evidence_first_v1.md` provides the shared methodological floor: articulation is relational; frequency is not hegemony; ambiguity is not automatically floating/empty signification; negative sentiment is not antagonism; affect is not sentiment; formation labels are provisional; corpus claims require corpus comparison; and abstention is valid.

## Source and codebook trust semantics

`source_profile_text()` exposes source/platform, actor/account, language, country, arena/actor type, organization/party and optional researcher hints as **contextual priors**. `codebook_context()` likewise tells the model that codebook entries are not proof that the current item expresses a formation or stance and that contradiction, hybridity and abstention are allowed.

Quotations and source-level theoretical claims must remain grounded in the current canonical source or direct multimodal attachment, never in source-profile priors, codebooks, old summaries or retrieved model prose.

## RAG and context memory

`assemble_analysis_context()` uses the existing `RetrievalBackend` and `context_runtime` abstractions. It applies stage policy, project filtering, top-k/depth, removes the current record from retrieved results, and excludes items with `review_status=rejected` or trust `rejected`. Reviewed/model-proposed memory remains trust-labelled. `RetrievalAudit.to_dict()` is retained separately from rendered text.

`high_accuracy` and `validation` now enable the theory/RAG context classes they are intended to exercise. `fast_local` suppresses theory, periodic-summary injection and RAG, making it a deliberate context-ablation profile rather than an accidental lower-quality production mode.

## Periodic summary integration and historical corpus time

The orchestrator selects the latest compatible summary with `PeriodicSummaryRepository.latest(project_id, scope, before=record_timestamp)`. Record timestamp means source creation/event time, falling back to collection time. Historical reprocessing therefore uses corpus time rather than the date on which a Roihu job happens to execute.

The selected summary carries the explicit banner `HISTORICAL SUMMARY CONTEXT — NOT CURRENT-SOURCE EVIDENCE` and remains situational memory only.

## Multimodal evidence audit

The provider-neutral `ChatRequest` now has an `images` attachment field. `FrameAwareProvider` inspects canonical frame references and, when a `media_ref` resolves to a readable local file, attaches that exact image to the matching frame-analysis request. Ollama requests place the image on the user message.

Each frame-stage context audit records one of two states:

```text
multimodal_visibility.declared = direct_image_pixels
```

when actual image pixels were attached, including the frame ID and materialized path, or:

```text
multimodal_visibility.declared = textual_derivatives_only
```

when the model saw only canonical frame metadata/OCR/other textual derivatives. An `s3://`, Allas or other remote reference is **not** falsely counted as direct visual access; preprocessing/storage must materialize it locally first. A filename, OCR transcript or frame ID is not equivalent to seeing the image.

Audio remains represented through ASR unless a future provider adapter explicitly attaches audio and records that fact.

## Stage order and previous-stage visibility

The contextual production ladder is:

1. deterministic/preprocessing enrichment;
2. frame analysis with a lean context policy and direct pixels when available;
3. summary/pre-analysis after frame results are present;
4. discourse analysis after summary/frame results are present;
5. postprocessing and discourse graph projection.

`previous_analysis_text()` serializes ASR, OCR, frames, frame analysis, translations, stage outputs, human-readable outputs and existing analysis, so later stages can explicitly use earlier results without those outputs being mislabelled as raw source evidence.

## Prompt/context injection hygiene

Source, memory and retrieved material stay in named user/context sections. They are not interpolated into the trusted system/method resource. Their provenance carries trust and evidence role. Instructions encountered inside source/RAG text therefore remain data rather than pipeline instructions.

Task contracts stay in the versioned prompt library, and machine-facing fields remain provider/Pydantic structured. Human-readable narratives remain separate surfaces.

## Budgeting and ablation

`ContextProfile` supplies deterministic context character/record/token-hint budgets. `context_runtime.assemble_context()` remains the bounded renderer for theory, previous summaries, memory and RAG. Current canonical source evidence remains a distinct fragment and is not silently truncated by a historical-memory budget.

This supports comparative runs along a controlled ladder: source/minimal -> project -> theory -> codebook/source profile -> previous-stage outputs -> periodic summary -> RAG. Richer context should be evaluated empirically rather than presumed superior merely because it is larger.

## Reproducibility checklist

For each model-assisted stage retain, where applicable:

- prompt resource IDs, versions, hashes and rendered prompt hash;
- actual model/provider/endpoint/fallback provenance;
- context profile;
- fragment kind/source/revision/trust/evidence-role/hash/size;
- canonical source identity;
- codebook/config/project resource revisions;
- RAG request ID/mode/filters/selected IDs/scores/paths;
- periodic-summary ID/hash/window;
- previous-stage outputs;
- direct multimodal attachment audit or explicit textual-derivatives-only declaration.

The production console entrypoints `laclaugpt-reprocess` and `laclaugpt-analysis-worker` are routed through the contextual staged pipeline. The lower-level canonical functions remain callable with explicit `PipelineContext` for tests and ablation experiments, but ad-hoc manually assembled caller strings are no longer the preferred production configuration.

The rule is simple: **a future researcher should be able to reconstruct not only what the model answered, but what evidence it saw, what contextual knowledge it was allowed to use, and what analytical task it was instructed to perform.**
