"""CLI for validating, rendering and fingerprinting Phase 1 research protocols."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .phase1_protocol import (
    compose_protocol_from_files,
    fingerprint,
    load_mapping,
    validate_codebook,
    validate_config,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = ROOT / "config" / "phase1" / "defaults.yaml"
PROFILES = ROOT / "config" / "phase1"
DEFAULT_CODEBOOK = ROOT / "codebooks" / "public" / "phase1_v1.yaml"


def _path_profile(value: str) -> Path:
    candidate = Path(value)
    if candidate.exists():
        return candidate
    return PROFILES / f"{value}.yaml"


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--defaults", type=Path, default=DEFAULTS)
    parser.add_argument("--profile", default="ai26")
    parser.add_argument("--codebook", action="append", type=Path, default=None)
    parser.add_argument("--private-overlay", type=Path)
    parser.add_argument("--machine-overlay", type=Path)
    parser.add_argument("--execution-overlay", type=Path)


def _protocol(args):
    return compose_protocol_from_files(
        defaults_path=args.defaults,
        profile_path=_path_profile(args.profile),
        codebook_paths=args.codebook or [DEFAULT_CODEBOOK],
        private_overlay_path=args.private_overlay,
        machine_overlay_path=args.machine_overlay,
        execution_overlay_path=args.execution_overlay,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect canonical LaclauGPT Phase 1 protocol resources")
    subs = parser.add_subparsers(dest="resource", required=True)

    config = subs.add_parser("config")
    config_sub = config.add_subparsers(dest="action", required=True)
    for name in ("validate", "render", "fingerprint"):
        p = config_sub.add_parser(name)
        _common(p)

    codebook = subs.add_parser("codebook")
    codebook_sub = codebook.add_subparsers(dest="action", required=True)
    for name in ("validate", "fingerprint"):
        p = codebook_sub.add_parser(name)
        p.add_argument("path", type=Path, nargs="?", default=DEFAULT_CODEBOOK)

    args = parser.parse_args(argv)
    if args.resource == "codebook":
        data = load_mapping(args.path)
        validate_codebook(data)
        if args.action == "fingerprint":
            print(fingerprint(data))
        else:
            print(f"valid: {args.path}")
        return 0

    protocol = _protocol(args)
    if args.action == "validate":
        validate_config(protocol.config)
        print(f"valid: {protocol.study_id} ({protocol.config_hash[:12]})")
    elif args.action == "render":
        print(json.dumps(protocol.redacted_config(), indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(protocol.config_hash)
        print(protocol.codebook_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
