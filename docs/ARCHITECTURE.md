# Architecture: where things are

A map of this repository for someone who has just cloned it. It answers "where do I find X"
and "what must I not touch"; the deep explanations live in the topical documents indexed in
[README.md](README.md).

## What this repository is

The **Data Analysis** stage of the LaclauGPT project. Collection (elsewhere) produces canonical
records; this repository analyses them stage by stage; Visualization reads the results. AI26 is
the only project under active development here; EP24, Hungary26 and Brazil26 are preserved for
reproducibility and move to their own repositories.

Runtime shape, in one sentence: **MongoDB holds canonical records and analysis results, Redis
coordinates workers and queues, CSC Allas holds files and large artifacts, and everything
runtime-generated lands under the untracked `data/` directory.**

## The tree

| Path | What lives there |
| --- | --- |
| `src/laclaugpt_data_analysis/` | the package: analysis stages, worker, storage, contracts, CLI |
| `src/laclaugpt_data_analysis/pipelines/` | pipeline registry and the vendored EP24 snapshots (see below) |
| `tests/` | pytest suite; issue-numbered modules pin specific behaviours |
| `scripts/` | operational wrappers run by cron or by hand on a host (shell, not importable code) |
| `tools/` | operator and auditing programs: contract checks, corpus diagnostics, vendor sync |
| `config/`, `schemas/`, `ontology/`, `codebooks/` | configuration, record schemas, ontology, coding instruments |
| `deployment/` | host deployment material |
| `docs/` | 70+ topical documents; start at [README.md](README.md) |
| `laclaugpt/` | the legacy foundation the current code was restored around; read before "restoring" a capability |
| `data/` | **untracked** runtime artifacts for this checkout |
| `AGENTS.md`, `HERMES.md`, `CODING_STYLE.md` | the contract an agent or contributor must follow |

Two files look like duplicates but are not: `AGENTS.md` is the canonical contract, `CLAUDE.md`
and `CODEX.md` are the per-client entries into it, and `HERMES.md` adds the branch and
legacy-restoration policy.

## The vendored half

`src/laclaugpt_data_analysis/pipelines/ep24/` is a **verbatim snapshot** of another repository,
38k of the package's 75k lines. It is not maintained here: `docs/EP24_SOURCE_INVENTORY.json`
records the source repository, the import time and the sync policy — *"re-run the import script
against a new upstream commit; never edit vendored files in place"* — and
`tests/test_multi_pipeline_registry.py` keeps the registry agreeing with that inventory.

Re-vendor with `tools/vendor_pipeline.py`; never hand-edit a vendored file. The inventory notes
its own `compatibility_deviations`, so a deviation is recorded rather than discovered later.

That one fact explains most of the tree's apparent size. The in-repository code is roughly
37k lines; the rest is preserved history.

## Pipelines

`pipelines/registry.py` is the single source of truth for "which analysis runs", and it refuses
to guess:

| id | package | stages | execution |
| --- | --- | --- | --- |
| `ai26` | `laclaugpt_data_analysis` | 0-preflight, 1-preprocess, 2-frame, 3-video, 4-summary, 5-postprocess, 6-laclau, 7-dna, 8-sna, 9-export | in-process |
| `ep24` | `pipelines.ep24.vendor` | 0-import … 9-rdf (Roihu steps 0–9) | script |
| `ep24-legacy` | `pipelines.ep24_legacy.vendor` | preprocess, frame, summary, populism, postprocess | script |

The same record analysed by a different implementation is a different result, which is why
execution keys carry the pipeline id: two pipelines must not share queues, leases or result
collections.

## Where do I find X

| I want | Look at |
| --- | --- |
| the worker that claims and executes tasks | `distributed_worker.py` |
| the queue, leases and task documents | `task_queue/models.py` (envelopes), `task_queue/redis_queue.py` (claims and leases) |
| what a canonical record is | `schemas/`, `field_contract.py`, `docs/CANONICAL_RECORD.md` |
| how a record is analysed end to end | `contextual_pipeline.py`, `canonical_pipeline.py`, `docs/DATA_ANALYSIS_PIPELINE.md` |
| AI26 stage prompts | `prompts/`, `prompt_library.py`, `docs/PROMPT_LIBRARY.md` |
| why a deployed checkout was refused | `deploy_drift.py`, `preflight.py`, `docs/AI26_LASKIN_OPERATIONS.md` |
| how a host run is scheduled | `scripts/run_ai26_laskin*.sh`, `docs/AI26_LASKIN_ANALYSIS.md` |
| tick telemetry and its alarms | `ai26_tick_telemetry.py`, `tick_status.py`, `docs/AI26_RUNTIME_512_516.md` |
| the CLI | `[project.scripts]` in `pyproject.toml`: `laclaugpt-analysis-worker`, `laclaugpt-analysis`, `laclaugpt-preflight`, `laclaugpt-reprocess`, `laclaugpt-ep24`, `laclaugpt-summarize-period`, `laclaugpt-freeze-ai26`, `laclaugpt-phase1-*` |
| why a number looks wrong | `tools/ai26_*_audit.py` and the matching `docs/` note before changing code |

## What must not be touched

- **`TOMI-LOCKED` markers.** A locked element is a human-controlled invariant; broad
  instructions ("refactor", "modernise", "make CI green") do not authorise changing it. Grep for
  the marker before editing anything that looks like a contract.
- **The vendored EP24 snapshots** (above).
- **Scientific semantics.** Refactoring may not change prompts, schemas, stage order, evidence
  and provenance handling, or output contracts.
- **Secrets.** Configuration inspection is redacted; credentials live outside the repository.

## Verify before you claim a change works

```bash
python tools/verify_contracts.py     # offline cross-module record/adapter contract check
pytest                               # full suite (pyproject supplies `pythonpath = ["src"]`)
ruff check src tests                 # style gate
```

CI runs the same three, with ruff limited to newly introduced violations. A change that touches
the record model, an adapter or backend selection must run `verify_contracts.py`; a change to a
shell wrapper has no suite, so verify its refusal paths explicitly (`bash -n`, then the exit
codes) and say so when reporting.
