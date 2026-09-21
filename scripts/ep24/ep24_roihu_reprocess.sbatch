#!/bin/bash
#SBATCH --job-name=ep24_reprocess
#SBATCH --account=project_2009497
#SBATCH --output=/scratch/project_2009497/LaclauGPT-Private/analysis/ep24/logs/reprocess_%j.out
#SBATCH --error=/scratch/project_2009497/LaclauGPT-Private/analysis/ep24/logs/reprocess_%j.err
#SBATCH --partition=gpumedium
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=72
#SBATCH --mem=120G
#SBATCH --gres=gpu:gh200:1
#SBATCH --time=1-12:00:00
#SBATCH --mail-type=ALL

set -euo pipefail

PUBLIC_ROOT=${LACLAUGPT_REPO_ROOT:-/scratch/project_2009497/LaclauGPT-Data-Analysis}
PRIVATE_ROOT=${LACLAUGPT_EP24_PRIVATE_ROOT:-/scratch/project_2009497/LaclauGPT-Private/analysis/ep24}
MODE=${EP24_RUN_MODE:-pilot}
MODEL=${EP24_ANALYSIS_MODEL:-gemma4:12b}
VENV=${EP24_ROIHU_VENV:-/scratch/project_2009497/LaclauGPT-Private/.venv-roihu}
OLLAMA_INSTALL_ROOT=${OLLAMA_INSTALL_ROOT:-/scratch/project_2009497/LaclauGPT-Private/.ollama}

mkdir -p "${PRIVATE_ROOT}"/{data,media,keyframes,logs,outputs,qa,provenance}
cd "${PUBLIC_ROOT}"

module --force purge
module load gcc/14.3.0
module load python-pytorch/2.13
module load ffmpeg
unset PYTHONPATH
unset PYTHONHOME

[[ -x "${VENV}/bin/python" ]] || {
  echo "Missing Roihu ARM64 venv: ${VENV}" >&2
  echo "Create it on Roihu and install requirements/roihu-ep24.txt." >&2
  exit 2
}
source "${VENV}/bin/activate"

python - <<'PY'
import sys, numpy, pandas, openpyxl, yaml
print("Python:", sys.executable)
print("NumPy:", numpy.__version__, numpy.__file__)
print("Pandas:", pandas.__version__)
print("openpyxl:", openpyxl.__version__)
print("PyYAML:", yaml.__version__)
PY

ffmpeg -version | head -n 1
ffprobe -version | head -n 1

# Phase 0 isolation smoke check. This must not import EP24/Roihu optional stacks.
python - <<'PY'
import laclaugpt
print("Phase 0 import: OK", getattr(laclaugpt, "__file__", ""))
PY

export PATH="${OLLAMA_INSTALL_ROOT}/bin:${PATH}"
export LD_LIBRARY_PATH="${OLLAMA_INSTALL_ROOT}/lib/ollama${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
if ! command -v ollama >/dev/null 2>&1; then
  if [[ ${OLLAMA_AUTO_INSTALL:-1} != 1 ]]; then
    echo "Ollama missing and auto-install disabled" >&2
    exit 2
  fi
  [[ $(uname -m) == aarch64 || $(uname -m) == arm64 ]] || {
    echo "Refusing ARM64 Ollama install on $(uname -m)" >&2
    exit 2
  }
  archive="${TMPDIR:-/tmp}/ollama-linux-arm64.tar.zst"
  curl --fail --location --retry 3 --output "${archive}" https://ollama.com/download/ollama-linux-arm64.tar.zst
  mkdir -p "${OLLAMA_INSTALL_ROOT}"
  zstd -dc "${archive}" | tar -xf - -C "${OLLAMA_INSTALL_ROOT}"
fi

OLLAMA_PORT=$((20000 + SLURM_JOB_ID % 20000))
export OLLAMA_HOST="http://127.0.0.1:${OLLAMA_PORT}"
export LLM_MODE=local
export LLM_ALLOW_CLOUD_FALLBACK=0
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}

OLLAMA_LOG="${PRIVATE_ROOT}/logs/ollama_${SLURM_JOB_ID}.log"
ollama serve >"${OLLAMA_LOG}" 2>&1 &
OLLAMA_PID=$!
cleanup() { kill "${OLLAMA_PID}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

for _ in {1..60}; do
  ollama list >/dev/null 2>&1 && break
  sleep 2
done
ollama list >/dev/null 2>&1 || {
  echo "Ollama failed to start; see ${OLLAMA_LOG}" >&2
  exit 3
}

ollama pull "${MODEL}"
ollama show "${MODEL}" >/dev/null

srun --ntasks=1 python -m laclaugpt_data_analysis.ep24_roihu preflight \
  --private-root "${PRIVATE_ROOT}" --model "${MODEL}"

srun --ntasks=1 python -m laclaugpt_data_analysis.ep24_roihu "${MODE}" \
  --private-root "${PRIVATE_ROOT}" --model "${MODEL}"
