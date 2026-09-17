# Canonical staged analysis pipeline

This document defines the canonical staged Analysis pipeline. The design keeps the original EP24 pipeline's researcher-readable multimodal ladder while enforcing a clearer evidence-first boundary for AI26 and future multimodal studies.

## Order

The canonical order is:

```text
0. load canonical source + project context
1. preprocess/enrich: ASR, translation, OCR, frames/keyframes, deterministic NLP
2. per-image/per-frame multimodal evidence analysis
3. item-level multimodal synthesis + light sociological context
4. Laclau/Mouffe/Palonen discourse analysis
5. specialised plugins/stages such as DNA or Critical AI Studies
6. strict Pydantic postprocessing into the canonical record
7. discourse-graph/vector persistence hooks
8. daily/filtered aggregate reports
9. ordinary canonical CSV/JSONL/researcher/dashboard exports
```

Stages are deliberately separate. Do not collapse the pipeline into one giant prompt. Separation keeps retries, caching, validation, researcher inspection and dashboard fields possible, and prevents early multimodal description from silently becoming ideology classification.

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

`PipelineContext` additionally carries optional configuration, codebook, context and project-configuration revisions. Model-run provenance stores those revisions, a deterministic SHA-256 hash of the project configuration, exact prompt-resource IDs/versions/hashes, rendered-prompt hash, and the resolved provider/model provenance.

## EP24 / historical compatibility

EP24 and generic historical runs keep the versioned prompt resources used by the earlier canonical path:

- `laclau.system:v1`
- `laclau.frame_analysis:v1`
- `laclau.summary_analysis:v1`
- `laclau.discourse_analysis:v1`

These files remain loadable for reproducibility. The EP24 frame prompt preserves useful legacy visual categories such as framing, scene, activity, objects, subjects, flags/symbols, platform cues and visible text. Historical summary outputs may retain their bounded candidate layer because they are explicitly a compatibility path, not the AI26 default.

## AI26 multimodal pre-analysis

AI26 now uses a different prompt family for stages 2 and 3:

```text
multimodal.system:v1
+ multimodal.frame_analysis:v1
+ multimodal.summary_analysis:v1
```

The method is grounded primarily in Bateman, Wildfeuer & Hiippala's problem-oriented multimodality and is compatible with the wider social-semiotic tradition. The goal is a reusable semiotic evidence layer before discourse theory.

### Stage 2: per-frame semiotic description

The AI26 frame schema records only descriptive/semiotic fields:

- material/canvas organisation and embedded regions;
- scene and participants;
- subjects, objects and activities;
- visual composition;
- visible text, usernames, symbols and interface cues;
- provenance/usage cues;
- concise semiotic contribution;
- uncertainty/evidence limits.

The schema intentionally has no fields for signifiers, frontiers, formations, populism, hegemony or ideological classification. Empty/uncertain output is valid.

AI26 project-specific relevance guidance is injected through the `{project_note}` variable rather than hard-coded into the generic multimodal method. It may draw attention to AI/LLM interfaces, labs/firms/policy actors, compute and data-centre infrastructure, robots, generated media, benchmarks/charts, regulation/safety/labour/environmental material, protests/memes/online communities and quoted media when those elements are actually present. The project note is context, not evidence.

### Stage 3: item synthesis + light Castells context

The item-level multimodal synthesis combines available source metadata, transcript/translation, OCR, frame analyses, audio observations and deterministic NLP. It reconstructs narrative/temporal sequence and records how modes reinforce, elaborate, anchor, contradict, quote/recontextualise or substitute for each other.

Its structured output contains conventional descriptive categories such as topics, entities, claims, demands, grievances, difficult language, event/time/location candidates and evidence-backed sentiment observations. Contradictions between modalities are preserved rather than silently resolved.

A separate `castells_context` intermediate stage provides a deliberately light reading inspired by *The Rise of the Network Society*. It can record only evidence-backed candidates for:

- actors / organisations / institutions;
- explicit or strongly implied networks and relations;
- flows of information, images, capital, technology, authority, people or other resources;
- nodes / hubs / communication channels;
- local embodied places and mediated/translocal `space of flows`;
- observable or explicitly claimed power/access/exclusion relations;
- uncertainty.

This is not formal SNA. Empty `networks_relations` or other Castells fields are correct when the source does not establish them. The model must not invent centrality, brokerage, structural holes, institutional power or unseen ties.

The synthesis ends with `Later analysis cues`. These are questions/candidates for downstream theoretical stages, not classifications. The AI26 multimodal summary schema therefore has no direct signifier/frontier/formation fields.

