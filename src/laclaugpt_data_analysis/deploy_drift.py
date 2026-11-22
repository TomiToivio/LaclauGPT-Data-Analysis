"""Report how far a deployed checkout has drifted from its upstream (issue #353).

The Laskin cron lines run their checkouts directly, and an editable install means the checkout
*is* the deployed code. Nothing pulled them, so on 2026-10-15 Analysis was nine commits behind
and three merged fixes were silently not in effect - every measurement taken from the live log
that day described pre-fix behaviour.

This module makes that visible from the place it matters: the wrapper's own preflight. It is
read-only, with warning-only default and an opt-in strict deployment gate:

* it runs ``git fetch`` and ``git rev-list``, nothing else;
* it never changes tracked files; only --strict can refuse to run;
* a stale runtime is a risk, not an emergency, and refusing would stall the corpus;
* any failure (no git, no network, not a repository) reports ``unknown`` rather than raising.

Usage::

    python -m laclaugpt_data_analysis.deploy_drift                  # this package's checkout
    python -m laclaugpt_data_analysis.deploy_drift --json
    python -m laclaugpt_data_analysis.deploy_drift --threshold 5    # allow five commits of lag
    python -m laclaugpt_data_analysis.deploy_drift --no-fetch       # offline, use existing refs
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_REFERENCE = "origin/main"
GIT_TIMEOUT_SECONDS = 20

CURRENT = "current"
BEHIND = "behind"
AHEAD = "ahead"
DIVERGED = "diverged"
UNKNOWN = "unknown"

#: The sibling checkouts that run from cron beside this one, by directory name.
SIBLING_NAMES = ("LaclauGPT-Data-Collection", "LaclauGPT-Data-Visualization")


def _git(args: list[str], cwd: Path, timeout: int = GIT_TIMEOUT_SECONDS) -> tuple[int, str]:
    """Run one git command read-only. Never raises."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    output = (completed.stdout or completed.stderr or "").strip()
    return completed.returncode, output


