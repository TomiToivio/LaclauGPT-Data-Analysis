#!/bin/bash
#SBATCH --job-name=laclaugpt_reprocess
#SBATCH --partition=gpumedium
#SBATCH --time=16:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=72
#SBATCH --mem=120G
#SBATCH --gres=gpu:gh200:1
#SBATCH --output=roihu_reprocess_%j.out
#SBATCH --error=roihu_reprocess_%j.err

# Submit with the account and private runtime values at invocation time, e.g.
# sbatch --account=<CSC_PROJECT> --export=ALL,STUDY_ID=hungary26,... this_file
# Never commit the account, private paths, study data, or credentials here.
set -euo pipefail

: "${STUDY_ID:?set STUDY_ID, e.g. hungary26}"
: "${LACLAUGPT_DATA_DIR:?set LACLAUGPT_DATA_DIR to private runtime storage}"
: "${LACLAUGPT_REPROCESS_DRIVER:?set LACLAUGPT_REPROCESS_DRIVER to an executable study driver}"

export LLM_MODE=local
export LLM_ALLOW_CLOUD_FALLBACK=0
export OLLAMA_KEEP_ALIVE=${OLLAMA_KEEP_ALIVE:-24h}
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}
export OMP_PLACES=cores
export OMP_PROC_BIND=spread

mkdir -p \
  "$LACLAUGPT_DATA_DIR" \
  "$LACLAUGPT_DATA_DIR/logs" \
  "$LACLAUGPT_DATA_DIR/models/ollama" \
  "$LACLAUGPT_DATA_DIR/tmp" \
  "$LACLAUGPT_DATA_DIR/runs/$STUDY_ID"

module --force purge
module load gcc/14.3.0
module load python-pytorch/2.13
module load ffmpeg
unset PYTHONPATH
unset PYTHONHOME

VENV=${LACLAUGPT_ROIHU_VENV:-$LACLAUGPT_DATA_DIR/.venv-roihu}
[[ -x "$VENV/bin/python" ]] || {
  echo "missing Roihu ARM64 virtualenv: $VENV" >&2
  echo "create it on roihu-gpu and install LaclauGPT-Data-Analysis plus study dependencies" >&2
  exit 2
}
source "$VENV/bin/activate"

python - <<'PY'
import numpy
print(f"NumPy preflight OK: {numpy.__version__}")
PY

OLLAMA_INSTALL_ROOT=${OLLAMA_INSTALL_ROOT:-$LACLAUGPT_DATA_DIR/ollama}
export OLLAMA_MODELS=${OLLAMA_MODELS:-$LACLAUGPT_DATA_DIR/models/ollama}
export PATH="$OLLAMA_INSTALL_ROOT/bin:$PATH"
export LD_LIBRARY_PATH="$OLLAMA_INSTALL_ROOT/lib/ollama${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

if ! command -v ollama >/dev/null 2>&1; then
  [[ $(uname -m) == aarch64 || $(uname -m) == arm64 ]] || {
    echo "Roihu Ollama bootstrap expects ARM64, got $(uname -m)" >&2
    exit 2
  }
  command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 2; }
  command -v zstd >/dev/null 2>&1 || { echo "zstd is required" >&2; exit 2; }
  : "${TMPDIR:?Roihu should provide TMPDIR inside the Slurm allocation}"
  archive="$TMPDIR/ollama-linux-arm64.tar.zst"
  curl --fail --location --retry 3 --output "$archive" \
    https://ollama.com/download/ollama-linux-arm64.tar.zst
  mkdir -p "$OLLAMA_INSTALL_ROOT"
  zstd -dc "$archive" | tar -xf - -C "$OLLAMA_INSTALL_ROOT"
fi

OLLAMA_PORT=$((20000 + SLURM_JOB_ID % 20000))
export OLLAMA_HOST="http://127.0.0.1:$OLLAMA_PORT"
OLLAMA_LOG="$LACLAUGPT_DATA_DIR/logs/ollama_${STUDY_ID}_${SLURM_JOB_ID}.log"
ollama serve >"$OLLAMA_LOG" 2>&1 &
OLLAMA_PID=$!
cleanup() { kill "$OLLAMA_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

for _ in {1..60}; do
  ollama list >/dev/null 2>&1 && break
  sleep 2
done
ollama list >/dev/null 2>&1 || { echo "Ollama failed to start: $OLLAMA_LOG" >&2; exit 3; }

MODEL=${LACLAUGPT_REPROCESS_MODEL:-gemma4:26b}
ollama pull "$MODEL"
if [[ -n ${LACLAUGPT_TRANSLATION_MODEL:-} ]]; then
  ollama pull "$LACLAUGPT_TRANSLATION_MODEL"
fi

[[ -x "$LACLAUGPT_REPROCESS_DRIVER" ]] || {
  echo "reprocess driver is not executable: $LACLAUGPT_REPROCESS_DRIVER" >&2
  exit 2
}

export LACLAUGPT_STUDY_ID="$STUDY_ID"
export LACLAUGPT_STUDY_CONFIG=${LACLAUGPT_STUDY_CONFIG:-}
export LACLAUGPT_REPROCESS_MODEL="$MODEL"

srun --ntasks=1 "$LACLAUGPT_REPROCESS_DRIVER" "$STUDY_ID"

echo "completed study reprocessing: $STUDY_ID"
