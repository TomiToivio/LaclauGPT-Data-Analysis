# AI26 upstream port: structured output, retries, stale outputs, output audit (#435)

What was taken from `LaclauGPT-Multimodal-Analysis` into AI26, at which revisions, and what was
deliberately not taken. The scientific method (Phase 1: Laclau/Mouffe, Palonen, sociotechnical
imaginaries, evidence traceability, uncertainty, human review) is untouched.

## Upstream references

| upstream | change | what it protects against |
| --- | --- | --- |
| `8cf5b97` (#403) | bound Step 7 JSON analysis text; retry truncated structured output | a truncated generation being parsed as a complete statement set |
| `6fb8548` (#407) | offline export-bundle audit: manifest hash, identities, child keys, stage statuses, JSONL | publishing a bundle whose parts disagree |
| `3724d0d` (#409) | Step 8 bounded JSON budget, 3 attempts, truncated ≠ schema-invalid | one retry class masking the other |
| `#408`/`#410` | clear previous Step 8 outputs when retrying; empty JSON / no evidence must not preserve earlier conclusions | stale claims surviving an empty re-run |
| `7366a02` (#404) | synchronise shared Ollama model pulls on Roihu | concurrent pulls racing a shared model store |

## What AI26 already had

`src/laclaugpt_data_analysis/llm/structured_output.py` carries the budget ladder
(`structured_output_ceiling`, `effective_structured_options`), `parse_structured`,
`classify_json_decode_failure` (truncated vs malformed vs schema-invalid) and `chat_structured` with
validation retries. `llm/ollama.py` classifies a length stop as `truncated`. `llm/base.py` carries the
generation fingerprint. `docs/AI26_PROMPT_BUDGET_425.md` measured AI26's ceiling and advises against
changing it without new evidence.

The prior screening is `docs/AI26_UPSTREAM_PORT_AUDIT.md`; its conclusions still hold — AI26 does not
resume by configuration hash (identity is the immutable handoff key), and its evidence grounding is
stricter than upstream's, recording offsets against the original text.

## What this port adds

1. **`tests/test_ai26_upstream_step7_step8_regressions.py`** (from #436, merged): provider length-stop
   never promotes partial JSON; retries double the budget; exhaustion raises `LLMTruncationError`;
   complete-but-invalid JSON uses validation retries rather than escalation.

2. **`tests/test_ai26_upstream_435_stale_outputs.py`**: the stale-output contract for the optional DNA
   stage, which is AI26's analogue of upstream Step 7/8 — a successful re-run with no statements
   replaces the previous statements; a failed re-run adds no statements and no history entry; the
   graph projection carries only what the record currently asserts, and no edge targets a relation id.

3. **Failure visibility** in `dna_statement_coding.py`: a failed retry is recorded in
   `analysis.plugin_failures["dna_statement_coding"]` with the error type and whether a previous
   result was preserved, before the exception propagates. Upstream clears stale outputs; AI26 keeps the
   last successful payload but now says so, so a consumer can tell "result from an earlier run" from
   "result of this run".

4. **`tools/ai26_output_audit.py`**: a read-only, privacy-safe audit of canonical output. Twelve
   checks: empty/duplicate identity, evidence without id, quote without offsets, offset mismatch,
   quote absent from the source text, relations citing unknown evidence, relations citing no evidence,
   complete-without-findings, complete-without-model-runs, model runs missing prompt/config revision,
   and a plugin result that disagrees with its latest recorded run. The report is counts, check names
   and status values — never a URL, a quotation or a transcript — so it can be published.

## Not ported, and why

- **EP24 step code**: AI26 has its own runner (`stages/runner.py`) and bounded worker. Copying numbered
  Roihu stage scripts would fork the pipeline.
- **Enabling DNA/SNA by default**: they remain opt-in; `docs/AI26_STEP_BY_STEP.md` keeps them marked
  non-production.
- **The Roihu model-pull synchronisation (#404)**: AI26's Laskin path does not pull models during
  analysis; the wrapper preflights the endpoint instead. Porting a lock for a race that does not occur
  would add a failure mode, not remove one.
- **The prompt-ceiling change**: `AI26_PROMPT_BUDGET_425.md` measured the budget; this port did not
  touch it.

## Verification

- Synthetic suites: `tests/test_ai26_upstream_step7_step8_regressions.py`,
  `tests/test_ai26_upstream_435_stale_outputs.py`, `tests/test_ai26_output_audit.py`.
- Laskin: `scripts/run_ai26_laskin.sh --check`, then a bounded cycle through the existing worker.
  Results are recorded in the issue comment; this document states the contract, not the run.
