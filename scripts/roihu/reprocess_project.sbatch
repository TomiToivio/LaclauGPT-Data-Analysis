#!/bin/bash
#SBATCH --job-name=laclaugpt-reprocess
#SBATCH --partition=gpumedium
#SBATCH --time=12:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=96G
#SBATCH --gres=gpu:gh200:1
#SBATCH --output=data/logs/reprocess_%j.out
#SBATCH --error=data/logs/reprocess_%j.err

# Public template. Set account, repository paths, private config path and secrets
# through a private wrapper/environment. Do not commit official-project values here.
set -euo pipefail

: "${LACLAUGPT_REPO_ROOT:?set private repository checkout path}"
: "${LACLAUGPT_PRIVATE_REPROCESS_CONFIG:?set private project config path}"
: "${LACLAUGPT_ROIHU_VENV:?set ARM64 Roihu virtualenv path}"

cd "$LACLAUGPT_REPO_ROOT"

module --force purge
module load gcc/14.3.0
module load python-pytorch/2.13
module load ffmpeg
unset PYTHONPATH PYTHONHOME
source "$LACLAUGPT_ROIHU_VENV/bin/activate"

export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}
export OMP_PLACES=cores
export OMP_PROC_BIND=spread
export LACLAUGPT_MACHINE=roihu
export LACLAUGPT_EXECUTION=slurm

# Optional local Ollama setup. Private wrapper may instead configure an explicit
# cloud/external provider according to the normal provider policy.
if command -v ollama >/dev/null 2>&1; then
  OLLAMA_PORT=$((20000 + SLURM_JOB_ID % 20000))
  export OLLAMA_HOST="http://127.0.0.1:${OLLAMA_PORT}"
  mkdir -p "${LACLAUGPT_DATA_DIR:-./data}/logs"
  ollama serve >"${LACLAUGPT_DATA_DIR:-./data}/logs/ollama_${SLURM_JOB_ID}.log" 2>&1 &
  OLLAMA_PID=$!
  trap 'kill "$OLLAMA_PID" 2>/dev/null || true' EXIT INT TERM
  for _ in {1..60}; do ollama list >/dev/null 2>&1 && break; sleep 2; done
fi

START=${REPROCESS_START:-0}
STOP=${REPROCESS_STOP:-}
srun --ntasks=1 bash scripts/roihu/run_reprocessing.sh "$LACLAUGPT_PRIVATE_REPROCESS_CONFIG" "$START" "$STOP"
