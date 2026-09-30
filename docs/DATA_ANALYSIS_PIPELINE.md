# Data analysis pipeline

What LaclauGPT does to one post, in order, with which prompt, and where the
result goes. Written to be readable by a researcher who knows Python but not the
framework.

This is the canonical pipeline document. Where another document disagrees with
this one, this one is correct.

## The pipeline in execution order

```text
source record (canonical)
  │
  ├─ 1. preprocess ................ extract ASR, OCR, keyframes, translations
  │                                  (no interpretation)
  │
  ├─ 2. modality routing .......... decide from the record what can be analysed
  │      │
  │      ├─ if usable visual media → 2a. frame analysis (per frame, descriptive)
  │      └─ else                  → (skipped, recorded as such)
  │
  ├─ 3. summary ................... descriptive first pass over the whole item
  │                                  (text + caption + transcript + OCR + frames)
  │
  ├─ 4. laclau .................... Laclau/Mouffe discourse analysis
  │                                  (the theory-bearing stage)
  │
  ├─ 5. postprocess ............... write the canonical analysis record
  │                                  (every object marked PROVISIONAL)
  │
  └─ 6. discourse graph ........... project for export / dashboard
                                     (+ optional graph and vector sinks)
```

Optional Phase 2 stages run only after the six steps above, and only when a
project explicitly declares them (see [Project configuration](#project-configuration)).

## Where the code lives

The pipeline is one module per step. Read them in this order:

```text
src/laclaugpt_data_analysis/stages/
  runner.py        <- START HERE: thin sequencing of everything below
  shared.py        plumbing: context, prompt envelope, provenance, capabilities
  proposals.py     the schemas a model stage may return
  prompt_map.py    which prompt each stage uses
  preprocess.py    stage 1
  frame.py         stage 2a
  summary.py       stage 2b
  laclau.py        stage 3
  postprocess.py   stage 4
  graph.py         stage 5
  evidence.py      evidence verification (the integrity rule)
```

`canonical_pipeline.py` at the package root is a **compatibility facade**: it
re-exports the same objects for existing callers, so `PipelineContext` there *is*
the one in `stages/`. New code should import from `laclaugpt_data_analysis.stages`.

## Stage by stage

### 1. preprocess

**What it does.** Turns a captured record into one carrying all derived inputs:
transcript, visible text, keyframes, translations.

**Why it exists.** Extraction is expensive and fallible, and studies differ (one
corpus has video, another is text-only). Keeping enrichment in one place means
extraction failures stay attributable to extraction rather than to
interpretation.

**In → out.** `record` → the same record with `intermediate.asr / ocr / frames /
translations` extended. Adds the `preprocess_contract` stage record stating the
source was preserved.

**Boundary.** It adds *representations of the source*, never *claims about it*.

### 2. modality routing, then 2a. frame analysis

**What it does.** Decides what can be analysed, then describes each usable frame.

**Why it exists.** A frame is analysed on its own; the summary then synthesises
across frames and text. Collapsing the two would let one image's reading become
the item-level description and would make per-frame retry impossible.

**In → out.** `record` → `intermediate.frame_analysis` (one entry per frame),
plus the `modality_plan` and `multimodal_visibility` stage records.

**Boundary.** Descriptive only. The pre-analysis boundary check
(`assert_preanalysis_boundary`) forbids ideology or populism classification here.

### 3. summary (descriptive first pass)

**What it does.** Describes the item: what it says, its entities and topics, its
claims, demands and grievances, its imagined futures.

**Why it exists.** The theory stage must rely on a description it did not write.
That is what makes the description reviewable on its own, and keeps a theory
change from silently altering it.

**In → out.** `record` → returns the summary proposal; writes
`human_readable.summary / generated_at / markdown`; records
`multimodal_synthesis`.

**Boundary.** Descriptive, not interpretive — the same boundary check applies.

### 4. laclau (discourse analysis)

**What it does.** Analyses how the item articulates meaning: demands, nodal
points, floating and empty signifiers, collective subjects, frontiers, and
whether the articulation is populist in the sense the project tests.

**Why it exists.** This is the theory stage. It is the most interpretive step, so
it runs last among the model stages and consumes a description it did not write.

**In → out.** `record` → returns the `DiscourseProposal`; records
`discourse_analysis`.

**Boundary.** May use the project's theoretical vocabulary. May **not** invent
evidence — see [Evidence](#evidence-the-integrity-rule).

### 5. postprocess

**What it does.** Writes both proposals into the canonical analysis record as
structured, evidence-linked objects.

**Why it exists.** It is the schema boundary. Reading one file tells you the
output contract, and review semantics are applied uniformly instead of being
decided per model call.

**In → out.** `record` + summary + discourse → the populated `record.analysis`;
records `postprocess` and `effective_analysis_stages`.

**Review semantics.** Every object is `review_status="PROVISIONAL"`. Objects that
depend on the wider corpus (floating/empty signifiers, formations) are also
marked `corpus_validation_required`. **A model proposal is not a finding until a
researcher validates it.**

### 6. discourse graph

**What it does.** Projects the analysis into a portable evidence graph: documents,
evidence, analytical objects, relations.

**Why it exists.** Exports (GraphML/GEXF) and the dashboard's network views read
this projection. It is a projection, not a second ontology: canonical ids remain
the single source of truth.

**In → out.** `record` → a dict `{"schema", "source_url", "nodes", "edges"}`.
The runner then offers it to the optional graph and vector sinks.

## Multimodal behaviour

**Multimodal is the default, decided by the record, not by a flag.** Routing
reads what the record actually carries:

- **Usable visual media present** (a materialised image, or frames extracted from
  video) → the frame stage runs automatically, and the summary synthesises across
  every available modality: post text/caption, metadata, transcript, visible text
  and frame descriptions.
- **No usable media** → the text path runs on post text plus metadata. No dummy
  media fields are required.
- **A derived modality is missing** (e.g. audio present but ASR produced
  nothing) → the record does **not** fail; the modality plan records what was
  available and the analysis proceeds with what exists.
- **Mixed datasets** → routing is per record, so text-only and visual items
  coexist in one project.

A remote URL alone is *not* visual evidence: only a materialised reference
(`local_ref`) or already-extracted canonical frames count.

Project configuration may switch expensive modality work off explicitly, but a
researcher never has to discover and flip a flag merely because media exists.

## Evidence: the integrity rule

> A model-proposed quotation counts as evidence only when the code can point at
> it in the source text.

Implemented in `stages/evidence.py`, applied by every stage that cites evidence.

- A quote **found** in the source gets real character offsets and `exact=True`.
- A quote **not found** is still recorded, with `exact=False` and no offsets.
  It is never dropped silently — the paraphrase rate is itself a finding about
  model reliability, and dropping it would destroy the audit trail.
- Quotes shorter than 12 characters are refused even when they match, because a
  very short string occurs by chance and would let a fragment masquerade as a
  quotation.

## Where prompts live

Prompt text: `src/laclaugpt_data_analysis/prompts/<corpus>/<stage>_<version>.md`.
Mapping from stage to prompt id: `stages/prompt_map.py`.

Prompts follow a three-layer model (see `prompts/README.md`):

```text
SYSTEM            stable methodological rules
RESEARCH CONTEXT  project + memory + RAG + prior analysis, with trust roles
CURRENT TASK      the operation to perform now + the evidence to analyse
```

**Provenance is preserved.** Every model call records the prompt ids, versions and
hashes it used, so a stored result can be traced back to the exact wording that
produced it. EP24 deliberately keeps its own historical prompt set so published
runs remain reproducible.

## Project configuration

Project settings live in the private runtime tree, not in this repository. The
analysis capability namespace is `analysis:`:

```yaml
analysis:
  laclau: true                        # theory stage
  sociotechnical_imaginaries: true    # imaginary candidates
  entities: true                      # projected from the summary
  topics: true
  sentiment: true
  sna: false                          # Phase 2 — opt-in only
  dna_statement_coding: {enabled: true}
analysis_phase: 1
```

Rules:

- A capability counts as enabled only when the project declares it **and** the
  phase permits it. Absence of configuration is never read as activation for the
  expensive or theory-specific stages.
- Phase 2 methods (`sna`, `ant`, `valueflows`, `dna_statement_coding`,
  `critical_ai`) never enter the Phase 1 default path; they require
  `analysis_phase >= 2`.
- A misspelled capability is rejected loudly rather than silently disabling a
  stage.
- Every result records `effective_analysis_stages`, so you can see which stages
  ran without inferring it from the output shape.

## Where codebooks, context and memory enter

They enter through the prompt envelope (`stages/shared.py`), as the middle
"research context" layer, and they stay **separate by trust role**:

- **project context** — framing, not evidence;
- **codebook entries** — controlled vocabulary for matching, rendered as a
  memory block;
- **memory context** — continuity across runs; never source evidence;
- **RAG context** — retrieved background.

Merging these early would destroy the distinction the audit trail depends on.

## Where storage and database concerns enter

Outside the scientific stages, at the ends:

- the **runner** offers the finished graph to an optional graph sink and the
  record text to an optional vector sink;
- **persistence, queuing and database access** live in the worker and storage
  modules (`distributed_worker.py`, `storage.py`, `task_queue.py`), which call
  `run_canonical_pipeline` as a library.

A stage file shows research logic; an engineer follows imports into those modules
when they need the plumbing.

## Where human review enters

At postprocess, via review status — every object is written `PROVISIONAL`. Review
then happens downstream (dashboard review screens, exports), and a validated
object is distinguishable from a raw proposal because the status is stored on the
object rather than inferred.

## Legacy and project compatibility

Different projects have different settings, schemas and modality availability.
Where a legacy shape needs translating, it is translated in a **named adapter**
rather than contaminating every stage with special cases:

- `modality_routing.py` — `legacy_multimodal_projection` renders the legacy EP24
  multimodal surface from canonical data, and recognises legacy media wording
  (e.g. `kind="photo"` as an image).
- `prompt_map.py` — maps EP24 to its historical prompt set.
- `stages/runner.py` — keeps `record.legacy` intact; legacy fields are preserved,
  never re-interpreted as source truth.

Modern canonical records remain the internal contract.

## How to run it

**Whole pipeline on one record** (as a library):

```python
from laclaugpt_data_analysis.stages import PipelineContext, run_canonical_pipeline

record = run_canonical_pipeline(
    record,
    provider=provider,                      # your LLM provider wrapper
    context=PipelineContext(project_config={"analysis": {"laclau": True}}),
    codebook_entries=entries,
    project_profile="ai26",
)
```

**Individual stages**, when you want to inspect one step in isolation:

```python
from laclaugpt_data_analysis.stages.preprocess import preprocess_record
from laclaugpt_data_analysis.stages.summary import summarize_record
from laclaugpt_data_analysis.stages.laclau import discourse_analysis
from laclaugpt_data_analysis.stages.postprocess import postprocess_record

record = preprocess_record(record)                      # no model needed
summary = summarize_record(record, provider=..., ...)   # needs a provider
discourse = discourse_analysis(record, provider=..., ...)
postprocess_record(record, summary, discourse, context)
```

**The deployed batch path** (queue, workers, storage) is the distributed worker;
see `docs/AI26_LASKIN_ANALYSIS.md` and `docs/AI26_DISTRIBUTED_WORKER.md`.

## Architecture at a glance

```text
                    ┌─────────────────────────────────────────┐
   canonical        │  runner.py — thin sequencing            │
   record  ────────▶│                                         │
                    │  1 preprocess   (no model)              │
                    │  2 route ─┬─ frame analysis (if visual) │
                    │           └─ else skipped               │
                    │  3 summary      (descriptive prompt)    │
                    │  4 laclau       (theory prompt)         │
                    │  5 postprocess  (schema boundary)       │
                    │  6 graph        (projection)            │
                    └───────────────┬─────────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
        canonical record      graph sink            vector sink
        (PROVISIONAL)         (GraphML/GEXF)        (embeddings)
              │
              ▼
        dashboard · exports · human review
```

## Related documents

- `docs/CANONICAL_RECORD.md` — the canonical record contract.
- `docs/FOUR_LAYER_RESEARCH_RECORD.md` — the research record layers.
- `docs/INTEROPERABILITY_ANALYSIS.md` — interchange formats.
- `docs/AI26_MULTIMODAL_METHOD.md` — AI26 study method: social-semiotic grounding, theory safeguards, data strata.
- `src/laclaugpt_data_analysis/prompts/README.md` — the prompt layering model.
- `docs/MIGRATION_MAP.md` — where pre-split material moved.
