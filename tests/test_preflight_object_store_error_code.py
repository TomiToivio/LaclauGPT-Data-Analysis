"""Regression tests: the object-store preflight must name the provider's failure code.

A fully exhausted Allas quota returned ``ClientError`` on every PUT. Because the
preflight reported only ``type(exc).__name__``, the daily log recorded a generic
store fault for 59 consecutive analysis cycles (AI26 #396) while the actionable
fact -- ``QuotaExceeded`` -- was in the discarded boto3 response.
"""
from __future__ import annotations

from laclaugpt_data_analysis import preflight
from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.preflight import _check_object_store, _s3_failure_detail


class _StoreError(Exception):
    """Stand-in for ``botocore.exceptions.ClientError`` (duck-typed on ``.response``)."""

    def __init__(self, code: str, status: int = 403):
        super().__init__(f"An error occurred ({code}) when calling the PutObject operation")
        self.response = {
            "Error": {"Code": code, "Message": "provider message"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }


class _RaisingStore:
    def __init__(self, *args, **kwargs):
        self.exc = kwargs.pop("_exc", None)

    def put_bytes(self, key, value, *, content_type="application/octet-stream"):
        raise _StoreError("QuotaExceeded")

    def delete(self, key):
        raise AssertionError("a failed upload must not attempt cleanup")


def _s3_settings() -> Settings:
    return Settings(
        project_id="ai26",
        object_backend="s3",
        s3_bucket="shared-ai26-bucket",
        s3_endpoint_url=None,
        s3_region=None,
        s3_signature_version="s3",
        s3_addressing_style="virtual",
    )


def test_failure_detail_keeps_provider_code_and_status():
    detail = _s3_failure_detail(_StoreError("QuotaExceeded"))
    assert detail["error"] == "_StoreError"
    assert detail["error_code"] == "QuotaExceeded"
    assert detail["http_status"] == 403


def test_failure_detail_without_response_reports_only_the_class():
    # A transport failure (no provider answer) must still be reportable.
    assert _s3_failure_detail(ConnectionError("boom")) == {"error": "ConnectionError"}


def test_object_store_check_reports_quota_code(monkeypatch):
    monkeypatch.setattr(preflight, "S3ArtifactStore", _RaisingStore)

    report = _check_object_store(_s3_settings())

    assert report["reachable"] is False
    assert report["writeable"] is False
    assert report["error_code"] == "QuotaExceeded"
    assert report["http_status"] == 403


def test_quota_refusal_is_named_in_problems(monkeypatch):
    store_check = {
        "backend": "s3",
        "configured": True,
        "reachable": False,
        "writeable": False,
        "error": "ClientError",
        "error_code": "QuotaExceeded",
        "http_status": 403,
    }
    monkeypatch.setattr("laclaugpt_data_analysis.config.load_settings", _s3_settings)
    monkeypatch.setattr(preflight, "_check_mongodb", lambda s: {"configured": False, "reachable": None})
    monkeypatch.setattr(preflight, "_check_redis", lambda s: {"configured": False, "reachable": None})
    monkeypatch.setattr(preflight, "_check_object_store", lambda s: dict(store_check))
    monkeypatch.setattr(
        preflight,
        "_check_ollama",
        lambda s: {"reachable": True, "model_present": True},
    )
    monkeypatch.setattr(preflight, "_dependency_problems", lambda *a, **k: [])

    report = preflight.preflight_report()

    problems = report["problems"]
    assert any("quota exhausted" in p and "QuotaExceeded" in p for p in problems), problems
    # The store answered; "unreachable" would send the operator to the wrong remedy.
    assert "object store unreachable" not in problems


def test_non_quota_write_failure_still_names_the_code(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "_check_object_store",
        lambda s: {"configured": True, "reachable": False, "writeable": False,
                   "error": "ClientError", "error_code": "AccessDenied"},
    )
    monkeypatch.setattr("laclaugpt_data_analysis.config.load_settings", _s3_settings)
    monkeypatch.setattr(preflight, "_check_mongodb", lambda s: {"configured": False, "reachable": None})
    monkeypatch.setattr(preflight, "_check_redis", lambda s: {"configured": False, "reachable": None})
    monkeypatch.setattr(preflight, "_check_ollama", lambda s: {"reachable": True, "model_present": True})
    monkeypatch.setattr(preflight, "_dependency_problems", lambda *a, **k: [])

    problems = preflight.preflight_report()["problems"]

    assert any("AccessDenied" in p for p in problems), problems
    assert not any("quota" in p for p in problems), problems
