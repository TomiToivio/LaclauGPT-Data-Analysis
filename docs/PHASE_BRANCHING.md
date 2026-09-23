# Phase branch workflow

This repository keeps persistent `phase-0` through `phase-4` branches.

As of 2026-09-21, **Phase 1 is active**. Phase 1 development goes directly to `main`. The `phase-1` branch is a passive compatibility/mirror ref and must match the validated `main` tree; it is not a development or pull-request target. The `phase-0` branch remains the preserved Phase 0 baseline. Later-phase branches may advance independently.

## Rules

1. Determine an issue's phase from its title/body, labels, milestone, linked roadmap, or explicit instruction.
2. For Phase 1, start from `main`; use a short-lived issue branch from `main` when needed and target the PR back to `main`.
3. Do not start Phase 1 work from `phase-1` and do not target Phase 1 PRs at `phase-1`.
4. Keep `phase-1` synchronized as a passive mirror of the validated `main` tree.
5. Do not target `main` with Phase 2/3/4 work while Phase 1 is active; use the matching `phase-N` branch instead.
6. Phase 0 maintenance stays on `phase-0`; it does not move `main` backward or redefine Phase 0 as Phase 1.
7. Unphased issues default to the active phase, currently Phase 1 on `main`.
8. For cross-repository Phase 1 work, use `main` in every affected LaclauGPT repository unless explicitly documented otherwise.
9. Backport minimal fixes between phases when required; never merge an entire later phase into the current stable phase just to obtain one fix.

`main` means the current active Phase 1 line.

Current invariant:

```text
main = Phase 1 active development/stable branch
phase-1 = passive mirror of main
phase-0 = preserved Phase 0 baseline
phase-2..phase-4 = isolated future work
```


## Passive mirror maintenance

The `Phase branch drift guard` workflow fast-forwards `phase-1` from the latest fetched `main` on each `main` push, on its nightly schedule, and when manually dispatched. It then verifies that both refs point to the same commit and tree. A direct push to `phase-1` runs the verification without copying that branch back to `main`. Synchronization uses a normal fast-forward push, never a force push: if `phase-1` contains divergent commits, the workflow fails and requires maintainer review. Do not develop on the mirror.

If the workflow cannot push because of branch protection or Actions permissions, grant the repository's GitHub Actions identity the narrow permission needed to update this passive branch, or use a separately approved branch-sync mechanism. Do not disable the drift check to hide a failed sync. The scheduled run also repairs missed updates, but alignment should be checked on the actual workflow run before marking a regression resolved.

When the project advances to a later phase, promotion into `main` requires explicit human approval.

Repository: `TomiToivio/LaclauGPT-Data-Analysis`.

Agents must read `AGENTS.md` and this file before issue-driven changes. Working on the wrong phase branch is an incorrect implementation.
