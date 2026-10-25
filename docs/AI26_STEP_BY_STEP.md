# AI26 Step 0–9 mapping and Laskin integration gate

Status: **design/integration audit**, not a new production orchestrator. Tracks [#341](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/issues/341). Date: 2026-10-15.

## Branch and method ownership

`main` is the active development branch; research phases do not select branches and no `phase-N` synchronization is required. The locked Paper 1 (research Phase 1) AI26 theory, sampling and method in `LaclauGPT/paper/PHASE_1_PAPER.md` is not edited. Network inference (DNA/SNA) remains an opt-in experimental module. Do not modify Tomi-owned `laclaugpt/step_*.py` scientific method files: see `laclaugpt/HUMAN_PIPELINE.md`. This mapping is a **presentation/contract layer** over existing code, not an alternative pipeline.

## Audited components

- Existing production: `src/laclaugpt_data_analysis/distributed_worker.py`, `src/laclaugpt_data_analysis/stages/`, `src/laclaugpt_data_analysis/stage_contract.py`, `scripts/run_ai26_laskin.sh`, `scripts/run_ai26_laskin_analysis.sh`, public `config/projects/ai26.yaml`, `config/machines/laskin.yaml`, `config/execution/laskin-cron.yaml`.
- Existing readable scaffold: `laclaugpt/pipeline_runner.py` and `laclaugpt/step_01_preprocess.py` through `step_07_sna.py`. Some step implementations intentionally raise `NotImplementedError`; **do not advertise as production-ready**.
- Existing Collection handoff: canonical records in MongoDB, `handoff.status=ready`, stable `handoff_key` including source revision; Redis `laclaugpt:ai26:stream:analysis-ready` contains references, not payloads.
- Existing Visualization: `configs/projects/ai26.yaml`, provenance projection, RDF/DNA/SNA adapters. Dashboard flags for DNA/SNA/RDF are disabled in the default AI26 profile.

## Logical AI26 stages (do not confuse with current internal stage names)

| AI26 logical step | Existing implementation/scaffold | Input → output | Scientific ownership |
|---|---|---|---|
| 0 handoff/preflight | Collection handoff + distributed worker seed-ready | `source_url`, `handoff_key`, `revision`, `status`, `raw_capture` → eligible immutable source reference | infrastructure |
| 1 preprocess | `stages/preprocess.py`, `laclaugpt/step_01_preprocess.py` | original content, language, provenance → normalized text/evidence refs | descriptive |
| 2 optional image/frame | `stages/frame.py`, `laclaugpt/step_02_frame.py` | verified frame/image reference → frame evidence or explicit not-applicable | descriptive |
| 3 optional video | media staging/whole-video capability **requires verification** | verified video reference → video evidence or explicit not-applicable | descriptive |
| 4 summary | `stages/summary.py`, `laclaugpt/step_03_summary.py` | text and available media evidence → bounded summary | descriptive; mandatory |
| 5 postprocess | `stages/postprocess.py`, `laclaugpt/step_04_postprocess.py` | summary/evidence → structured descriptive fields | descriptive; mandatory |
| 6 Laclau/Palonen/imaginaries | `stages/laclau.py`, `laclaugpt/step_05_laclau.py`, project config | exact source evidence → claims, signifiers, formations, evidence-backed imaginaries and uncertainty | locked Paper 1 semantics; mandatory |
| 7 DNA | DNA statement coding and `laclaugpt/step_06_dna.py` | reviewable statements → provisional relations | **experimental module** |
| 8 SNA | network projection and `laclaugpt/step_07_sna.py` | provenance-linked edges → graph metrics | **experimental module** |
| 9 export | RDF/graph adapters, canonical Mongo record | `analysis`, `intermediate`, `provenance`, `review` → idempotent Visualization projection | infrastructure |

Required logical order: `0 → 1 → [2/3 if actual media] → 4 → 5 → 6 → 9`. Never treat absent media as a failure; never block Stage 9 on experimental 7/8. Existing source `source_url`, exact quotations, timestamps, provenance, human annotations and revisions are not overwritten by hypothetical model findings.

**Important:** this is a target numbering crosswalk, not a claim that the current production queue exposes ten independently callable entrypoints. #341 remains open until each step is runnable and tested, without creating another competing pipeline.

## Cross-repository contract findings

All three repositories' inspected `schemas/research-record.schema.json` have the same required top-level properties: `schema_version`, `source_url`, `raw_capture`, `source`, `content`, `intermediate`, `analysis`, `human_readable`, `provenance`, `review`, `legacy`. However, on 2026-10-15 **Analysis schema_version.const is 1.2.0; Collection and Visualization are 1.1.0**. Their strict JSON Schema validators therefore cannot all validate a single version unchanged. See [Collection #271](https://github.com/TomiToivio/LaclauGPT-Data-Collection/issues/271) and [Visualization #182](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/issues/182). This demonstrates a version contract mismatch, **not** a tested failure of the live Mongo/dashboard path. Do not silently change any version constant to conceal it.

Collection's stable handoff key is `hash(collection_id + source_url + revision)`; use it for idempotency. Mongo routing must be verified from actual private runtime before claiming that the dashboard consumes the same collection. Visualization's `docs/PROVENANCE_CONTRACT.md` specifies upstream safe run/config/prompt/model/codebook revisions and unknown fallbacks. Never conflate absent provenance with a scientifically inferred field.

## Laskin operator gates (nothing activated by this change)

1. Install current package in a private Laskin checkout as documented in `docs/AI26_LASKIN_ANALYSIS.md`. Use the existing `scripts/run_ai26_laskin.sh`; **do not deploy the human-readable scaffold as a competing worker**.
2. Run `python tools/check_ai26_contracts.py --collection ../LaclauGPT-Data-Collection --visualization ../LaclauGPT-Data-Visualization` on adjacent checked-out repos. It exits **1** on the current 1.2.0/1.1.0 mismatch and names the repository that must accept the emitted version (Data Collection still declares 1.1.0); Visualization's `enum` accepts both. Exit **2** means a schema could not be read, and the message names the file (issue #382).
3. Use `scripts/run_ai26_laskin.sh --check` after provisioning Laskin private config, Ollama and dependencies. This is not proof of runtime correctness unless exit codes and logs are checked.
4. Run bounded small-sample manual pilot, retain source IDs and stage statuses, review output against source evidence, and check Collection input/Visualization display with the same real Mongo DB and collection settings.
5. Only after schema resolution, integration tests, representative human review and sign-off, enable staggered cron using the documented installer. No cron activation or production store migration is part of this PR.

## Remaining acceptance work

- Confirm whole-video stage 3 evidence semantics, step-by-step entrypoints, stage registry, effective prompt render/validation, prompt/schema hash, explicit not-applicable status and retries.
- Add fixture-driven cross-repo producer/consumer tests for multimodal, text-only, multilingual and missing provenance. Confirm stable Mongo collection names and identity across private runtime settings.
- Demonstrate restart-safe/idempotent bounded pilot on Laskin and actual Visualization consumption. Preserve EP24/Roihu references.

## Live verification of the running path (2026-10-15)

The section above is read from code and public schemas. This is the counterpart it
asks for -- the Mongo routing verified **from the actual private runtime on Laskin**,
measured rather than restated. It does not alter the version-mismatch finding.

### The path, measured

| Point | Measured |
| --- | --- |
| cron | root crontab, hourly and staggered: collect `:10`, media `:30`, analysis `:05` |
| analysis entry | `scripts/run_ai26_laskin.sh`, bounded in *claims* with a wall-clock ceiling |
| preflight | `--check` returns `status: ok`; Ollama `:11500` serves `gemma4:12b`; MongoDB, Redis and the S3 object store reachable |
| worker health | recent cycles end `worker_status=0 report_status=0 status=0` |
| queue | Redis `laclaugpt:ai26:stream:analysis:ai26-distributed-001:tasks`, 4,900 entries, two consumer groups |

Collections, measured in the project database (`<project>__<kind>` convention):

| Collection | Documents | Note |
| --- | --- | --- |
| `ai26__records` | 1,511 | incoming canonical records, `collection_id: ai26` for all |
| `ai26__analysis_results` | 2,120 | outgoing results; Visualization reads these |
| `ai26__analysis_failures` | 1,190 | historical plus live; split by window below |
| `ai26__periodic_summaries` | 44,756 | |
| `ai26__processing` | 8 | in-flight state |
| `ai26__analyzed` | 21 | legacy; Visualization must not consult it |
| `ai26__relations`, `ai26__annotations` | absent | consistent, not a defect -- see below |

The incoming handoff block carries exactly `arena`, `collection_id`,
`contract_version`, `handoff_key`, `project_id`, `published_at`, `reason`,
`revision`, `run_id`, `source_priority`, `source_url`, `status`. Outgoing results
carry the 13-key envelope Visualization unwraps, with a provenance block naming the
codebook/config sha256, the model, the capability gate and the Paper 1 revisions.

### Absent namespaces are consistent with policy, not a defect

`ai26__relations` and `ai26__annotations` are absent, and both absences are
*correct*: the relations namespace belongs to the experimental network modules,
which the capability gate disables, and Visualization mirrors that gate in its own
project config (`sna: false`, `dna_statement_coding.enabled: false`, `critical_ai`,
`rdf`). Reporting these as missing data would be a false alarm; the accurate
statement is that nothing is expected to write them under the default profile.

### Contract tests, run on both sides

- Analysis: `test_analysis_contracts.py`, `test_ai26_laskin_config.py`,
  `test_ai26_cycle_outcome.py`, `test_ai26_multimethod.py` -- **40 tests pass** (exit 0).
- Visualization: `test_issue144_analysis_results_handoff.py`,
  `test_issue150_unwrap_analysis_envelope.py`, `test_distributed_namespace.py`,
  `test_ai26_project_config.py`, `test_issue34_ai26_dashboard.py` -- **35 passed**.
- Visualization service: active (user scope) and answering **HTTP 200** on its bound
  address -- measured with a request, not read off a port list.

### Live failure classes, and which issues already track them

Failures were split by window so that a stale count cannot be read as a live one:

| Class | 24 h | 7 d | 30 d | Status |
| --- | --- | --- | --- | --- |
| `ValidationError` | 16 | 146 | 409 | tracked: Analysis #342 |
| `JSONDecodeError` | 14 | 125 | 361 | tracked: Analysis #343 |
| `LLMTruncationError` | 0 | 80 | 284 | documented retry behaviour of a thinking model |
| `ProviderError` / `ConnectionError` | 2 | 22 | 26 | retried; no issue yet |
| `ValueError: manifest mismatch` | 0 | 0 | 110 | **historical** (2026-09-21...30), superseded by #121/#277 |

Two conclusions: the record-schema disagreement is so far a **strict-version
contract** problem (#271, Visualization #182) and not an observed failure of the
live path; and the manifest-mismatch class must not be re-filed, because every one
of those failures predates the fixes.

### The readable scaffold does not yet run

The seven step modules under `laclaugpt/` are **stubs**: every step body raises
`NotImplementedError`, and `pipeline_runner.py` sequences them through injected
step functions so the sequencing is testable without scientific bodies. So today
the executable analysis is the distributed worker and the readable surface is a
tested skeleton awaiting bodies -- neither is yet the independently runnable
step surface #341 requires.

## Three senses of "phase" -- say which one is meant

The word carries three different meanings here, and #341's own rule is that phase
drift must not happen. They are not interchangeable:

1. **Research-programme phase** -- the Paper 1 (research Phase 1) theory, sampling and
   method versus the ongoing AI26 study. Research phases describe research work, not
   software versions, and they do not select branches.
2. **`analysis_phase`** in `config/projects/ai26.yaml` -- a capability gate: at `1`
   the experimental modules are unavailable *regardless of what else is enabled*.
3. **The older label "Experimental Phase 2"** for steps 7 and 8 -- precisely what (2)
   gates; prefer *experimental module*.

So (3) is a subset of (2), and neither is (1). Recommended wording in all step
documentation: *Paper 1 method* / *capability gate* / *experimental module*.
This changes no branch governance and no version constant.


## Read-only per-step inspection (incremental #341 delivery)

The CLI now supports an explicit **contract-only** dry-run for each logical step:

```bash
python -m laclaugpt_data_analysis.ai26 step 4 --project ai26 --machine laskin --limit 10 --dry-run
python -m laclaugpt_data_analysis.ai26 step 7 --dry-run --json
```

This uses the packaged stage registry, **not** a second executor. Its output identifies
the declared modules, inputs/outputs, conditional media rules and research-phase status.
A logical step may map to more than one module (step 5) or none (step 0), and this
command is honest about that. It does **not** open Mongo/Redis, check a live record,
evaluate media applicability, claim work, render a model prompt, or perform analysis.
The `--limit` argument is validated but does not cap actual executions in this
inspection mode. For the existing bounded worker, see `scripts/ai26_run_next.sh`,
whose `--apply` is a separate operator action.

This is **not** a replacement for the independently executable scientific stage
bodies and reviewed Laskin pilot still required to close #341.

## Local registry/prompt integrity check

Run `python -m laclaugpt_data_analysis.ai26 validate-contract --json` before
reviewing or deploying registry changes. The offline command checks stage IDs,
logical reading-order numbering, canonical/experimental module separation,
conditional media requirements and the existence of versioned AI26 prompt
resources referenced by stages. It exits 1 and reports individual findings
when declarations disagree. It never claims tasks or calls a model.

This check is **not** the cross-repository schema validator at
`tools/check_ai26_contracts.py`, a fully assembled prompt preview, or a Laskin
production pilot. Those acceptance gates remain independent and required.
