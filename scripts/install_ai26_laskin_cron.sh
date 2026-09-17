#!/usr/bin/env bash
# Install/update the canonical AI26 analysis cron entry on Laskin.
#
# The analysis tick runs hourly at :05, staggered from the Collection jobs
# (:10 collect, :30 media). The worker itself remains bounded and protected by
# flock in scripts/run_ai26_laskin.sh.
#
# Installing/updating cron is also the deployment boundary for a frozen run:
# refresh the manifest to the current public Git revision, then prove one
# cron-equivalent cycle exits successfully before installing the schedule.
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PRIVATE_ROOT=${LACLAUGPT_PRIVATE_ROOT:-/mnt/workspace/LaclauGPT-Private/runtime/ai26}
PRIVATE_CONFIG_DIR=${LACLAUGPT_PRIVATE_CONFIG_DIR:-"$PRIVATE_ROOT/analysis/ai26"}
LOG_FILE=${LACLAUGPT_AI26_ANALYSIS_LOG:-"$PRIVATE_ROOT/analysis/ai26-laskin-analysis.log"}
PUBLIC_CODEBOOK=${LACLAUGPT_AI26_PUBLIC_CODEBOOK:-"$ROOT_DIR/codebooks/public/ai26_v2.yaml"}
PRIVATE_OVERLAY=${LACLAUGPT_AI26_PRIVATE_OVERLAY:-"$PRIVATE_CONFIG_DIR/codebooks/ai26_overlay.yaml"}
ANALYSIS_CONFIG=${LACLAUGPT_AI26_ANALYSIS_CONFIG:-"$PRIVATE_CONFIG_DIR/analysis.json"}
CRON_TAG="# LaclauGPT AI26 analysis"
CRON_LINE="5 * * * * /bin/bash $ROOT_DIR/scripts/run_ai26_laskin.sh >> $LOG_FILE 2>&1 $CRON_TAG"

mkdir -p "$(dirname "$LOG_FILE")"

[[ -f "$ANALYSIS_CONFIG" ]] || {
  printf 'ERROR: missing analysis config: %s\n' "$ANALYSIS_CONFIG" >&2
  exit 2
}
[[ -f "$PUBLIC_CODEBOOK" ]] || {
  printf 'ERROR: missing public codebook: %s\n' "$PUBLIC_CODEBOOK" >&2
  exit 2
}

# Load the same private runtime contract as the cron wrapper so run/model values
# come from one source of truth.
ENV_FILE=${LACLAUGPT_ENV_FILE:-"$PRIVATE_CONFIG_DIR/laskin.env"}
[[ -f "$ENV_FILE" ]] || {
  printf 'ERROR: missing private environment file: %s\n' "$ENV_FILE" >&2
  exit 2
}
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

: "${LACLAUGPT_RUN_ID:?LACLAUGPT_RUN_ID is required}"
MODEL=${LACLAUGPT_LLM_MODEL:-gemma4:12b}

# Refresh the frozen provenance pin after a deployment/update. Keep the strict
# runtime guard: we update the manifest deliberately instead of allowing drift.
FREEZE_ARGS=(
  --private-root "$PRIVATE_CONFIG_DIR"
  --public-codebook "$PUBLIC_CODEBOOK"
  --analysis-config "$ANALYSIS_CONFIG"
  --run-id "$LACLAUGPT_RUN_ID"
  --model "$MODEL"
)
if [[ -f "$PRIVATE_OVERLAY" ]]; then
  FREEZE_ARGS+=(--private-overlay "$PRIVATE_OVERLAY")
fi

printf 'Refreshing AI26 frozen run manifest for current checkout...\n'
"$ROOT_DIR/.venv/bin/laclaugpt-freeze-ai26" "${FREEZE_ARGS[@]}" >/dev/null

# Test the exact unattended entry point before touching crontab. This catches a
# stale manifest, broken endpoint, missing model, or other deployment error now
# rather than leaving cron to fail silently every hour.
printf 'Verifying one cron-equivalent AI26 cycle...\n'
LACLAUGPT_PRIVATE_ROOT="$PRIVATE_ROOT" \
LACLAUGPT_PRIVATE_CONFIG_DIR="$PRIVATE_CONFIG_DIR" \
LACLAUGPT_ENV_FILE="$ENV_FILE" \
  /bin/bash "$ROOT_DIR/scripts/run_ai26_laskin.sh" --once

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

# Preserve the existing crontab, replacing only our own tagged entry. Also
# remove an older untagged invocation of the same wrapper to prevent duplicates.
(crontab -l 2>/dev/null || true) \
  | grep -vF "$CRON_TAG" \
  | grep -vF "$ROOT_DIR/scripts/run_ai26_laskin.sh" \
  > "$TMP" || true
printf '%s\n' "$CRON_LINE" >> "$TMP"
crontab "$TMP"

printf 'Installed AI26 analysis cron entry:\n%s\n' "$CRON_LINE"
