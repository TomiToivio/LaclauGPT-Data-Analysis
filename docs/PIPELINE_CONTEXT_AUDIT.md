# Pipeline context audit

This document answers the operational question: **what did each LLM-assisted model call know, where did that information come from, and was it source evidence or contextual memory?**

It was created for issue #55 after auditing the production paths on `main`. The durable target contract is `AnalysisContextBundle` in `src/laclaugpt_data_analysis/analysis_context.py`. It composes the existing `ContextItem` / `ContextSnapshot`, `PromptEnvelope`, `PipelineContext`, periodic-summary and RAG mechanisms rather than creating a parallel memory system.

## Context contract

Every LLM-assisted stage should be describable through these fragments:

| Fragment | Evidence role | Typical source | Notes |
|---|---|---|---|
| project background | context | versioned project resource/private overlay | compact study background; never proof of the current document |
| theory/method | context | versioned theory resource | selected by task; OCR/entity extraction should not receive unnecessary theory |
| source profile | context | source metadata/researcher profile | source/actor prior knowledge; may be contradicted by the current item |
| codebook | context | public/private project codebook | researcher prior, not current-source evidence |
| situational summary | context | preceding compatible periodic summary | explicitly `context_not_evidence`; must precede the current item/window |
| memory | context | reviewed/corpus context via `context_runtime` | bounded by context profile |
| RAG | context | MongoDB/Neo4j/vector/graph/hybrid retrieval | bounded and provenance tracked; never cited as current-source evidence |
| current source | **source evidence** | canonical record | source metadata, content, raw capture and raw metadata |
| previous analysis | provisional context | canonical intermediate/stage outputs | ASR, OCR, frames, frame analysis, translations and earlier stage outputs |
| task contract | instruction | versioned prompt library | detailed task plus structured output contract |

`AnalysisContextFragment` records kind, source, revision, trust, evidence role, record IDs, metadata, character length and SHA-256. `AnalysisContextBundle.audit_snapshot()` provides one inspectable machine-readable answer to “what did this call know?”

## Current-state audit

| Stage/runtime | Project background | Theory | Codebook/source profile | RAG/memory | Periodic summary | Current evidence | Previous stages | Task/schema | Current status/problem |
|---|---|---|---|---|---|---|---|---|---|
| `pipeline.py::analyze_record()` | no dedicated project layer | `laclau.system:v1` only | codebook relevance block | none | none | `record.content.text` + URL only | no | `laclau.document_analysis:v1` + Pydantic schema | **compatibility path remains context-poor and should be migrated to `AnalysisContextBundle` / canonical envelope before being treated as scientifically equivalent to the canonical pipeline** |
| canonical frame analysis | caller-populated `PipelineContext.project_context` | system guardrails | full codebook rendered into memory; caller source context | no RAG by default | caller-populated situational context | canonical source serialization plus frame metadata in task | preprocessing outputs are serialized in previous-analysis section | `laclau.frame_analysis:v1` + `FrameProposal` | envelope is good, but project/theory/source population is caller-dependent; verify model-provider visual attachment separately from textual frame metadata |
| canonical summary | caller-populated | system guardrails + project note | codebook aliases/labels; caller source context | only when caller/RAG wrapper populates it | only when caller injects it | full canonical source serialization | ASR/OCR/frames/translations/stage outputs/existing analysis | `laclau.summary_analysis:v1` + `SummaryProposal` | strong envelope, inconsistent production population |
| canonical discourse | caller-populated | system guardrails + project note | codebook aliases/labels; caller source context | only when caller/RAG wrapper populates it | only when caller injects it | full canonical source serialization | all previous canonical analysis | `laclau.discourse_analysis:v1` + `DiscourseProposal` | strong envelope, but richer task-specific theory should be supplied as a first-class method fragment rather than hidden in ad-hoc caller strings |
| `rag_pipeline.py` | inherited from base `PipelineContext` | inherited | inherited | bounded retrieval for summary/discourse | inherited | canonical record | yes | canonical prompt resources | correct architectural location for retrieval; retrieval must remain labelled context, exclude/reduce current-document self retrieval and record retrieval audit |
| restricted reprocessing / CSC Roihu | currently project ID string | indirect system prompt only | codebook passed | no centralized context loader in the visible runner | not automatically loaded | canonical record + staged/preprocessed media outputs | yes | canonical prompts | **production population is too thin:** visible call constructs `PipelineContext(project_context=self.config.project_id)` |
| distributed worker | static/minimal project note in current worker | indirect | frozen codebook | path-dependent | not automatically loaded | canonical record | yes | canonical prompts | production context population is minimal/static and should use the same loader/profile rules as local and Roihu paths |
| periodic summary synthesis | project/scope/window in summary entity | summary-specific prompt guardrails | aggregates, not source codebook dump | previous summaries as bounded context only | the current object is the periodic summary stage itself | deterministic aggregate evidence refs | prior compatible summaries | `periodic_summary.narrative:v1` | correctly marks historical summary context as not current evidence; can be injected into later `PipelineContext` with ID/hash provenance |
| Luhmann/other plugins | plugin-specific | plugin-specific | plugin-specific | audit per plugin call | usually absent | varies | varies | varies | every plugin that calls an LLM should eventually accept the same bundle or explicitly document why it needs a smaller subset |

