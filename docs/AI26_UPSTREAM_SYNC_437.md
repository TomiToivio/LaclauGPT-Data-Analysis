# AI26 upstream sync (#437): change matrix against Multimodal-Analysis

Audited 2026-11-16. Target: this repository at `1077c42` (AI26 canonical pipeline, 7 steps).
Upstream: `LaclauGPT-Multimodal-Analysis` at `858f383` — the merge that carries #401 (RDF namespace),
#403 (step-7 truncation), #404 (Ollama pull races), #408 (stale SNA outputs), #409/#410 (step-8 JSON
budget, retry, provenance clearing), #246 (checkpoint-exporter manifest reads).

## The premise that changes the work

**AI26 does not run EP24's step modules.** Its canonical pipeline is
`preprocess → frame (media-optional) → summary → laclau → postprocess → evidence → graph`
(`ai26 stages`), with Phase 2 `dna`/`sna` kept separate. The upstream step 7/8 code is EP24's
Leifeld-DNA and SNA stages; AI26's equivalents are Phase 2 and are not part of Phase 1's contract.

So "port the upstream fixes" cannot mean copying those modules. What transfers is the **failure
handling around a model call**, and that layer is already provider-neutral in
`llm/{base,ollama,structured_output}.py`.

## Matrix

| upstream change | AI26 counterpart | state | evidence |
| --- | --- | --- | --- |
| #403 step-7 bounded JSON + compact retry | `llm/structured_output.chat_structured`: schema-example retry, `json_repair`, budget ladder | **already present** | `tests/test_ai26_upstream_step7_step8_regressions.py` (4 tests) |
| #409 step-8 explicit `num_predict` + retry | `llm/base.DEFAULT_OPTIONS` sets `num_predict`; `complete_with_empty_retry` retries empty answers; truncation surfaces as `LLMTruncationError` instead of being retried blindly | **already present, different shape** | same test module; `llm/ollama.py:326-358` |
| #409 truncation named, not disguised | `finish_reason`/`truncated` on `LLMResponse`, `LLMTruncationError` | **already present** | `llm/base.py` |
| #404 concurrent Ollama pulls / partial blobs | none — AI26 uses a configured endpoint, no pull path | **not applicable** | `config/machines/laskin.yaml` |
| #408 / #410 clear stale stage output on retry | AI26 writes stage output once per canonical record with claim semantics (`claims.py`) | **not directly applicable** | claim/lease model differs from EP24's in-place CSV |
| #401 RDF `.example` namespace | AI26 `graph` stage projects its own evidence graph, no RDF namespace | **not applicable** | `ai26 stages` |
| #246 read the checkpoint exporter's manifest | AI26 reads Collection handoff records, not an EP24 manifest | **not applicable** | `ai26 status` |
| `think=False` for structured output | applied in `llm/ollama.py` when the model supports it | **already present** | `llm/ollama.py:407` |

**Nothing was copied into AI26 in this pass, because nothing applicable was missing.** The one genuine
gap found is not inside AI26: the `pipelines/ep24/vendor/` copy of the EP24 step modules is 110 diff
lines behind upstream (missing #403's bounded prompt, `think=False`, the retry loop and #409/#410's
guards). It is referenced only by `ep24_stage_contract.py` and an example script, not by the AI26
runtime, so it is a maintenance defect for the vendored EP24 path — filed separately rather than
silently rewritten, because a vendor sync is its own change with its own review.

## Laskin verification performed (non-destructive)

```
$ python -m laclaugpt_data_analysis.ai26 status
  project   present  config/projects/ai26.yaml
  machine   present  config/machines/laskin.yaml
  execution present  config/execution/laskin-cron.yaml
  steps     7 canonical; Phase 2 separate: dna, sna
  registry  src/laclaugpt_data_analysis/stages/registry.json (v1)

$ python -m laclaugpt_data_analysis.ai26 validate-contract
  AI26 local registry/prompt contract: OK

$ python -m laclaugpt_data_analysis.ai26 step 1|5|6 --dry-run --limit 1
  contract inspection only: no records inspected or claimed, no provider invoked, no outputs written
```

**Not performed, deliberately:** a bounded `--apply` run. The AI26 collection and analysis cycles are
live on `laskin-cron` and a claim would consume records from the production queue; the issue forbids
disrupting a live production run, and the dry-run path above is the documented non-destructive
preflight. That boundary is stated rather than glossed: CI and mocks are not proof of Laskin
functionality, and neither is a dry run — what it proves is that the contract, the machine config and
the stage map resolve on the host that runs them.

## Follow-ups filed

- Vendored EP24 step 7/8 drift (see the issue referencing this document).
