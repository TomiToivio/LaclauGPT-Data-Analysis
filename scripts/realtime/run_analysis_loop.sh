#!/usr/bin/env bash
set -euo pipefail

INPUT=${LACLAUGPT_REALTIME_INPUT:?set LACLAUGPT_REALTIME_INPUT to canonical Collection JSONL}
OUTPUT=${LACLAUGPT_REALTIME_OUTPUT:?set LACLAUGPT_REALTIME_OUTPUT to Analysis JSONL}
INTERVAL=${LACLAUGPT_REALTIME_INTERVAL_SECONDS:-60}
MODEL=${LACLAUGPT_REALTIME_MODEL:-auto}
CODEBOOK=${LACLAUGPT_REALTIME_CODEBOOK:-}
LIMIT=${LACLAUGPT_REALTIME_LIMIT_PER_PASS:-0}

export LLM_MODE=${LLM_MODE:-local}
export LLM_ALLOW_CLOUD_FALLBACK=0

args=(
  --input "$INPUT"
  --output "$OUTPUT"
  --model "$MODEL"
  --limit "$LIMIT"
)
if [[ -n "$CODEBOOK" ]]; then
  args+=(--codebook "$CODEBOOK")
fi

while true; do
  python scripts/realtime/analyze_jsonl_incremental.py "${args[@]}"
  sleep "$INTERVAL"
done
