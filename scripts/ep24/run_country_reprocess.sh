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
private_codebook="${runtime}/private_codebooks/ep24_${code,,}.json"
run_config="${runtime}/run_configs/arena_ep24_${country}_pilot.yaml"
public_codebook="${LACLAUGPT_REPO_ROOT}/codebooks/public/ep24_fi_pl_v2.yaml"
effective_dir="${runtime}/effective_codebooks"
effective_codebook="${effective_dir}/ep24_${code,,}_effective.json"

# These are intentionally external/private inputs. The public repository must
# never contain the real manifests, legacy row-level data, country codebooks,
# private run configs, credentials, or research media.
for required in "$manifest" "$legacy_csv" "$private_codebook" "$run_config" "$public_codebook"; do
  [[ -s "$required" ]] || {
    echo "Required EP24 runtime input is missing: $required" >&2
    echo "See docs/ep24-reprocessing.md for the privacy-safe staging contract." >&2
    exit 21
  }
done

mkdir -p "$runtime"/{videos,annotations,human_reports,reviews,tmp,effective_codebooks,canonical}
export LACLAUGPT_MEMORY_DIR=${LACLAUGPT_MEMORY_DIR:-${LACLAUGPT_DATA_DIR}/memory}
export LLM_MODE=local
export LLM_ALLOW_CLOUD_FALLBACK=0
export EP24_REQUIRE_HUMAN_CODEBOOK=1

# Build the effective codebook outside Git: public methodology/language rules +
# private researcher-grounded entity/theme normalization and notes. The merged
# result is runtime research material and must never be committed.
python -m laclaugpt_data_analysis.ep24_reprocessing merge-codebooks \
  --public "$public_codebook" \
  --private "$private_codebook" \
  --output "$effective_codebook"

export EP24_PUBLIC_CODEBOOK="$public_codebook"
export EP24_PRIVATE_HUMAN_CODEBOOK="$private_codebook"
export EP24_EFFECTIVE_CODEBOOK="$effective_codebook"
export EP24_FRAME_PROMPT_ID="ep24.frame_analysis:v1"
export EP24_TRANSLATION_PROMPT_ID="ep24.translation:v1"
export EP24_SUMMARY_PROMPT_ID="ep24.summary_analysis:v1"
export EP24_LACLAU_PROMPT_ID="ep24.laclau_analysis:v1"

# The public module contains reusable analysis components, but the historical
# EP24 end-to-end driver still lives in restricted research code. Until that
# driver is fully disentangled from private project material, provide its path
# explicitly at runtime rather than copying restricted resources here. The
# driver can consume EP24_EFFECTIVE_CODEBOOK and the versioned prompt IDs above.
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

# When the private driver emits canonical records, create a dashboard dataframe
# that preserves the complete historical EP24 column contract and appends all
# modern canonical/intermediate/evidence/review fields.
canonical_jsonl="${EP24_CANONICAL_JSONL:-${runtime}/canonical/${country}.jsonl}"
if [[ -s "$canonical_jsonl" ]]; then
  dashboard_csv="${runtime}/csv/ep24_${country}_reprocessed.csv"
  python -m laclaugpt_data_analysis.ep24_reprocessing export-dashboard \
    --records "$canonical_jsonl" \
    --output "$dashboard_csv"
  echo "Combined legacy + canonical dashboard dataframe: $dashboard_csv"
else
  echo "No canonical JSONL found at $canonical_jsonl; legacy annotations remain available." >&2
fi

echo "EP24 ${country} reprocessing complete"
echo "Annotations: $annotations"
echo "Effective codebook (private runtime): $effective_codebook"
echo "Outputs remain under private runtime root: $runtime"
