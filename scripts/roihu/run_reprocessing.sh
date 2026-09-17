#!/usr/bin/env bash
set -euo pipefail

CONFIG=${1:?usage: run_reprocessing.sh PRIVATE_CONFIG [START] [STOP]}
START=${2:-0}
STOP=${3:-}

: "${LACLAUGPT_PROJECT_ID:?set LACLAUGPT_PROJECT_ID from private runtime config}"
: "${LACLAUGPT_MONGODB_URI:?set LACLAUGPT_MONGODB_URI from private runtime config}"
: "${LACLAUGPT_REDIS_URL:?set LACLAUGPT_REDIS_URL from private runtime config}"
: "${LACLAUGPT_S3_BUCKET:?set LACLAUGPT_S3_BUCKET from private runtime config}"

export LACLAUGPT_MACHINE=${LACLAUGPT_MACHINE:-roihu}
export LACLAUGPT_EXECUTION=${LACLAUGPT_EXECUTION:-slurm}
export LACLAUGPT_STORAGE=${LACLAUGPT_STORAGE:-distributed}
export LACLAUGPT_STORAGE_BACKEND=${LACLAUGPT_STORAGE_BACKEND:-mongodb}
export LACLAUGPT_CACHE_BACKEND=${LACLAUGPT_CACHE_BACKEND:-redis}
export LACLAUGPT_OBJECT_BACKEND=${LACLAUGPT_OBJECT_BACKEND:-s3}
export LLM_ALLOW_CLOUD_FALLBACK=${LLM_ALLOW_CLOUD_FALLBACK:-0}

mkdir -p "${LACLAUGPT_DATA_DIR:-./data}"/{logs,csv,tmp,artifacts}

ARGS=(--config "$CONFIG" --start "$START")
if [[ -n "$STOP" ]]; then ARGS+=(--stop "$STOP"); fi

exec laclaugpt-reprocess "${ARGS[@]}"
