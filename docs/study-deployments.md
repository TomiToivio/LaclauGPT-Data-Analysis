# Study deployment contracts

This repository contains reusable analysis machinery. Research datasets, machine credentials, CSC project identifiers, private codebooks, operational target lists, and concrete host paths stay outside Git.

## AI26 near-real-time server analysis

AI26 can run as an incremental canonical-record pipeline on a Linux research server:

```text
LaclauGPT-Data-Collection canonical JSONL
        -> scripts/realtime/analyze_jsonl_incremental.py
        -> canonical analyzed JSONL
        -> LaclauGPT-Data-Visualization Monitor / Review / Explore
```

The incremental worker never modifies the Collection input. It keys completed work by canonical `source_url` and appends only previously unseen records to the Analysis output.

Example private runtime environment:

```bash
export LACLAUGPT_REALTIME_INPUT=/private/collection/ai26/canonical.jsonl
export LACLAUGPT_REALTIME_OUTPUT=/private/analysis/ai26/analyzed.jsonl
export LACLAUGPT_REALTIME_CODEBOOK=/private/codebooks/ai26.json
export LACLAUGPT_REALTIME_MODEL=gemma4:26b
export LACLAUGPT_REALTIME_INTERVAL_SECONDS=60
export LLM_MODE=local
export LLM_ALLOW_CLOUD_FALLBACK=0
scripts/realtime/run_analysis_loop.sh
```

The paths are placeholders. A private systemd unit or supervisor should provide the real locations and restart policy. Do not commit that unit if it contains private host/path information.

## EP24 Finland + Poland on CSC Roihu

The public EP24 compatibility harness is documented in `docs/ep24-reprocessing.md` and lives under `scripts/ep24/`. It provides the reusable Roihu/Ollama/runtime orchestration while requiring restricted EP24 manifests, row-level source data, country codebooks, run configuration, and the still-private compatibility driver to be staged externally.

EP24 output remains under the private runtime data root. The researcher-facing canonical/researcher exports can be visualized by `LaclauGPT-Data-Visualization` without committing them.

## Hungary26 reprocessing on CSC Roihu

Hungary26 uses the generic public batch harness:

```bash
sbatch --account=<CSC_PROJECT> \
  --export=ALL,STUDY_ID=hungary26,LACLAUGPT_DATA_DIR=/private/runtime,LACLAUGPT_REPROCESS_DRIVER=/private/bin/reprocess-study \
  scripts/reprocessing/roihu_study_reprocess.sbatch
```

The public batch file supplies:

- a GH200-compatible Roihu Slurm resource profile;
- compiler/PyTorch/ffmpeg module initialization;
- ARM64 virtualenv and NumPy preflight;
- job-specific loopback Ollama server;
- local-only LLM mode with cloud fallback disabled;
- configurable local analysis and translation models;
- a private executable driver boundary.

The Hungary26 driver, dataset, project-specific codebook, researcher annotations, media and concrete CSC paths remain private. The driver should emit canonical analysis records and provenance so Visualization does not need a Hungary-specific schema.

## Why EP24 and Hungary26 are different public harnesses

EP24 currently has a known compatibility pipeline with several historical multimodal/export steps, so its public wrapper preserves that exact external contract. Hungary26 is being prepared as a new modular study and therefore uses the generic study-reprocessing boundary. As reusable EP24 stages are migrated into this package, both should converge on the generic contract.

## Safety invariant

No deployment may silently fall back from local research inference to cloud inference. Public scripts set `LLM_ALLOW_CLOUD_FALLBACK=0`. Any future cloud use must be an explicit study-level decision with appropriate data-governance review.
