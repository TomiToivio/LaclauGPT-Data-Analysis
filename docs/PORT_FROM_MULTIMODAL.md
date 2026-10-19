# Porting applicable fixes from Multimodal-Analysis into AI26 (#372)

Dispositions for the audit candidates named in the issue. Every row was read from
the upstream PR itself (`gh pr view` / `gh pr diff`), and every "already present"
claim was verified by grepping this repository rather than assumed.

Rule applied throughout: **AI26's Phase 1 methodology, codebooks, prompts and
schema contracts are locked.** EP24 Steps 1-9 are a reference implementation, not
a template. A port is only justified where AI26 is genuinely missing a behaviour.

| PR | Behaviour it changes upstream | Disposition | Reason |
| --- | --- | --- | --- |
| [#285](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/285) | Step 8 edges may only quote asr/ocr evidence; prompt contract rejects unknown stream kinds | Already present | AI26 has an evidence-integrity stage in `stages/registry.json` and strict span tests (`tests/test_evidence_span_strictness.py`); packet/stream machinery is EP24-format-specific |
| [#286](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/286) | Empty upstream must fail explicitly, not report false success; Allas/SLURM path handling | Already present | AI26's worker filters `handoff.status == "ready"` at claim time (`distributed_worker.py`); the rest is Roihu SLURM/Allas-specific |
| [#287](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/287) | Resume/cache hashes bound to effective generation settings | Already present | `phase1_protocol.py` fingerprints config + codebook + prompt; option resolution goes through `llm/` |
| [#288](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/288) | Ordered SLURM country submission with `afterok` chain and manifest | Not applicable | AI26/Laskin is cron-bounded with flock (`run_ai26_laskin.sh --once`); no SLURM |
| [#289](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/289) | Repairs four EP24 defects (SNA label regex, grounded-span heading parser) | Not applicable | Defects in EP24-only modules; AI26's `sna/` and `stages/laclau.py` are different implementations (the affected strings do not occur here) |
| [#290](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/290) | Evidence provenance labels; keep scanning after budget exhaustion; log dropped fields | Already present | AI26's evidence stage verifies asserted quotations against the source and the canonical contract keeps provenance distinguishable |
| [#291](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/291) | Strict per-country sequential pipeline; surface failed-row root cause | Not applicable | EP24 SLURM chain; the row-diagnostic pattern already exists (`tests/test_issue_283_failure_diagnostics.py`) |
| [#292](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/292) | **Fail-fast dependency preflight**: explicit import verification in the running interpreter, `STEP PREFLIGHT ERROR:`, exit 2 | **Ported** | AI26's `preflight.py` reported reachability but could not say *which interpreter was missing which module*, and the shell check silently skipped when `curl` was absent |
| [#293](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/293) | Regression test pinning the expected dependency tuple | **Ported** | `tests/test_issue372_preflight.py` |
| [#294](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/294) | One shared Steps 4-8 prompt/context builder as a single source | Already present | AI26 already has a canonical prompt library with stable IDs, versions and hashes (`src/laclaugpt_data_analysis/prompts/`, `docs/PROMPT_LIBRARY.md`); EP24's module layout is not portable |
| [#295](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/295) | Documentation-only review template for a manual acceptance gate | Not applicable | EP24-specific human-acceptance artifact, no production code |
| [#296](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis/pull/296) | Step 8 honours the shared context budget instead of a shadowed local name | Not applicable | Closed unmerged; an EP24 env-var shadowing defect in a component AI26 does not have. AI26 centralises budgets in `context_profiles.py` with regression coverage |

## The one port, in detail

`preflight.py` gains `_dependency_problems()`: it probes the interpreter that is
actually running for `pymongo`, `redis` and `ollama`, and names each missing one
with the interpreter path and the remedy. `main(--strict)` prints those messages
to stderr and exits 2, so misconfiguration fails in seconds at the operator
entrypoint rather than surfacing as a failed worker cycle. The check is purely
local -- an import probe, no sockets, no store, no model call -- and it prints no
credentials; endpoint reporting continues to go through `sanitize_url()`.

What it does not change: the existing Mongo/Redis/object-store/Ollama
reachability checks, the JSON report, the non-strict exit codes, or any pipeline
behaviour. Nothing in the Phase 1 contract, the codebooks or the prompts.

## Still to do on #372

The remaining candidates in the issue are dispositions above, not work items.
What remains is the verification half the issue also asks for: a bounded smoke
test and an end-to-end cycle on Laskin against the deployed revision, with the
logs inspected for failures, duplication and provenance.
