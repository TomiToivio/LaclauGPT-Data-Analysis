#!/usr/bin/env python3
"""Vendor a frozen snapshot of an upstream EP24 pipeline into this repository (#399).

The issue asks for *imported runnable implementations*, not wrappers around upstream
branches, and it asks for a controlled snapshot with a sync policy rather than a runtime
dependency on mutable refs. This script performs that import reproducibly:

* it copies files from a **pinned upstream SHA**, never from a branch tip;
* it writes `PROVENANCE.json` with the source repository, SHA, license, file map and a
  SHA-256 per file, so a later drift is detectable rather than suspected;
* it refuses to overwrite an existing snapshot without `--force`, because silently
  replacing an imported historical implementation destroys the reproduction you imported
  it for.

Usage:
    python tools/vendor_pipeline.py --source <checkout> --ref <sha> --dest <dir> \
        --pipeline-id ep24 --paths . --include '*.py'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def git(source: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(source), *args], capture_output=True, text=True, check=True
    ).stdout


def tracked_files(source: Path, ref: str, paths: list[str]) -> list[str]:
    out = git(source, "ls-tree", "-r", "--name-only", ref, "--", *paths)
    return [line for line in out.splitlines() if line.strip()]


def blob(source: Path, ref: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(source), "show", f"{ref}:{path}"],
        capture_output=True, check=True,
    ).stdout


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, type=Path, help="upstream checkout")
    p.add_argument("--ref", required=True, help="pinned commit SHA")
    p.add_argument("--dest", required=True, type=Path, help="destination directory")
    p.add_argument("--pipeline-id", required=True)
    p.add_argument("--paths", nargs="+", default=["."])
    p.add_argument("--suffix", default=".py", help="only vendor files with this suffix")
    p.add_argument("--repo", default="TomiToivio/LaclauGPT-Multimodal-Analysis")
    p.add_argument("--license", default="See upstream repository")
    p.add_argument("--exclude", nargs="*", default=[], help="path prefixes to skip")
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)

    source = args.source.resolve()
    dest = args.dest.resolve()
    provenance_path = dest / "PROVENANCE.json"
    if provenance_path.exists() and not args.force:
        print(f"refusing to overwrite existing snapshot: {provenance_path}", file=sys.stderr)
        return 2

    # A branch name would make the import irreproducible the moment upstream moves.
    resolved = git(source, "rev-parse", args.ref).strip()
    if len(resolved) != 40:
        print(f"ref did not resolve to a commit: {args.ref}", file=sys.stderr)
        return 2

    files = [
        f for f in tracked_files(source, resolved, args.paths)
        if (not args.suffix or f.endswith(args.suffix))
        # Upstream's own test suite is not vendored: it targets upstream's environment
        # and would be collected by this repository's CI, failing for reasons that say
        # nothing about the import.
        and not any(f == x or f.startswith(x.rstrip("/") + "/") for x in args.exclude)
    ]
    if not files:
        print("no files matched; refusing to write an empty snapshot", file=sys.stderr)
        return 3

    (dest / "src").mkdir(parents=True, exist_ok=True)
    file_map: dict[str, dict] = {}
    for path in files:
        data = blob(source, resolved, path)
        target = dest / "src" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        file_map[path] = {
            "dest": f"src/{path}",
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    provenance = {
        "pipeline_id": args.pipeline_id,
        "source_repository": args.repo,
        "source_ref": resolved,
        "license": args.license,
        "imported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "imported_by": "tools/vendor_pipeline.py",
        "sync_policy": (
            "Frozen snapshot. Upstream is not a runtime dependency. Re-import only by "
            "pinning a new SHA and recording the diff; never by pulling a branch."
        ),
        "file_count": len(file_map),
        "files": file_map,
    }
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    print(f"vendored {len(file_map)} files from {args.pipeline_id}@{resolved[:8]} -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
