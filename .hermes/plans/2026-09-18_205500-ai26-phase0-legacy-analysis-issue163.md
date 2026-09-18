# Plan: hand-coded AI26 Phase 0 legacy analysis on Laskin (issue #163)

> **For Hermes:** planning only. Issue #163 says "Do not implement Phase 0 yet",
> "Do not create a Phase 0 branch or milestone" and "Tomi will then give agents
> one small implementation task at a time". Nothing below may be executed until
> Tomi picks a step.

**Goal:** define a deliberately small, hand-editable AI26 analysis path that runs
under cron on Laskin, built from the legacy Multimodal stages and the
`vasama-osint/tree/AI` module pattern, so Phase 1 can be restored one layer at a
time around a working baseline.

**Architecture:** keep the Phase 1 package (`src/laclaugpt_data_analysis/`)
untouched and inactive. Phase 0 lives in `laclaugpt/` as plain scripts that each
do one stage, read/write MongoDB, and are individually cron-schedulable.

**Tech stack:** Python 3.11, `feedparser`, `ollama`, `pydantic`, `pymongo`
(`laclaugpt/requirements.txt`). No Redis, no Allas, no multimodal stack.

---

## Current state (verified, not assumed)

Already present in `laclaugpt/` on `main` — Phase 0 is partly built:

