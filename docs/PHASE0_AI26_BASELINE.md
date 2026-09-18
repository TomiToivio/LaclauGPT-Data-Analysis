# AI26 Phase 0 analysis baseline

Issue #191 defines the deliberately small, legacy-style Data Analysis baseline that comes **before** Phase 1 is restored.

This is not a new framework. It is the minimum inspectable path needed to keep AI26 RSS text moving through analysis on Laskin.

## Practical references

Phase 0 follows the behavioral style of the older LaclauGPT work rather than the current Phase 1 abstraction stack:

- `TomiToivio/LaclauGPT-Multimodal-Analysis` is the practical reference for the sequential preprocessing → analysis → postprocessing style.
- `TomiToivio/vasama-osint/tree/AI` is the practical reference for explicit cron/module execution.
- The current implementation lives under `laclaugpt/` and is intentionally hand-coded and directly readable.

The legacy repositories are references, not dependencies. Phase 0 should copy proven behavior only where it keeps the current AI26 text path simpler.

## Phase 0 boundary

The baseline is intentionally narrow:

```text
RSS/article text already stored in MongoDB
        ↓
preprocess
        ↓
summary
        ↓
postprocess / validate summary
        ↓
Laclaudian discourse analysis
        ↓
write results and stage status back to the same MongoDB corpus
```

For project `ai26`, collection and analysis meet at:

```text
laclaugpt2_ai26_scraper_collection
```

External MongoDB is the only required state service for the Phase 0 analysis path.

Phase 0 does **not** require Redis, CSC Allas/S3, SQLite core state, browser collection, frame analysis, OCR, Whisper, media processing, queues, event buses, agents, plugin orchestration, DNA or SNA.

## Current implementation

The minimal runtime is already represented by these explicit modules:

```text
laclaugpt/
  laclaugpt_mongo.py
  laclaugpt_preprocess.py
  laclaugpt_summary.py
  laclaugpt_postprocess.py
  laclaugpt_discourse.py
  laclaugpt_ontology.py
  laclaugpt_process.py
```

`laclaugpt_process.py` is the one normal entry point. It reads pending documents, runs the selected stage(s), writes outputs back through `laclaugpt_mongo.py`, and records per-stage status under `phase0.*`.

The supported sequence is:

```text
preprocess → summary → postprocess → discourse
```

Each stage can also be run independently with `--stage`.

A failed document is marked with an error status and does not need to stop the rest of the batch. `--retry-errors` provides an explicit retry path.

## Laskin / CLI / cron

The operator cutover and runtime commands are documented in `docs/PHASE0_LASKIN_CUTOVER.md`.

Minimum environment:

```bash
export MONGO_URI='mongodb://...'
export MONGO_DB_NAME='...'
export LACLAUGPT_PROJECT_ID='ai26'
export OLLAMA_MODEL='...'
```

Smoke one document:

```bash
python laclaugpt/laclaugpt_process.py --project ai26 --limit 1 --dry-run
python laclaugpt/laclaugpt_process.py --project ai26 --limit 1
```

Batch execution:

```bash
python laclaugpt/laclaugpt_process.py --project ai26 --limit 100 --stage all
```

Example deliberately boring cron entry:

```cron
*/10 * * * * cd /path/to/LaclauGPT-Data-Analysis && /path/to/python laclaugpt/laclaugpt_process.py --project ai26 --limit 100 --stage all >> data/logs/phase0-cron.log 2>&1
```

Keep logs human-readable and keep launch points explicit. Phase 0 should be understandable without tracing hidden orchestration.

## What Phase 0 deliberately bypasses

Existing Phase 1 code remains available as reference material, but the Phase 0 runtime does not need to route through:

- the generic plugin pipeline;
- distributed coordination;
- Redis cache/queue abstractions;
- Allas/S3 object storage;
- generic multimodal processing;
- frame analysis;
- generalized graph/export orchestration;
- RAG or persistent memory unless a later issue explicitly restores them;
- Phase 2 methods such as DNA or SNA.

No useful Phase 1 code should be deleted merely because the Phase 0 baseline bypasses it.

## Restoration rule

Once this baseline remains stable end to end, Phase 1 returns one capability at a time. Every restoration should be a separate, reviewable task and must leave the pipeline runnable.

Suggested order:

1. stabilize the Phase 0 MongoDB input/output contract;
2. restore richer Phase 1 preprocessing semantics where needed;
3. restore frame analysis as an optional capability;
4. restore multimodal summary support;
5. restore richer Phase 1 Laclaudian analysis contracts;
6. restore postprocessing/projection refinements;
7. restore canonical schema and provenance layers;
8. restore validation machinery;
9. restore context / persistent memory;
10. restore RAG if empirically useful;
11. restore Redis / Allas / distributed coordination where required;
12. restore graph/export layers;
13. restore remaining Phase 1 generalization.

Do not combine several of these into one "architecture" change.

## Follow-up issue rule

Follow-up implementation work should be split into single-purpose issues. A good issue should answer one concrete question such as:

- restore one Phase 1 preprocessing field;
- add one optional frame-analysis adapter;
- move one memory function to MongoDB;
- add one RAG retrieval path;
- add one provenance field;
- add one graph export;
- add one validation check.

Avoid umbrella implementation issues that silently reintroduce the whole Phase 1 stack.

## Definition of the Phase 0 baseline

The baseline is complete when a researcher can inspect the code and answer, without framework archaeology:

- which MongoDB records are selected;
- what preprocessing changes are made;
- what prompt/model runs;
- what summary/discourse output is produced;
- what fields are written;
- which stage failed;
- how to retry it;
- how cron invokes it;
- which Phase 1 capabilities are still intentionally absent.

That simplicity is a feature of Phase 0, not technical debt to remove immediately.
