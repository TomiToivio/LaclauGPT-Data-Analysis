#!/usr/bin/env bash
# AI26 distributed analysis on Laskin — manual bring-up and cron entry point.
#
# Architecture (docs/AI26_DISTRIBUTED_WORKER.md): the worker is BOUNDED. It
# claims at most --max-tasks tasks and exits. Cron therefore drains the queue
# every few minutes; nothing here starts a perpetual scheduler or an immortal
# worker.
#
# Usage:
#   scripts/run_ai26_laskin.sh --once            one bounded cycle
#   scripts/run_ai26_laskin.sh --debug --once    verbose diagnostics on stdout
#   scripts/run_ai26_laskin.sh --check           preflight only, no work
#   scripts/run_ai26_laskin.sh                   same as --once (cron-safe)
#
# Exit codes: 0 success, 2 configuration/preflight failure, 3 already running,
#             4 periodic-report failure, otherwise worker status is propagated.
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# The private root is machine-specific and must never be committed. Supply it
# through the environment; the wrapper fails fast when it is missing.
PRIVATE_ROOT=${LACLAUGPT_PRIVATE_ROOT:-}
PRIVATE_CONFIG_DIR=${LACLAUGPT_PRIVATE_CONFIG_DIR:-}
LOCK_FILE=${LACLAUGPT_AI26_ANALYSIS_LOCK:-}

MAX_TASKS=${LACLAUGPT_MAX_TASKS:-10}
RECLAIM_IDLE_MS=${LACLAUGPT_RECLAIM_IDLE_MS:-300000}
RUN_MODE="once"
CHECK_ONLY=0
DEBUG_FLAG=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --once)   RUN_MODE="once" ;;
    --debug)  DEBUG_FLAG=1 ;;
    --check)  CHECK_ONLY=1 ;;
    -h|--help)
      sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *)
      echo "unknown option: $1" >&2
      exit 2 ;;
  esac
  shift
done

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }
fail() { printf '[%s] ERROR: %s\n' "$(date -Is)" "$*" >&2; exit 2; }

# ---------------------------------------------------------------- preflight --
[[ -d "$ROOT_DIR" ]] || fail "repository root not found: $ROOT_DIR"
[[ -n "$PRIVATE_ROOT" ]] || fail "LACLAUGPT_PRIVATE_ROOT is required (machine-specific private root; never committed)"
[[ -d "$PRIVATE_ROOT" ]] || fail "private root not found: $PRIVATE_ROOT"
if [[ -z "$PRIVATE_CONFIG_DIR" ]]; then
  PRIVATE_CONFIG_DIR="$PRIVATE_ROOT/analysis/ai26"
fi
if [[ -z "$LOCK_FILE" ]]; then
  LOCK_FILE="$PRIVATE_CONFIG_DIR/run/ai26-laskin-analysis.lock"
fi
ENV_FILE=${LACLAUGPT_ENV_FILE:-"$PRIVATE_CONFIG_DIR/laskin.env"}
[[ -f "$ENV_FILE" ]] || fail "missing private environment file: $ENV_FILE"

# Load the private runtime contract. Cron inherits no interactive shell, which
# is the whole reason this wrapper exists.
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# Required settings: fail fast rather than half-run a distributed job.
: "${LACLAUGPT_PROJECT_ID:?LACLAUGPT_PROJECT_ID is required}"
: "${LACLAUGPT_RUN_ID:?LACLAUGPT_RUN_ID is required}"
: "${LACLAUGPT_MONGODB_URI:?LACLAUGPT_MONGODB_URI is required}"
: "${LACLAUGPT_REDIS_URL:?LACLAUGPT_REDIS_URL is required}"
: "${LACLAUGPT_S3_BUCKET:?LACLAUGPT_S3_BUCKET is required}"

[[ "$LACLAUGPT_PROJECT_ID" == "ai26" ]] || fail "this wrapper only runs the ai26 project"

