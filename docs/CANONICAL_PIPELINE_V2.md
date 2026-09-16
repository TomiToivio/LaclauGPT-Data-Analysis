# Canonical staged analysis pipeline

This document defines the implementation introduced for issue #20. The goal is to keep the original EP24 pipeline's researcher-readable multimodal ladder while using the current evidence-first LaclauGPT theory and canonical record.

## Order

The canonical order is:

```text
0. load canonical source + project context
1. preprocess/enrich
2. per-image/per-frame analysis
3. human-readable summary + generic NLP/social-data-science pre-analysis
4. Laclau/Mouffe/Palonen discourse pre-analysis
5. strict Pydantic postprocessing into the canonical record
6. discourse-graph/vector persistence hooks
7. daily/filtered aggregate reports
8. ordinary canonical CSV/JSONL/researcher/dashboard exports
```

Stages are deliberately separate. Do not collapse the pipeline into one giant prompt. Separation keeps retries, caching, validation, researcher inspection and dashboard fields possible.

## Prompt envelope

Every LLM call uses `context_envelope.PromptEnvelope` with the same eight ordered sections:

1. project context;
2. source/codebook context;
3. latest situational/daily report, or an explicit empty placeholder;
4. canonical context memory such as entities/signifiers/formations/aliases;
5. optional RAG results, labelled as context rather than evidence;
6. complete current source item, including the raw collector payload;
7. all previous analysis stages, including legacy fields;
8. precise current task and structured-output contract.

The envelope records provenance separately for each context family. RAG, codebooks and memory must never be silently promoted to source evidence.

## EP24 example profile

The EP24 frame prompt preserves the useful visual categories of the legacy `puhti_frame.py` pipeline:

```text
Analyse this frame in the context of the 2024 European Parliament election study.
Describe framing/shot composition, scene and background, activity, objects, subjects,
flags and political symbols, platform or screen-recording cues, visible text, usernames
and handles. Use the transcript, OCR, source metadata and prior stage results as context.
Do not infer identities that are not visually/textually supported. Candidate political
signifiers are provisional only.
```

The EP24 summary profile follows the spirit of `puhti_summary.py`: narrative reconstruction, political/domain classification, difficult language, topics, entities, sentiment for comparison with conventional NLP, claims/grievances and a light Laclaudian candidate layer. Full Laclaudian analysis belongs to the next stage.

## AI26 example profile

AI26 is grounded in the public `LaclauGPT/paper/PAPER.md` research design. It does not assume election-campaign imagery.

```text
Analyse this frame as part of AI26, a study of ideological contestation over AI.
In addition to generic visual description, inspect AI labs/models/demos, data centres,
robots, LLM interfaces, AI-generated media, corporate or policy material, protests,
memes, charts and other AI-related imagery. Record visible usernames and text. You may
identify candidate AI-related symbols/signifiers or future visions, but do not classify
an ideological formation or stabilized sociotechnical imaginary from one frame.
```

The AI26 human-readable summary additionally records claims about what AI is and can/will do, desirable and feared futures, candidate sociotechnical imaginaries, ownership/control/governance assumptions, labour/automation, safety/x-risk, Critical AI/power/inequality, acceleration/abundance and anti-AI/resistance claims when evidenced.

## Theory rules for the discourse stage

The dedicated discourse stage is governed by current `THEORY.md` semantics:

- document-level outputs remain provisional;
- frequency is not hegemony;
- polysemy is not empty signification;
- negative sentiment is not antagonism;
- sentiment is not affective investment;
- a collective label is not automatically a constructed political subject;
- populism requires an evidenced collective Us and constitutive antagonistic Frontier;
- floating/empty signifier, formation, imaginary stabilization and hegemonic claims require corpus-level comparison/validation;
- empty outputs and abstention are valid;
- human review is authoritative.

## Three data strata that must survive

The canonical record and exports must keep all of the following:

1. **Raw source**: complete API/RSS/scraper/browser payload and native metadata, including unknown collector fields.
2. **Researcher-visible intermediate/legacy data**: transcripts, translated transcripts, OCR, frames, per-frame analyses, deterministic NLP, old compatibility columns such as `whisperResult` where imported, and the human-readable summary.
3. **Current structured LaclauGPT data**: entities, topics/classifications where configured, signifiers, relations, collective subjects, frontiers, affects, formula of populism, formation/imaginary candidates, uncertainty, abstentions, evidence/provenance and review state.

The existing four-layer researcher-record/export code remains the projection layer. Issue #20 does not replace it.

## Preprocessing backends

`canonical_pipeline.preprocess_record()` accepts a preprocessor hook. A deployment can therefore compose the already-existing backends without making them hard requirements of the core package:

- spaCy NER;
- transformers/BERT classifiers;
- sentence-transformers;
- Whisper ASR;
- translation;
- OpenCV scene/keyframe extraction;
- OCR;
- BERTopic/gensim/sklearn topic methods.

A text-only record remains valid. Multimodal fields must not be fabricated merely to satisfy a flat export.

## Daily reports and context feedback

`reporting.build_daily_report()` creates an offline deterministic Markdown report plus structured top entities/signifiers/formations and source references. Reports can be filtered by:

- `signifier`;
- `author`;
- `formation`;
- `platform`;
- `country`.

The latest relevant report can be inserted into the next run's `situational_context`. Counts are candidate signals only and the report explicitly warns against reading recurrence as hegemony or theoretical status.

## RAG, memory and codebooks

The pipeline consumes, rather than replaces, the context architecture from issue #19 and `CONTEXT_MEMORY_DESIGN.md`.

- codebooks/context memory prevent entity/signifier multiplication;
- RAG is optional recall/augmentation and is kept separate from evidence;
- ChromaDB or another vector backend can implement the `VectorSink` protocol;
- ArangoDB or another graph backend can implement the `GraphSink` protocol;
- Redis may distribute current codebook/context snapshots using the existing cache namespace;
- no external service is required for offline tests or local CSV/SQLite operation.

## Discourse graph

`build_discourse_graph()` is a storage-neutral projection over canonical record objects. It uses normalized relation vocabulary such as `ARTICULATES`, `EQUIVALENT_TO`, `DIFFERENTIATED_FROM`, `ANTAGONISTIC_TO` and `CANDIDATE_IN` rather than defining a second research ontology.

An ArangoDB adapter should persist this projection while retaining evidence/provenance/review metadata. Graph storage does not make an analytical edge true merely because it exists.

## Distributed storage flow

Project namespaces now support explicit MongoDB collection states:

```text
<project>__raw         # collection/source handoff
<project>__processing  # analysis in progress / resumable state
<project>__analyzed    # visualization-ready canonical records
```

Legacy `<project>__annotations` remains available for compatibility. Local CSV/SQLite uses the same logical state names as file/table names. Large media and derived artifacts belong in local files or S3-compatible storage such as CSC Allas rather than MongoDB documents.

## Validation

Normal CI uses fake providers and synthetic records. Tests verify the eight-part prompt envelope, preservation of raw + legacy + human-readable + structured layers, provisional theory outputs, graph projection, daily report filtering and distributed collection namespaces. Live Ollama/MongoDB/Redis/Allas/ChromaDB/ArangoDB tests remain opt-in integration tests.
