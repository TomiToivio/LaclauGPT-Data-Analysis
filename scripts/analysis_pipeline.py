#!/usr/bin/env python3
"""Version-aware entrypoint for independently pinned scientific pipelines (#399)."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = {
    "ai26": {"path": ".", "source": "LaclauGPT-Data-Analysis", "steps": "canonical AI26", "mode": "native"},
    "ep24": {"path": "external/ep24-current", "source": "Multimodal-Analysis/main", "steps": "0-9", "mode": "roihu"},
    "ep24-legacy": {"path": "external/ep24-legacy", "source": "Multimodal-Analysis/legacy", "steps": "preprocess,frame,summary,postprocess,populism", "mode": "historical"},
}
LEGACY_STEPS = {"preprocess", "frame", "summary", "postprocess", "populism"}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "verify", "run"))
    parser.add_argument("--pipeline", choices=PIPELINES)
    parser.add_argument("--step", choices=sorted(LEGACY_STEPS))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    ns = parser.parse_args(argv)
    if ns.action == "list":
        print(json.dumps(PIPELINES, indent=2, sort_keys=True))
        return 0
    if not ns.pipeline:
        parser.error("--pipeline is required for verify and run")
    info = PIPELINES[ns.pipeline]
    root = ROOT / info["path"]
    if ns.pipeline == "ep24":
        expected = root / "scripts/roihu/run_pipeline.sh"
    elif ns.pipeline == "ep24-legacy":
        expected = root / "puhti_preprocess.py"
    else:
        expected = ROOT / "scripts/run_ai26_laskin.sh"
    if not expected.is_file():
        print(f"Missing {expected}; git submodule update --init --recursive", file=sys.stderr)
        return 2
    if ns.action == "verify":
        print(f"{ns.pipeline}: checkout present at {root}")
        subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True)
        return 0
    args = ns.args[1:] if ns.args and ns.args[0] == "--" else ns.args
    if ns.pipeline == "ai26":
        print("AI26 continues through its existing Laskin/worker launchers; no implicit new scheduler.", file=sys.stderr)
        return 2
    if ns.pipeline == "ep24":
        cmd = ["bash", str(expected), *args]
        env = dict(os.environ, LACLAUGPT_MULTIMODAL_PUBLIC_ROOT=str(root))
    else:
        if not ns.step:
            parser.error("legacy EP24 requires --step; historical stages are separate commands")
        cmd = [sys.executable, str(root / f"puhti_{ns.step}.py"), *args]
        env = dict(os.environ)
    return subprocess.call(cmd, cwd=root, env=env)

if __name__ == "__main__":
    raise SystemExit(main())