def checkout_drift(
    path: str | Path,
    *,
    reference: str = DEFAULT_REFERENCE,
    fetch: bool = True,
    timeout: int = GIT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Describe one checkout's distance from ``reference``.

    Returns a dict whose ``state`` is one of ``current``, ``behind``, ``ahead``, ``diverged``
    or ``unknown``. ``behind`` and ``ahead`` are ``None`` when they could not be measured.
    """
    checkout = Path(path)
    report: dict[str, Any] = {
        "name": checkout.name,
        "path": str(checkout),
        "reference": reference,
        "branch": "",
        "head": "",
        "behind": None,
        "ahead": None,
        "state": UNKNOWN,
        "detail": "",
    }

    if not checkout.is_dir():
        report["detail"] = "checkout not found"
        return report

    code, inside = _git(["rev-parse", "--is-inside-work-tree"], checkout, timeout)
    if code != 0 or inside != "true":
        report["detail"] = "not a git work tree"
        return report

    code, branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], checkout, timeout)
    report["branch"] = branch.splitlines()[0] if code == 0 else ""

    if fetch:
        code, detail = _git(["fetch", "--quiet", "origin", "+refs/heads/main:refs/remotes/origin/main"] if reference == DEFAULT_REFERENCE else ["fetch", "--quiet", "origin"], checkout, timeout)
        if code != 0:
            report["detail"] = "fetch from origin failed"
            return report

    code, head = _git(["rev-parse", "--short", "HEAD"], checkout, timeout)
    report["head"] = head.splitlines()[0] if code == 0 else ""

    code, counts = _git(
        ["rev-list", "--left-right", "--count", f"HEAD...{reference}"], checkout, timeout
    )
    if code != 0 or not counts:
        if not report["detail"]:
            report["detail"] = f"cannot compare with {reference}"
        return report

    parts = counts.split()
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        report["detail"] = f"unexpected rev-list output: {counts[:60]}"
        return report

    ahead, behind = int(parts[0]), int(parts[1])
    report["ahead"], report["behind"] = ahead, behind
    if behind and ahead:
        report["state"] = DIVERGED
    elif behind:
        report["state"] = BEHIND
    elif ahead:
        report["state"] = AHEAD
    else:
        report["state"] = CURRENT
    return report


def sibling_checkouts(path: str | Path) -> list[Path]:
    """The cron checkouts that sit beside ``path``, when they exist."""
    parent = Path(path).resolve().parent
    return [parent / name for name in SIBLING_NAMES if (parent / name).is_dir()]


def drift_report(
    paths: list[str | Path],
    *,
    reference: str = DEFAULT_REFERENCE,
    fetch: bool = True,
) -> list[dict[str, Any]]:
    """One drift report per checkout, in the order given."""
    return [checkout_drift(path, reference=reference, fetch=fetch) for path in paths]


def _needs_attention(report: dict[str, Any], threshold: int) -> bool:
    if report["state"] in {BEHIND, DIVERGED, UNKNOWN}:
        behind = report["behind"] or 0
        return report["state"] != BEHIND or behind > threshold
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m laclaugpt_data_analysis.deploy_drift",
        description=(
            "Report how far the deployed checkouts have drifted from their upstream. "
            "Default warning-only; --strict rejects unsafe checkout states. "
            "Use --strict --path PATH to gate the active service only."
        ),
    )
    parser.add_argument(
        "--path", action="append", default=[], help="a checkout to check (repeatable)"
    )
    parser.add_argument("--reference", default=DEFAULT_REFERENCE, help="the upstream ref to compare")
    parser.add_argument("--threshold", type=int, default=0, help="commits of lag to tolerate")
    parser.add_argument("--no-fetch", action="store_true", help="do not contact the remote")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--strict", action="store_true", help="require clean main checkouts matching freshly fetched origin/main")
    parser.add_argument("--quiet", action="store_true", help="print nothing when all are current")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.strict and (args.no_fetch or args.threshold or args.reference != DEFAULT_REFERENCE):
        print("strict mode requires freshly fetched origin/main and zero tolerance", file=sys.stderr)
        return 2
    if args.threshold < 0:
        print("error: --threshold must be zero or greater", file=sys.stderr)
        return 2

    paths = [Path(p) for p in args.path]
    if not paths:
        here = Path(__file__).resolve().parents[2]
        paths = [here, *(here.parent / name for name in SIBLING_NAMES)] if args.strict else [here, *sibling_checkouts(here)]

    reports = drift_report(paths, reference=args.reference, fetch=not args.no_fetch)
    flagged = [r for r in reports if _needs_attention(r, args.threshold)]

    if args.strict:
        flagged = []
        for path, report in zip(paths, reports, strict=True):
            code, changes = _git(["status", "--porcelain", "--untracked-files=normal"], path)
            if code or changes:
                report["detail"] = "could not verify clean working tree" if code else "working tree has local changes"
            if report["state"] != CURRENT or report["branch"] != "main" or report["detail"]:
                flagged.append(report)
                print(
                    f"deployment rejected: path={path} branch={report['branch']} "
                    f"expected_branch=main state={report['state']} "
                    f"detail={report['detail'] or 'checkout differs from origin/main'}; "
                    "remedy: inspect git status, fetch origin/main, and only "
                    "fast-forward when no cron job is active",
                    file=sys.stderr,
                )

    if args.json:
        print(
            json.dumps(
                {
                    "read_only": True,
                    "threshold": args.threshold,
                    "fetched": not args.no_fetch,
                    "checkouts": reports,
                    "needs_attention": [r["name"] for r in flagged],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 2 if args.strict and flagged else 0

    if args.quiet and not flagged:
        return 0

    for report in reports:
        if report["behind"] is None:
            print(
                f"  drift {report['name']:<32} {report['state']:<9} {report['detail']}".rstrip()
            )
        else:
            print(
                f"  drift {report['name']:<32} {report['state']:<9} "
                f"behind={report['behind']} ahead={report['ahead']} head={report['head']}"
            )
    for report in flagged:
        print(
            f"WARNING: {report['name']} is {report['state']} "
            f"({report['behind']} behind {report['reference']}) - merged fixes may not be in "
            f"effect until this checkout is refreshed (issue #353)",
            file=sys.stderr,
        )
    return 2 if args.strict and flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
