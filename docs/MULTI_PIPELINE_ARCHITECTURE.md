# Multi-pipeline architecture (#399)

This repository analyses more than one project. Before #399 it had one runnable pipeline
and AI26 was the *implementation* rather than an entry in a catalogue, so running EP24
meant running a different checkout. A pipeline is now a named, explicit choice.

## Registered pipelines

| id | implementation | stages | status |
| --- | --- | --- | --- |
| `ai26` | AI26 canonical stages in this repository | 7 | production; unchanged by #399 |
| `ep24` | current EP24, Roihu Step 0–9, imported from upstream `main` | 10 | importable and selectable here |
| `ep24-legacy` | historical Puhti-era EP24, imported from upstream `legacy` | 5 | preserved for reproduction; needs its compatibility environment |

```bash
laclaugpt-analysis-pipelines list
laclaugpt-analysis-pipelines show ep24
laclaugpt-analysis-pipelines check ep24 --strict
laclaugpt-analysis-pipelines namespace ep24 --run-id my-run
```

Selection is explicit. There is **no default and no fallback**: a caller that does not
name a pipeline does not get one silently chosen for it.

## Four identities that must not be confused

| identity | example | why it is separate |
| --- | --- | --- |
| project / dataset | `ep24` | what the records are |
| pipeline implementation version | `ep24` @ `db123759…` | which code analysed them |
| scientific configuration / codebook version | private codebook SHA | what the coding rules were |
| execution run id | `roihu-test-abc123` | which attempt produced this |

Two versions must be able to analyse the **same input** without their outputs becoming
indistinguishable. The pipeline id is therefore part of every durable key, not metadata
attached afterwards:

```
analysis:ep24:my-run:tasks            analysis_results__ep24
analysis:ep24-legacy:my-run:tasks     analysis_results__ep24-legacy
```

A shared stream would let one version consume the other's tasks; a shared result
collection would let one overwrite the other. `pipeline_namespace()` returns these keys
and a test asserts all five are distinct across the three pipelines for one run id.

## Imported implementations, not wrappers

Both EP24 versions are vendored snapshots, produced by `tools/vendor_pipeline.py` from a
**pinned commit**:

- `src/laclaugpt_data_analysis/pipelines/ep24/` — 91 files from upstream `main`
  (`db123759fe21b194275d87d6ccc3b7c4f98a2055`), including `step_0…step_9`, `ep24_pipeline`,
  `ep24_cli`, `ep24_schema`, `scripts/ep24` and `config`.
- `src/laclaugpt_data_analysis/pipelines/ep24_legacy/` — the 5 historical scripts
  (`puhti_preprocess`, `puhti_frame`, `puhti_summary`, `puhti_populism`,
  `puhti_postprocess`) from upstream `legacy`
  (`e011c34274c41923e801c32c824c5afa7468e1a1`).

Each snapshot carries `PROVENANCE.json`: source repository, exact SHA, license, per-file
SHA-256 and the import policy. `test_vendored_files_match_their_recorded_hashes` re-hashes
every file, so drift is detected rather than suspected.

Upstream's own test suite is deliberately **not** vendored: it targets upstream's
environment and would be collected by this repository's CI, failing for reasons that say
nothing about the import.

### Sync policy

The snapshots are frozen. Upstream is not a runtime dependency, because a branch
reference would mean the "historical" implementation silently changing. To take an
upstream change: pin a new SHA, run `tools/vendor_pipeline.py` into a scratch directory,
review the diff, then re-import with `--force` and record why in the PR. The tool refuses
to overwrite an existing snapshot without that flag.

## Legacy EP24 is preserved, not modernised

`ep24-legacy` imports `cv2`, `easyocr`, `ollama` and `pandas`. Those are *its* historical
requirements, and they are declared rather than installed here:

```
$ laclaugpt-analysis-pipelines check ep24-legacy --strict
{ "import_error": "ModuleNotFoundError: No module named 'easyocr'", "selectable": false }
```

It exits non-zero. That is the correct answer, not a bug: the alternative — declaring it
selectable — would let a caller believe a historical run happened when nothing ran.
Reproduce it in an isolated environment built from its own requirements; do not add
OpenCV and EASYOCR to this package to make a registry row look green.

## AI26 is unchanged

The registry describes AI26 with the stage names that actually exist in
`laclaugpt_data_analysis/stages/`; a test fails if that list drifts. The Laskin realtime
runner keeps its CLI and environment contract, and no AI26 module imports the pipelines
package.

## Adding a pipeline

1. `tools/vendor_pipeline.py` from a pinned SHA into `pipelines/<id>/` (or write native
   code in this repository for anything not imported).
2. Register a `PipelineSpec` in `pipelines/__init__.py` with stages, entry module and
   declared requirements.
3. Add the namespace check: two pipelines on one run id must produce different keys.
4. Declare requirements honestly — a missing dependency must show up in `check`, not in
   the middle of a run.

## What is not done

- No live EP24 run has been executed from this repository, on Roihu or elsewhere; the
  EP24 Roihu orchestration scripts are vendored but not wired to this package's worker.
- The legacy compatibility environment is documented, not provisioned.
- Version-aware comparison of one frozen EP24 sample across current and legacy is
  prepared for (separate namespaces and provenance) but not exercised.
