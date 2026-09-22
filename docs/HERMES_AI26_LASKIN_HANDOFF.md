# Hermes handoff: AI26 Phase 1 Analysis on Laskin

This is the host-execution handoff for issue #294. The repository-side Phase 1 AI26 Laskin runtime is already implemented. Hermes should bring up, verify and operate that runtime on Laskin rather than create a parallel engine.

## Entrance gate

Collection issue `TomiToivio/LaclauGPT-Data-Collection#169` passed its Step 1 gate on 2026-09-22. Its sanitized completion evidence reports canonical schema `1.1.0`, handoff contract `1.0` / `ai26-phase1-handoff-v1`, a shared `ai26` namespace, and fresh records visible to Analysis through the Analysis-side ready-handoff query.

Issue #294 still requires a fresh Analysis execution against the current Laskin/private runtime. Do not substitute the older #274 live proof for this run.

## Already prepared in Git

- `scripts/run_ai26_laskin.sh`: bounded, locked, incremental worker entry point with preflight support.
- `scripts/install_ai26_laskin_cron.sh`: refreshes the frozen run, verifies a cron-equivalent cycle, installs a single tagged hourly entry, then runs preflight.
- `docs/AI26_LASKIN_ANALYSIS.md`: canonical operator guide.
- Canonical Collection ingestion, retry/dead-letter behavior, Mongo durability, Redis coordination, multimodal staging and provenance.
- AI26 runtime policy reads the configured study date boundary rather than hard-coding it.
- Mongo-backed idempotent 24h reports and direct Analysis -> Visualization handoff.
- `src/laclaugpt_data_analysis/phase1_handoff.py` provides the public-safe Visualization projection.

Do not introduce a second AI26-only analysis engine or browser logic.

## Hermes mission on Laskin

1. Read `AGENTS.md`, `HERMES.md`, `skills/laclaugpt-data-analysis/SKILL.md`, `docs/AI26_REFERENCE_CASE.md`, `docs/AI26_LASKIN_ANALYSIS.md`, `docs/AI26_DISTRIBUTED_WORKER.md`, `docs/DISTRIBUTED_PROJECT_STORAGE.md`, `docs/DEPLOYMENT_AND_HERMES.md`, `docs/PROMPT_LIBRARY.md`, issue #294, and the current AI26 project/machine/execution configs before changing anything.
2. Verify the public checkout and authorized private root. Do not discard unrelated local work and do not copy private overlays into Git.
3. Confirm Collection issue #169 remains closed with `STEP 1 PASS` and that at least one fresh canonical `ai26` record is still eligible for Analysis without manual reshaping.
4. Update/install the current repository and required extras according to the runbook.
5. Run the documented repository quality gates before live work:

```bash
python tools/verify_contracts.py
ruff check .
pytest
```

Run any additional mypy/public-tree/privacy gates required by `AGENTS.md` and the current repository configuration.

6. Run the exact unattended preflight:

```bash
./scripts/run_ai26_laskin.sh --check
```

The check must claim no work and must not print credentials.

7. Confirm the configured model endpoint/model are available according to the machine profile. Record the effective backend/model in sanitized evidence. Do not silently switch to cloud routing unless the authorized runtime configuration explicitly enables it.
8. Execute one bounded production-like cycle with the canonical wrapper:

```bash
./scripts/run_ai26_laskin.sh --once
```

Use `--debug --once` only when diagnostics are needed. Do not replace the wrapper with an ad-hoc runner.

9. For a bounded sample of newly claimed records, verify:
   - canonical identity remains `source_url`;
   - source evidence survives unchanged;
   - project/study namespace remains `ai26`;
   - prompt ID/version/hash and rendered-prompt hash are recorded as designed;
   - model/backend/options, config/codebook/schema fingerprints and run provenance are present;
   - non-trivial interpretations retain evidence references;
   - uncertainty and abstention remain possible;
   - unsupported categories may remain empty;
   - failed records become explicit failures rather than partial successes;
   - durable results remain resumable.

10. Verify the active Phase 1 stage order follows the documented canonical path:

```text
preprocess
-> optional frame/media analysis when enabled and real media evidence exists
-> summary / relational representation as configured
-> Laclaudian discourse analysis
-> postprocess
-> durable result
```

Do not treat a media filename/reference as visual evidence unless the media was actually materialized and validated.

11. Audit the bounded run for parse/schema failures, missing evidence, forced classifications, missing abstention, stale-cache reuse after relevant fingerprint changes, duplicate processing, lost provenance, wrong project namespace, broken media/object staging, model endpoint failure, silent cloud fallback, stuck claims, and malformed Visualization envelopes.

12. Re-run the same bounded cycle or documented resume path and verify idempotency, retry policy, stale-result invalidation, restart coherence, stable `source_url` identity, and absence of duplicate logical results.

13. Run or verify the idempotent 24h report path. Confirm it uses only completed canonical results, remains provenance-rich and bounded, keeps model interpretation provisional, writes only to the authorized private runtime location, and is idempotent for the same window where designed.

14. Verify logs/status are operational and free of secrets.

## Cross-repo exit check

Use a freshly analyzed canonical Collection record from the shared `ai26` namespace. Analysis must preserve stable `source_url`, study/collection identity, source evidence, analysis provenance, uncertainty/abstention, failure distinction and default human-review state, then expose the result through the canonical Visualization handoff (`laclaugpt-analysis-visualization-v1`) without a bespoke export transform.

Verify the Visualization deployment can consume the new result unchanged. Do not modify Visualization semantics from this repository.

## Research-integrity checks

Keep source evidence, descriptive pre-analysis, model-generated candidates and researcher-authored categories distinguishable. Do not promote candidate formations/signifiers/relations into researcher truth. Preserve uncertainty/abstention and review state. Do not move Phase 2 DNA/SNA/Luhmann/Castells extensions into the mandatory Phase 1 path.

## Defects

For every concrete reproducible defect found during the live run:

1. search open and recently closed issues for the same defect;
2. update the existing issue if one already covers it;
3. otherwise create a narrowly scoped issue in the owning repository;
4. add a synthetic regression test for generic public-code defects when applicable.

Collection defects belong in Collection. Visualization/render/review defects belong in Visualization. Do not add cross-module workaround semantics here.

## Stop conditions

Stop the Step 2 handoff and document a blocker if canonical input semantics are corrupted, evidence/provenance is lost, model output is stored as validated human interpretation, the project namespace is wrong, cloud fallback occurs silently, durable writes are unreliable, resume/idempotency creates duplicates or corruption, Visualization cannot consume the canonical output, a `TOMI-LOCKED` invariant would need bypassing, or credentials/config would need to be invented.

## Completion evidence for issue #294

Post only sanitized evidence:

- execution date/time;
- Analysis Git SHA;
- Collection #169 status/link;
- effective project/schema/result-envelope versions;
- quality-gate and preflight status;
- public-safe model/backend identifier;
- tasks claimed/succeeded/failed/skipped;
- stage-level success/failure totals;
- evidence/provenance/uncertainty and abstention checks;
- resume/idempotency result;
- periodic-report result if applicable;
- MongoDB/Redis/S3 capability status without endpoints/credentials;
- Visualization handoff result;
- links to every new or updated defect issue;
- explicit **STEP 2 PASS** or **STEP 2 BLOCKED**.

Do not post prompts/codebooks from private overlays, research rows, endpoints, tokens or credentials. Do not claim overall Phase 1 readiness from this issue.
