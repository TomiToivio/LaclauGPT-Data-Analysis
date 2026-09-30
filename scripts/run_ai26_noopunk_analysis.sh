#!/usr/bin/env bash
# AI26 Phase 2 analysis on NooPunk -- a BOUNDED, USER-ACTIVATED batch
# (issue LaclauGPT#71).
#
# NooPunk is an interactive workstation: analysis is OFF BY DEFAULT and runs only
# when the user asks for it. There is deliberately NO cron entry and no perpetual
# scheduler here -- see docs/AI26_NOOPUNK_ANALYSIS.md. Laskin remains the
# always-on execution node; this wrapper exists so the user can test the full
# pipeline against the same shared queue without permanently consuming the GPU.
#
# Usage:
#   run_ai26_noopunk_analysis.sh [--model local|cloud] [--max-tasks N] [--dry-run]
#
#   --model local   gemma4:e2b        (default; lighter, for local testing)
#   --model cloud   gemma4:31b-cloud  (explicit opt-in only, never implicit)
#   --max-tasks N   bounded batch size (default 3, deliberately small)
#   --dry-run       validate configuration and exit without claiming work
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ENV_FILE=${LACLAUGPT_ENV_FILE:-"$ROOT_DIR/data/config/ai26/noopunk.env"}
LOCK_FILE=${LACLAUGPT_AI26_ANALYSIS_LOCK:-"$ROOT_DIR/data/tmp/ai26-noopunk-analysis.lock"}

MODEL_KIND="local"
MAX_TASKS="${LACLAUGPT_MAX_TASKS:-3}"
DRY_RUN=0

while (( $# )); do
  case "$1" in
    --model)      MODEL_KIND="${2:-}"; shift 2 ;;
    --max-tasks)  MAX_TASKS="${2:-}"; shift 2 ;;
    --dry-run)    DRY_RUN=1; shift ;;
    -h|--help)    sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "ERROR: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

case "$MODEL_KIND" in
  local|cloud) ;;
  *) fail "--model must be local or cloud (got '$MODEL_KIND'); there is no default that reaches the cloud" ;;
esac
case "$MAX_TASKS" in
  ''|*[!0-9]*) fail "--max-tasks must be a positive integer (got '$MAX_TASKS')" ;;
esac
(( MAX_TASKS >= 1 )) || fail "--max-tasks must be at least 1"

mkdir -p "$ROOT_DIR/data/tmp" "$ROOT_DIR/data/logs"
[[ -f "$ENV_FILE" ]] || fail "missing env file: $ENV_FILE (NooPunk settings live in the private repository)"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

PRIVATE_DIR=${LACLAUGPT_PRIVATE_CONFIG_DIR:-"$ROOT_DIR/data/config/ai26"}

# Same required surface as Laskin: the shared distributed AI26 backend. NooPunk
# must not substitute a local store, so these are required rather than optional.
: "${LACLAUGPT_RUN_ID:?required}"
: "${LACLAUGPT_MONGODB_URI:?required}"
: "${LACLAUGPT_REDIS_URL:?required}"
: "${LACLAUGPT_S3_BUCKET:?required}"
: "${LACLAUGPT_LLM_ENDPOINT:?required}"

export OLLAMA_HOST="$LACLAUGPT_LLM_ENDPOINT"

# --- identity: identical to Laskin except for the machine class ---
export LACLAUGPT_PROJECT_ID=ai26
export LACLAUGPT_MACHINE=laptop          # interactive workstation, not linux-server
export LACLAUGPT_EXECUTION=interactive   # user-activated, not cron
export LACLAUGPT_STORAGE=distributed
export LACLAUGPT_DATA_BACKEND=mongodb
export LACLAUGPT_CACHE_BACKEND=redis
export LACLAUGPT_OBJECT_BACKEND=s3

# --- model selection: explicit, logged, and never a silent cloud upgrade ---
case "$MODEL_KIND" in
  local)
    MODEL="${LACLAUGPT_LLM_MODEL:-gemma4:e2b}"
    ;;
  cloud)
    MODEL="${LACLAUGPT_LLM_CLOUD_MODEL:-gemma4:31b-cloud}"
    echo "NOTE: cloud model explicitly requested: $MODEL" >&2
    ;;
esac

export LLM_MODE="$MODEL_KIND"
export LACLAUGPT_LLM_MODE="$([ "$MODEL_KIND" = cloud ] && echo cloud-ollama || echo local-ollama)"
# Cloud fallback from the local path stays off: a local run that silently
# escalated to the cloud model would be both a rules fork and an unasked cost.
export LLM_ALLOW_CLOUD_FALLBACK=0
export LACLAUGPT_LLM_MODEL="$MODEL"
export LACLAUGPT_OLLAMA_MODEL="$MODEL"
export LACLAUGPT_PRIVATE_CONFIG_DIR="$PRIVATE_DIR"

echo "[$(date -Is)] AI26 NooPunk analysis: model=$MODEL mode=$MODEL_KIND batch=$MAX_TASKS endpoint=$LACLAUGPT_LLM_ENDPOINT"

if (( DRY_RUN )); then
  echo "dry-run: configuration validated; no work claimed"
  exit 0
fi

# A bounded batch, guarded against overlapping interactive runs. NooPunk should
# not race Laskin: claim a small number of tasks and exit.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "AI26 NooPunk analysis already running; exiting cleanly" >&2
  exit 0
fi

cd "$ROOT_DIR"
laclaugpt-analysis-worker \
  --run-manifest "$PRIVATE_DIR/run-manifest.json" \
  --private-config "$PRIVATE_DIR/analysis.json" \
  --codebook "$PRIVATE_DIR/codebook.json" \
  --worker-id "noopunk-interactive-${HOSTNAME:-unknown}" \
  --seed-ready \
  --reclaim-idle-ms "${LACLAUGPT_RECLAIM_IDLE_MS:-300000}" \
  --max-tasks "$MAX_TASKS"
echo "[$(date -Is)] AI26 NooPunk analysis end run=$LACLAUGPT_RUN_ID"
