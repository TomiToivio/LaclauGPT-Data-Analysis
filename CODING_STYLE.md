# LaclauGPT Data Analysis coding style

This repository is research software. Optimize it for the researcher reading the code six months later.

The architectural reference for the human-readable analysis pipeline is the step-oriented style developed in `LaclauGPT-Multimodal-Analysis`. As that EP24/Roihu pipeline is generalized into AI26, preserve the same visible, inspectable structure instead of replacing it with a more abstract framework.

## Core rule: one analysis step = one obvious file

Each major scientific analysis operation should have one clearly named Python entry-point file.

The current AI26 human-owned Phase 2 pipeline is:

```text
laclaugpt/step_01_preprocess.py
laclaugpt/step_02_frame.py
laclaugpt/step_03_summary.py
laclaugpt/step_04_postprocess.py
laclaugpt/step_05_laclau.py
laclaugpt/step_06_dna.py
laclaugpt/step_07_sna.py
```

These files are TOMI-LOCKED. Do not modify, rename, merge, regenerate, move or replace them unless Tomi explicitly authorizes the specific step.

A step should be understandable as a research operation without tracing through a maze of factories, providers or class hierarchies. It may import shared infrastructure, but the scientific intent and important control flow should remain visible.

Where a step exposes a direct CLI, preserve the simplest possible invocation, for example:

```bash
python laclaugpt/step_01_preprocess.py
```

Additional CLI options, sbatch wrappers, cron execution and distributed workers are welcome, but they are layers around the readable step rather than replacements for it.

## Shared infrastructure belongs in clearly named modules

Code genuinely shared across steps should live in small, descriptive modules.

Examples already used by this repository include:

```text
laclaugpt/laclaugpt_mongo.py
laclaugpt/laclaugpt_redis.py
laclaugpt/laclaugpt_ollama.py
laclaugpt/pipeline_io.py
laclaugpt/pipeline_storage.py
laclaugpt/pipeline_models.py
laclaugpt/pipeline_prompts.py
laclaugpt/pipeline_rdf.py
```

The rule of thumb is:

> Shared infrastructure should be abstracted. Research logic should remain visible.

Prefer `from laclaugpt_mongo import ...` over deep framework imports whose purpose is not obvious from the step file.

## Readability over architectural cleverness

Prefer:

- straightforward functions;
- explicit control flow;
- descriptive variable names;
- obvious inputs and outputs;
- visible prompts and theory choices;
- small cohesive support modules;
- deterministic data flow;
- comments that explain why a methodological decision exists.

Avoid unnecessary:

- class hierarchies;
- factories;
- plugin machinery for simple step sequencing;
- dependency-injection frameworks;
- deeply nested utility layers;
- premature abstraction;
- generic enterprise architecture that hides the research procedure.

The reusable `src/laclaugpt_data_analysis/` package may provide storage-neutral contracts, adapters and tested infrastructure. That package must support the readable human pipeline rather than make the scientific pipeline disappear inside it.

## Logging is part of reproducibility

Use extensive human-readable debug/info logging.

A log should make it possible to answer:

> What exactly is this step doing right now, with what data, using which model/prompt, and where is the result going?

Log, when applicable:

- step start and end;
- input file, collection, table or query;
- country, sample and filters;
- number of records;
- current record where useful;
- model/provider actually used;
- prompt stage/version;
- fields passed between steps;
- output destination;
- MongoDB/SQLite/CSV/Allas writes;
- retries and fallbacks;
- validation failures;
- exceptions with enough context to reproduce the failure.

Do not log private data or secrets merely for verbosity. Privacy rules still win.

## Comments and documentation are features

Each major step should ideally document:

- its purpose;
- pipeline position;
- expected inputs;
- fields it preserves;
- fields it creates;
- outputs and destinations;
- databases/files used;
- model/provider expectations;
- important assumptions;
- CLI examples;
- non-obvious transformations;
- research/theory decisions.

Comments should explain why, especially where a decision follows Laclau/Mouffe, Castells, DNA, SNA, populism research, assemblage/network theory or another methodological commitment.

## Theory-heavy prompts are intentional research code

LaclauGPT is not only an ETL system. Prompts encode scientific assumptions.

Therefore:

- keep prompts readable and reviewable;
- do not aggressively shorten theory-rich system instructions;
- do not move them into opaque abstractions merely to make Python files shorter;
- preserve theoretical context and method boundaries;
- version prompt changes when wording can affect model behaviour;
- preserve prompt provenance required by the canonical runtime.

The prompt library under `src/laclaugpt_data_analysis/prompts/` remains the canonical versioned resource system where required by the runtime, while researcher-facing prompt documents and step files should make the method easy to inspect.

## Keep data flow explicit

Every step should make it reasonably obvious:

- what it reads;
- which fields it expects;
- what it preserves;
- which new fields it adds;
- what it writes;
- what the next step receives.

Prefer preserving all previous fields and appending new analysis output over destructive reshaping.

`source_url` remains the canonical source identity. Canonical-record, provenance, evidence, privacy and runtime-data contracts remain authoritative.

## Self-contained does not mean duplicated

A scientific step should be understandable by itself, but boring infrastructure should not be copied into every file.

Good:

```python
from laclaugpt_mongo import ...
from laclaugpt_ollama import ...
```

Less desirable:

```python
from framework.runtime.pipeline.step_factory import AbstractStepProvider
```

The visible step is the unit a researcher audits. Shared infrastructure is there to make that step simpler.

## Migration direction

`LaclauGPT-Multimodal-Analysis` is the architectural/code-style reference for the next AI26 evolution of this repository.

Once the Roihu EP24 reprocessing pipeline is verified end to end:

1. preserve the working EP24 implementation and publication history in its project repository;
2. use its simple step-oriented structure as the basis for modernizing AI26 Data Analysis;
3. adapt the proven EP24/Roihu implementation to AI26 rather than reverting to older opaque architecture;
4. keep the seven human-owned AI26 step files as the visible scientific surface;
5. move reusable storage/model/runtime plumbing into clearly named helper modules around those steps;
6. preserve canonical schemas, evidence, provenance, privacy and distributed operation while doing so.

In short:

> Multimodal-Analysis is the architectural ancestor of the rebuilt AI26 Data-Analysis pipeline.

## Relationship to the package pipeline

The repository currently contains two complementary surfaces:

- `laclaugpt/`: the human-readable, human-owned Phase 2 scientific pipeline and supporting scripts;
- `src/laclaugpt_data_analysis/`: reusable tested contracts, adapters, providers, canonical-record logic and operational infrastructure.

Do not let the second surface erase the first. A future maintainer should be able to start with the numbered `laclaugpt/step_*.py` files and understand what the research pipeline does before learning its deployment machinery.

## Guiding principle

**Readable research software beats clever research software.**

Optimize for inspectability, reproducibility and methodological transparency.
