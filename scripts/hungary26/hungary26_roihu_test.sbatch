#!/bin/bash
#SBATCH --job-name=hungary26_test
#SBATCH --output=hungary26_test_%j.out
#SBATCH --error=hungary26_test_%j.err
#SBATCH --partition=gpumedium
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=72
#SBATCH --mem=120G
#SBATCH --gres=gpu:gh200:1
#SBATCH --time=1-12:00:00
#SBATCH --mail-type=ALL

set -euo pipefail

APP_DIR=${APP_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}
: "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT:?Set LACLAUGPT_HUNGARY26_PRIVATE_ROOT before submitting}"
export LACLAUGPT_HUNGARY26_PRIVATE_ROOT
PRIVATE_REPO=${LACLAUGPT_PRIVATE_REPO:-$(dirname "$(dirname "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}")")}
MODE=${MODE:-smoke}
[[ -d "${APP_DIR}" && -d "${PRIVATE_REPO}" ]] || { echo "Missing public/private checkout; set APP_DIR and LACLAUGPT_PRIVATE_REPO" >&2; exit 2; }

export OLLAMA_MODEL=gemma4:12b
export LLM_MODE=local
export LLM_ALLOW_CLOUD_FALLBACK=0
export OLLAMA_MODELS=${OLLAMA_MODELS:-${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}/.ollama/models}
export OLLAMA_INSTALL_ROOT=${OLLAMA_INSTALL_ROOT:-${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}/.ollama}
export OLLAMA_AUTO_INSTALL=${OLLAMA_AUTO_INSTALL:-1}
export OLLAMA_NUM_CTX=${OLLAMA_NUM_CTX:-32768}
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}
export OMP_PLACES=cores
export OMP_PROC_BIND=spread

mkdir -p   "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}/logs"   "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}/data"   "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}/media"   "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}/keyframes"   "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}/outputs"   "${OLLAMA_MODELS}"

module --force purge
module load python-pytorch/2.10
module load ffmpeg
unset PYTHONPATH
unset PYTHONHOME

command -v ffmpeg >/dev/null 2>&1 || { echo "ffmpeg is not on PATH" >&2; exit 2; }
command -v ffprobe >/dev/null 2>&1 || { echo "ffprobe is not on PATH" >&2; exit 2; }

VENV=${VENV:-${APP_DIR}/.venv-roihu-gpu}
if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "Missing Roihu ARM64 venv: ${VENV}" >&2
  echo "Create it on roihu-gpu.csc.fi; never copy a Puhti x86 environment." >&2
  exit 2
fi
source "${VENV}/bin/activate"

cd "${APP_DIR}"

# Stage from the already-initialized private legacy submodule only if needed.
if [[ ! -s "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}/source/hungary2026_instagram.xlsx" || ! -s "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}/source/hungary2026_tiktok.xlsx" ]]; then
  if [[ -f "${PRIVATE_REPO}/legacy/LaclauGPT-Discourse-Analysis-Private/data/hungrary2026/hungary2026_instagram.xlsx" ]]; then
    (cd "${PRIVATE_REPO}" && "${VENV}/bin/python" analysis/hungary26/migrate_from_legacy.py)
  else
    echo "Hungary26 workbooks missing. On a login node: cd ${PRIVATE_REPO} && git submodule update --init --recursive && python analysis/hungary26/migrate_from_legacy.py" >&2
    exit 2
  fi
fi
if [[ ! -s "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}/run/hungary26_roihu.yaml" || ! -s "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}/codebooks/hungary26_private.json" ]]; then
  (cd "${PRIVATE_REPO}" && "${VENV}/bin/python" analysis/hungary26/build_runtime.py --root "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}")
fi

"${VENV}/bin/python" - <<'PY'
import os
import sys
import numpy
print(f"NumPy preflight OK: {numpy.__version__} from {numpy.__file__}")
print(f"Python: {sys.executable}")
print(f"CWD: {os.getcwd()}")
PY

# Phase 0 isolation smoke test: this must not import Hungary multimodal extras.
"${VENV}/bin/python" - <<'PY'
import laclaugpt_preprocess
assert "cv2" not in laclaugpt_preprocess.__dict__
print("Phase 0 isolation smoke test OK")
PY

export PATH="${OLLAMA_INSTALL_ROOT}/bin:${PATH}"
export LD_LIBRARY_PATH="${OLLAMA_INSTALL_ROOT}/lib/ollama${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

if ! command -v ollama >/dev/null 2>&1; then
  if [[ ${OLLAMA_AUTO_INSTALL} != 1 ]]; then
    echo "ollama missing and OLLAMA_AUTO_INSTALL=${OLLAMA_AUTO_INSTALL}" >&2
    exit 2
  fi
  [[ $(uname -m) == aarch64 || $(uname -m) == arm64 ]] || {
    echo "Refusing ARM64 Ollama install on $(uname -m)" >&2
    exit 2
  }
  command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 2; }
  command -v zstd >/dev/null 2>&1 || { echo "zstd is required" >&2; exit 2; }
  : "${TMPDIR:?Roihu should provide TMPDIR}"
  archive="${TMPDIR}/ollama-linux-arm64.tar.zst"
  curl --fail --location --retry 3 --output "${archive}"     https://ollama.com/download/ollama-linux-arm64.tar.zst
  mkdir -p "${OLLAMA_INSTALL_ROOT}"
  zstd -dc "${archive}" | tar -xf - -C "${OLLAMA_INSTALL_ROOT}"
fi

export OLLAMA_HOST="127.0.0.1:$((20000 + SLURM_JOB_ID % 20000))"
OLLAMA_LOG="${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}/logs/ollama_${SLURM_JOB_ID}.log"
ollama serve > "${OLLAMA_LOG}" 2>&1 &
OLLAMA_PID=$!
trap 'kill "${OLLAMA_PID}" 2>/dev/null || true' EXIT INT TERM

for _ in {1..60}; do
  ollama list >/dev/null 2>&1 && break
  sleep 2
done
ollama list >/dev/null 2>&1 || { echo "Ollama did not start: ${OLLAMA_LOG}" >&2; exit 3; }

ollama pull "${OLLAMA_MODEL}"
ollama show "${OLLAMA_MODEL}" >/dev/null

# Private settings may point boto3 at CSC Allas through environment or config.
# No MongoDB or Redis variables are required by this workflow.
srun --ntasks=1 "${VENV}/bin/python" -m laclaugpt_data_analysis.hungary26_roihu   "${MODE}"   --private-root "${LACLAUGPT_HUNGARY26_PRIVATE_ROOT}"   --model "${OLLAMA_MODEL}"
