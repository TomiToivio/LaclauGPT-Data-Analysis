# Pipeline context audit

This document answers the operational question: **what did each LLM-assisted model call know, where did that information come from, and was it source evidence or contextual memory?**

It was created for issue #55 after auditing the production paths on `main`. The durable contract is `AnalysisContextBundle` in `src/laclaugpt_data_analysis/analysis_context.py`, with production-facing selection in `context_orchestration.py`. It composes the existing `ContextItem` / `ContextSnapshot`, `PromptEnvelope`, `PipelineContext`, periodic-summary and RAG mechanisms rather than creating a parallel memory system.

## Context contract

Every LLM-assisted stage should be describable through these fragments:

| Fragment | Evidence role | Typical source | Notes |
|---|---|---|---|
| project background | context | versioned project resource/private overlay | compact study background; never proof of the current document |
| theory/method | context | versioned theory resource | selected by task; OCR/entity extraction should not receive unnecessary theory |
| source profile | context | source metadata/researcher profile | source/actor prior knowledge; may be contradicted by the current item |
| codebook | context | public/private project codebook | researcher prior, not current-source evidence |
| situational summary | context | preceding compatible periodic summary | explicitly `context_not_evidence`; must precede the current item/window |
| memory | context | reviewed/corpus context via `context_runtime` | bounded by context profile; rejected memory is excluded |
| RAG | context | MongoDB/Neo4j/vector/graph/hybrid retrieval | bounded and provenance tracked; current-record self retrieval is removed |
| current source | **source evidence** | canonical record | source metadata, content, raw capture and raw metadata |
| previous analysis | provisional context | canonical intermediate/stage outputs | ASR, OCR, frames, frame analysis, translations and earlier stage outputs |
| task contract | instruction | versioned prompt library | detailed task plus structured output contract |

`AnalysisContextFragment` records kind, source, revision, trust, evidence role, record IDs, metadata, character length and SHA-256. `AnalysisContextBundle.audit_snapshot()` provides one inspectable machine-readable answer to “what did this call know?”

## Audited baseline before issue #55

| Stage/runtime | Project background | Theory | Codebook/source profile | RAG/memory | Periodic summary | Current evidence | Previous stages | Task/schema | Baseline problem |
|---|---|---|---|---|---|---|---|---|---|
| old `pipeline.py::analyze_record()` | none | `laclau.system:v1` only | codebook relevance block | none | none | text + URL only | no | `laclau.document_analysis:v1` + Pydantic schema | compatibility path bypassed canonical envelope |
| canonical frame analysis | caller-populated | brief system guardrails | flat codebook + optional source context | no RAG by design | caller-dependent | canonical serialization + frame metadata | preprocessing outputs | versioned prompt + `FrameProposal` | actual image attachment was not demonstrated by this path |
| canonical summary | caller-populated | brief guardrails | flat codebook labels/aliases | only via RAG wrapper/caller | caller-dependent | full canonical serialization | yes | versioned prompt + `SummaryProposal` | context architecture existed but runtime loading was not centralized |
| canonical discourse | caller-populated | brief guardrails | flat codebook labels/aliases | only via RAG wrapper/caller | caller-dependent | full canonical serialization | yes | versioned prompt + `DiscourseProposal` | rich method/project/situational context depended on caller strings |
| restricted reprocessing / Roihu | project ID string | indirect | codebook passed | not centralized | not automatically loaded | canonical record + preprocess output | yes | canonical prompts | production context population was thin |
| distributed worker | static/minimal project note | indirect | frozen codebook | path-dependent | not automatically loaded | canonical record | yes | canonical prompts | production population was minimal/static |
| periodic summary synthesis | project/scope/window | summary prompt guardrails | aggregates | previous summaries only | native stage | aggregate evidence refs | prior summaries | `periodic_summary.narrative:v1` | already correctly separated historical context from evidence |
| plugins | plugin-specific | plugin-specific | plugin-specific | plugin-specific | usually absent | varied | varied | varied | no common declaration/audit surface |

