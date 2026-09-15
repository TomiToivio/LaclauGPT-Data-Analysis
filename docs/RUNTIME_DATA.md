# Runtime data layout

All runtime and study-specific analysis material belongs under the repository-local `data/` directory. The entire `data/` tree is ignored by Git.

Use the shared structure: `data/logs`, `data/database`, `data/config`, `data/files`, `data/csv`, `data/jsonl`, `data/codebooks`, `data/sources`, `data/downloads`, `data/media`, `data/models/ollama`, `data/models/whisper`, `data/cache`, `data/tmp`, `data/exports`, `data/artifacts`, `data/runs`, `data/transcripts`, and `data/frames`.

Do not create top-level runtime roots such as `var/`, `logs/`, `database/`, `outputs/` or model-cache directories. Use `Settings.data_dir`, `Settings.data_path()` and `Settings.ensure_local_directories()`.

## Local module chain

If Collection and Analysis run on the same host, set `LACLAUGPT_COLLECTION_DATA_DIR` to the sibling Collection module's `data/` directory. Analysis may consume canonical Collection exports and local storage directly from there without copying private material into Git.

## Distributed module chain

For distributed deployments, use MongoDB for canonical records, Redis for cache/coordination, and S3-compatible object storage such as CSC Allas for files and large objects. CSV/JSONL transfer is the explicit manual fallback.
