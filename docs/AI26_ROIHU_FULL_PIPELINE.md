# AI26 Roihu bounded full-pipeline test alongside Laskin

Issue #390. **Laskin remains the real-time production runner.** Roihu is an optional bounded Slurm integration test. Do not install a Roihu cron job or replace Laskin's scheduler.

## Existing scientific implementation

The `laclaugpt-analysis-worker` entry point invokes the canonical AI26 pipeline using remote MongoDB for records/results, Redis for task coordination and CSC Allas for objects. It is not a Roihu-specific scientific fork. Inspect `docs/AI26_DISTRIBUTED_WORKER.md` for the frozen manifest and exact task contract. Compare outputs with `docs/AI26_STEP_BY_STEP.md` for Step 0–9 coverage. **Verify each intended stage is enabled in the frozen analysis configuration**; running the worker alone does not prove that optional stages ran. Do not claim an entire 0–9 run until stage outputs are audited.

## Installation

On an allocated Roihu environment with CSC modules available, check `bash scripts/roihu/install_ai26.sh --check` then run `LACLAUGPT_ROIHU_VENV=/path/in/project/.venv-roihu bash scripts/roihu/install_ai26.sh`. This uses architecture-compatible CSC Python/PyTorch modules and installs the remote, Ollama and analysis extras. Install a Roihu ARM64-compatible Ollama binary into private project storage, expose it on PATH, and pre-pull the frozen model (`gemma4:12b` is the distributed worker's documented test default). GPU/model compatibility and FFmpeg must be verified on the target allocation.

Create a private environment file with permissions 600 outside version control (default `data/config/ai26/roihu.env`) containing `LACLAUGPT_RUN_ID=roihu-test-<unique-id>`, `LACLAUGPT_PRIVATE_CONFIG_DIR`, `LACLAUGPT_MONGODB_URI`, `LACLAUGPT_REDIS_URL`, `LACLAUGPT_S3_ENDPOINT`, `LACLAUGPT_S3_BUCKET`, storage authentication and optional `LACLAUGPT_ROIHU_VENV`. Do not commit or paste secrets. Include `LACLAUGPT_MAX_TASKS=5`.

The private config directory must contain `run-manifest.json`, `analysis.json`, and `codebook.json`. Manifest must match the test run ID, configuration and codebook SHA-256 hashes, model and public Git revision; follow `docs/AI26_DISTRIBUTED_WORKER.md`. **Keep canonical source records in the shared MongoDB but isolate test task/run namespaces.** Before the test, confirm the Redis stream and MongoDB output keys are scoped by run ID (inspect existing implementation and query the actual keys); a run ID alone is not sufficient isolation if the deployed worker shares a global queue. Do not submit until this is proven. Seed only a bounded, explicitly selected sample into that isolated namespace. Roihu's script intentionally does not use `--seed-ready` to prevent surprising production task creation.

## Prove the wiring without spending a task

```bash
LACLAUGPT_DRY_RUN=1 bash scripts/roihu/ai26_full_pipeline.sbatch
```

Prints the run id, isolated stream name, task bound, model, config directory, host and Git
SHA, then exits **before** preflight and before any claim. It deliberately does not
require MongoDB, Redis or Allas: preflight is fail-closed on unreachable services, which
would make the dry run useless precisely on a host being prepared. Add
`LACLAUGPT_DRY_RUN_PREFLIGHT=1` to include the real preflight anyway.

## Provenance of every run

Each job writes `provenance_<job id>.json` beside the logs (`LACLAUGPT_ROIHU_PROVENANCE`
overrides the path), with a `start` and an `end` block:

| field | why it is there |
| --- | --- |
| `run_id`, `project_id`, `worker_id` | identifies the isolated namespace the work belonged to |
| `host`, `machine`, `platform`, `python` | says where it ran, which is how nondeterminism is explained later |
| `git_sha` | the exact code revision, suffixed `-dirty` if the tree was modified — a run from a modified tree must not claim the commit's behaviour |
| `model`, `llm_mode`, `cloud_fallback_allowed` | the model actually used, and that no cloud fallback was permitted |
| `frozen_config` | SHA-256 of `run-manifest.json`, `analysis.json`, `codebook.json` |
| `slurm` | job id, partition, account, CPUs, memory, GPUs, array index |
| `worker_status`, `elapsed_seconds` | the outcome and duration, recorded on exit including on failure |

This is what makes a Roihu run comparable to a concurrent Laskin run instead of merely
finished.

## Submit and inspect

From the repository checkout with the private environment path configured:

```bash
export LACLAUGPT_ENV_FILE=/private/ai26/roihu.env
sbatch --account=<CSC_PROJECT> --partition=gpumedium --time=04:00:00 \
  --export=ALL,LACLAUGPT_ENV_FILE scripts/roihu/ai26_full_pipeline.sbatch
squeue -u "$USER"
sacct -j <JOB_ID> --format=JobID,State,Elapsed,MaxRSS,ExitCode
scancel <JOB_ID>
```

The Slurm directives are examples; check live CSC partition/GPU availability and adapt resource arguments to the project allocation. Slurm stdout/stderr are written to the submission directory by default. Ollama logs stay in the private log directory.

## Simultaneous validation matrix

1. Confirm Laskin's existing cron is active, healthy and using its production run/queue; do **not** pause or reconfigure it.
2. Freeze public commit, schema, model and codebook/config for a five-record representative Roihu test. Verify test/production queue isolation before submission.
3. Check MongoDB, Redis and Allas connectivity from a Roihu allocation without printing credentials.
4. Seed test-specific reference-only Redis tasks through the existing controlled worker API. Confirm no production claim will be possible.
5. Submit Roihu Slurm; watch both Laskin cron successes and Roihu Slurm state.
6. Audit every required scientific stage (0–9 or current equivalent), media staging, derived Allas references, durable MongoDB result keys, record counts, output shape, SHA/model/prompt/codebook provenance and missing stages.
7. Kill/requeue a bounded test job; inspect lease/reclaim and duplicate prevention. Test missing media and incompatible manifests.
8. Save a redacted report: date, commit, run ID, stage completeness, per-stage timings, record counts, failures, Allas object checks, Laskin unaffected, and any outstanding blocks.

## Still requires the cluster

Nothing in this repository can perform these, and the issue must not be marked complete
until they are done on a real allocation:

1. **Install on Roihu** — CSC modules, ARM64/GH200 PyTorch, FFmpeg, a compatible Ollama
   binary and the pre-pulled model.
2. **A real `sbatch` submission** through the canonical pipeline, with stage-by-stage
   evidence that every required stage ran (running the worker does not prove optional
   stages were enabled).
3. **Live isolation check** — confirm from inside the allocation that the Redis stream and
   group are the `roihu-test-*` ones, and that production keys are untouched.
4. **Concurrent observation** — Laskin cron healthy while the Roihu job runs, with no
   double-claiming or overwritten results.
5. **Interruption and reclaim** — kill and requeue a bounded job; confirm no duplicate
   results.
6. **The comparison report** — counts, timings, failures, storage paths, and an explanation
   of any hardware or model nondeterminism.

## Limits and safety

This repository change cannot itself submit CSC jobs, install project credentials, prove Roihu GPU/model compatibility or establish live Mongo/Redis/Allas connectivity. Do not mark the issue fully complete until a real Slurm run and simultaneous Laskin observation have been performed. Never seed/claim production tasks from the test. Existing production Laskin wrapper is unchanged.
