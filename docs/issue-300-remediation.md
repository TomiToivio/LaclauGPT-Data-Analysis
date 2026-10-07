# Issue #300: exhausted structured-output budget

When both structured attempts stop for length (normally 4096 then 8192 output
tokens), the AI26 worker records one terminal failure with
`terminal_reason=unanalysable_within_budget`, dead-letters and acknowledges the
task. Future seeding skips the terminal idempotency key. Ordinary validation
errors retain their bounded retry policy.

## Superseded-budget auto-retry (issue #321)

A ceiling that has since been raised must not keep pinning the documents it killed.
The seeder therefore re-arms a terminal failure **once, automatically**, when the
running ceiling is strictly greater than the `output_budget_tokens` recorded on the
failure. The behaviour is implemented by
`DurableTaskStore.rearm_terminal_failure_if_budget_increased`, called from both the
seed path and the claim path of `distributed_worker.py`, and driven by
`structured_output_ceiling()`.

What the guard rails are:

- **only** `terminal_reason == "unanalysable_within_budget"` qualifies — a document
  that died of a schema error, a provider fault or any other cause is never re-driven;
- only when `output_budget_tokens < current_ceiling` — an *unchanged* ceiling is not
  enough, and a rollback to a smaller ceiling re-arms nothing;
- a failure with **no** recorded `output_budget_tokens` is never re-armed (an absent
  budget must not read as `0`, or every legacy failure would qualify);
- the re-arm sets `rearmed_at`, so each individual failure event is re-armed once. A
  document that fails again at the new ceiling writes a **new** terminal event carrying
  the **new** budget, which is then not itself superseded — so this cannot loop at a
  stable ceiling;
- the store adapter is looked up defensively, so a durable store that predates this
  capability simply keeps the old strict-skip behaviour.

The manual `--rearm-failed <idempotency-key>` escape hatch remains for the cases this
does not cover, and still works when the failure reason is not a budget exhaustion.

Measured against the live Laskin store on 2026-10-07 (`ai26-distributed-001`, ceiling
16384): of 223 unrearmed terminal documents, **173 are eligible** — 168 recorded at
8192 and 5 at 4096 — and 50 are correctly skipped (7 already at 16384, 43 with no
recorded budget or another terminal reason). This matches the issue's own analysis.

The failure record includes `output_budget_tokens`,
`required_output_tokens_lower_bound`, `generated_output_chars`, and
`finish_reason`. The lower bound is **8193** tokens for a length stop at 8192;
the exact required length cannot be inferred from an incomplete generation.
Do not treat output character count as a token count or raise the ceiling without
a controlled measurement. The existing bounded response diagnostic is for
private operational inspection, not publication.

**A decode-path anomaly remains an open measurement, not a settled mechanism**
(issue #321). Across the 168 documents that died at the 8192 ceiling the recorded
`generated_output_chars` averages **0.479 characters per spent token**, against
**3.10** measured on a healthy call to the same model — and one document emitted
**4 characters** from an 8192-token budget. That is far too little content to have
exhausted the budget honestly, so a mass re-drive may spend the budget for the same
outcome. The re-arm is safe (bounded, one-shot, provenance-preserving) but the
*recovery rate* should be measured on a bounded sample before any conclusion is drawn
about how much of the backlog is genuinely recoverable.

To retry after changing the prompt, configuration or model, re-freeze the run as
required by the immutable manifest; the automatic path handles a ceiling increase, and
`--rearm-failed <idempotency-key>` remains available for everything else. Check events,
distinct affected keys, and terminal reasons separately; older failure events are
historical and are not deleted.

Regression: `tests/test_issue_300_terminal_truncation.py` uses a synthetic
always-length-stopped provider and checks single terminal event, dead-letter,
no reseeding, explicit rearm, and the distinct schema-error retry path.
`tests/test_issue_321_terminal_ceiling_rearm.py` covers the superseded-budget re-arm.

Verification commands: `python tools/verify_contracts.py` and `pytest`.
