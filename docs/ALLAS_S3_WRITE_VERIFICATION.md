# CSC Allas S3 write verification

Use this smoke test after configuring a distributed Analysis runtime and before enabling unattended Laskin/Roihu workers. A successful `HeadBucket` or list operation is not sufficient because read-only requests can succeed even when upload signature/addressing settings are wrong.

## Required client settings

For CSC Allas, configure the Analysis process with the same S3 contract used by Collection:

```bash
export LACLAUGPT_OBJECT_BACKEND=s3
export LACLAUGPT_S3_ENDPOINT=https://a3s.fi
export LACLAUGPT_S3_BUCKET=<bucket>
export LACLAUGPT_S3_REGION=<region>
export LACLAUGPT_S3_ACCESS_KEY_ID=<private-access-key>
export LACLAUGPT_S3_SECRET_ACCESS_KEY=<private-secret-key>
export LACLAUGPT_S3_SIGNATURE_VERSION=s3
export LACLAUGPT_S3_ADDRESSING_STYLE=auto
```

Keep credentials in ignored/private runtime configuration. Do not commit them.

`LACLAUGPT_S3_SIGNATURE_VERSION=s3` selects SigV2. `LACLAUGPT_S3_ADDRESSING_STYLE=auto` lets boto3 use virtual-host addressing for DNS-compatible bucket names rather than forcing path-style requests.

## Write → read → verify → delete

Run from the repository virtual environment with the private runtime environment loaded:

```bash
python - <<'PY'
from uuid import uuid4

from laclaugpt_data_analysis.config import load_settings
from laclaugpt_data_analysis.storage import artifact_store

settings = load_settings()
store = artifact_store(settings)
key = f"verification/allas-write-{uuid4().hex}.txt"
payload = "laclaugpt-analysis Allas write verification\n"

print(f"bucket: {settings.s3_bucket}")
print(f"key: {store._key(key)}")

try:
    store.put_text(key, payload)
    assert store.exists(key), "uploaded object is not visible through head_object"
    observed = store.get_text(key)
    assert observed == payload, "round-trip payload mismatch"
    print("PASS: write/read verification succeeded")
finally:
    store.delete(key)
    assert not store.exists(key), "verification object was not deleted"
    print("PASS: verification object deleted")
PY
```

The object is written below the configured project Analysis namespace, for example `projects/ai26/analysis/verification/...`.

## Failure interpretation

If the upload fails with `MissingContentLength`, confirm that `LACLAUGPT_S3_SIGNATURE_VERSION=s3` is loaded by the Analysis process. If Allas rejects the request with an addressing-related 403/compatibility error, confirm `LACLAUGPT_S3_ADDRESSING_STYLE=auto` and do not force `path` addressing.

Also verify the endpoint, bucket, region and credentials against the private `allas-conf` configuration. Avoid printing secret values in logs.
