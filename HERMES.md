# Hermes operation

Hermes operates LaclauGPT Data Analysis through the same deployment profiles, canonical record contract and runner APIs used by researchers and schedulers.

Rules:

- Never reimplement analysis logic inside the agent layer.
- Validate the deployment profile before launching work.
- Never expose secrets when inspecting configuration.
- Never silently switch from local Ollama to cloud inference.
- `gemma4:31b-cloud` requires explicit cloud permission.
- Preserve canonical `source_url` identity across every run and backend.
- Keep codebook, review, provenance and uncertainty semantics intact.
- Store private runtime material, logs, exports, models and state under `data/` unless an external private scratch root is explicitly configured.
- Do not invent CSC project IDs, usernames, scratch paths or credentials.
- Use `integrations.hermes` operations for plan, launch, status, resume and export.
- Agent-triggered runs must carry `caller=hermes-agent` provenance.

See `docs/DEPLOYMENT_AND_HERMES.md` for laptop, Roihu, Linux-server and storage topology guidance.