# Analysis semantics come from the project layer; capability from the machine
# layer; scheduling from this cron layer. Never hard-code credentials here.
export LACLAUGPT_MACHINE=${LACLAUGPT_MACHINE:-laskin}
export LACLAUGPT_EXECUTION=${LACLAUGPT_EXECUTION:-cron}
export LACLAUGPT_STORAGE=${LACLAUGPT_STORAGE:-distributed}
export LACLAUGPT_DATA_BACKEND=${LACLAUGPT_DATA_BACKEND:-mongodb}
export LACLAUGPT_CACHE_BACKEND=${LACLAUGPT_CACHE_BACKEND:-redis}
export LACLAUGPT_OBJECT_BACKEND=${LACLAUGPT_OBJECT_BACKEND:-s3}
export LACLAUGPT_LLM_MODE=${LACLAUGPT_LLM_MODE:-local-ollama}
export LACLAUGPT_LLM_MODEL=${LACLAUGPT_LLM_MODEL:-gemma4:12b}
export LACLAUGPT_LLM_ENDPOINT=${LACLAUGPT_LLM_ENDPOINT:-http://127.0.0.1:11500}
export LACLAUGPT_CALLER=${LACLAUGPT_CALLER:-laskin-cron}
# Cloud inference is never silently enabled for a research run.
export LACLAUGPT_CLOUD_ALLOWED=false
export LLM_ALLOW_CLOUD_FALLBACK=0

# Debug/trace are opt-in. Trace additionally allows full prompt/evidence
# bodies into the log, so it must be requested explicitly.
if (( DEBUG_FLAG )); then
  export LACLAUGPT_DEBUG=${LACLAUGPT_DEBUG:-1}
fi

# Resolve the interpreter without relying on an interactive shell or PATH.
PY="$ROOT_DIR/.venv/bin/python"
[[ -x "$PY" ]] || fail "virtualenv interpreter not found: $PY (create it and pip install -e '.[remote,ollama]')"

# Ollama preflight: the endpoint must answer and the model must be present.
OLLAMA_BASE="${LACLAUGPT_LLM_ENDPOINT%/}"
if command -v curl >/dev/null 2>&1; then
  if ! curl -fsS --max-time 10 "$OLLAMA_BASE/api/tags" -o /tmp/ai26-ollama-tags.$$ 2>/dev/null; then
    fail "Ollama endpoint unreachable: $OLLAMA_BASE (start Ollama or fix LACLAUGPT_LLM_ENDPOINT)"
  fi
  if ! grep -q "\"${LACLAUGPT_LLM_MODEL}\"" /tmp/ai26-ollama-tags.$$; then
    rm -f /tmp/ai26-ollama-tags.$$
    fail "model '${LACLAUGPT_LLM_MODEL}' not present on $OLLAMA_BASE (ollama pull ${LACLAUGPT_LLM_MODEL})"
  fi
  rm -f /tmp/ai26-ollama-tags.$$
  log "ollama ok: $OLLAMA_BASE serves ${LACLAUGPT_LLM_MODEL}"
else
  log "curl not available; skipping Ollama preflight"
fi

# Configuration validation (offline, redacted).
if ! "$PY" -m laclaugpt_data_analysis.preflight; then
  log "preflight reported a configuration problem"
fi

if (( CHECK_ONLY )); then
  log "preflight complete (--check); no tasks claimed"
  exit 0
fi

# --------------------------------------------------------------- run cycle --
RUN_MANIFEST="$PRIVATE_CONFIG_DIR/run-manifest.json"
PRIVATE_CONFIG="$PRIVATE_CONFIG_DIR/analysis.json"
CODEBOOK="$PRIVATE_CONFIG_DIR/codebook.json"
for required in "$RUN_MANIFEST" "$PRIVATE_CONFIG" "$CODEBOOK"; do
  [[ -f "$required" ]] || fail "missing frozen runtime input: $required"
done

mkdir -p "$(dirname "$LOCK_FILE")" "$PRIVATE_CONFIG_DIR/logs"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "AI26 Laskin analysis already running; exiting cleanly"
  exit 3
fi

cd "$ROOT_DIR"

# The frozen manifest is a provenance boundary, not a permanent deployment pin.
# A source-changing deploy legitimately makes it stale. Cron must repair that
# boundary deliberately before work starts, while holding the same lock as the
# worker so no cycle can observe a half-refreshed runtime.
RUNTIME_STATE=$("$PY" - "$RUN_MANIFEST" <<'PY'
import json
import sys
from pathlib import Path

from laclaugpt_data_analysis.distributed_worker import _runtime_public_git_sha, _source_tree_sha256

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps({
    "manifest_git": str(manifest.get("public_git_sha") or ""),
    "manifest_tree": str(manifest.get("source_tree_sha256") or ""),
    "runtime_git": _runtime_public_git_sha(),
    "runtime_tree": _source_tree_sha256(),
}, sort_keys=True))
PY
)
MANIFEST_GIT=$(printf '%s' "$RUNTIME_STATE" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["manifest_git"])')
MANIFEST_TREE=$(printf '%s' "$RUNTIME_STATE" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["manifest_tree"])')
RUNTIME_GIT=$(printf '%s' "$RUNTIME_STATE" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["runtime_git"])')
RUNTIME_TREE=$(printf '%s' "$RUNTIME_STATE" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["runtime_tree"])')

