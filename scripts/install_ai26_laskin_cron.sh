#!/usr/bin/env bash
# Install/update the canonical AI26 analysis cron entry on Laskin.
#
# The analysis tick runs hourly at :05, staggered from the Collection jobs
# (:10 collect, :30 media). The worker itself remains bounded and protected by
# flock in scripts/run_ai26_laskin.sh.
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PRIVATE_ROOT=${LACLAUGPT_PRIVATE_ROOT:-/mnt/workspace/LaclauGPT-Private}
LOG_FILE=${LACLAUGPT_AI26_ANALYSIS_LOG:-"$PRIVATE_ROOT/runtime/ai26/analysis/ai26-laskin-analysis.log"}
CRON_TAG="# LaclauGPT AI26 analysis"
CRON_LINE="5 * * * * LACLAUGPT_PRIVATE_ROOT=$PRIVATE_ROOT /bin/bash $ROOT_DIR/scripts/run_ai26_laskin.sh >> $LOG_FILE 2>&1 $CRON_TAG"

mkdir -p "$(dirname "$LOG_FILE")"

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

# Verify the exact environment contract installed for cron before reporting
# success. --check performs preflight only and claims no tasks.
if ! LACLAUGPT_PRIVATE_ROOT="$PRIVATE_ROOT" /bin/bash "$ROOT_DIR/scripts/run_ai26_laskin.sh" --check; then
  printf 'ERROR: installed AI26 analysis cron entry failed preflight; inspect configuration before relying on cron.\n' >&2
  exit 1
fi

printf 'Installed and verified AI26 analysis cron entry:\n%s\n' "$CRON_LINE"
