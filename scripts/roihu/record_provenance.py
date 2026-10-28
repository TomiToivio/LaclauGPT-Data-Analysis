#!/usr/bin/env python3
"""Record reproducible provenance for one bounded AI26 Roihu run (issue #390).

The issue requires every run to be identifiable after the fact: job ID, host, Git SHA,
timings, model/provider, prompt/codebook/config revisions and a reproducible manifest.
A Slurm job that writes only its scientific outputs cannot be reproduced or compared with
a concurrent Laskin run, so this writes a small JSON document twice per job:

    start  — before the worker claims anything
    end    — on exit, including the worker's status and the elapsed time

It is deliberately boring: no network, no database, no credentials. It records what the
environment already says and what the checkout can hash, so it works identically on a
login node, inside an allocation, and in a test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def git_sha(root: Path) -> str | None:
    """The exact code revision, preferring the checkout itself.

    A submission from a dirty tree is recorded as such rather than silently claiming the
    commit's behaviour: `-dirty` is the difference between a reproducible run and a
    plausible one.
    """
    try:
        sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        return f"{sha}-dirty" if dirty else sha
    except (OSError, subprocess.SubprocessError):
        return None


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def slurm_facts() -> dict[str, str]:
    keys = (
        "SLURM_JOB_ID", "SLURM_JOB_NAME", "SLURM_PARTITION", "SLURM_ACCOUNT",
        "SLURM_CPUS_PER_TASK", "SLURM_MEM_PER_NODE", "SLURM_JOB_GPUS",
        "SLURM_ARRAY_TASK_ID", "SLURM_SUBMIT_DIR",
    )
    return {k.lower(): os.environ[k] for k in keys if os.environ.get(k)}


def collect(root: Path, config_dir: Path | None) -> dict:
    facts: dict = {
        "issue": 390,
        "phase_time": utcnow(),
        "run_id": os.environ.get("LACLAUGPT_RUN_ID", ""),
        "project_id": os.environ.get("LACLAUGPT_PROJECT_ID", ""),
        "worker_id": os.environ.get("LACLAUGPT_WORKER_ID", ""),
        "host": platform.node(),
        "machine": os.environ.get("LACLAUGPT_MACHINE", ""),
        "execution": os.environ.get("LACLAUGPT_EXECUTION", ""),
        "ollama_model": os.environ.get("LACLAUGPT_OLLAMA_MODEL", ""),
        "llm_mode": os.environ.get("LLM_MODE", ""),
        "cloud_fallback_allowed": os.environ.get("LLM_ALLOW_CLOUD_FALLBACK", ""),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "git_sha": git_sha(root),
        "slurm": slurm_facts(),
    }
    if config_dir is not None:
        facts["frozen_config"] = {
            name: sha256_file(config_dir / name)
            for name in ("run-manifest.json", "analysis.json", "codebook.json")
        }
    return facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("start", "end"))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--config-dir", default=None)
    parser.add_argument("--status", default=None, help="worker exit status (end phase)")
    parser.add_argument("--elapsed-seconds", default=None, type=int)
    args = parser.parse_args(argv)

    config_dir = Path(args.config_dir) if args.config_dir else None
    if config_dir is not None and not config_dir.is_dir():
        print(f"provenance: config dir not found: {config_dir}", file=sys.stderr)
        return 2

    facts = collect(args.root, config_dir)

    document: dict = {}
    if args.out.exists():
        try:
            document = json.loads(args.out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            document = {}

    if args.phase == "start":
        document = {"start": facts}
    else:
        document.setdefault("start", {})
        document["end"] = facts
        document["worker_exit_status"] = args.status
        document["elapsed_seconds"] = args.elapsed_seconds

    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_suffix(args.out.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.out)
    print(f"provenance {args.phase}: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
