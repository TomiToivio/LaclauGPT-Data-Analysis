#!/bin/bash
#SBATCH --job-name=ep24_reprocess
#SBATCH --account=project_2009497
#SBATCH --output=/scratch/project_2009497/LaclauGPT-Data-Analysis/ep24-reprocess-%j.out
#SBATCH --error=/scratch/project_2009497/LaclauGPT-Data-Analysis/ep24-reprocess-%j.err
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
PRIVATE_REPO=${LACLAUGPT_PRIVATE_REPO:-/scratch/project_2009497/LaclauGPT-Private}
PRIVATE_ROOT=${LACLAUGPT_EP24_PRIVATE_ROOT:-${PRIVATE_REPO}/analysis/ep24}
MODE=${EP24_RUN_MODE:-pilot}
MODEL=${EP24_ANALYSIS_MODEL:-gemma4:12b}
VENV=${EP24_ROIHU_VENV:-${PUBLIC_ROOT}/.venv-roihu-gpu}
OLLAMA_INSTALL_ROOT=${OLLAMA_INSTALL_ROOT:-${PRIVATE_ROOT}/.ollama}

[[ -d "${PUBLIC_ROOT}" && -d "${PRIVATE_REPO}" ]] || { echo "Missing public/private checkout under /scratch/project_2009497; pull both repositories first" >&2; exit 2; }
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

# One-time source migration is automatic when the pinned legacy submodule is locally available.
if [[ ! -s "${PRIVATE_ROOT}/source/ep24_finland_dashboard_9_1_2026.csv" || ! -s "${PRIVATE_ROOT}/source/ep24_poland_dashboard_9_1_2026.csv" || ! -s "${PRIVATE_ROOT}/codebooks/ep24_common_private.json" ]]; then
  if [[ -f "${PRIVATE_REPO}/legacy/LaclauGPT-Discourse-Analysis-Private/data/research_notes.xlsx" ]]; then
    (cd "${PRIVATE_REPO}" && bash analysis/ep24/migrate_from_legacy.sh)
  else
    echo "EP24 source/codebooks missing. On a login node: cd ${PRIVATE_REPO} && git submodule update --init --recursive && bash analysis/ep24/migrate_from_legacy.sh" >&2
    exit 2
  fi
fi

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
export OLLAMA_MODELS=${OLLAMA_MODELS:-${PRIVATE_ROOT}/.ollama/models}
mkdir -p "${OLLAMA_MODELS}"
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
