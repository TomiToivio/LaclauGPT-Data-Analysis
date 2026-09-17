# Hungary26 reprocessing on CSC Roihu

This runbook implements issue #107's public side. The public repository contains generic normalization, audit logic, prompt contracts, public context, tests and Slurm launchers. Real Hungary26 rows, binary workbooks, researcher notes, private codebooks, machine paths and credentials remain under `LaclauGPT-Private/analysis/hungary26/`.

## Legacy findings carried forward

The legacy Hungary Roihu v1 splitter performed full-scan OCR and required agreement across multiple detectors, which made it slow and overly selective. The later `splitting2` design changed this to cheap-first candidate generation, OCR only around candidate boundaries and bounded expensive fallback. For current reprocessing, treat splitting as media preprocessing rather than a scientific requirement: short videos should remain whole where the current multimodal model can consume them, and longer media should be segmented only when needed while preserving parent identity, timestamps, checksums and audiovisual context.

The legacy `KEEP_PRIVATE/ep24/generated_codebooks/ep24_hu.json` is empty at the audited legacy head, so it is not a usable Hungary26 codebook by itself. Rebuild the private grounding layer from the Hungary26 workbooks/researcher material and any useful non-empty legacy aliases/notes.

## 1. Clone/update repositories

```bash
git clone https://github.com/TomiToivio/LaclauGPT-Data-Analysis.git
git clone git@github.com:TomiToivio/LaclauGPT-Private.git
cd LaclauGPT-Data-Analysis
git pull --ff-only
cd ../LaclauGPT-Private
git pull --ff-only
git submodule update --init --recursive
```

## 2. Migrate the private Hungary26 layer

From `LaclauGPT-Private`:

```bash
python analysis/hungary26/migrate_from_legacy.py \
  --legacy-root legacy/LaclauGPT-Discourse-Analysis-Private \
  --target-root analysis/hungary26
```

The migration intentionally looks under historical `data/hungrary2026/`. It is checksum-aware and safe to rerun. It refuses conflicting targets unless `--replace` is explicit. Review `analysis/hungary26/provenance/migration.json` after migration.

Expected private layout:

```text
analysis/hungary26/
  source/hungary2026_instagram.xlsx
  source/hungary2026_tiktok.xlsx
  codebooks/hungary26_private.json
  run/hungary26_roihu.yaml
  provenance/
  legacy/
  outputs/
```

## 3. Rebuild/review the private codebook

The private codebook must declare `project: hungary26`. Every entry must carry exactly one provenance class in `metadata.provenance_class`:

- `researcher_private`: workbook/researcher-grounded material with workbook/sheet/row or research-note provenance;
- `public_context`: dated public factual context with source URL/date;
- `model_candidate`: unreviewed model-discovered proposal.

Do not silently promote `model_candidate` entries. Preserve Hungarian surface forms and diacritics. Run collision review before analysis:

```bash
python -m laclaugpt_data_analysis.hungary26 codebook-collisions \
  --codebook ../LaclauGPT-Private/analysis/hungary26/codebooks/hungary26_private.json \
  --output ../LaclauGPT-Private/analysis/hungary26/outputs/codebook-collisions.json
```

The public source registry is `codebooks/public/hungary26_context_v1.yaml`. Public context supports recognition and chronology only, not substantive item labels.

## 4. Create the Roihu environment

On Roihu:

```bash
module purge
module load gcc/14.3.0
module load python-pytorch/2.13
module load ffmpeg
python -m venv --system-site-packages .venv-roihu
source .venv-roihu/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements/roihu-hungary26.txt
python -m pip install -e .
ffmpeg -version
ollama --version
```

The requirements file is intentionally Python-only. `ffmpeg`, Ollama, CUDA/GH200 support and CSC modules are system/runtime dependencies.

## 5. Configure local-only Ollama

Choose a loopback port at runtime; do not commit a machine-specific endpoint.

```bash
export OLLAMA_HOST=127.0.0.1:11434
export LACLAUGPT_LLM_ENDPOINT=http://127.0.0.1:11434
export LLM_MODE=local
export LLM_ALLOW_CLOUD_FALLBACK=0
ollama serve
```

In another shell, confirm the exact configured model exists:

```bash
ollama list
ollama show "${LACLAUGPT_HUNGARY26_MODEL:-gemma4:12b}"
```

Record the exact model identifier/digest in the private run metadata when available.

## 6. Preflight and source audit

```bash
export LACLAUGPT_HUNGARY26_PRIVATE_ROOT=/path/to/LaclauGPT-Private/analysis/hungary26
python -m laclaugpt_data_analysis.hungary26 preflight --private-root "$LACLAUGPT_HUNGARY26_PRIVATE_ROOT"

python -m laclaugpt_data_analysis.hungary26 audit \
  --instagram "$LACLAUGPT_HUNGARY26_PRIVATE_ROOT/source/hungary2026_instagram.xlsx" \
  --tiktok "$LACLAUGPT_HUNGARY26_PRIVATE_ROOT/source/hungary2026_tiktok.xlsx" \
  --json "$LACLAUGPT_HUNGARY26_PRIVATE_ROOT/outputs/source-audit.json" \
  --markdown "$LACLAUGPT_HUNGARY26_PRIVATE_ROOT/outputs/source-audit.md"
```

