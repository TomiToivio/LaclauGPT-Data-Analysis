#!/usr/bin/env bash
# AI26 Roihu preflight (#390): fail before spending GPU time.
#
# Checks the things that actually stop a run: the env file, the required keys, the frozen inputs, the
# repository preflight (MongoDB/Redis/Allas/Ollama reachability), the test-run isolation, and that the
# selected sample is non-empty. Prints presence, never values.
#
# Usage:
#   AI26_ENV_FILE=/path/to/roihu.env bash scripts/roihu/preflight_ai26.sh
#   AI26_ENV_FILE=... AI26_DRY_RUN=1 bash scripts/roihu/preflight_ai26.sh   # offline, no services
set -euo pipefail

ROOT_DIR=${LACLAUGPT_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
ENV_FILE=${AI26_ENV_FILE:-"$ROOT_DIR/data/config/ai26/roihu.env"}
PRIVATE_CONFIG_DIR=${LACLAUGPT_PRIVATE_CONFIG_DIR:-}
DRY_RUN=${AI26_DRY_RUN:-0}
failures=0

ok()   { printf '  OK    %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; failures=$((failures + 1)); }
warn() { printf '  WARN  %s\n' "$*"; }

echo "AI26 Roihu preflight  ($(date -Is))"
echo "repo: $ROOT_DIR"

# --- env file -----------------------------------------------------------------------------------
echo
echo "environment"
if [[ -f "$ENV_FILE" ]]; then
  ok "env file present: $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  if [[ "$DRY_RUN" == "1" ]]; then
    warn "env file missing: $ENV_FILE (allowed in dry run)"
  else
    bad "env file missing: $ENV_FILE"
  fi
fi

for key in LACLAUGPT_RUN_ID LACLAUGPT_MONGODB_URI LACLAUGPT_REDIS_URL LACLAUGPT_S3_ENDPOINT LACLAUGPT_S3_BUCKET LACLAUGPT_LLM_ENDPOINT; do
  if [[ -n "${!key:-}" ]]; then ok "$key is set"; else
    if [[ "$DRY_RUN" == "1" ]]; then warn "$key not set (dry run)"; else bad "$key is not set"; fi
  fi
done

# --- isolation: a Roihu test must never adopt the production run identity -------------------------
echo
echo "test-run isolation"
if [[ -z "${LACLAUGPT_RUN_ID:-}" ]]; then
  if [[ "$DRY_RUN" == "1" ]]; then warn "LACLAUGPT_RUN_ID unset (dry run)"; else bad "LACLAUGPT_RUN_ID unset"; fi
else
  if [[ -n "${LACLAUGPT_PRODUCTION_RUN_ID:-}" && "${LACLAUGPT_RUN_ID}" == "${LACLAUGPT_PRODUCTION_RUN_ID}" ]]; then
    bad "LACLAUGPT_RUN_ID equals the production run id — a test must not reuse it"
  else
    ok "run id: ${LACLAUGPT_RUN_ID}"
  fi
  namespace=${LACLAUGPT_TEST_NAMESPACE:-test-${LACLAUGPT_RUN_ID}}
  if [[ "$namespace" == test-* ]]; then
    ok "output/task namespace: $namespace"
  else
    bad "namespace '$namespace' must start with 'test-' so production keys cannot be overwritten"
  fi
fi

# --- frozen inputs ------------------------------------------------------------------------------
echo
echo "frozen inputs"
if [[ -n "$PRIVATE_CONFIG_DIR" && -d "$PRIVATE_CONFIG_DIR" ]]; then
  ok "private config dir: $PRIVATE_CONFIG_DIR"
  for f in run-manifest.json analysis.json codebook.json; do
    if [[ -f "$PRIVATE_CONFIG_DIR/$f" ]]; then ok "$f present"; else
      if [[ "$DRY_RUN" == "1" ]]; then warn "$f missing (dry run)"; else bad "$f missing"; fi
    fi
  done
else
  if [[ "$DRY_RUN" == "1" ]]; then warn "LACLAUGPT_PRIVATE_CONFIG_DIR not set (dry run)"; else
    bad "LACLAUGPT_PRIVATE_CONFIG_DIR missing or not a directory"
  fi
fi

# --- sample -------------------------------------------------------------------------------------
echo
echo "bounded sample"
sample=${LACLAUGPT_SAMPLE_MANIFEST:-}
if [[ -n "$sample" && -f "$sample" ]]; then
  lines=$(grep -cve '^[[:space:]]*$' "$sample" || true)
  if [[ "$lines" -gt 0 ]]; then ok "sample manifest: $lines record(s)"; else bad "sample manifest is empty"; fi
else
  if [[ "$DRY_RUN" == "1" ]]; then warn "no sample manifest (dry run)"; else
    warn "LACLAUGPT_SAMPLE_MANIFEST unset — the run will take whatever the queue offers"
  fi
fi

# --- repository preflight -----------------------------------------------------------------------
echo
echo "runtime reachability (repository preflight)"
if [[ "$DRY_RUN" == "1" ]]; then
  warn "skipped in dry run"
elif command -v laclaugpt-preflight >/dev/null 2>&1; then
  set +e
  out=$(laclaugpt-preflight 2>&1)
  status=$?
  set -e
  printf '%s\n' "$out" | tail -25 | sed 's/^/  /'
  if [[ "$status" -eq 0 ]]; then ok "laclaugpt-preflight exited 0"; else bad "laclaugpt-preflight exited $status"; fi
else
  bad "laclaugpt-preflight not on PATH (run install_ai26.sh first)"
fi

echo
if [[ "$failures" -gt 0 ]]; then
  echo "preflight: $failures failure(s)"
  exit 1
fi
echo "preflight: all checks passed"
