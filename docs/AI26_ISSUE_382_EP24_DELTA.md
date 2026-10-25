# Issue #382: EP24 late-fix → AI26 Laskin disposition

Audit baseline: AI26 `main` at merge commit `f1106ccb5805cd6e2e7717624108e86d1f1145ce`; EP24 `main` at `c3ffc569dea1b2c008000075f23bbea46ef8dfc8` (2026-10-25). Follow up on [earlier upstream audit](AI26_UPSTREAM_PORT_AUDIT.md), not a replacement.

A disposition of **already covered** means the named AI26 path implements the analogous contract; it does **not** claim Laskin production acceptance. **Needs investigation** and **EP24-specific** are tracked explicitly, not represented as migrated code.

| EP24 upstream | Failure class | AI26 candidate / disposition | Required follow-up |
| --- | --- | --- | --- |
| [#305](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/305) | HEPP24 dated ID regex | **EP24-specific** HEPP24 identity syntax does not belong in AI26 | Verify canonical AI26 `source_url` validator and handoff identity for new source families |
| [#304](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/304) | Invalid media rows must not masquerade as processed | **Needs investigation**: `canonical.py` enforces nonempty `source_url`; `task_queue.py` validates required task fields, but `seed_ready_tasks` can abort an entire page on one malformed handoff | Failure-injection test with invalid middle handoff, decide durable quarantine instead of data loss |
| [#303](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/303) | Recover missing IDs/URLs from verified composite source | **EP24-specific** HEPP24 Mongo key recovery; AI26 has canonical source URL and handoff key | Check Collection→Analysis contract for recoverable legitimate source IDs; never synthesize keys |
| [#302](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/302) | Eligibility subset complete vs upstream empty | **Already covered in part**: `_run_bounded_cycle` records `idle`, `seeded`, `completed`, `duplicate`; `_cycle_exit_code` errors if seeded with no completions | Verify telemetry/collection emptiness in live Laskin traces |
| [#301](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/301) | Mutable prompt/codebook context corrupts following records | **Ported** in [AI26 PR #383](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/pull/383): deep-copy per-task `PipelineContext`; regression `tests/test_issue_382_context_isolation.py` | Verify merged revision on Laskin |
| [#300](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/300) | Failed-row diagnostics, cache invalidation | **Partly covered**: `AI26TaskWorker.run_once` stores failure class and terminal failures; `_failure_diagnostics` includes structured model evidence; immutable revision check in `WorkerBinding.validate_runtime_code` | Verify per-record diagnostic persistence and no stale media cache in runtime |
| [#299](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/299) | Media filename recovery and per-row staging | **Mostly EP24-specific**; AI26 `AI26Handler` uses `MediaStager` and fails retriably rather than accepting degraded media silently | Test mixed valid/missing object references and source identity |
| [#298](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/298) | Nullable `video_status` guard | **EP24-specific** field; broader nullable-analysis status requires case-specific validation | Check `CanonicalRecord` optional status schema during malformed LLM response regression |
| [#297](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/297) | Interrupted cached MP4 incorrectly reused | **Needs investigation**: AI26 also has media staging/cache but uses a distinct implementation | Test interrupted object transfer and rejection of partial cached media |
| [Step 4 truncation](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/commit/812aedfee4d1173452c88aed9fe763cbebeb8f77) | Incomplete LLM response may look cacheable | **Already covered in part** by `LLMTruncationError` and `AI26TaskWorker` retry/terminal policy | Exercise missing `finish_reason`, truncated JSON, retry ceiling and persistence |

## Verification still required before closing #382

- [ ] Run `python -m pytest -q` and any repository lint/contract checks against a clean full checkout; record revision and failures.
- [ ] Validate source-identity quarantine, nullable statuses, interrupted cache/media, malformed model output, and partial-batch failure using focused regression tests.
- [ ] Run `scripts/run_ai26_laskin.sh --check`, `python -m laclaugpt_data_analysis.preflight`, and `python -m laclaugpt_data_analysis.deploy_drift --json` in the **actual Laskin venv**; record deployed SHA and environment.
- [ ] Execute one bounded production AI26 cycle without killing/interrupting existing work; verify Mongo and Redis durable state and provenance, downstream output, cron locks and telemetry.
- [ ] Review any unresolved upstream commits since the baseline SHA and update this matrix.
- [ ] Merge only verified code, check post-deploy health, and close #382 only when all acceptance criteria are evidenced.

The upstream EP24 media/Roihu implementation is **not** a wholesale dependency of AI26 Laskin. The aim is equivalent failure protection while keeping Phase 1 methods and codebooks frozen.
