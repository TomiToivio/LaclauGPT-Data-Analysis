#!/bin/bash
set -euo pipefail

country=${1:?usage: run_country_reprocess.sh finland|poland}
case "$country" in
  finland) code=FI ;;
  poland) code=PL ;;
  *) echo "country must be finland or poland" >&2; exit 2 ;;
esac

: "${LACLAUGPT_REPO_ROOT:?set LACLAUGPT_REPO_ROOT}"
: "${LACLAUGPT_DATA_DIR:?set LACLAUGPT_DATA_DIR}"

runtime="${LACLAUGPT_DATA_DIR}/ep24"
manifest="${runtime}/csv/${country}_sample20.csv"
legacy_csv="${runtime}/csv/ep24_${country}.csv"
codebook="${runtime}/private_codebooks/ep24_${code,,}.json"
run_config="${runtime}/run_configs/arena_ep24_${country}_pilot.yaml"

# These are intentionally external/private inputs. The public repository must
# never contain the real manifests, legacy row-level data, country codebooks,
# private run configs, credentials, or research media.
for required in "$manifest" "$legacy_csv" "$codebook" "$run_config"; do
  [[ -s "$required" ]] || {
    echo "Required private EP24 runtime input is missing: $required" >&2
    echo "See docs/ep24-reprocessing.md for the privacy-safe staging contract." >&2
    exit 21
  }
done

mkdir -p "$runtime"/{videos,annotations,human_reports,reviews,tmp}
export LACLAUGPT_MEMORY_DIR=${LACLAUGPT_MEMORY_DIR:-${LACLAUGPT_DATA_DIR}/memory}
export LLM_MODE=local
export LLM_ALLOW_CLOUD_FALLBACK=0
export EP24_REQUIRE_HUMAN_CODEBOOK=1

# The public module contains reusable analysis components, but the historical
# EP24 end-to-end driver still lives in restricted research code. Until that
# driver is fully disentangled from private project material, provide its path
# explicitly at runtime rather than copying it here.
: "${EP24_PIPELINE_SCRIPT:?Set EP24_PIPELINE_SCRIPT to the private ep24_mm_pipeline.py at runtime}"
[[ -f "$EP24_PIPELINE_SCRIPT" ]] || {
  echo "EP24_PIPELINE_SCRIPT does not exist: $EP24_PIPELINE_SCRIPT" >&2
  exit 22
}

python "$EP24_PIPELINE_SCRIPT" \
  --country "$country" \
  --repo-root "${EP24_PRIVATE_REPO_ROOT:-$(dirname "$EP24_PIPELINE_SCRIPT")}" \
  --data-root "$LACLAUGPT_DATA_DIR" \
  --run-config "$run_config" \
  --require-human-codebook

annotations="${runtime}/annotations/${country}_sample20_annotations.jsonl"
[[ -s "$annotations" ]] || {
  echo "Pipeline completed without expected annotations: $annotations" >&2
  exit 23
}

echo "EP24 ${country} reprocessing complete"
echo "Annotations: $annotations"
echo "Outputs remain under private runtime root: $runtime"
