"""CLI for validating, rendering and fingerprinting Phase 1 research protocols."""
from __future__ import annotations

import argparse
import json
from importlib import resources
from pathlib import Path
from typing import Sequence

from .phase1_protocol import (
    compose_protocol,
    deep_merge,
    fingerprint,
    load_mapping,
    validate_codebook,
    validate_config,
)

PACKAGE_ROOT = resources.files("laclaugpt_data_analysis")
RESOURCE_ROOT = PACKAGE_ROOT.joinpath("resources", "phase1")
DEFAULTS = RESOURCE_ROOT.joinpath("defaults.yaml")
PROFILES = RESOURCE_ROOT
DEFAULT_CODEBOOK = RESOURCE_ROOT.joinpath("phase1_v1.yaml")


def _path_profile(value: str):
    candidate = Path(value)
    if candidate.exists():
        return candidate
    packaged = PROFILES.joinpath(f"{value}.yaml")
    if packaged.is_file():
        return packaged
    raise FileNotFoundError(f"Phase 1 profile not found: {value}")


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--defaults", default=None)
    parser.add_argument("--profile", default="ai26")
    parser.add_argument("--codebook", action="append", default=None)
    parser.add_argument("--private-overlay")
    parser.add_argument("--machine-overlay")
    parser.add_argument("--execution-overlay")


def _resolve_codebook(path_value: str):
    candidate = Path(path_value)
    if candidate.exists():
        return candidate
    if path_value == "codebooks/public/phase1_v1.yaml":
        return DEFAULT_CODEBOOK
    raise FileNotFoundError(
        f"Configured codebook does not exist: {path_value}. "
        "Provide --codebook or a valid private/machine overlay path."
    )


def _protocol(args):
    defaults_path = Path(args.defaults) if args.defaults else DEFAULTS
    defaults = load_mapping(defaults_path)
    profile = load_mapping(_path_profile(args.profile))
    private_overlay = load_mapping(args.private_overlay) if args.private_overlay else {}
    machine_overlay = load_mapping(args.machine_overlay) if args.machine_overlay else {}
    execution_overlay = load_mapping(args.execution_overlay) if args.execution_overlay else {}

    effective = deep_merge(
        defaults,
        profile,
        private_overlay,
        machine_overlay,
        execution_overlay,
    )
    validate_config(effective)

    configured = list(effective["codebooks"]["paths"])
    if args.codebook:
        explicit = [str(Path(item)) for item in args.codebook]
        if configured != explicit:
            raise ValueError(
                "--codebook must match effective codebooks.paths exactly; "
                f"configured={configured!r}, explicit={explicit!r}"
            )
        codebook_paths = [Path(item) for item in args.codebook]
    else:
        codebook_paths = [_resolve_codebook(item) for item in configured]

    return compose_protocol(
        defaults=defaults,
        profile=profile,
        codebooks=[load_mapping(path) for path in codebook_paths],
        private_overlay=private_overlay,
        machine_overlay=machine_overlay,
        execution_overlay=execution_overlay,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect canonical LaclauGPT Phase 1 protocol resources"
    )
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
        p.add_argument("path", nargs="?", default=None)

    args = parser.parse_args(argv)
    if args.resource == "codebook":
        source = Path(args.path) if args.path else DEFAULT_CODEBOOK
        data = load_mapping(source)
        validate_codebook(data)
        if args.action == "fingerprint":
            print(fingerprint(data))
        else:
            print(f"valid: {source}")
        return 0

    protocol = _protocol(args)
    if args.action == "validate":
        validate_config(protocol.config)
        print(f"valid: {protocol.study_id} ({protocol.config_hash[:12]})")
    elif args.action == "render":
        print(
            json.dumps(
                protocol.redacted_config(),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        print(protocol.config_hash)
        print(protocol.codebook_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