| File | Role | State |
| --- | --- | --- |
| `laclaugpt_mongo.py` | Mongo access | works: `MONGO_URI`, `MONGO_DB_NAME`, collection `laclaugpt2_<project>_scraper_collection` |
| `laclaugpt_collect_rss.py` | RSS → Mongo | works; canonical URL + category filters |
| `laclaugpt_validate_rss.py` | feed validation | works (category-filter check added in #171) |
| `laclaugpt_preprocess.py` | normalize | `preprocess_record()` |
| `laclaugpt_summary.py` | LLM summary | `summarize_record()`, prompt v1 |
| `laclaugpt_postprocess.py` | Pydantic validate | `validate_summary()` → `DocumentSummary` |
| `laclaugpt_discourse.py` | Laclau analysis | `analyze_discourse()`, prompt v1 |
| `laclaugpt_process.py` | orchestrator | `--stage preprocess\|summary\|postprocess\|discourse\|all` |
| `laclaugpt_ontology.py`, `laclaugpt_seed_graph.py` | RDF/graph | present (scope check needed, see Risks) |
| `laclaugpt_redis.py` | Redis ping | **Phase 1 leftover — must leave the Phase 0 runtime** |
| `puhti_*.py` | legacy reference | copies of the Multimodal scripts; reference only |

**Blocking defect found while planning:** `tests/test_phase0_formula_components.py`
imports `AffectObservation`, `FormulaComponents`, `FrontierConstruct`,
`UsConstruct`, `to_graph_observations` from `laclaugpt_discourse.py`, but that
module exports only `analyze_discourse()` (58 lines). The import fails, so
`pytest` aborts collection and **main is red for Phase 0**. See "Open questions".

Measured Laskin/runtime facts: host is `laskin01`; MongoDB and Ollama are local;
Phase 1 AI26 runtime (collection timers, capture service, hourly analysis cron,
Streamlit dashboard) has been **stopped and documented** in
`/mnt/workspace/LaclauGPT-Private/runtime/ai26/phase1_shutdown/PHASE1_SHUTDOWN.md`.

---

## 1. Which legacy Multimodal stages to reuse/adapt

Source: `TomiToivio/LaclauGPT-Multimodal-Analysis` (`puhti_*.py`).

| Legacy stage | Verdict | Why |
| --- | --- | --- |
| `puhti_preprocess.py` | **reuse the shape, drop the payload** | Its value is sequencing/robustness (choose best text, normalize, stable id). Its dependencies (OpenCV, EasyOCR, keyframes, SQLite cache) are all out of scope. Phase 0 keeps only the text path. |
| `puhti_frame.py` | **defer entirely** | Frame analysis is explicitly a non-goal. Keep the documented hook `preprocess → [future frame] → summary`; install nothing. |
| `puhti_summary.py` | **adapt** | Keep the system/user prompt split and the bounded `ollama.chat` options (`temperature: 0.0`, explicit `num_ctx`). Retarget prompt content to the AI26 codebook + `PHASE_1_PAPER.md`. |
| `puhti_postprocess.py` | **adapt** | Keep "LLM text → validated Pydantic" and the raw-response retention. Replace the SQLite table with MongoDB fields. |
| `puhti_populism.py` | **replace, do not port** | Its `FormulaOfPopulism`/`PopulismElement` model and binary populism verdict are exactly what #163 forbids. Keep the *idea* (Us / frontier / affect detection) as candidate structures with evidence and abstention. |

Legacy patterns worth preserving: rotating file logs, one module per stage, a
`--language`/`--project` style selector, and re-running a stage when a document
is already processed being a no-op.

## 2. Which `vasama-osint/tree/AI` cron/module patterns to reuse

Verified shape of that branch: a top-level `cron.sh` that calls one script per
stage in order (`cron_collect.py`, `cron_preprocess.py`, `cron_process.py`,
`cron_postprocess.py`, …), each with a thin `.sh` wrapper, plus `osint_mongo.py`
as the single Mongo access point.

Reuse:

- **one script per stage, no framework** — the stage list *is* the architecture;
- **`cron.sh` as the "run everything in order" convenience** alongside individual
  stage commands, which #163 requires for independent scheduling;
- **a single Mongo helper module** (`laclaugpt_mongo.py`) so no stage invents its
  own connection;
- **rotating file logs under a repo-local `data/logs/`**, matching
  `docs/RUNTIME_DATA.md` (`data/` is gitignored — never `var/`, `logs/`, `outputs/`);
- **idempotent upsert keyed by a stable identity** (`source_url`), so a rerun
  does not duplicate.

Do **not** reuse: its hard-coded credential style, its pandas/CSV intermediate
files, or its dashboard/geocode steps (out of Phase 0 scope).

## 3. Minimum Laskin Phase 0 analysis flow

```
RSS feeds
   ↓  laclaugpt_collect_rss.py        (Collection side; #82)
MongoDB: raw RSS/text record
   ↓  laclaugpt_preprocess.py         text + metadata normalize, stable id
   ↓  [future: frame analysis — NOT implemented]
   ↓  laclaugpt_summary.py            LLM summary (raw response retained)
   ↓  laclaugpt_postprocess.py        → validated DocumentSummary (Pydantic)
   ↓  laclaugpt_discourse.py          candidate Laclau structures (no verdict)
MongoDB: phase0.* results + status + provenance
```

Each stage is separately runnable; `laclaugpt_process.py` runs a bounded batch of
them for cron. Frame analysis is a documented hook only.

## 4. Minimum inputs and outputs

**Input** — one MongoDB document per source, minimum fields:
`source_url` (identity), `title`, `source_date`, `source_text`/`normalized_text`,
`actor_name`, `arena`, `ai_formation`, `political_formation`, `source_type`,
`language`, `categories`.

**Output** — fields written back on the same document, all idempotent:

| Field | Written by |
| --- | --- |
| `document_id`, `normalized_text`, `content_hash`, `metadata` | preprocess |
| `phase0_summary_raw` (pre-validation LLM text) | summary |
| `phase0_summary` (parsed dict) | summary |
| `phase0_summary_validated` (`DocumentSummary`) | postprocess |
| `phase0_summary_validation_error` | postprocess (on failure) |
| `phase0_discourse_raw`, `phase0_discourse`, `phase0_ontology` | discourse |
| `phase0.<stage>.status` ∈ `pending\|ok\|error` + timestamp + error | every stage |

`DocumentSummary` stays small: `document_id`, `source_url`, `source_date`,
`actor_name`, `title`, `summary`, `claims[]`, `actors[]`, `entities[]`,
`topics[]`, `signifiers[]`, `future_visions[]`, `governance_positions[]`,
`evidence[]`, `uncertainty_notes[]`, `model_metadata`, `prompt_version`.

## 5. Logging, failure and retry behaviour

- Per-stage `status` + error message is stored on the document; **a failed
  document never aborts the batch** (each stage catches, records, and moves on).
- The **raw LLM response is retained before validation** so a parse/validation
  failure is debuggable rather than destructive.
- `--retry-errors` selects documents with any `phase0.*.status == "error"`;
  the default query selects documents whose `discourse` stage is not `ok`, which
  makes the whole pipeline safely re-runnable.
- `--dry-run` computes without writing, for inspection before a live tick.
- Rotating logs under `data/logs/<stage>.log`, one file per stage.
- Cron entries should be staggered (as Phase 1 did) and each wrapper should load
  its own env so cron needs no inherited environment.

## 6. Phase 1 abstractions to bypass temporarily

Bypass (leave in the repo, keep out of the Phase 0 runtime): the entire
`src/laclaugpt_data_analysis/` package — `distributed_worker.py`, `coordination.py`,
Redis task queues, `multimethod.py`, `discourse_network/`, `dna_statement_coding.py`,
`mongodb_rag.py`, `memory/`, `context_*`, `canonical_pipeline.py`,
`interchange.py`, plugin discovery, exporters, and `laclaugpt/laclaugpt_redis.py`.

Rule: Phase 0 code must not import from `laclaugpt_data_analysis`, and no hidden
fallback may reach for it.

## 7. Stepwise Phase 0 → Phase 1 restoration sequence

One capability per step; each step must leave a working pipeline and be verified
(collection → Mongo record → compatibility with Phase 0 analysis) before the next.

1. stabilize Phase 0 input/output (freeze the field contract above);
2. restore Phase 1 preprocessing contract;
3. restore frame-analysis contract;
4. restore multimodal summary contract;
5. restore Phase 1 Laclaudian analysis contract;
6. restore postprocessing;
7. restore canonical schema/provenance;
8. restore validation;
9. restore context/memory;
10. restore RAG if needed;
11. restore storage/coordination abstractions (Redis/Allas);
12. restore graph/export features;
13. restore remaining Phase 1 generalization.

This ordering is Tomi's from #163; it is not a schedule — steps happen only when
he requests them.

## Files likely to change (when implementation is authorized)

- Create: `laclaugpt/laclaugpt_process.py` extensions as needed, `laclaugpt/README.md` cron section, `data/logs/` (gitignored)
- Modify: `laclaugpt/laclaugpt_discourse.py` (restore missing exports / settle the schema), `laclaugpt/laclaugpt_summary.py` (AI26 prompts), `tests/test_phase0_formula_components.py`
- Delete/bypass: `laclaugpt/laclaugpt_redis.py` from the Phase 0 path

## Tests / validation

- `python laclaugpt/laclaugpt_validate_rss.py --all` — every enabled/candidate feed
  must validate before a live collection run (category filters incl.).
- One text-only smoke fixture proving preprocess → summary → postprocess →
  discourse → persistence, and that a rerun does not duplicate the document.
- `pytest tests/test_phase0_*.py` must collect and pass (currently it does not).
- No test may require multimedia fixtures.

## Risks, tradeoffs, open questions

- **Main is currently red for Phase 0** (broken imports in
  `test_phase0_formula_components.py`). Any "verify Phase 0 works" step is blocked
  until this is resolved; it is the natural first task.
- **Schema ambiguity to resolve with Tomi:** `laclaugpt_discourse.py` today returns
  free-form `phase0_discourse` JSON, while the failing test expects typed
  `FormulaComponents`/`UsConstruct`/`FrontierConstruct`/`AffectObservation`
  objects. Which is authoritative for Phase 0?
- **Prompt scope:** `laclaugpt_summary.py` and `laclaugpt_discourse.py` prompts must
  be retargeted to `codebooks/public/ai26_v2.yaml` and `paper/PHASE_1_PAPER.md`
  (co-occurrence ≠ articulation; difference ≠ antagonism; sentiment ≠ affect;
  frequency ≠ hegemony; one claim ≠ imaginary; source identity ≠ formation
  evidence). Changing prompt wording needs a new `PROMPT_VERSION`.
- **Ontology/RDF scope creep:** `laclaugpt_ontology.py` and `laclaugpt_seed_graph.py`
  went in via #179/#180. #163 lists graph/export as a *later* restoration step, so
  these need an explicit in/out decision rather than being assumed Phase 0.
- **Ollama endpoint:** Phase 1 analysis used `:11500`; Phase 0 should pin its
  endpoint explicitly (`OLLAMA_HOST`) instead of inheriting a Phase 1 default.
- Uncommitted #171 work (validated 13/13 source list + category-filter check) is on
  branch `issue-171-validate-rss-feeds` and is not yet pushed.

## Definition of done for this plan

Deliverable is this document only. No Phase 0 code was implemented, no branch or
milestone was created, and no Phase 1 code was deleted.