The generic audit checks record counts, platform differences, stable IDs, exact/near duplicates, missing fields and provenance preservation. Private tooling may append row-level examples and legacy-output comparisons under the private output tree.

## 7. Validate the public implementation offline

```bash
pytest -q tests/test_hungary26.py tests/test_study_deployment_harnesses.py
```

No network or real research rows are required for these tests.

## 8. Dry-run the canonical pipeline

The private `run/hungary26_roihu.yaml` must point to a canonical JSON/JSONL manifest and private effective codebook. The canonical manifest is staged privately from the normalized workbook records/media; never commit it.

```bash
export LACLAUGPT_HUNGARY26_RUN_CONFIG="$LACLAUGPT_HUNGARY26_PRIVATE_ROOT/run/hungary26_roihu.yaml"
scripts/hungary26/run_reprocess.sh dry-run
```

`laclaugpt-reprocess` validates the manifest/config/codebook and reports the planned record count and codebook fingerprint without inference.

## 9. Pilot

Generate a deterministic, platform-balanced source pilot first:

```bash
python -m laclaugpt_data_analysis.hungary26 pilot \
  --instagram "$LACLAUGPT_HUNGARY26_PRIVATE_ROOT/source/hungary2026_instagram.xlsx" \
  --tiktok "$LACLAUGPT_HUNGARY26_PRIVATE_ROOT/source/hungary2026_tiktok.xlsx" \
  --output "$LACLAUGPT_HUNGARY26_PRIVATE_ROOT/outputs/pilot-source-records.jsonl"
```

Stage the corresponding canonical pilot manifest privately, then submit:

```bash
sbatch --account=<CSC_PROJECT> \
  --export=ALL,MODE=pilot,LACLAUGPT_HUNGARY26_PRIVATE_ROOT="$LACLAUGPT_HUNGARY26_PRIVATE_ROOT",LACLAUGPT_HUNGARY26_RUN_CONFIG="$LACLAUGPT_HUNGARY26_RUN_CONFIG" \
  scripts/hungary26/hungary26_roihu_reprocess.sbatch
```

Do not start the full corpus until the pilot comparison has been manually reviewed. Compare entity resolution, theme normalization, speaker/source attribution, Hungarian ASR, translation preservation, multimodal evidence coverage, splitting/context preservation, unsupported interpretation rate, Laclau claim grounding, abstention quality, provenance and consistency across reposts/near duplicates. Longer output is not evidence of better output.

## 10. Full run / platform subsets / resume

```bash
# both platforms
sbatch --account=<CSC_PROJECT> --export=ALL,MODE=full,PLATFORM=both,... scripts/hungary26/hungary26_roihu_reprocess.sbatch

# Instagram only
sbatch --account=<CSC_PROJECT> --export=ALL,MODE=full,PLATFORM=instagram,... scripts/hungary26/hungary26_roihu_reprocess.sbatch

# TikTok only
sbatch --account=<CSC_PROJECT> --export=ALL,MODE=full,PLATFORM=tiktok,... scripts/hungary26/hungary26_roihu_reprocess.sbatch

# resume uses the same durable reprocessing completion markers/checkpoints
sbatch --account=<CSC_PROJECT> --export=ALL,MODE=resume,PLATFORM=both,... scripts/hungary26/hungary26_roihu_reprocess.sbatch
```

The account is always supplied at submission time. The shared reprocessing engine writes durable completion markers and atomic checkpoints, so reruns skip completed records unless explicitly forced.

## 11. Prompt/method contract

The Hungary-specific layer does not create a separate analysis architecture. The intended sequence is:

1. multimodal evidence extraction / descriptive frame analysis;
2. multimodal summary + light sociological analysis;
3. Laclau / Mouffe / Palonen analysis;
4. optional DNA-compatible discourse-network analysis when enabled in project settings;
5. other generic plugins only when methodologically justified.

Hungary prompt guardrails live under `src/laclaugpt_data_analysis/prompts/hungary26/`. AI26 Critical AI Studies interpretation is not enabled merely because it exists elsewhere in the package.

## 12. Output and privacy

Keep runtime logs, checkpoints, audits, comparisons and researcher exports outside the public checkout, preferably under private project storage/scratch with explicit retention. Public Git may contain synthetic fixtures, algorithms, schemas and documentation only. Never commit workbook rows, private handles, restricted source identifiers, researcher notes, CSC account IDs, cookies/tokens or private storage paths.
