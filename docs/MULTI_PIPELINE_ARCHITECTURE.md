# Multi-pipeline architecture (#399)

The repository now carries **three selectable analysis implementations** instead of assuming AI26 is
the only pipeline. Selection is explicit; a wrong id fails.

| id | implementation | source | exec |
| --- | --- | --- | --- |
| `ai26` | AI26 canonical (in-tree) | this repo | in-process |
| `ep24` | EP24 current, Roihu Step 0–9 | Multimodal `main` @ `db123759` | script |
| `ep24-legacy` | EP24 legacy, Puhti era | Multimodal `legacy` @ `e011c342` | script |

## What was imported

A **byte-identical snapshot**, not an adaptation:

- EP24 current: 38 modules (`ep24_*.py`, `step_0`…`step_9`), 10,419 lines.
- EP24 legacy: 5 modules (`puhti_preprocess`, `puhti_frame`, `puhti_summary`, `puhti_populism`,
  `puhti_postprocess`), 1,454 lines.
- 483 KB total, each file recorded with its SHA-256 in `docs/EP24_SOURCE_INVENTORY.json`.

A test recomputes every checksum, so an accidental formatter run or hand edit fails CI rather than
silently changing the science. That test already earned its place: `ruff --fix` rewrote 43 vendored
files during this work, the checksum test caught it, the snapshot was restored, and the vendor
directories are now excluded from Ruff.

## One deliberate deviation from upstream

Five vendored files hard-coded a concrete CSC deployment path (`/scratch/project_2009497/...`). A
public repository must not publish a project identifier, so each occurrence is replaced with
`project_XXXXXXX`. Both hashes are recorded per file — `upstream_sha256` and the committed `sha256` —
and the deviation is listed under `compatibility_deviations` (D-1). Nothing else changed: the
checksum test compares committed bytes against the recorded post-redaction hash, so this one edit is
auditable rather than invisible.

The vendored trees are also excluded from the repository's "bounded Redis client" static rule. That
rule governs this repository's own adapters; rewriting a byte-identical snapshot would break the
fidelity contract. The risk is real and recorded: when the EP24 scripts are executed, the
compatibility wrapper must supply bounded clients.

## Finding: the upstream code is scripts, not importable modules

Naively importing the snapshot executes it. `puhti_populism.py` runs `for country in countries:` at
module level, `puhti_summary.py` opens a SQLite file, and several `ep24_*` modules parse `argv` on
import. Importing them is *running the analysis*.

So the registry records `execution="script"` for both EP24 versions, and the test suite **compiles**
every vendored file instead of importing it — proving the snapshot is intact without executing a
pipeline. Running them is a separate, documented step under a compatibility environment; that is the
difference between "the code is here" and "the pipeline ran".

## Selection

```bash
laclaugpt-analysis pipelines list
laclaugpt-analysis pipelines show ep24-legacy --json
```

```python
from laclaugpt_data_analysis.pipelines import get_pipeline

spec = get_pipeline("ep24-legacy")   # raises UnknownPipeline, never falls back
spec.source_sha, spec.stages, spec.execution
```

AI26 keeps its existing entry points (`laclaugpt-analysis-worker`, Laskin cron contracts); the registry
is additive, and a test asserts the worker entry point still points where it did.

## Namespace separation

`pipeline_keys()` derives every execution key from project **and pipeline** and run:

```
laclaugpt:<project>:<pipeline>:<run>:stream:tasks
laclaugpt:<project>:<pipeline>:<run>:group:workers
laclaugpt:<project>:<pipeline>:<run>:stream:dead
<project>__<pipeline>__analysis_results
<project>/<pipeline>/<run>/…            (Allas prefix)
```

Tests assert that AI26, EP24 and EP24-legacy produce three distinct values for every key even with an
identical run id — the same frozen record analysed by two versions must never share a queue or a
result collection. Result *collections* stay per-pipeline; the run id lives on each document, which is
asserted so nobody assumes run-level collection isolation that does not exist.

## What is not done

- **Running either EP24 snapshot has not been executed.** The code is imported and parseable; no
  legacy compatibility environment, no Roihu submission, no sample run.
- Current EP24's Roihu install/preflight/submit scripts are **not** adapted here.
- Version-aware comparison of a frozen sample across EP24 and EP24-legacy is not implemented.
- `ai26` remains in-tree rather than moved under `pipelines/ai26/`: moving a running production
  pipeline is a destructive change that belongs in its own PR with the migration notes the issue asks
  for, not in the same change that introduces the registry.
