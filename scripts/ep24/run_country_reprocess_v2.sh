#!/bin/bash
set -euo pipefail

country=${1:?usage: run_country_reprocess_v2.sh finland|poland}
case "$country" in
  finland) code=fi ;;
  poland) code=pl ;;
  *) echo "country must be finland or poland" >&2; exit 2 ;;
esac

: "${LACLAUGPT_REPO_ROOT:?set LACLAUGPT_REPO_ROOT}"
: "${LACLAUGPT_DATA_DIR:?set LACLAUGPT_DATA_DIR}"

mode=${EP24_RUN_MODE:-pilot}
sample_size=${EP24_SAMPLE_SIZE:-20}
runtime="${LACLAUGPT_DATA_DIR}/ep24"
legacy_csv="${runtime}/csv/ep24_${country}.csv"
manifest="${runtime}/csv/${country}_sample20.csv"
audit="${runtime}/audits/${country}_legacy_audit.md"
new_csv="${runtime}/csv/ep24_${country}_reprocessed.csv"
comparison="${runtime}/comparisons/${country}_old_vs_new.md"

case "$mode" in
  pilot|full|dry-run) ;;
  *) echo "EP24_RUN_MODE must be pilot, full, or dry-run" >&2; exit 2 ;;
esac

[[ -s "$legacy_csv" ]] || {
  echo "Missing private EP24 source CSV: $legacy_csv" >&2
  echo "Stage LaclauGPT-Private/analysis/ep24 into LACLAUGPT_DATA_DIR first." >&2
  exit 31
}
mkdir -p "$runtime"/{csv,audits,comparisons}

python -m laclaugpt_data_analysis.ep24_quality audit-legacy \
  --country "$country" \
  --source "$legacy_csv" \
  --output "$audit"

if [[ "$mode" == full ]]; then
  # The proven private EP24 driver historically names its input manifest
  # *_sample20.csv. For a full-country run we retain that compatibility filename
  # but populate it with the complete country CSV. The audit report records that
  # this is a full run; no substantive sampling metadata enters model evidence.
  cp -p "$legacy_csv" "$manifest"
else
  python -m laclaugpt_data_analysis.ep24_quality sample \
    --country "$country" \
    --source "$legacy_csv" \
    --output "$manifest" \
    --size "$sample_size"
fi

export EP24_PIPELINE_SCRIPT=${EP24_PIPELINE_SCRIPT:-"${runtime}/private_pipeline/ep24_mm_pipeline.py"}
export EP24_PRIVATE_REPO_ROOT=${EP24_PRIVATE_REPO_ROOT:-"${runtime}/private_pipeline"}

for required in \
  "$manifest" \
  "$runtime/private_codebooks/ep24_${code}.json" \
  "$runtime/run_configs/arena_ep24_${country}_pilot.yaml" \
  "$EP24_PIPELINE_SCRIPT"; do
  [[ -s "$required" ]] || {
    echo "EP24 preflight failed: required private runtime input missing: $required" >&2
    exit 32
  }
done

if [[ "$mode" == dry-run ]]; then
  echo "EP24 dry-run preflight OK for $country"
  echo "Legacy audit: $audit"
  echo "Prepared deterministic pilot manifest: $manifest"
  exit 0
fi

bash "${LACLAUGPT_REPO_ROOT}/scripts/ep24/run_country_reprocess.sh" "$country"

if [[ -s "$new_csv" ]]; then
  python -m laclaugpt_data_analysis.ep24_quality compare \
    --old "$legacy_csv" \
    --new "$new_csv" \
    --output "$comparison"
  echo "Old-vs-new comparison: $comparison"
else
  echo "No reprocessed dashboard CSV at $new_csv; comparison deferred." >&2
fi

echo "Legacy quality audit: $audit"
echo "EP24 mode: $mode"
