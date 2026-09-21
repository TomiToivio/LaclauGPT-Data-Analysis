# Phase branch workflow

This repository uses persistent `phase-0` through `phase-4` branches.

As of 2026-09-20, **Phase 1 is active**, so `main` and `phase-1` must represent the same current stable baseline. The `phase-0` branch remains the preserved Phase 0 baseline and must not be repurposed as Phase 1. Later-phase branches may advance independently.

## Rules

1. Determine an issue's phase from its title/body, labels, milestone, linked roadmap, or explicit instruction.
2. Start work from the matching `phase-N` branch.
3. Prefer an issue branch from that phase branch and PR back to the same `phase-N`.
4. Do not target `main` with Phase-2/3/4 work while Phase 1 is active.
5. Current Phase-1 work lands in `phase-1`, is validated there, then `main` is synchronized.
6. Phase-0 maintenance stays on `phase-0`; it does not move `main` backward or redefine Phase 0 as Phase 1.
7. Unphased issues default to the active phase, currently Phase 1.
8. For cross-repository work, use the same phase branch in every affected LaclauGPT repo unless explicitly documented otherwise.
9. Backport minimal fixes between phases when required; never merge an entire later phase into the current stable phase just to obtain one fix.

`main` means the current active phase, not the globally newest code.

Current invariant:

```text
main == phase-1 current stable baseline
phase-0 = preserved Phase 0 baseline
phase-2..phase-4 = isolated future work
```

When the project advances to a later phase, promotion into `main` requires explicit human approval.

## Drift guard

`main` and `phase-1` may have different commit ancestry (for example, a merge commit that preserves
phase-specific history), but their checked-out trees must be identical while Phase 1 is active.

A scheduled/manual GitHub Actions check in `.github/workflows/phase-branch-drift.yml` fetches both refs
and fails if `git diff origin/main origin/phase-1` is non-empty. Any change merged to one active ref
must therefore be synchronized to the other immediately.

`phase-0` is intentionally different: it is the preserved Phase 0 baseline, is an ancestor of current
`main`, and is not expected to track Phase 1 runtime fixes. Its divergence is isolation, not drift.
Phase 0 maintenance must continue to target `phase-0` explicitly.

Repository: `TomiToivio/LaclauGPT-Data-Analysis`.

Agents must read `AGENTS.md` and this file before issue-driven changes. Working on the wrong phase branch is an incorrect implementation.