## Stage 4: dedicated discourse analysis

After multimodal pre-analysis, AI26 returns to the Laclau prompt family:

```text
laclau.system:v1
+ laclau.discourse_analysis:v1
```

This dedicated stage remains responsible for signifiers, articulations, equivalence/difference, collective subjects, frontiers, antagonism, affective investment, populism, formations, imaginaries and related theory-facing candidates. Document-level outputs remain provisional and may require corpus-level comparison.

The theory safeguards remain:

- frequency is not hegemony;
- polysemy is not floating or empty signification;
- negative sentiment is not antagonism;
- sentiment is not affective investment;
- a collective label is not automatically a constructed political subject;
- populism requires an evidenced collective Us and constitutive antagonistic Frontier;
- floating/empty signifier, formation, imaginary stabilization and hegemonic claims require corpus-level comparison/validation;
- empty outputs and abstention are valid;
- human review is authoritative.

## Later specialised stages

DNA, Critical AI Studies, Bourdieu, Luhmann and other specialised plugins/stages may consume the same grounded intermediate record after the multimodal synthesis. They must not be folded back into the generic multimodal prompt. This preserves a common evidence layer that multiple theories can inspect independently.

## Data strata that must survive

The canonical record and exports keep all of the following:

1. **Raw source**: complete API/RSS/scraper/browser payload and native metadata, including unknown collector fields.
2. **Source representations / preprocessing**: transcripts, translations, OCR, frames/keyframes and deterministic NLP.
3. **Multimodal intermediate evidence**: per-frame semiotic analysis, item-level multimodal synthesis, light Castells context, exact prompt/model provenance and the human-readable synthesis.
4. **Later structured analysis**: entities/topics/classifications where configured, Laclau/Mouffe/Palonen outputs, specialised plugin results, uncertainty, abstentions, evidence/provenance and review state.
5. **Legacy compatibility**: imported historical columns and prompt paths remain available without defining the new default method.

A text-only record remains valid. Multimodal fields must not be fabricated merely to satisfy a flat export.

## Preprocessing backends

`canonical_pipeline.preprocess_record()` accepts a preprocessor hook. A deployment can therefore compose existing backends without making them hard requirements of the core package:

- spaCy NER;
- transformers/BERT classifiers;
- sentence-transformers;
- Whisper ASR;
- translation;
- OpenCV scene/keyframe extraction;
- OCR;
- BERTopic/gensim/sklearn topic methods.

## Daily reports and context feedback

`reporting.build_daily_report()` creates an offline deterministic Markdown report plus structured top entities/signifiers/formations and source references. Reports can be filtered by signifier, author, formation, platform or country. The latest relevant report can be inserted into the next run's `situational_context`; counts are candidate signals only and do not establish hegemony or theoretical status.

## RAG, memory and codebooks

The pipeline consumes, rather than replaces, the context architecture from `CONTEXT_MEMORY_DESIGN.md`.

- codebooks/context memory prevent entity/signifier multiplication;
- RAG is optional recall/augmentation and is kept separate from evidence;
- ChromaDB or another vector backend can implement the `VectorSink` protocol;
- ArangoDB or another graph backend can implement the `GraphSink` protocol;
- Redis may distribute current codebook/context snapshots using the existing cache namespace;
- no external service is required for offline tests or local CSV/SQLite operation.

## Discourse graph

`build_discourse_graph()` is a storage-neutral projection over canonical record objects. It uses normalized relation vocabulary such as `ARTICULATES`, `EQUIVALENT_TO`, `DIFFERENTIATED_FROM`, `ANTAGONISTIC_TO` and `CANDIDATE_IN` rather than defining a second research ontology.

## Distributed storage flow

Project namespaces support explicit MongoDB collection states:

```text
<project>__raw         # collection/source handoff
<project>__processing  # analysis in progress / resumable state
<project>__analyzed    # visualization-ready canonical records
```

Legacy `<project>__annotations` remains available for compatibility. Local CSV/SQLite uses the same logical state names as file/table names. Large media and derived artifacts belong in local files or S3-compatible storage such as CSC Allas rather than MongoDB documents.

## Validation

Normal CI uses fake providers and synthetic records. Tests verify prompt loading/hashing/rendering, AI26 multimodal prompt selection, preservation of raw + legacy + human-readable + structured layers, uncertainty/abstention, contradictory modalities, empty Castells network fields, exact model/prompt/config provenance, dedicated discourse-stage separation, graph projection, daily report filtering and distributed collection namespaces. Live vision/Ollama/MongoDB/Redis/Allas tests remain opt-in integration tests.