if [[ "$MANIFEST_TREE" != "$RUNTIME_TREE" || "$MANIFEST_GIT" != "$RUNTIME_GIT" ]]; then
  PUBLIC_CODEBOOK=${LACLAUGPT_AI26_PUBLIC_CODEBOOK:-"$ROOT_DIR/codebooks/public/ai26_v2.yaml"}
  PRIVATE_OVERLAY=${LACLAUGPT_AI26_PRIVATE_OVERLAY:-"$PRIVATE_CONFIG_DIR/codebooks/ai26_overlay.yaml"}
  FREEZE_BIN="$ROOT_DIR/.venv/bin/laclaugpt-freeze-ai26"
  [[ -x "$FREEZE_BIN" ]] || fail "stale manifest detected but freeze command not found: $FREEZE_BIN"
  [[ -f "$PUBLIC_CODEBOOK" ]] || fail "stale manifest detected but public AI26 codebook not found: $PUBLIC_CODEBOOK"

  log "AI26 manifest stale; re-freezing before scheduled analysis manifest_git=$MANIFEST_GIT runtime_git=$RUNTIME_GIT manifest_tree=$MANIFEST_TREE runtime_tree=$RUNTIME_TREE"
  FREEZE_ARGS=(
    --private-root "$PRIVATE_CONFIG_DIR"
    --public-codebook "$PUBLIC_CODEBOOK"
    --analysis-config "$PRIVATE_CONFIG"
    --run-id "$LACLAUGPT_RUN_ID"
    --model "$LACLAUGPT_LLM_MODEL"
    --public-git-sha "$RUNTIME_GIT"
  )
  if [[ -f "$PRIVATE_OVERLAY" ]]; then
    FREEZE_ARGS+=(--private-overlay "$PRIVATE_OVERLAY")
  fi
  "$FREEZE_BIN" "${FREEZE_ARGS[@]}" >/dev/null
  log "AI26 manifest re-frozen for scheduled analysis git=$RUNTIME_GIT tree=$RUNTIME_TREE"
fi

log "AI26 Laskin analysis start run=$LACLAUGPT_RUN_ID max_tasks=$MAX_TASKS mode=$RUN_MODE debug=${LACLAUGPT_DEBUG:-0}"

set +e
"$ROOT_DIR/.venv/bin/laclaugpt-analysis-worker" \
  --run-manifest "$RUN_MANIFEST" \
  --private-config "$PRIVATE_CONFIG" \
  --codebook "$CODEBOOK" \
  --worker-id "laskin-cron-${HOSTNAME:-unknown}" \
  --seed-ready \
  --reclaim-idle-ms "$RECLAIM_IDLE_MS" \
  --max-tasks "$MAX_TASKS"
WORKER_STATUS=$?
set -e
REPORT_STATUS="not-run"
FINAL_STATUS=$WORKER_STATUS

# Periodic reports are part of the Phase 1 runtime contract. Recomputing the
# latest completed window on every successful hourly tick is safe because the
# report command upserts stable report identities. Report-stage failures use
# exit 4 so monitoring can distinguish them from worker/task failures.
if [[ "$WORKER_STATUS" -eq 0 && "${LACLAUGPT_PERIODIC_REPORTS:-1}" != "0" ]]; then
  REPORT_BIN="$ROOT_DIR/.venv/bin/laclaugpt-phase1-laskin-report"
  if [[ -x "$REPORT_BIN" ]]; then
    log "AI26 Phase 1 periodic report start run=$LACLAUGPT_RUN_ID"
    set +e
    "$REPORT_BIN" --run-id "$LACLAUGPT_RUN_ID"
    REPORT_STATUS=$?
    set -e
    if [[ "$REPORT_STATUS" -ne 0 ]]; then
      log "AI26 Phase 1 periodic report failed status=$REPORT_STATUS"
      FINAL_STATUS=4
    else
      log "AI26 Phase 1 periodic report end status=0"
    fi
  else
    REPORT_STATUS="missing"
    log "AI26 Phase 1 periodic report command missing: $REPORT_BIN"
    FINAL_STATUS=4
  fi
elif [[ "${LACLAUGPT_PERIODIC_REPORTS:-1}" == "0" ]]; then
  REPORT_STATUS="disabled"
fi

log "AI26 Laskin analysis end worker_status=$WORKER_STATUS report_status=$REPORT_STATUS status=$FINAL_STATUS"
exit "$FINAL_STATUS"
