# Issue #300: exhausted structured-output budget

When both structured attempts stop for length (normally 4096 then 8192 output
tokens), the AI26 worker records one terminal failure with
`terminal_reason=unanalysable_within_budget`, dead-letters and acknowledges the
task. Future seeding skips the terminal idempotency key. Ordinary validation
errors retain their bounded retry policy.

The failure record includes `output_budget_tokens`,
`required_output_tokens_lower_bound`, `generated_output_chars`, and
`finish_reason`. The lower bound is **8193** tokens for a length stop at 8192;
the exact required length cannot be inferred from an incomplete generation.
Do not treat output character count as a token count or raise the ceiling without
a controlled measurement. The existing bounded response diagnostic is for
private operational inspection, not publication.

To retry after changing the prompt, configuration or model, re-freeze the run as
required by the immutable manifest and deliberately invoke the worker's existing
`--rearm-failed <idempotency-key>` mechanism. Do not automatically rearm on
an hourly cycle. Check events, distinct affected keys, and terminal reasons
separately; older failure events are historical and are not deleted.

Regression: `tests/test_issue_300_terminal_truncation.py` uses a synthetic
always-length-stopped provider and checks single terminal event, dead-letter,
no reseeding, explicit rearm, and the distinct schema-error retry path.

Verification commands: `python tools/verify_contracts.py` and `pytest`.
These are not claimed to have been executed on Laskin by this change.
