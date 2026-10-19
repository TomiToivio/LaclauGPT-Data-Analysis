# #341 — Acceptance record: the AI26 Step 0–9 pipeline

**What this record is.** A criterion-by-criterion check of issue #341 against merged artefacts, plus **live verification on Laskin** on 2026-10-19. It exists because the issue's own checkboxes are unticked whatever the real state, so closure has to be argued from files and measurements rather than from the issue text.

**What closure does and does not mean.** Closing #341 means the **contract layer and the production pipeline it describes are delivered and running on the target host**. It does not mean the locked Phase 1 paper changed, that steps 7/8 are validated science, or that every historical aspiration in this long issue was implemented literally. Each exception is named below rather than absorbed into a green checkmark.

## Live verification on Laskin

Measured at **`918b4be` = `origin/main`** on the deployed checkout. The SHA is pinned because `main` moved five times during this verification (`547147f → 918b4be`), every step of it a #341 fix from a concurrent session.

| Check | Result |
| --- | --- |
| Runtime revision | Analysis **`918b4be` == `origin/main`**, clean tree; Collection `132d03f` == `origin/main`; Visualization `cf7ec60` (**10 behind**, see below) |
| `ai26 stages` · `status` · `contract` · `validate-contract` · `render-prompt` | exit 0 each; `validate-contract` prints *"AI26 local registry/prompt contract: OK"* |
| `ai26 step 0..9 --dry-run` | **10/10 exit 0** |
| Preflight `run_ai26_laskin.sh --check` | `status: ok`; `gemma4:12b` present at `:11500`; `cloud_allowed: false` |
| Full test suite, clean worktree of `918b4be` | **exit 0** |
| Contract verifiers | Analysis 6 ok / Collection 7 ok / Visualization 7 ok |
| Bounded live cycle | see the closure comment — measured, not asserted |

`--check` is the proof that matters most for "runs on Laskin": it resolves the private config, reaches the model endpoint and confirms the model is present, which is precisely what a code-exists check cannot show.

## The eight "Done when" criteria

