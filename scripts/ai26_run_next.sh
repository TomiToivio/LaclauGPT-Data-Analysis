#!/usr/bin/env bash
# Safe, bounded AI26 operator command. Delegates ALL queue claims and locking to
# run_ai26_laskin.sh; this script does not access Mongo, Redis or the model.
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
LIMIT=10
APPLY=0
while (($#)); do
  case "$1" in
    --limit)
      (($# >= 2)) || { echo "missing --limit value" >&2; exit 2; }
      LIMIT=$2; shift 2 ;;
    --apply) APPLY=1; shift ;;
    --dry-run) APPLY=0; shift ;;
    -h|--help)
      echo "Usage: scripts/ai26_run_next.sh [--limit N] [--dry-run | --apply]"
      echo "Default is dry-run. --apply runs a bounded cycle through the existing flock-protected Laskin wrapper."
      exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
# ``003`` is the integer 3, so leading zeroes are normalised below rather than
# rejected — the normalisation line existed while this guard forbade the only
# input it was written for, and the acceptance test caught the contradiction.
# The digit cap matters: without it ``10#`` wraps a 17-digit value into a legal
# one and the range check stops meaning anything. The cap is applied to the
# string length, before any arithmetic touches it.
if [[ ! "$LIMIT" =~ ^[0-9]+$ ]] || (( ${#LIMIT} > 4 )) || (( 10#$LIMIT < 1 || 10#$LIMIT > 100 )); then
  echo "--limit must be an integer from 1 to 100" >&2
  exit 2
fi
# Normalize leading zeroes for the worker and prevent shell arithmetic ambiguity.
LIMIT=$((10#$LIMIT))
if (( ! APPLY )); then
  printf 'dry-run: would execute one bounded AI26 Laskin worker cycle (max_tasks=%d) through existing wrapper; no tasks claimed\n' "$LIMIT"
  exit 0
fi
export LACLAUGPT_MAX_TASKS="$LIMIT"
exec bash "$ROOT_DIR/scripts/run_ai26_laskin.sh" --once
