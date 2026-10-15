# Bounded AI26 run-next delegation (#341)

Use `bash scripts/ai26_run_next.sh --limit 3` to **preview** a bounded
cycle. The default is dry-run and does not require a private environment,
claim any task, contact a model, or touch storage.

After reviewing the runtime configuration and ensuring the host is Laskin,
`bash scripts/ai26_run_next.sh --limit 3 --apply` delegates to the existing
`scripts/run_ai26_laskin.sh --once` path with
`LACLAUGPT_MAX_TASKS=3`. That wrapper remains the **sole owner** of
preflight, frozen manifest checks, the `flock` lease, bounded worker
execution, watchdog timeout, periodic report, and exit statuses. This
command does not run a named scientific stage in isolation; that remains an
unimplemented part of #341.

Only limits 1–100 are accepted. If another cycle holds the lock, the wrapper
returns its existing busy exit status (3); this command does not bypass it.
Do not run `--apply` from CI or a workstation without authorized private
runtime configuration. No cron is installed or changed by this addition.

`python -m pytest -q tests/test_issue_341_bounded_run_next.py` checks
the offline dry-run and fail-closed argument paths. Operator acceptance
still requires a bounded Laskin pilot, human review, and explicit deployment
sign-off. Phase 1 scientific methods and prompts are unchanged.
