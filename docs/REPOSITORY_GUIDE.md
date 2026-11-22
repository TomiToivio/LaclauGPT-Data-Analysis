# Repository navigation for human maintainers

This guide maps the **existing** code, rather than proposing another pipeline or
changing scientific behavior. Start here when trying to answer "where does this
piece of analysis happen?" For the actual execution order, see
[Data Analysis Pipeline](DATA_ANALYSIS_PIPELINE.md).

## Where to look

| Location | Responsibility | Reader's entry point |
| --- | --- | --- |
| `laclaugpt/step_01_preprocess.py` through `step_07_sna.py` | Seven researcher-owned scientific step entry points | [Human pipeline](../laclaugpt/HUMAN_PIPELINE.md) |
| `laclaugpt/pipeline_runner.py` | Human-pipeline orchestration | [Human pipeline](../laclaugpt/HUMAN_PIPELINE.md) |
| `laclaugpt/pipeline_*.py`, `laclaugpt/laclaugpt_*.py` | Supporting I/O, storage, models, prompts, provider helpers | [Coding style](../CODING_STYLE.md) |
| `src/laclaugpt_data_analysis/` | Installable Python package, shared contracts, operational integrations | [Data Analysis Pipeline](DATA_ANALYSIS_PIPELINE.md) |
| `src/laclaugpt_data_analysis/analysis/` | Optional and complementary analytical backends | [Methods](methods/) |
| `src/laclaugpt_data_analysis/llm/` | Model interfaces, routing and output handling | [Prompt library](PROMPT_LIBRARY.md) |
| `src/laclaugpt_data_analysis/pipelines/` | Versioned operational pipeline implementations, including legacy adapters | [Data Analysis Pipeline](DATA_ANALYSIS_PIPELINE.md) |
| `config/` | Project, machine and execution configuration | [AI26 Laskin operations](AI26_LASKIN_OPERATIONS.md) |
| `codebooks/`, `contexts/` | Research coding instruments and context | [Codebooks](../codebooks/README.md) |
| `scripts/`, `deployment/` | Entry-point scripts, batch/cron and deployment wrappers | [Analysis runtime](ANALYSIS_RUNTIME.md) |
| `tests/` | Unit, integration and regression tests | `pyproject.toml` pytest configuration |
| `docs/` | Contracts, operations and methodology documentation | [Data Analysis Pipeline](DATA_ANALYSIS_PIPELINE.md) |

## Current layout and safe migration policy

The repository deliberately has **two surfaces**, not two interchangeable copies
of the same research code:

1. The `laclaugpt/` directory exposes the readable scientific workflow.
   Its seven `step_*.py` files are **TOMI-LOCKED**. Do not edit, rename, move
   or replace them without explicit step-specific authorization.
2. The `src/laclaugpt_data_analysis/` directory is an installable library used
   for contracts, runtime and reusable infrastructure. Its import path and
   declared console scripts are public compatibility surfaces.

Some legacy study and EP24 artifacts are intentionally present. Do not delete
them merely because their names look old. First establish callers, contracts
and provenance requirements, then migrate incrementally with regression tests.
For the ongoing pipeline-readability work, coordinate with
[issue #303](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/issues/303).
For the repository-wide cleanup, see
[issue #523](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/issues/523).

## Developer commands

From the repository root, using Python 3.11 or newer:

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m ruff format --check src tests
```

These commands check the installable package and tests. The explicitly excluded
vendored EP24 source snapshots must not be reformatted or changed in the name
of cleanup; see `pyproject.toml` and `docs/EP24_SOURCE_INVENTORY.json`.
Do not assume a successful unit test run proves AI26/EP24 runtime parity:
verify representative project fixtures and deployment entry points when
changing the relevant modules.

## Python documentation conventions

- Use PEP 8 naming and consistently formatted imports.
- Use concise PEP 257 module and public-function/class docstrings with a
  description of inputs, outputs and exceptional behavior where useful.
- Explain **why** a methodological branch, compatibility adaptation, privacy
  rule or provenance guard exists. Do not narrate obvious Python syntax.
- Prefer explicit, readable functions over extra layers of generic wrappers.
- Keep theory/prompt edits separate from readability-only changes: wording
  changes can alter model outputs.

**Practical test:** A reader should find the scientific step in a numbered
file, its supporting contract or adapter in a descriptively named module,
and the operational invocation in one documented CLI or script.
