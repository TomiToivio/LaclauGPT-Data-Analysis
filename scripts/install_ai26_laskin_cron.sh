#!/usr/bin/env bash
# Install/update the canonical AI26 analysis cron entry on Laskin.
#
# The analysis tick runs hourly at :05, staggered from the Collection jobs
# (:10 collect, :30 media). The worker itself remains bounded and protected by
# flock in scripts/run_ai26_laskin.sh.
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PRIVATE_ROOT=${LACLAUGPT_PRIVATE_ROOT:-/mnt/workspace/LaclauGPT-Private/runtime/ai26}
LOG_FILE=${LACLAUGPT_AI26_ANALYSIS_LOG:-"$PRIVATE_ROOT/analysis/ai26-laskin-analysis.log"}
CRON_TAG="# LaclauGPT AI26 analysis"
CRON_LINE="5 * * * * /bin/bash $ROOT_DIR/scripts/run_ai26_laskin.sh >> $LOG_FILE 2>&1 $CRON_TAG"

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

printf 'Installed AI26 analysis cron entry:\n%s\n' "$CRON_LINE"
