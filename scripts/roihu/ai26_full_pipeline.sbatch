#!/bin/bash
# AI26 — bounded full-pipeline run on CSC Roihu (#390).
#
# One submission runs the canonical Step 0–9 analysis pipeline on a bounded sample: preflight, the
# distributed worker (which executes the canonical pipeline per task, no Roihu-only science code),
# then a provenance manifest recording what actually ran.
#
# Resource directives below are the documented Roihu GPU shape as of 2026-10-28
# (https://docs.csc.fi/computing/running/batch-job-partitions/): one GH200 GPU grants up to 72 CPU
# cores and ~217 GB total memory per reserved GPU. Confirm against current CSC documentation before
# relying on them, and copy the file to a private deployment path if your project differs.
#
#   sbatch scripts/roihu/ai26_full_pipeline.sbatch
#   AI26_DRY_RUN=1 bash scripts/roihu/ai26_full_pipeline.sbatch    # offline plan, no services
#
#SBATCH --job-name=ai26-full-pipeline
#SBATCH --partition=gpumedium
#SBATCH --gres=gpu:gh200:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=ai26-full-%j.out
#SBATCH --error=ai26-full-%j.err

set -euo pipefail

ROOT_DIR=${LACLAUGPT_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
ENV_FILE=${AI26_ENV_FILE:-"$ROOT_DIR/data/config/ai26/roihu.env"}
DRY_RUN=${AI26_DRY_RUN:-0}
MAX_TASKS=${LACLAUGPT_MAX_TASKS:-25}
LEASE_MS=${LACLAUGPT_RECLAIM_IDLE_MS:-300000}

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }
die() { printf '[%s] ERROR: %s\n' "$(date -Is)" "$*" >&2; exit 2; }

log "AI26 full pipeline on ${SLURM_JOB_ID:-manual} (dry_run=$DRY_RUN)"
log "repo: $ROOT_DIR"

[[ -f "$ENV_FILE" ]] || die "missing env file: $ENV_FILE"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# --- fail-closed isolation -----------------------------------------------------------------------
# A Roihu batch is a test against the shared production plane. It must never adopt the production run
# identity or write into a production namespace, because that would let test results mark real tasks
# complete. This is checked here as well as in preflight so a direct `sbatch` cannot skip it.
: "${LACLAUGPT_RUN_ID:?LACLAUGPT_RUN_ID is required}"
if [[ -n "${LACLAUGPT_PRODUCTION_RUN_ID:-}" && "$LACLAUGPT_RUN_ID" == "$LACLAUGPT_PRODUCTION_RUN_ID" ]]; then
  die "LACLAUGPT_RUN_ID equals LACLAUGPT_PRODUCTION_RUN_ID; a test must use its own run id"
fi
NAMESPACE=${LACLAUGPT_TEST_NAMESPACE:-test-${LACLAUGPT_RUN_ID}}
[[ "$NAMESPACE" == test-* ]] || die "namespace '$NAMESPACE' must start with 'test-'"
export LACLAUGPT_TEST_NAMESPACE="$NAMESPACE"
log "run id: $LACLAUGPT_RUN_ID   namespace: $NAMESPACE"

export LACLAUGPT_PROJECT_ID=${LACLAUGPT_PROJECT_ID:-ai26}
export LACLAUGPT_MACHINE=roihu
export LACLAUGPT_EXECUTION=slurm
export LACLAUGPT_STORAGE=distributed
export LACLAUGPT_DATA_BACKEND=mongodb
export LACLAUGPT_CACHE_BACKEND=redis
export LACLAUGPT_OBJECT_BACKEND=s3

# --- provenance ----------------------------------------------------------------------------------
GIT_SHA=$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || echo unknown)
RUN_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
MANIFEST_DIR=${LACLAUGPT_RUN_MANIFEST_DIR:-"$ROOT_DIR/data/runs/$NAMESPACE"}
WORKER_ID="roihu-${SLURM_JOB_ID:-manual}-${SLURM_ARRAY_TASK_ID:-0}"

if [[ "$DRY_RUN" == "1" ]]; then
  log "DRY RUN — nothing will be executed"
  log "  preflight:  bash scripts/roihu/preflight_ai26.sh"
  log "  worker:     laclaugpt-analysis-worker --run-manifest ... --max-tasks $MAX_TASKS --worker-id $WORKER_ID"
  log "  manifest:   $MANIFEST_DIR/run-manifest-$RUN_STAMP.json (git $GIT_SHA)"
  exit 0
fi

# --- preflight -----------------------------------------------------------------------------------
log "preflight"
bash "$ROOT_DIR/scripts/roihu/preflight_ai26.sh" || die "preflight failed; not submitting work"

# --- pipeline ------------------------------------------------------------------------------------
# `laclaugpt-analysis-worker` executes the canonical pipeline (Steps 0–9) for each claimed task. There
# is deliberately no Roihu-specific science path: the same entrypoint runs on Laskin.
mkdir -p "$MANIFEST_DIR"
started=$(date +%s)
log "starting worker $WORKER_ID (max_tasks=$MAX_TASKS)"

set +e
laclaugpt-analysis-worker \
  --run-manifest "${LACLAUGPT_PRIVATE_CONFIG_DIR}/run-manifest.json" \
  --private-config "${LACLAUGPT_PRIVATE_CONFIG_DIR}/analysis.json" \
  --codebook "${LACLAUGPT_PRIVATE_CONFIG_DIR}/codebook.json" \
  --worker-id "$WORKER_ID" \
  --seed-ready \
  --reclaim-idle-ms "$LEASE_MS" \
  --max-tasks "$MAX_TASKS" 2>&1 | tee "$MANIFEST_DIR/worker-$RUN_STAMP.log"
worker_status=${PIPESTATUS[0]}
set -e
finished=$(date +%s)
elapsed=$((finished - started))

cat > "$MANIFEST_DIR/run-manifest-$RUN_STAMP.json" <<JSON
{
  "run_id": "${LACLAUGPT_RUN_ID}",
  "namespace": "${NAMESPACE}",
  "execution": "slurm",
  "machine": "roihu",
  "slurm_job_id": "${SLURM_JOB_ID:-manual}",
  "worker_id": "${WORKER_ID}",
  "git_sha": "${GIT_SHA}",
  "ollama_model": "${LACLAUGPT_OLLAMA_MODEL:-unknown}",
  "llm_endpoint_present": true,
  "max_tasks": ${MAX_TASKS},
  "worker_exit_status": ${worker_status},
  "elapsed_seconds": ${elapsed},
  "started_at": "${RUN_STAMP}"
}
JSON

log "worker exit status: $worker_status after ${elapsed}s"
log "provenance manifest: $MANIFEST_DIR/run-manifest-$RUN_STAMP.json"
if [[ "$worker_status" -ne 0 ]]; then
  die "worker failed; see $MANIFEST_DIR/worker-$RUN_STAMP.log"
fi
log "done"
