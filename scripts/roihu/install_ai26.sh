#!/usr/bin/env bash
# Bootstrap on a Roihu login node; never install into a shared Laskin venv.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
VENV=${LACLAUGPT_ROIHU_VENV:-"$ROOT/.venv-roihu"}
if [[ "${1:-}" == "--help" ]]; then
  echo "Usage: LACLAUGPT_ROIHU_VENV=/project/path/.venv-roihu bash scripts/roihu/install_ai26.sh [--check]"
  exit 0
fi
if [[ $(uname -m) != aarch64 ]]; then
  echo "WARNING: this environment is $(uname -m); Roihu GH200 expects aarch64. Do not copy x86 environments." >&2
fi
command -v module >/dev/null 2>&1 || { echo "CSC environment modules unavailable; run on Roihu" >&2; exit 2; }
module --force purge
module load gcc/14.3.0
module load python-pytorch/2.13
module load ffmpeg
if [[ "${1:-}" == "--check" ]]; then
  python -c 'import sys,platform; print(sys.version); print(platform.machine())'
  command -v ffmpeg
  exit 0
fi
python -m venv --system-site-packages "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -e "$ROOT[remote,ollama,analysis,arrow,nlp,rag,rdf]"
"$VENV/bin/python" -c 'import pymongo, redis, boto3, ollama; print("AI26 Roihu Python dependencies OK")'
echo "Installed to $VENV; configure an untracked environment file and local Ollama/models separately."
