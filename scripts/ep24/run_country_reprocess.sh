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

cat >&2 <<EOF
========================================================================
EP24 ${code} REPROCESSING PRIVACY/PREFLIGHT REMINDER
------------------------------------------------------------------------
This public repository does NOT contain the researcher-generated EP24
entities, themes, research notes, legacy rows, manifests, or private run
configuration.

The Roihu rerun MUST load the private country grounding from:
  ${private_codebook}

The job will FAIL CLOSED if the private codebook is missing or if the
public+private merged codebook contains no private entities or themes.
Do not bypass this check for a real EP24 reprocessing run.

See: EP24_PRIVATE_DATA_REQUIRED.md
========================================================================
EOF

# These are intentionally external/private inputs. The public repository must
# never contain the real manifests, legacy row-level data, country codebooks,
# private run configs, credentials, or research media.
for required in "$manifest" "$legacy_csv" "$private_codebook" "$run_config" "$public_codebook"; do
  [[ -s "$required" ]] || {
    echo "Required EP24 runtime input is missing: $required" >&2
    echo "REFUSING TO RUN WITHOUT THE PRIVATE EP24 INPUT LAYER." >&2
    echo "See EP24_PRIVATE_DATA_REQUIRED.md and docs/ep24-reprocessing.md." >&2
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

# Fail closed unless the generated effective codebook demonstrably contains the
# hidden researcher-derived country layer. This prevents a Roihu rerun from
# silently falling back to the public/example codebook only.
python - "$private_codebook" "$effective_codebook" "$code" <<'PY'
import json
import sys
from pathlib import Path

private_path = Path(sys.argv[1])
effective_path = Path(sys.argv[2])
expected_country = sys.argv[3].upper()

private = json.loads(private_path.read_text(encoding="utf-8"))
effective = json.loads(effective_path.read_text(encoding="utf-8"))

private_country = str(private.get("country_code") or "").upper()
if private_country != expected_country:
    raise SystemExit(
        f"PRIVATE EP24 PREFLIGHT FAILED: expected {expected_country}, "
        f"but {private_path.name} declares {private_country or 'no country_code'}"
    )

entries = effective.get("entries") or []
private_entries = [
    item for item in entries
    if isinstance(item, dict)
    and isinstance(item.get("metadata"), dict)
    and item["metadata"].get("private_runtime") is True
]
private_entities = [item for item in private_entries if item.get("kind") == "entity"]
private_themes = [item for item in private_entries if item.get("kind") == "topic"]
notes = ((effective.get("sections") or {}).get("human_research_notes") or [])

if not private_entities:
    raise SystemExit(
        "PRIVATE EP24 PREFLIGHT FAILED: effective codebook contains zero "
        "researcher-derived private entities. Refusing to reprocess."
    )
if not private_themes:
    raise SystemExit(
        "PRIVATE EP24 PREFLIGHT FAILED: effective codebook contains zero "
        "researcher-derived private themes. Refusing to reprocess."
    )

print("PRIVATE EP24 GROUNDING VERIFIED")
print(f"  country: {expected_country}")
print(f"  private entities loaded: {len(private_entities)}")
print(f"  private themes loaded: {len(private_themes)}")
print(f"  private research notes loaded: {len(notes)}")
print(f"  effective codebook: {effective_path}")
if not notes:
    print(
        "  WARNING: no private research notes were found. Entities/themes are "
        "loaded, but verify whether research notes were expected for this run.",
        file=sys.stderr,
    )
PY

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
