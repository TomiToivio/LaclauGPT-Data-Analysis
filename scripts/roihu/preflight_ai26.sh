#!/usr/bin/env bash
set -euo pipefail
: "${LACLAUGPT_RUN_ID:?missing run id}"
: "${LACLAUGPT_PRIVATE_CONFIG_DIR:?missing config directory}"
: "${LACLAUGPT_MONGODB_URI:?missing MongoDB URI}"
: "${LACLAUGPT_REDIS_URL:?missing Redis URL}"
: "${LACLAUGPT_S3_ENDPOINT:?missing Allas endpoint}"
: "${LACLAUGPT_S3_BUCKET:?missing Allas bucket}"
[[ "$LACLAUGPT_RUN_ID" == roihu-test-* ]] || { echo "Use isolated roihu-test run ID" >&2; exit 2; }
for f in run-manifest.json analysis.json codebook.json; do
  [[ -r "$LACLAUGPT_PRIVATE_CONFIG_DIR/$f" ]] || { echo "Missing private $f" >&2; exit 2; }
done
python - <<'PY'
import hashlib,json,os,pathlib
d=pathlib.Path(os.environ["LACLAUGPT_PRIVATE_CONFIG_DIR"])
m=json.loads((d/"run-manifest.json").read_text())
assert m.get("project_id")=="ai26", "Wrong project"
assert m.get("run_id")==os.environ["LACLAUGPT_RUN_ID"], "Run ID mismatch"
for name,key in [("analysis.json","config_sha256"),("codebook.json","codebook_sha256")]:
    expected=m.get(key)
    actual=hashlib.sha256((d/name).read_bytes()).hexdigest()
    assert expected==actual, f"{name} hash mismatch"
print("Frozen test manifest/config/codebook match")
PY
python -m laclaugpt_data_analysis.preflight --strict
echo "Preflight passed (configuration only; distributed service availability must also be verified during live test)"