| # | Criterion | Where it is answered | Status |
| --- | --- | --- | --- |
| 1 | Explicit readable Step 0–9 mapping, phase ownership, machine/project profiles and stage dependencies published | `docs/AI26_STEP_BY_STEP.md` (mapping table, branch ownership, required order, operator gates); `stages/registry.json` (8 canonical + 2 Phase 2); `config/projects/ai26.yaml`, `config/machines/laskin.yaml`, `config/execution/laskin-cron.yaml` | met |
| 2 | Every stage individually runnable, documented, commented, tested, restart-safe, with readable and schema-validated prompts | `ai26 step N --dry-run` ×10; `scripts/ai26_run_next.sh` (dry-run default, `--apply` runs a bounded cycle through the **existing** flock); prompts resolved with ids and sha256 by `render-prompt`; `validate-contract` fails on registry/prompt drift; production stage modules implemented (`preprocess` 75, `frame` 127, `summary` 143, `laclau` 110, `postprocess` 270, `evidence` 109, `graph` 170 lines, none stubbed); restart safety from the worker's claim/lease model | met, with the scaffold exception below |
| 3 | Text-only flow executes 0/1/4/5/6/9; image and video conditional and documented | Registry marks `frame` as media-required and `video` as a stage with no module; those are the only media-gated steps, so a text-only record provably has no conditional step; live cycles complete text records with `not_applicable` semantics instead of failure | met |
| 4 | Sociotechnical imaginaries in Step 6, with source quotes/uncertainty and Phase 1 alignment documented | `stage_contract.py`: `sociotechnical_imaginaries`, `status="implemented"`, `runtime_stage="discourse"`, `output_fields=("imaginaries",)`, `prompt_keys=("discourse",)`; `stages/proposals.py` carries `sociotechnical_imaginary_candidates`, `desirable_futures`, `feared_futures`, `ownership_governance_assumptions`, `uncertainty`; `postprocess.py` maps them into `record.analysis.imaginaries` **only when enabled**; `rdf.py` exports `ns.SociotechnicalImaginary`; `docs/AI26_REFERENCE_CASE.md` pins *"one speculative future != stabilized sociotechnical imaginary"* | met |
| 5 | Steps 7/8 experimental Phase 2 isolated and nonblocking | Separate `phase_2_stages` list, never in `canonical_stages` (a registry test asserts the split); `analysis_phase` in `config/projects/ai26.yaml` gates the capability regardless of other flags | met |
| 6 | Collection/Visualization contracts verified end-to-end, cross-repo issues linked | Analysis 6 / Collection 7 / Visualization 7 contract checks pass on the host; the `source.extensions` namespace fix (#352) resolved a real producer/consumer break found on a stored 1.1.0 record; Collection's opt-in 1.2.0 adapter is documented and tested | met |
| 7 | Laskin staggered cron templates, locks, observability, rollback and bounded pilot validated; nothing activated by default | Crons stagger (collect `:10`, media `:30`, analysis `:05`); `flock` verified by real deferrals (*"already running; exiting cleanly"*, exit 3); `deploy_drift` warns hourly and never refuses; `docs/AI26_LASKIN_OPERATIONS.md` carries failure modes and recovery; #360's report ceiling bounds the stage that used to starve ticks; bounded cycles measured repeatedly | met (activation was the maintainer's, not a PR's) |
| 8 | Human review confirms methodological fidelity and source traceability | **This record.** The maintainer's instruction to close is the review checkpoint being spent | met by author sign-off |

## The one exception, stated plainly

**The seven human-readable step modules under `laclaugpt/step_*.py` are still stubs** (`NotImplementedError`), and this closure does not claim otherwise. They are **maintainer-owned scientific method files** — `laclaugpt/HUMAN_PIPELINE.md` and the repository's agent rules put them outside an agent's remit, and `docs/AI26_STEP_BY_STEP.md` already says so in *"The readable scaffold does not yet run"*.

What *is* delivered is the layer the issue asks for around them: a registry naming every logical step and its module, a CLI that inspects any step without executing it, contracts that fail when registry and prompts drift, prompts resolvable to exact text and hash, and a bounded execution path that reuses the single production lock instead of opening a second claim path. When those bodies are written by their owner they slot into the same registry and contracts; nothing in this closure has to be undone for them.

## What verifying actually found

Four findings. The last one is a real defect that only appeared because the pipeline was run rather than inspected.

1. **The deployed checkout was dirty, and it blocked the fast-forward.** Three operator scripts carried a local `100644 → 100755` mode change with **zero content change**. `git merge --ff-only` therefore refused (`error: Your local changes … would be overwritten`), leaving the host on `a76a9d1` while `main` was two commits ahead — the exact "repository correct, runtime older" class this issue exists to end. Resolved by restoring the three files (content-identical, so nothing operator-authored was discarded) and fast-forwarding; **#370 upstream had already fixed the cause**, by committing those scripts executable after the documented commands failed with `Permission denied`. The lesson generalises: a mode-only diff is still a dirty tree, and the release gate's "if the working tree is dirty, stop and investigate" is what would have caught it sooner.
2. **`main` was red at `547147f`** — two `step 3` dry-run tests still asserted `stages == []`, written before #366 made a module-less step *inspectable* rather than unknown. A concurrent session fixed it as **#369** while I was measuring, so the fix is theirs and not mine; verified green at `918b4be`.
3. **A live misclassification in the JSON-failure diagnostics (#343 lineage).** The first record the bounded cycle touched produced this line:

```
structured parse failed (validation attempt 1): Unterminated string starting at: line 3 column 21 (char 49)
structured JSON decode failed: shape=other_invalid_json pos=49 brace_balance=1 bracket_balance=0 chars=193
```

`brace_balance=1` with an unterminated string is a **truncated response**, and the actionable label is `possibly_truncated` — it tells an operator to look at the token budget rather than at the model's grammar. It was labelled `other_invalid_json` because the classifier's truncation test used `exc.pos >= len(text) - 2`, and Python reports the position where an unterminated string **started** (char 49 of 193), never where the output stopped. The same heuristic mislabelled the opposite case: `{"summary": 1, "claims": }` ends in a closing brace two characters from the error and is *malformed*, not truncated, yet it was called `possibly_truncated`.

Fixed here: the classifier now asks what the response **ends with** (`ends_open`) and whether it is **unbalanced** (the brace/bracket counts added in #359 — previously computed and reported but never used for the decision), plus the hard `Unterminated string` signal. Two regression tests pin both directions, including the real 193-character shape above. Full suite on the fixed tree: **exit 0**.
4. **No other defect in the CLI or the pipeline.** Every subcommand and all ten dry-run steps exit 0 on the deployed revision, and the suite is green there.

## Two deliberate design choices worth recording

1. **No `retry-errors` verb, and no claiming verbs in the CLI.** The issue's CLI sketch lists `retry-errors`; it is absent on purpose. Claiming, locking, retrying and the cycle ceiling belong to the one wrapper that owns the flock — a second path is how two workers end up on one record. `run-next --apply` delegates to that wrapper rather than reimplementing it.
2. **The CLI is read-only.** `step` requires `--dry-run`; `validate-contract` states explicitly that remote Collection/Visualization and the live runtime are *not* checked. A tool that reports "OK" about something it did not check is worse than no tool.

## Carried forward, not buried

- **The `laclaugpt/step_*.py` bodies** — maintainer-owned, as above.
- **Visualization is 10 commits behind `origin/main`** on this host. Its contract checks pass, but merged fixes there may not be in effect; refreshing it is safe (no writer) and remains an operator step.
- **Scientific review of interpretations** — the pipeline produces proposals, never findings; using them in a manuscript is a research judgement, not a build artefact.

— recorded by Ai (愛), 2026-10-19
