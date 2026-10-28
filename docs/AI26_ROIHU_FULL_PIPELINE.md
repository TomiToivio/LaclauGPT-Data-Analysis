# AI26 full pipeline on CSC Roihu (#390)

Roihu is a **bounded integration and performance test** against the shared production plane. It is not
a second scheduler and it does not replace Laskin, which remains the authoritative continuous AI26
runner. Nothing here changes the science pipeline: the same `laclaugpt-analysis-worker` entrypoint that
runs nightly on Laskin runs inside the Slurm job.

## Roles

| Host | Role | Scheduling |
| --- | --- | --- |
| Laskin | authoritative continuous analysis | hourly cron, unaffected by this document |
| Roihu | bounded test / performance run | one submitted batch job, then done |

Shared between them: AI26 MongoDB, Redis and CSC Allas namespace. Machine identity is provenance only.

## What this adds

| Piece | Path | Purpose |
| --- | --- | --- |
| bootstrap | `scripts/roihu/install_ai26.sh` | modules, aarch64-aware venv, extras, ffmpeg, model runtime, repository preflight |
| preflight | `scripts/roihu/preflight_ai26.sh` | fails before GPU time is spent: env, frozen inputs, sample, reachability, isolation |
| pipeline | `scripts/roihu/ai26_full_pipeline.sbatch` | preflight → canonical worker → provenance manifest |
| tests | `tests/test_ai26_roihu_full_pipeline.py` | offline refusal/dry-run/contract checks |

## 1. Setup

On a Roihu login node:

```bash
module purge
export AI26_ENV_FILE=$HOME/ai26/roihu.env       # never committed
bash scripts/roihu/install_ai26.sh
```

Notes that cost time if you discover them the hard way:

- **Roihu GPU nodes are aarch64 (GH200).** A Puhti or x86_64 virtualenv cannot be reused; the installer
  builds a fresh one under `LACLAUGPT_SCRATCH`.
- **`module purge` removes the compiler**, and `ffmpeg`'s module needs it — so `gcc` is loaded before
  `ffmpeg`. Reversing that order produces link failures that look unrelated.
- The pipeline reaches a model through `LACLAUGPT_LLM_ENDPOINT`. Either start Ollama inside the job
  (`OLLAMA_HOST=127.0.0.1:11434`) or point at an endpoint reachable from the compute node. Model
  selection stays configurable and is recorded in the run manifest.

The env file holds endpoints and credentials; the repository only ever sees key presence.

## 2. Preflight

```bash
AI26_ENV_FILE=$HOME/ai26/roihu.env bash scripts/roihu/preflight_ai26.sh
```

It checks: env file present, required keys set, frozen `run-manifest.json` / `analysis.json` /
`codebook.json`, a non-empty sample, `LACLAUGPT_RUN_ID` present, and that the run is **not** carrying the
production identity. Values are never printed — only presence.

Offline (no services, no credentials):

```bash
AI26_DRY_RUN=1 bash scripts/roihu/preflight_ai26.sh
```

## 3. Submit

```bash
sbatch scripts/roihu/ai26_full_pipeline.sbatch
```

Plan without submitting:

```bash
AI26_DRY_RUN=1 bash scripts/roihu/ai26_full_pipeline.sbatch
squeue -u "$USER"
sacct -j <JOBID> --format=JobID,State,Elapsed,MaxRSS,AllocTRES
tail -f ai26-full-<JOBID>.out
scancel <JOBID>
```

Resource directives in the script (`gpumedium`, `gres=gpu:gh200:1`, 16 CPUs, 64G, 04:00:00) follow the
documented Roihu GPU shape as read on 2026-10-28 from
<https://docs.csc.fi/computing/running/batch-job-partitions/>: one reserved GPU grants access to up to 72
CPU cores and roughly 217 GB of combined HBM/LPDDR memory. **Confirm the current values before relying
on them**, and copy the script to a private path if your project's account or partition differs.

## 4. Isolation — the rule that matters

A Roihu test reads the same canonical input corpus but must never look like production to the queue:

- `LACLAUGPT_RUN_ID` **must differ** from `LACLAUGPT_PRODUCTION_RUN_ID`. The batch script refuses to run
  otherwise.
- The output/task namespace defaults to `test-<run_id>` and **must start with `test-`**; anything else is
  refused before any work starts.
- The worker binds each task to the frozen manifest's `run_id` and fails closed on a mismatch, so a test
  cannot acknowledge or complete a production task.

This is enforced in two places (preflight and the batch script) because a direct `sbatch` must not be
able to skip the check.

## 5. Provenance

Each run writes `data/runs/<namespace>/run-manifest-<stamp>.json` with: run id, namespace, Slurm job id,
worker id, Git SHA, model, max tasks, exit status, elapsed time, start time. Logs sit beside it. Neither
file contains credentials or research content.

## 6. What is verified, and what is not

**Verified on a workstation (offline):**

- both scripts parse; the isolation guard refuses a production run id, a non-`test-` namespace and a
  missing run id (15 tests);
- dry-run produces the plan without touching any service;
- the batch script uses the canonical worker entrypoint and records provenance fields;
- no production run id or secret is committed (checked by the public-tree policy too).

**Not verified — requires an authorised Roihu account, which this workstation does not have:**

- `install_ai26.sh` actually completing on a GH200 node (modules, wheels, ffmpeg);
- a real `sbatch` run against shared MongoDB/Redis/Allas;
- concurrent Laskin + Roihu execution, contention, interruption and requeue behaviour;
- throughput and resource numbers.

Until those are run and recorded, this issue's acceptance criteria 1–5 remain **unmet by evidence**, and
the runbook above is the manual validation plan.

## 7. Cleanup

```bash
scancel <JOBID>                     # if still queued/running
rm -rf "$LACLAUGPT_SCRATCH/ai26-venv"   # optional: reclaim scratch
```

Leave the shared MongoDB/Redis/Allas data alone. A test run's outputs are namespaced; removing the
run's namespace is a separate, explicit decision.
