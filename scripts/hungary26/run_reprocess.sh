#!/usr/bin/env bash
set -euo pipefail

mode="${1:-dry-run}"
platform="${2:-both}"
private_root="${LACLAUGPT_HUNGARY26_PRIVATE_ROOT:?Set LACLAUGPT_HUNGARY26_PRIVATE_ROOT to LaclauGPT-Private/analysis/hungary26}"
runtime="${LACLAUGPT_HUNGARY26_RUNTIME:-${TMPDIR:-/tmp}/laclaugpt-hungary26-${SLURM_JOB_ID:-local}}"
config="${LACLAUGPT_HUNGARY26_RUN_CONFIG:-$private_root/run/hungary26_roihu.yaml}"
instagram="$private_root/source/hungary2026_instagram.xlsx"
tiktok="$private_root/source/hungary2026_tiktok.xlsx"
mkdir -p "$runtime/audit" "$runtime/manifests" "$runtime/logs"

export LACLAUGPT_PROJECT_ID=hungary26
export LLM_MODE=local
export LLM_ALLOW_CLOUD_FALLBACK=0
: "${LACLAUGPT_LLM_ENDPOINT:=${OLLAMA_HOST:-http://127.0.0.1:11434}}"
export LACLAUGPT_LLM_ENDPOINT
export OLLAMA_HOST="$LACLAUGPT_LLM_ENDPOINT"

python -m laclaugpt_data_analysis.hungary26 preflight --private-root "$private_root"
command -v ffmpeg >/dev/null || { echo "ffmpeg is required" >&2; exit 2; }
command -v ollama >/dev/null || { echo "ollama is required" >&2; exit 2; }

python -m laclaugpt_data_analysis.hungary26 audit \
  --instagram "$instagram" --tiktok "$tiktok" \
  --json "$runtime/audit/source-audit.json" \
  --markdown "$runtime/audit/source-audit.md"

case "$mode" in
  dry-run)
    laclaugpt-reprocess --config "$config" --dry-run
    ;;
  pilot)
    python -m laclaugpt_data_analysis.hungary26 pilot \
      --instagram "$instagram" --tiktok "$tiktok" \
      --output "$runtime/manifests/pilot-source-records.jsonl"
    # The private staging workflow converts the selected source records to the
    # canonical pilot manifest referenced by the run config. Refuse to guess it.
    test -f "$(python - <<'PY'
import os, yaml
p=os.environ['LACLAUGPT_HUNGARY26_RUN_CONFIG'] if os.getenv('LACLAUGPT_HUNGARY26_RUN_CONFIG') else os.path.join(os.environ['LACLAUGPT_HUNGARY26_PRIVATE_ROOT'],'run','hungary26_roihu.yaml')
print(yaml.safe_load(open(p, encoding='utf-8'))['manifest'])
PY
)" || { echo "private canonical pilot manifest is not staged" >&2; exit 2; }
    laclaugpt-reprocess --config "$config"
    ;;
  full|resume)
    case "$platform" in both|instagram|tiktok) ;; *) echo "platform must be both, instagram, or tiktok" >&2; exit 2;; esac
    export LACLAUGPT_HUNGARY26_PLATFORM="$platform"
    laclaugpt-reprocess --config "$config"
    ;;
  *)
    echo "usage: $0 {dry-run|pilot|full|resume} [both|instagram|tiktok]" >&2
    exit 2
    ;;
esac
