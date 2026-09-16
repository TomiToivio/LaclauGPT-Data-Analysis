#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ENV_FILE=${LACLAUGPT_ENV_FILE:-"$ROOT_DIR/data/config/ai26/laskin.env"}
PRIVATE_DIR=${LACLAUGPT_PRIVATE_CONFIG_DIR:-"$ROOT_DIR/data/config/ai26"}
LOCK_FILE=${LACLAUGPT_AI26_ANALYSIS_LOCK:-"$ROOT_DIR/data/tmp/ai26-laskin-analysis.lock"}

mkdir -p "$ROOT_DIR/data/tmp" "$ROOT_DIR/data/logs"
[[ -f "$ENV_FILE" ]] || { echo "missing env file: $ENV_FILE" >&2; exit 2; }

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${LACLAUGPT_RUN_ID:?required}"
: "${LACLAUGPT_MONGODB_URI:?required}"
: "${LACLAUGPT_REDIS_URL:?required}"
: "${LACLAUGPT_S3_ENDPOINT:?required}"
: "${LACLAUGPT_S3_BUCKET:?required}"
: "${OLLAMA_HOST:?required}"

export LACLAUGPT_PROJECT_ID=ai26
export LACLAUGPT_MACHINE=linux-server
export LACLAUGPT_EXECUTION=cron
export LACLAUGPT_STORAGE=distributed
export LACLAUGPT_DATA_BACKEND=mongodb
export LACLAUGPT_CACHE_BACKEND=redis
export LACLAUGPT_OBJECT_BACKEND=s3
export LLM_MODE=${LLM_MODE:-local}
export LLM_ALLOW_CLOUD_FALLBACK=${LLM_ALLOW_CLOUD_FALLBACK:-0}
export LACLAUGPT_OLLAMA_MODEL=${LACLAUGPT_OLLAMA_MODEL:-gemma4:12b}
export LACLAUGPT_PRIVATE_CONFIG_DIR="$PRIVATE_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "AI26 Laskin analysis already running; exiting cleanly" >&2
  exit 0
fi

cd "$ROOT_DIR"
echo "[$(date -Is)] AI26 Laskin analysis start run=$LACLAUGPT_RUN_ID"
laclaugpt-analysis-worker \
  --run-manifest "$PRIVATE_DIR/run-manifest.json" \
  --private-config "$PRIVATE_DIR/analysis.json" \
  --codebook "$PRIVATE_DIR/codebook.json" \
  --worker-id "laskin-cron-${HOSTNAME:-unknown}" \
  --seed-ready \
  --reclaim-idle-ms "${LACLAUGPT_RECLAIM_IDLE_MS:-300000}" \
  --max-tasks "${LACLAUGPT_MAX_TASKS:-10}"
echo "[$(date -Is)] AI26 Laskin analysis end run=$LACLAUGPT_RUN_ID"