## Verified strengths

`context_envelope.py` already provides a good separation of `PROJECT CONTEXT`, `SOURCE CONTEXT`, `SITUATIONAL CONTEXT`, `CONTEXT MEMORY`, `RAG CONTEXT`, `CURRENT SOURCE ITEM`, `PREVIOUS ANALYSIS` and `TASK`. `source_item_text()` serializes canonical source metadata/content/raw capture; `previous_analysis_text()` serializes ASR, OCR, frames, frame analysis, translations, stage outputs, human-readable outputs, existing analysis and legacy material.

`context_runtime.py` already provides deterministic, bounded `assemble_context()` behavior with profiles, hashes and source provenance. It should remain the policy/budget mechanism for memory and retrieved items rather than being duplicated.

The periodic-summary implementation provides the missing situational-memory layer and explicitly labels prior summaries as `historical_summary_context` / `context_not_evidence` before injection into later analysis.

## Gaps and migration rules

1. **No scientifically distinct hidden compatibility semantics.** `pipeline.py::analyze_record()` is a legacy/simple path until it is migrated to the same bundle/envelope semantics. New production runners should prefer the canonical pipeline.
2. **Production callers must populate context, not merely expose fields.** A structurally perfect empty envelope is still an empty envelope. Reprocessing, distributed and local runners should share one project/profile-aware context loader.
3. **Theory is selected by task.** `contexts/theory/evidence_first_v1.md` is the baseline evidence-first method context. Rich Laclau/Palonen or sociotechnical-imaginary resources may be added separately and selected only for interpretive stages.
4. **Project background is versioned and compact.** `contexts/projects/ai26_v1.md` is the first public-safe example. EP24/Hungary26 can use generic public resources plus private overlays without leaking restricted settings.
5. **Codebook priors are not evidence.** `analysis_context.codebook_context()` explicitly tells the model that actor/formation associations may be contradicted and that hybridity/abstention are valid.
6. **RAG has a question and a budget.** Retrieval should be stage-specific, project-isolated, filtered where useful, provenance-tracked and bounded by `ContextProfile`. Rejected analysis must not return as positive memory.
7. **Periodic summaries are situational context only.** Only compatible summaries preceding the current item/window should be used. Summary IDs/hashes belong in provenance.
8. **Current evidence remains canonical.** Quotations and source-level theoretical claims must be grounded in current canonical source evidence, not memory, codebooks, project descriptions or previous model prose.
9. **Multimodal evidence must be explicit.** Canonical previous-analysis serialization exposes frame/OCR/ASR results, but a provider call that is meant to inspect pixels must also verify that the actual image/frame payload is supplied by the multimodal adapter. Textual metadata about a frame is not equivalent to seeing the frame.

## Recommended task policy

| Task | Project | Theory | Codebook/source | Previous summary | RAG | Current evidence | Previous stages |
|---|---:|---:|---:|---:|---:|---:|---:|
| deterministic preprocessing | minimal | no | identifiers only | no | no | yes | no |
| frame/image description | compact | evidence-first only | relevant source/codebook | optional/no | no by default | actual visual evidence + canonical metadata | preprocess |
| summary/pre-analysis | yes | evidence-first | relevant | yes | optional hybrid | yes | yes |
| discourse analysis | yes | evidence-first + task-specific Laclau/Palonen | relevant | yes | hybrid where configured | yes | yes |
| validation/review | yes | method + validation rules | relevant | bounded | reviewed-memory emphasis | yes | yes |

## Reproducibility and provenance

For each model-assisted stage retain:

- prompt resource IDs, versions and hashes;
- rendered prompt hash;
- model/provider/endpoint/fallback provenance;
- `AnalysisContextBundle.audit_snapshot()` or equivalent fragment hashes;
- RAG retrieval audit and record IDs when retrieval is used;
- periodic-summary ID/hash when situational context is used;
- codebook/config/project-context revisions;
- canonical source URL/record identity.

The rule is intentionally simple: **a future researcher should be able to reconstruct not only what the model answered, but what information classes were made available to it and which of those classes were evidence versus context.**