## After issue #55

| Stage/runtime | Context assembly | Evidence/context separation | Retrieval/time policy | Provenance / remaining caveat |
|---|---|---|---|---|
| `pipeline.py::analyze_record()` | `AnalysisContextBundle` -> canonical `PromptEnvelope` | current canonical source is `source_evidence`; project/theory/codebook/summary/memory/RAG are contextual | optional project, theory, situational, memory and RAG arguments use the same envelope semantics | records `context_audit`, profile and envelope provenance; no longer a scientifically distinct text-only prompt path |
| production context orchestration | `assemble_analysis_context()` with `AnalysisContextPolicy` + `StageContextPolicy` | source/codebook formation hints explicitly labelled priors; rejected memory removed | stage-specific RAG; self-retrieval removed; periodic summary selected with `before=record_timestamp` | retrieval audit, context hashes and multimodal visibility declaration included |
| canonical frame | canonical envelope remains the execution surface | source vs previous analysis stay separate | default policy disables theory/summary/memory/RAG for frame description | current provider call is conservatively recorded as `textual_derivatives_only` unless an adapter explicitly attaches pixels/audio; textual frame metadata is not claimed as visual perception |
| canonical summary/discourse | canonical envelope plus production bundle adapter | codebook and source profile are priors; current canonical source remains evidence | `high_accuracy` enables bounded theory/summary/RAG; `fast_local` is an explicit ablation profile | rich context can be assembled consistently by local, distributed and batch callers without duplicating RAG/memory systems |
| periodic summary | `PeriodicDiscourseSummary` / repository | `historical_summary_context`, `context_not_evidence` | historical selection is by record/corpus timestamp, not wall clock | summary ID/hash/window appear in context metadata/provenance |
| RAG/memory | existing `RetrievalBackend` + `context_runtime` | retrieved text remains context; rejected memory is excluded | per-stage mode/top-k/depth; current canonical ID removed from results | `RetrievalAudit.to_dict()` retained in bundle provenance |
| project resources | versioned Markdown resources plus private overlay path | all project resources are context | public-safe AI26, EP24 and Hungary26 examples; project selected by config/path | generic engine has no mandatory AI26 semantics |
| theory | versioned `contexts/theory/evidence_first_v1.md` | method context only | high-accuracy/validation profiles include it; fast-local omits it | task-specific richer resources can be added without dumping the whole paper into every task |

## Context profiles and ablation

The existing `context_runtime.py` remains the deterministic budget/policy layer. `high_accuracy` and `validation` now enable the theory/RAG classes they are intended to exercise. `fast_local` intentionally suppresses theory, periodic-summary injection and RAG, providing a useful source-oriented ablation baseline rather than accidental low-context behavior.

This makes comparative research runs possible along a simple ladder: source-only/minimal -> project -> theory -> codebook/source profile -> previous-stage outputs -> situational summary -> RAG. Context should be judged empirically rather than assumed to improve results simply because it is larger.

## Project and theory resources

Public-safe versioned project resources live under `contexts/projects/`:

- `ai26_v1.md`
- `ep24_generic_v1.md`
- `hungary26_generic_v1.md`

Private source lists, annotations, codebooks and operational settings remain outside the public repository and can be supplied as configured overlays. Generic code contains no mandatory project-specific formation labels.

`contexts/theory/evidence_first_v1.md` supplies the shared evidence-first methodological floor: articulation is relational, frequency is not hegemony, ambiguity is not empty signification, negative sentiment is not antagonism, affect is not sentiment, formation labels are provisional, corpus claims need corpus evidence, and abstention is valid.

## Source/codebook trust semantics

`source_profile_text()` can expose platform, source type, author/account, language, country, arena/actor type, organization/party and an optional researcher source/formation hint. It always states that these are contextual priors. `analysis_context.codebook_context()` similarly tells the model that codebook entries are not proof that the current item expresses a formation or stance, and that contradiction, hybridity and abstention are valid.

