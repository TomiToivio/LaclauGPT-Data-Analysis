#!/bin/bash
#SBATCH --job-name=ep24_reprocess
#SBATCH --partition=gpumedium
#SBATCH --time=16:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=72
#SBATCH --mem=120G
#SBATCH --gres=gpu:gh200:1
#SBATCH --output=ep24_reprocess_%j.out
#SBATCH --error=ep24_reprocess_%j.err

# Public EP24 Finland/Poland reprocessing harness for CSC Roihu.
# No project IDs, private paths, credentials, datasets, manifests, codebooks,
# researcher annotations, or other restricted material are committed here.
# Supply machine/project-specific values at submission time, for example:
#   sbatch --account=<CSC_PROJECT> --export=ALL,LACLAUGPT_DATA_DIR=/scratch/... \
#     scripts/ep24/ep24_roihu_reprocess.sbatch

set -euo pipefail

: "${LACLAUGPT_DATA_DIR:?Set LACLAUGPT_DATA_DIR to a private runtime data root outside the repository}"
export LACLAUGPT_REPO_ROOT=${LACLAUGPT_REPO_ROOT:-$PWD}
export LACLAUGPT_MEMORY_DIR=${LACLAUGPT_MEMORY_DIR:-${LACLAUGPT_DATA_DIR}/memory}
export OLLAMA_MODELS=${OLLAMA_MODELS:-${LACLAUGPT_DATA_DIR}/ollama-models}
export OLLAMA_INSTALL_ROOT=${OLLAMA_INSTALL_ROOT:-${LACLAUGPT_DATA_DIR}/ollama}
export OLLAMA_KEEP_ALIVE=${OLLAMA_KEEP_ALIVE:-24h}
export LLM_MODE=local
export LLM_ALLOW_CLOUD_FALLBACK=0
export EP24_REQUIRE_HUMAN_CODEBOOK=1
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}
export OMP_PLACES=cores
export OMP_PROC_BIND=spread

mkdir -p \
  "${LACLAUGPT_DATA_DIR}" \
  "${LACLAUGPT_MEMORY_DIR}" \
  "${OLLAMA_MODELS}" \
  "${LACLAUGPT_DATA_DIR}/ollama-logs" \
  "${LACLAUGPT_DATA_DIR}"/ep24/{csv,videos,annotations,human_reports,reviews,tmp,private_codebooks,run_configs}

cd "${LACLAUGPT_REPO_ROOT}"

module --force purge
module load gcc/14.3.0
module load python-pytorch/2.13
module load ffmpeg
unset PYTHONPATH
unset PYTHONHOME

command -v ffmpeg >/dev/null 2>&1 || {
  echo "ffmpeg is not available after loading Roihu modules" >&2
  exit 2
}

: "${TMPDIR:?Roihu should provide TMPDIR inside the Slurm allocation}"
VENV=${EP24_ROIHU_VENV:-${LACLAUGPT_DATA_DIR}/.venv-roihu}
if [[ ! -x "${VENV}/bin/python" ]]; then
  cat >&2 <<EOF
Missing Roihu ARM64 virtual environment: ${VENV}
Create it on roihu-gpu.csc.fi:
  module --force purge
  module load gcc/14.3.0
  module load python-pytorch/2.13
  module load ffmpeg
  python -m venv --system-site-packages "${VENV}"
  source "${VENV}/bin/activate"
  python -m pip install --upgrade pip setuptools wheel
  python -m pip install -e '.[all]'
EOF
  exit 2
fi
source "${VENV}/bin/activate"

python - <<'PY'
import numpy
print(f"NumPy preflight OK: {numpy.__version__} from {numpy.__file__}")
PY

export PATH="${OLLAMA_INSTALL_ROOT}/bin:${PATH}"
export LD_LIBRARY_PATH="${OLLAMA_INSTALL_ROOT}/lib/ollama${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

if ! command -v ollama >/dev/null 2>&1; then
  if [[ ${OLLAMA_AUTO_INSTALL:-1} != 1 ]]; then
    echo "ollama is missing and OLLAMA_AUTO_INSTALL is disabled" >&2
    exit 2
  fi
  [[ $(uname -m) == aarch64 || $(uname -m) == arm64 ]] || {
    echo "Refusing ARM64 Ollama install on architecture $(uname -m)" >&2
    exit 2
  }
  command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 2; }
  command -v zstd >/dev/null 2>&1 || { echo "zstd is required" >&2; exit 2; }
  archive="${TMPDIR}/ollama-linux-arm64.tar.zst"
  curl --fail --location --retry 3 --output "${archive}" https://ollama.com/download/ollama-linux-arm64.tar.zst
  mkdir -p "${OLLAMA_INSTALL_ROOT}"
  zstd -dc "${archive}" | tar -xf - -C "${OLLAMA_INSTALL_ROOT}"
fi

OLLAMA_PORT=$((20000 + SLURM_JOB_ID % 20000))
export OLLAMA_HOST="http://127.0.0.1:${OLLAMA_PORT}"
OLLAMA_LOG="${LACLAUGPT_DATA_DIR}/ollama-logs/serve_${SLURM_JOB_ID}.log"
ollama serve >"${OLLAMA_LOG}" 2>&1 &
OLLAMA_PID=$!
cleanup() { kill "${OLLAMA_PID}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

for _ in {1..60}; do
  ollama list >/dev/null 2>&1 && break
  sleep 2
done
ollama list >/dev/null 2>&1 || {
  echo "Ollama did not start; see ${OLLAMA_LOG}" >&2
  exit 3
}

ollama pull "${EP24_ANALYSIS_MODEL:-gemma4:26b}"
ollama pull "${EP24_TRANSLATION_MODEL:-translategemma:27b}"

for country in finland poland; do
  echo "=== Starting public EP24 reprocessing harness: ${country} ==="
  srun --ntasks=1 bash scripts/ep24/run_country_reprocess.sh "${country}"
  echo "=== Finished: ${country} ==="
done
