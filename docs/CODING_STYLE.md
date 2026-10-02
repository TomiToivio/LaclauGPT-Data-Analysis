# LaclauGPT Coding Style

> **Status:** documentation of the code style this repository follows and of the
> style it is being rebuilt toward. Nothing here changes pipeline behaviour, and
> nothing here relaxes the repository's existing locks.
>
> **Guiding principle: optimize for the researcher reading the code six months
> later.** Readable research software beats clever research software.

This is a research pipeline. The code must stay understandable to researchers and
future maintainers, so readability and research transparency take priority over
abstraction.

The reference implementation of this style is `LaclauGPT-Multimodal-Analysis`. The
AI26 pipeline here is being rebuilt toward it; see
[Migration direction](#10-migration-direction-ep24--ai26) and
[Repository status](#repository-status).

## 1. One analysis step = one clearly named file

Each major analysis step lives in its own Python file, directly executable, and
readable in one sitting. In this repository that is the `laclaugpt/` scaffold:

```text
laclaugpt/step_01_preprocess.py
laclaugpt/step_02_frame.py
laclaugpt/step_03_summary.py
laclaugpt/step_04_postprocess.py
laclaugpt/step_05_laclau.py
laclaugpt/step_06_dna.py
laclaugpt/step_07_sna.py
```

A step must remain runnable as a simple direct invocation:

```bash
python laclaugpt/step_01_preprocess.py
```

CLI options, sbatch and cron wrappers are additive; they must never become the
only way to run a step.

**These seven files are TOMI-LOCKED.** See
[What this guide does not override](#what-this-guide-does-not-override). The naming
convention above is the one to preserve; it is not an invitation to restructure the
files.

## 2. Shared infrastructure lives in separate, clearly named modules

Code genuinely shared by several steps is factored into named modules rather than
duplicated:

```text
laclaugpt/laclaugpt_mongo.py        MongoDB access
laclaugpt/laclaugpt_redis.py        Redis access
laclaugpt/laclaugpt_ollama.py       local LLM provider
laclaugpt/laclaugpt_ontology.py     ontology / graph vocabulary
laclaugpt/laclaugpt_geocode.py      geocoding
laclaugpt/pipeline_io.py            record I/O
laclaugpt/pipeline_models.py        the per-step Pydantic contracts
laclaugpt/pipeline_prompts.py       prompt loading
laclaugpt/pipeline_rdf.py           RDF export
laclaugpt/pipeline_runner.py        orchestration
laclaugpt/pipeline_storage.py       persistence
```

The `laclaugpt_*.py` prefix marks infrastructure helpers; `pipeline_*.py` marks the
scaffold's own plumbing. The step files stay readable entry points.

Rule of thumb:

> **Shared infrastructure should be abstracted. Research logic should remain
> visible.**

## 3. Prefer readability over architectural cleverness

Prefer straightforward functions, explicit control flow, descriptive names, obvious
inputs and outputs, simple modules, visible prompts, and visible pipeline stages.

Avoid unnecessary class hierarchies, factories, plugin frameworks,
dependency-injection machinery, deeply nested utility layers, premature abstraction,
and "enterprise" architecture for its own sake.

The existing `src/laclaugpt_data_analysis/` package remains available as
infrastructure and reference code. This guide does not delete or rewrite it, and it
is **not** the pattern to extend for new scientific steps: new steps go in
`laclaugpt/` in the readable style.

## 4. Heavy debug logging is a feature

Extensive info/debug logging is intentional. A human must be able to answer:

> "What exactly is this step doing right now, with what data, and where is the
> result going?"

Log step start/end, input files and database collections, project/sample/filters,
record counts, the current record where useful, model used, prompt stage, fields
passed between steps, output destinations, database and backup writes, retries and
fallbacks, validation failures, and exceptions with context.

## 5. Use generous comments and docstrings

Every step carries a module docstring covering purpose, pipeline position, expected
inputs, outputs produced, databases/files used, models used, important assumptions,
and CLI examples. The existing step modules already do this — note that each names
its **legacy reference** (`puhti_preprocess.py`, `puhti_populism.py`, …), which is
the useful form: a reader can see the lineage without reading the old code.
Comment non-obvious transformations, and comment research and theory decisions.

Comments explain **why**, not only **what**.

## 6. System prompts may be long and theory-heavy

Heavy system prompts are intentional and are research code. The prompts encode
theoretical and methodological assumptions (Laclau, Castells, Leifeld/DNA, SNA,
ideology, discourse theory, populism, assemblages).

This repository already keeps them as readable files rather than inline strings:

```text
laclaugpt/PROMPT_LACLAU.md
laclaugpt/PROMPT_DNA.md
laclaugpt/PROMPT_SNA.md
```

Keep that shape. Do not aggressively shorten prompts, and do not move them into
opaque abstractions for code neatness. Prompt readability is part of code
readability, and reviewers must be able to see the method.

## 7. Keep data flow explicit

Every step must make it obvious what it reads, which fields it expects, which new
fields it creates, what it preserves, what it writes, and what the next step
receives. The per-step contracts live in `laclaugpt/pipeline_models.py`; the
canonical record contract is `docs/CANONICAL_RECORD.md` plus the project-wide
`TomiToivio/LaclauGPT/docs/CANONICAL_DATA_CONTRACT.md`.

New analytical fields are additive: a step preserves all previous fields and appends
its own outputs. Avoid hidden mutations and implicit schema changes. Where a step
produces an interpretation, keep descriptive outputs and theory-facing
interpretations separate.

## 8. Self-contained does not mean duplicated infrastructure

A step must be understandable as a standalone research operation while still being
allowed to import shared infrastructure:

```python
from laclaugpt_mongo import find_documents
from pipeline_models import HumanPipelineRecord, LaclauResult
```

What to avoid is importing plumbing instead of writing the step:

```python
from framework.runtime.pipeline.step_factory import AbstractStepProvider
```

## 9. Tests and verification

Wherever practical, a behavioural change is demonstrated by **executing** the code,
not by reading it. For a guard you add, prove it fails when the defect is
reintroduced, then restore the file and confirm it passes again. A guard whose
sabotage still passes is a broken guard, not reassurance.

## 10. Migration direction (EP24 → AI26)

Once the Roihu EP24 reprocessing pipeline in `LaclauGPT-Multimodal-Analysis` works
end-to-end:

1. preserve the working EP24 implementation and its history;
2. use the Multimodal-Analysis structure as the basis for modernizing this
   repository;
3. adapt that code from EP24 to AI26 rather than reverting to the older
   Data-Analysis architecture;
4. preserve this simple, step-oriented style throughout the migration.

> **Multimodal-Analysis becomes the architectural ancestor of the rebuilt AI26
> Data-Analysis pipeline.**

**Status: not started.** No EP24→AI26 port has been performed. The `laclaugpt/`
scaffold exists and its steps are unimplemented by design (see
[Repository status](#repository-status)).

## Repository status

| | `LaclauGPT-Multimodal-Analysis` (reference) | this repository |
|---|---|---|
| steps | `step_1_roihu_*.py` … `step_9_roihu_rdf.py`, implemented | `laclaugpt/step_01_*.py` … `step_07_sna.py`, **TOMI-LOCKED, pending hand-coding** |
| infrastructure | `ep24_*.py` | `laclaugpt/laclaugpt_*.py`, `pipeline_*.py` |
| theory prompts | in the step modules | `laclaugpt/PROMPT_*.md` |
| legacy reference | `puhti_*.py` | `laclaugpt/puhti_*.py` (references for reimplementation, not code to copy wholesale) |

## What this guide does not override

Repository-specific rules win where they are narrower.

- **`laclaugpt/step_01…step_07` are TOMI-LOCKED.** Per `AGENTS.md` §"Human-owned
  analysis steps (issue #315)" and `laclaugpt/HUMAN_PIPELINE.md`, the seven
  `step_*.py` modules are the human-written scientific method. Agents work *around*
  them, not inside them: agent-authored changes may add or repair I/O, Pydantic
  contracts, prompts, RDF/export layers, orchestration, tests, deployment code and
  adapters, but must not modify, rename, merge, replace or move the seven scientific
  step files without explicit authorisation for that specific step change. There is
  **one** canonical seven-step scaffold; do not create a parallel step package.
- **Output vs code readability.** `AGENTS.md` priorities machine-readable canonical
  records over human-readable **reports** for the AI26 repositories. That is a
  decision about pipeline *output*; this guide is about code *readability*. The two
  are compatible and nothing here reopens the output question.
- **Schema and contract changes** still require reading `docs/CANONICAL_RECORD.md`
  and the project-wide canonical data contract first, as `AGENTS.md` requires.

## See also

- [Human-readable pipeline scaffold](../laclaugpt/HUMAN_PIPELINE.md)
- [Data analysis pipeline](DATA_ANALYSIS_PIPELINE.md)
- [Canonical record](CANONICAL_RECORD.md)
- [Agent guidance](../AGENTS.md)
