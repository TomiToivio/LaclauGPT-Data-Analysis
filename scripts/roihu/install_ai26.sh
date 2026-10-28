#!/usr/bin/env bash
# AI26 analysis — Roihu (CSC) bootstrap (#390).
#
# Configures one GH200 node for the canonical AI26 analysis pipeline: modules, Python environment,
# media/ASR dependencies, a local model runtime, and then the repository's own preflight.
#
# Roihu GPU nodes are NVIDIA GH200 (aarch64). A Puhti/x86_64 virtualenv is not compatible and must not
# be reused; this script always builds its own under the project scratch directory.
#
# Usage (on a Roihu login node, after `module purge`):
#   AI26_ENV_FILE=/path/to/roihu.env bash scripts/roihu/install_ai26.sh
#
# Everything machine- or account-specific comes from the environment file, which is never committed.
set -euo pipefail

ROOT_DIR=${LACLAUGPT_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
ENV_FILE=${AI26_ENV_FILE:-"$ROOT_DIR/data/config/ai26/roihu.env"}
VENV_DIR=${AI26_VENV_DIR:-"${LACLAUGPT_SCRATCH:-$ROOT_DIR/.venv-roihu}/ai26-venv"}
EXTRAS=${AI26_EXTRAS:-analysis,distributed}

log() { printf '[install %s] %s\n' "$(date -Is)" "$*"; }
die() { printf '[install %s] ERROR: %s\n' "$(date -Is)" "$*" >&2; exit 1; }

# --- 1. architecture ----------------------------------------------------------------------------
ARCH=$(uname -m)
log "architecture: $ARCH"
case "$ARCH" in
  aarch64) ;;
  x86_64) log "warning: x86_64 detected; Roihu GH200 nodes are aarch64. Continuing, but this is not a Roihu node." ;;
  *) die "unsupported architecture: $ARCH" ;;
esac

# --- 2. modules ---------------------------------------------------------------------------------
# CSC's `module` is a shell function; it only exists in an interactive/login-capable shell.
if command -v module >/dev/null 2>&1 || type module >/dev/null 2>&1; then
  # `module purge` also removes the compiler, and ffmpeg's own module needs it, so gcc is loaded
  # first. This ordering is the difference between a working ffmpeg and a confusing link failure.
  module purge >/dev/null 2>&1 || true
  for mod in "${AI26_MODULES:-gcc ffmpeg}"; do
    log "module load $mod"
    module load "$mod" || die "module load $mod failed; check available modules with 'module avail'"
  done
else
  log "no environment modules available; relying on system tools"
fi

command -v ffmpeg >/dev/null 2>&1 \
  || die "ffmpeg not found. On Roihu: 'module purge && module load gcc ffmpeg' (order matters)."
log "ffmpeg: $(ffmpeg -version 2>/dev/null | head -1)"

# --- 3. python environment ----------------------------------------------------------------------
PYTHON_BIN=${AI26_PYTHON:-python3}
"$PYTHON_BIN" -c 'import sys; print(f"python {sys.version.split()[0]}")'
mkdir -p "$(dirname "$VENV_DIR")"
if [[ ! -d "$VENV_DIR" ]]; then
  log "creating virtualenv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR" || die "venv creation failed (is python3-venv available?)"
else
  log "reusing virtualenv at $VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --quiet --upgrade pip setuptools wheel
log "installing repository with extras: $EXTRAS"
python -m pip install --quiet -e "$ROOT_DIR[$EXTRAS]" \
  || die "pip install failed; inspect $ROOT_DIR/pyproject.toml extras for this platform"

# --- 4. model runtime ---------------------------------------------------------------------------
# The pipeline speaks to any Ollama-compatible endpoint through LACLAUGPT_LLM_ENDPOINT, so a running
# service is not required here — but it must exist somewhere reachable from the compute node.
if command -v ollama >/dev/null 2>&1; then
  log "ollama present: $(ollama --version 2>/dev/null | head -1)"
else
  log "no ollama binary on PATH. Either run a local Ollama service for this job"
  log "  (OLLAMA_HOST=127.0.0.1:11434, started inside the batch script), or point"
  log "  LACLAUGPT_LLM_ENDPOINT at an existing reachable endpoint."
fi

# --- 5. configuration presence (values are never printed) ----------------------------------------
if [[ -f "$ENV_FILE" ]]; then
  log "env file found: $ENV_FILE"
  for key in LACLAUGPT_MONGODB_URI LACLAUGPT_REDIS_URL LACLAUGPT_S3_ENDPOINT LACLAUGPT_S3_BUCKET; do
    if grep -qE "^[[:space:]]*(export[[:space:]]+)?${key}=" "$ENV_FILE"; then
      log "  $key: present"
    else
      log "  $key: MISSING"
    fi
  done
else
  log "warning: no env file at $ENV_FILE — create it from the documented template before submitting"
fi

# --- 6. repository preflight --------------------------------------------------------------------
if command -v laclaugpt-preflight >/dev/null 2>&1; then
  log "running repository preflight"
  set +e
  laclaugpt-preflight 2>&1 | tail -40
  preflight_status=${PIPESTATUS[0]}
  set -e
  log "preflight exit status: $preflight_status (non-zero means the runtime would fail closed)"
else
  log "laclaugpt-preflight not installed; the install is incomplete"
  exit 1
fi

log "done. next: bash scripts/roihu/preflight_ai26.sh, then sbatch scripts/roihu/ai26_full_pipeline.sbatch"