A formation hint can therefore guide interpretation without becoming an evidence reference. Quotations and current-document claims must still come from current canonical source evidence.

## RAG and context memory

`assemble_analysis_context()` uses the existing retrieval and context-runtime abstractions. It applies stage policy, project filters, top-k/depth, excludes the current record from retrieved results, and filters memory marked `rejected`. Accepted/reviewed memory remains trust-labelled. The full retrieval audit is retained separately from rendered text.

The default `high_accuracy` policy enables bounded RAG for summary, discourse, validation and compatibility/document analysis while leaving frame description without RAG by default. `fast_local` disables RAG through the existing profile policy.

## Periodic summary integration and historical time

The context orchestrator calls `PeriodicSummaryRepository.latest(project_id, scope, before=record_timestamp)`. The timestamp is the source event/creation time, falling back to collection time, so EP24/Hungary26 historical reprocessing cannot accidentally receive a summary from the future merely because the batch is executing today.

The selected summary is rendered with the explicit banner `HISTORICAL SUMMARY CONTEXT — NOT CURRENT-SOURCE EVIDENCE` and carries summary ID/hash/window metadata. It remains situational memory, never a quotation source for the current item.

## Multimodal evidence audit

The canonical source and previous-analysis sections expose frame records, OCR, ASR, translations and prior frame analysis. That proves visibility of textual derivatives, **not** direct visibility of pixels or audio. The unified context provenance therefore defaults to:

```text
multimodal_visibility.declared = textual_derivatives_only
```

A provider adapter must change/augment this provenance only when it actually attaches image/frame/audio bytes to the model request. A frame ID, file path or OCR transcript is not equivalent to the model seeing the image. This prevents the pipeline from making a false multimodal claim.

## Prompt/context injection hygiene

Current source text, RAG text and memory remain inside structurally named user/context sections. They are never interpolated into the trusted system/method resource. Their provenance carries a trust class and evidence role. External instructions encountered inside source/RAG material are therefore data, not pipeline instructions.

Task contracts continue to come from the versioned prompt library and machine fields remain Pydantic/provider-structured. Human-readable Markdown remains a separate narrative surface where the analysis stage provides it.

## Budgeting and truncation

`ContextProfile` supplies deterministic `max_context_chars`, `max_records` and token hints. `context_runtime.assemble_context()` remains the bounded renderer for theory, previous summaries, memory and RAG. The typed bundle keeps current canonical source evidence in its own fragment instead of silently mixing it into that historical-context budget.

An oversized current source must not be silently truncated by the memory budget. Model-specific source chunking/hierarchical synthesis should be explicit and recorded by the caller/provider path when needed.

## Reproducibility and provenance

For each model-assisted stage retain, where applicable:

- prompt resource IDs, versions and hashes;
- rendered prompt hash;
- model/provider/endpoint/fallback provenance;
- `AnalysisContextBundle.audit_snapshot()` fragment hashes, sizes, trust and evidence roles;
- context profile;
- RAG request ID/mode/filters/selected IDs/scores/paths;
- periodic-summary ID/hash/window;
- codebook/config/project-context revisions;
- canonical source URL/record identity;
- previous-stage outputs;
- declared multimodal visibility.

The compatibility path now writes the context audit into both the model-run and analysis provenance records. Canonical staged paths already retain envelope provenance and can consume the same `PipelineContext` adapter from the production orchestrator.

## Remaining operational boundary

`AnalysisContextBundle` and `assemble_analysis_context()` are the canonical context contract. Production local, distributed and Roihu launchers should construct their `PipelineContext` through this assembler rather than manually writing ad-hoc strings. Existing canonical execution functions intentionally remain backwards compatible with an explicitly supplied `PipelineContext`; this is useful for tests and ablation runs, but manual caller strings should not be treated as the preferred production configuration.

The rule is simple: **a future researcher should be able to reconstruct not only what the model answered, but what evidence it saw, what contextual knowledge it was allowed to use, and what analytical task it was instructed to perform.**
