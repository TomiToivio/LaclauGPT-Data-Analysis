# Repository map

Where things live, in one page. Written for a Python developer or a social-science researcher who needs to
locate a pipeline stage, inspect a result or run the worker.

## The one-paragraph version

This repository is the **Data Analysis** stage of LaclauGPT. It consumes documents collected elsewhere
([Data Collection](https://github.com/TomiToivio/LaclauGPT-Data-Collection)), runs the AI26 Phase 1 discourse
analysis (Laclau/Mouffe categories, evidence-anchored), and writes canonical records plus an analysis result
into MongoDB. A separate repository renders them
([Data Visualization](https://github.com/TomiToivio/LaclauGPT-Data-Visualization)). The scientific contract
lives in the meta-repository's `paper/PHASE_1_PAPER.md` and `THEORY.md`; **this repository implements it and
must not quietly reinterpret it.**

## Top level

| path | what it is |
| --- | --- |
| `src/laclaugpt_data_analysis/` | the package — all production code |
| `tests/` | pytest suite; the fastest way to learn behaviour |
| `scripts/` | operator entry points (shell wrappers, cron targets, one-off tools) |
| `config/`, `codebooks/`, `contexts/`, `ontology/`, `schemas/` | data the pipeline reads: study configs, codebooks, context packs, ontology, JSON/RDF schemas |
| `docs/` | operational and acceptance documentation (see "Where to read first" below) |
| `deployment/`, `external/`, `evaluation/`, `tools/` | deployment assets, vendored externals, evaluation harnesses, ad-hoc tools |
| `data/` | local runtime output; **not** a source of truth and not versioned content |
| `AGENTS.md`, `CLAUDE.md`, `CODEX.md`, `HERMES.md`, `CODING_STYLE.md`, `CONTRIBUTING.md` | agent and contributor instructions |

## Inside the package

`src/laclaugpt_data_analysis/` is organised by role, not by paper section:

- **`stages/`** — Phase 1 itself: prompt construction, proposal parsing, post-processing, evidence and
  verbatim handling. Start here to understand the science.
- **`analysis/`**, **`analysis_context.py`** — assembling what a stage sees (context, codebook, prior state).
- **`llm/`** — provider adapters (`ollama.py`), structured-output parsing (`structured_output.py`), JSON repair,
  routing. All model-touching code lives here.
- **`discourse_network/`**, **`sna/`**, **`multimodal/`** — the opt-in extensions. None of them are default.
- **`pipelines/`** — pipeline wiring and the CLI (`laclaugpt-analysis`), including the vendored EP24 steps.
- **`interoperability/`**, **`canonical.py`**, **`schemas`** consumers — the canonical record contract.
- **`phase1_*.py` modules** — the Laskin runtime: config, worker, periodic report, shadow runs.
- **`preflight.py`**, **`deploy_drift.py`**, **`tick_status`-family telemetry** — the
  configuration checks, deployment drift detection and per-cycle status reporting.
- **[`task_queue/`](../src/laclaugpt_data_analysis/task_queue/)** — formerly `task_queue.py`. Existing Python
  imports use `laclaugpt_data_analysis.task_queue`. Read `models.py` for task identity and resume rules,
  `worker.py` for retries and acknowledgement, and the individual store modules for result persistence.

## Entry points (from `[project.scripts]`)

| command | for |
| --- | --- |
| `laclaugpt-analysis-worker` | the bounded analysis worker (claims tasks, analyses, exits) |
| `laclaugpt-analysis` | the pipeline CLI |
| `laclaugpt-phase1-laskin` | one bounded Laskin cycle |
| `laclaugpt-phase1-laskin-report` | the periodic Phase 1 report |
| `laclaugpt-phase1-config` | configuration inspection |
| `laclaugpt-phase1-shadow` | shadow run against the existing pipeline |
| `laclaugpt-summarize-period` | periodic summary |
| `laclaugpt-preflight` | configuration validation, offline and redacted |
| `laclaugpt-freeze-ai26` | freeze the run manifest |
| `laclaugpt-reprocess`, `laclaugpt-ep24`, `laclaugpt-hungary26-roihu` | historical/other studies — dormant |

## Common commands

```bash
# install for development
pip install -e '.[dev,remote,ollama]'   # extras: analysis, arrow, nlp, topics, phase1-nlp, ollama, rag, rdf, remote, dev, all
python -m pytest -q                     # the whole suite
ruff check .                            # lint

# operational (Laskin)
scripts/run_ai26_laskin.sh --check      # preflight only, claims nothing
scripts/run_ai26_laskin.sh              # one bounded cycle (what cron runs)
```

`--check` is the one an operator should run before trusting anything: it validates configuration, checks the
checkout state and prints a verdict without claiming a task.

## Where to read first

1. `docs/AI26_DISTRIBUTED_WORKER.md` — how one cycle is claimed, bounded and finished.
2. `docs/AI26_STEP_BY_STEP.md` — what the stages do, in order.
3. `docs/AI26_PROMPT_BUDGET_425.md` — why the prompt budget is what it is (measured, not guessed).
4. `docs/AI26_LASKIN_ANALYSIS.md` — running it on the Laskin host.
5. `CODING_STYLE.md` — the conventions this repository actually follows.

## Rules a newcomer will otherwise learn the hard way

- **The paper is upstream of the code.** Phase 1 categories are locked; a change that alters what a code
  *means* is a scientific decision, not a refactor.
- **Nothing writes unless it is configured to.** The object store, the review log and other side effects are
  opt-in by environment variable, and a missing variable must disable the write, never silently enable it.
- **Telemetry must not fail a cycle.** Journal, progress and status writers are best-effort by design.
- **`data/` and checkouts are runtime state.** Merged fixes do not take effect until the checkout is
  refreshed — verify the running behaviour, not the git state.
