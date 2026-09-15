# EP24 Finland/Poland reprocessing on CSC Roihu

This public repository contains the reusable, privacy-safe orchestration for reprocessing the EP24 Finland and Poland pilot data. The real research data and restricted project material stay outside Git.

## Privacy boundary

Do **not** commit any of the following here:

- Finland/Poland EP24 manifests or legacy row-level CSVs
- videos, transcripts, OCR output, annotations, researcher exports or reports
- human-generated country workbooks or compiled country codebooks
- private run configurations that reveal restricted source lists, paths, identifiers or credentials
- CSC project IDs, private scratch paths, Allas credentials, tokens, cookies, API keys or authenticated URLs

The public scripts fail closed when required private inputs are missing. Generated outputs are written below `LACLAUGPT_DATA_DIR`, which must point outside the repository.

## Private runtime layout

Stage the restricted inputs on the machine running the job, for example:

```text
$LACLAUGPT_DATA_DIR/
  ep24/
    csv/
      finland_sample20.csv
      poland_sample20.csv
      ep24_finland.csv
      ep24_poland.csv
    private_codebooks/
      ep24_fi.json
      ep24_pl.json
    run_configs/
      arena_ep24_finland_pilot.yaml
      arena_ep24_poland_pilot.yaml
    videos/
    annotations/
    human_reports/
    reviews/
    tmp/
```

The filenames mirror the current private EP24 pilot contract without publishing their contents.

## Current compatibility bridge

The historical end-to-end EP24 driver still imports private project modules and human-codebook support. Until that driver is fully disentangled, keep it in the restricted repository and provide it at runtime:

```bash
export LACLAUGPT_DATA_DIR=/private/runtime/root
export EP24_PRIVATE_REPO_ROOT=/path/to/LaclauGPT-Discourse-Analysis-Private
export EP24_PIPELINE_SCRIPT="$EP24_PRIVATE_REPO_ROOT/ep24_mm_pipeline.py"
```

This lets the public Data Analysis repository own the reusable deployment contract while the restricted repository continues to supply only the parts that cannot yet be published safely.

## Roihu environment

The batch harness follows the known working Roihu pattern:

- GH200 GPU allocation
- `gcc/14.3.0`, `python-pytorch/2.13`, and `ffmpeg`
- ARM64 virtual environment created on `roihu-gpu.csc.fi`
- local Ollama only, with cloud fallback disabled
- job-specific Ollama port
- default analysis model `gemma4:26b`
- default translation model `translategemma:27b`
- human country codebook required

Machine- and project-specific values are intentionally supplied at submission/runtime rather than committed.

Example:

```bash
cd /path/to/LaclauGPT-Data-Analysis
export LACLAUGPT_DATA_DIR=/scratch/<project>/<user>/laclaugpt-data
export EP24_PRIVATE_REPO_ROOT=/scratch/<project>/LaclauGPT-Discourse-Analysis-Private
export EP24_PIPELINE_SCRIPT="$EP24_PRIVATE_REPO_ROOT/ep24_mm_pipeline.py"
sbatch --account=<CSC_PROJECT> --export=ALL scripts/ep24/ep24_roihu_reprocess.sbatch
```

## What should move here later

The following code can be migrated into this public repository once it has been separated from restricted resources and tested using synthetic fixtures:

1. generic EP24 manifest/media adapters
2. generic ASR, OCR, keyframe and multimodal evidence stages
3. model/config validation helpers
4. canonical-data construction using the shared LaclauGPT interchange schema
5. generic researcher CSV and human-readable report exporters
6. data-quality and run-comparison utilities

The migration rule is simple: algorithms and schemas may be public; real research rows, identifiers, private codebooks, credentials and project-local configuration may not.
