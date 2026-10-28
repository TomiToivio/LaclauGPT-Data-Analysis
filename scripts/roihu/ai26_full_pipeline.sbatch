#!/usr/bin/env bash
#SBATCH --job-name=ai26-roihu-test
#SBATCH --partition=gpumedium
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:gh200:1
#SBATCH --time=04:00:00
#SBATCH --mem=48G
set -euo pipefail
# Override resource directives using sbatch arguments. Script is bounded; not a scheduler.
ROOT=${LACLAUGPT_REPO_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}
ENV_FILE=${LACLAUGPT_ENV_FILE:-"$ROOT/data/config/ai26/roihu.env"}
[[ -f "$ENV_FILE" ]] || { echo "Private Roihu env file missing: $ENV_FILE" >&2; exit 2; }
[[ $(stat -c %a "$ENV_FILE") =~ ^(600|400)$ ]] || { echo "Set private env permissions to 600 or 400" >&2; exit 2; }
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
: "${LACLAUGPT_PRIVATE_CONFIG_DIR:?required}"
: "${LACLAUGPT_MONGODB_URI:?required}"
: "${LACLAUGPT_REDIS_URL:?required}"
: "${LACLAUGPT_S3_ENDPOINT:?required}"
: "${LACLAUGPT_S3_BUCKET:?required}"
: "${LACLAUGPT_RUN_ID:?required}"
[[ "${LACLAUGPT_PROJECT_ID:-ai26}" == ai26 ]] || { echo "Only AI26 is supported" >&2; exit 2; }
[[ "$LACLAUGPT_RUN_ID" == roihu-test-* ]] || {
  echo "Refusing production/shared run ID; use roihu-test-<unique-id> and isolated test queue" >&2; exit 2;
}
[[ "${LACLAUGPT_MAX_TASKS:-5}" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid task limit" >&2; exit 2; }
[[ "${LACLAUGPT_MAX_TASKS:-5}" -le 25 ]] || { echo "Test limit >25 refused" >&2; exit 2; }
module --force purge
module load gcc/14.3.0
module load python-pytorch/2.13
module load ffmpeg
unset PYTHONPATH PYTHONHOME
VENV=${LACLAUGPT_ROIHU_VENV:-"$ROOT/.venv-roihu"}
[[ -x "$VENV/bin/python" ]] || { echo "Install ARM64 Roihu venv first" >&2; exit 2; }
source "$VENV/bin/activate"
export LACLAUGPT_PROJECT_ID=ai26 LACLAUGPT_MACHINE=roihu LACLAUGPT_EXECUTION=slurm
export LACLAUGPT_STORAGE=distributed LACLAUGPT_DATA_BACKEND=mongodb
export LACLAUGPT_CACHE_BACKEND=redis LACLAUGPT_OBJECT_BACKEND=s3
export LLM_MODE=local LLM_ALLOW_CLOUD_FALLBACK=0
export LACLAUGPT_OLLAMA_MODEL=${LACLAUGPT_OLLAMA_MODEL:-gemma4:12b}
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-8}
cd "$ROOT"
bash scripts/roihu/preflight_ai26.sh
# One local model process per allocated job; no dependence on a login-node model server.
command -v ollama >/dev/null || { echo "Install compatible ARM64 Ollama (private project directory)" >&2; exit 2; }
export OLLAMA_HOST="http://127.0.0.1:$((20000 + ${SLURM_JOB_ID:-1} % 20000))"
LOGDIR=${LACLAUGPT_ROIHU_LOG_DIR:-"$LACLAUGPT_PRIVATE_CONFIG_DIR/logs"}
mkdir -p "$LOGDIR"
ollama serve >"$LOGDIR/ollama_${SLURM_JOB_ID:-manual}.log" 2>&1 &
OLLAMA_PID=$!
trap 'kill "$OLLAMA_PID" 2>/dev/null || true' EXIT INT TERM
ready=0
for _ in {1..60}; do
  if ollama list >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
(( ready )) || { echo "Ollama startup failed" >&2; exit 3; }
ollama show "$LACLAUGPT_OLLAMA_MODEL" >/dev/null 2>&1 || {
  echo "Required local model missing; pre-pull on Roihu; no automatic cloud fallback" >&2; exit 3;
}
# Never seed the production queue. Pre-seed bounded test tasks into the isolated run
# using the documented worker protocol. Existing worker runs canonical stages.
WORKER_ID="roihu-${SLURM_JOB_ID:-manual}-${SLURM_ARRAY_TASK_ID:-0}"
srun --ntasks=1 laclaugpt-analysis-worker \
  --run-manifest "$LACLAUGPT_PRIVATE_CONFIG_DIR/run-manifest.json" \
  --private-config "$LACLAUGPT_PRIVATE_CONFIG_DIR/analysis.json" \
  --codebook "$LACLAUGPT_PRIVATE_CONFIG_DIR/codebook.json" \
  --worker-id "$WORKER_ID" \
  --max-tasks "${LACLAUGPT_MAX_TASKS:-5}" \
  --reclaim-idle-ms "${LACLAUGPT_RECLAIM_IDLE_MS:-300000}"
echo "Roihu AI26 test worker completed: $WORKER_ID"
