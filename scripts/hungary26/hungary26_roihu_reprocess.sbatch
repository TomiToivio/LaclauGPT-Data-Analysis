#!/usr/bin/env bash
#SBATCH --job-name=hungary26-reprocess
#SBATCH --gres=gpu:gh200:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=12:00:00
#SBATCH --output=hungary26_reprocess_%j.out
#SBATCH --error=hungary26_reprocess_%j.err

set -euo pipefail
# Supply --account at sbatch invocation time. Never commit a CSC project/account ID.
mode="${MODE:-pilot}"
platform="${PLATFORM:-both}"

module purge
module load gcc/14.3.0 || true
module load python-pytorch/2.13 || true
module load ffmpeg || true

: "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT:?Export private Hungary26 root before submitting}"
: "${LACLAUGPT_HUNGARY26_RUNTIME:=${TMPDIR:-/tmp}/laclaugpt-hungary26-${SLURM_JOB_ID}}"
: "${OLLAMA_PORT:=11434}"
export LACLAUGPT_HUNGARY26_RUNTIME
export OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}"
export LACLAUGPT_LLM_ENDPOINT="http://${OLLAMA_HOST}"
export LLM_MODE=local
export LLM_ALLOW_CLOUD_FALLBACK=0

ollama serve >"$LACLAUGPT_HUNGARY26_RUNTIME/ollama.log" 2>&1 &
ollama_pid=$!
trap 'kill "$ollama_pid" 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do
  if ollama list >/dev/null 2>&1; then break; fi
  sleep 2
done
ollama list >/dev/null 2>&1 || { echo "job-local Ollama failed to start" >&2; exit 2; }

model="${LACLAUGPT_HUNGARY26_MODEL:-gemma4:12b}"
ollama show "$model" >/dev/null 2>&1 || { echo "required Ollama model missing: $model" >&2; exit 2; }

scripts/hungary26/run_reprocess.sh "$mode" "$platform"
