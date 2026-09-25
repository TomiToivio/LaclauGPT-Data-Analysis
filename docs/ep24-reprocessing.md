# EP24 Finland/Poland Phase 1 reprocessing on CSC Roihu

Issue #245 uses a direct, privacy-safe public runner:

```text
python -m laclaugpt_data_analysis.ep24_roihu
```

The active research data and codebooks live only in `LaclauGPT-Private/analysis/ep24`. The public repository contains orchestration, schemas, synthetic tests, and the reusable SQLite/CSV implementation.

## Deployment

Set allocation and private roots in your local shell. Slurm account and private log destinations belong to the submission command, not tracked scripts:

```bash
export CSC_ACCOUNT="<your-csc-allocation>"
export LACLAUGPT_REPO_ROOT="<path-to-public-checkout>"
export LACLAUGPT_PRIVATE_REPO="<path-to-private-checkout>"
export LACLAUGPT_EP24_PRIVATE_ROOT="${LACLAUGPT_PRIVATE_REPO}/analysis/ep24"
cd "$LACLAUGPT_REPO_ROOT" && git pull --ff-only
cd "$LACLAUGPT_PRIVATE_REPO" && git pull --ff-only
mkdir -p "$LACLAUGPT_EP24_PRIVATE_ROOT/logs"
cd "$LACLAUGPT_REPO_ROOT"
EP24_RUN_MODE=smoke sbatch --account="$CSC_ACCOUNT" \\
  --output="$LACLAUGPT_EP24_PRIVATE_ROOT/logs/reprocess_%j.out" \\
  --error="$LACLAUGPT_EP24_PRIVATE_ROOT/logs/reprocess_%j.err" \\
  scripts/ep24/ep24_roihu_reprocess.sbatch
```

The launcher requires `LACLAUGPT_EP24_PRIVATE_ROOT`, defaults its public checkout to the submission directory and derives the private checkout from the private root unless overridden. Do not commit allocation IDs or absolute private paths.

The private repository tracks `analysis/ep24/logs/.gitkeep` so Slurm can open its log files before the job body runs. The job requires the five authoritative workbooks/CSVs and the three codebooks as ordinary tracked files in the canonical private repository. It never initializes a submodule or fetches legacy data on a compute node. One-time private promotion is `bash analysis/ep24/promote_legacy_inputs.sh --commit` followed by `git push origin main`. Only after both EP24 and Hungary26 inputs have been committed and pushed, run `bash scripts/finalize_native_research_data.sh` to remove the legacy gitlink safely. A Roihu ARM64 venv at `.venv-roihu-gpu` (or `EP24_ROIHU_VENV`) and local model availability/download access remain necessary. Run `EP24_RUN_MODE=pilot` or `full` only after reviewing smoke outputs; pilot is the default.

## Phase 1 analytical order

The runtime now enforces this order:

```text
legacy row + source metadata + media reference
  -> media materialization and checksum/type validation
  -> source text + legacy OCR/ASR + frames + optional new ASR
  -> Phase 1 descriptive social-semiotic pre-analysis
  -> Laclau/Mouffe/Palonen discourse analysis
  -> post-processing / codebook reconciliation
  -> Finland + Poland + combined CSV and QA
```

The descriptive pre-analysis is validated with `MultimodalSummaryProposal` and `assert_preanalysis_boundary`. Political fields such as ideology, populism, sentiment, frontiers, political demands, nodal points, and empty/floating signifiers are rejected at that stage and remain downstream.

Actual local image/frame paths are attached to the local Ollama request. A filename, S3 key, OCR string, or generated summary is never treated as visual evidence by itself.

## Evidence and provenance

The SQLite runtime includes explicit logical tables for:

```text
records
representations
media_assets
source_units
alignments
asr
ocr
frames
social_semiotic_preanalysis
relations
legacy_annotations
discourse_analysis
postprocess
comparative_analysis
uncertainties
failures
run_metadata
```

Legacy OCR and Whisper fields are retained as `legacy-derived-not-reverified` evidence until the original media is successfully reprocessed. Text-only rows remain valid and receive explicit missing-modality states rather than fabricated visual or audio evidence.

Media resolution accepts row-level local/media/Allas references and an optional private `media_mapping` in `run/ep24_roihu.yaml`. Materialized files are checksummed before downstream use. Existing valid local files are reused.

Optional new ASR is local-only and lazy. Set `enable_asr: true` in the private run config to use `faster-whisper`; otherwise the runtime records `not_processed` explicitly and can still use preserved legacy transcript evidence.

## Runtime contract

The Roihu implementation intentionally uses:

- SQLite for resumable state and provenance;
- Pandas CSV for researcher-readable input/output;
- local files for media, frames, logs, QA, and reports;
- local Ollama only, defaulting to `gemma4:12b`;
- ffmpeg/ffprobe for deterministic video frame extraction;
- no MongoDB;
- no Redis;
- no cloud fallback.

Cache fingerprints incorporate source content, model, prompt versions, codebook fingerprint, and private run configuration. Changed fingerprints invalidate downstream stages.

The launcher loads the Roihu `python-pytorch` and `ffmpeg` modules, unsets inherited Python path state, verifies NumPy/Pandas/openpyxl/PyYAML, performs a Phase 0 import smoke check, starts a job-local localhost Ollama server, verifies the model, and invokes the preflight before processing.

## Outputs

Private researcher outputs are:

```text
data/finland.csv
data/poland.csv
data/combined.csv
data/failures.csv
data/legacy_comparison.csv
outputs/roihu-reprocess-<job-id>.md
```

Original source and legacy columns are retained. New stage payload/status columns keep the social-semiotic pre-analysis, discourse analysis, multimodal coverage, codebook matches, and errors inspectable without erasing Finland/Poland identity.

Phase 0 requirements remain untouched. EP24/Roihu dependencies stay in `requirements/roihu-ep24.txt`.
