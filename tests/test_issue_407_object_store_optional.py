"""#407 / #396: a full object store must not block work that never writes to it.

The AI26 analysis worker reads records from MongoDB and calls a local model. The object store is where the
EP24 *media* pipeline stages files. When the Allas quota filled, preflight refused to start the analysis
worker at all — for 59 cycles — and 1,172 ready X records stayed unseeded behind an unrelated bucket.

The flag is deliberately not a silencer: the check still runs and its verdict stays in the report, so the
quota is visible in every log line. It only stops being *blocking* when the run declares it does not need it.
"""
from __future__ import annotations

from laclaugpt_data_analysis import preflight
from laclaugpt_data_analysis.config import Settings


def _settings(*, required: bool) -> Settings:
    return Settings(project_id="ai26", object_backend="s3", object_store_required=required,
                    s3_bucket="bucket", s3_endpoint_url="https://example.invalid")


def _patch(monkeypatch, store_check, settings):
    monkeypatch.setattr("laclaugpt_data_analysis.config.load_settings", lambda: settings)
    monkeypatch.setattr(preflight, "_check_mongodb", lambda s: {"configured": False, "reachable": None})
    monkeypatch.setattr(preflight, "_check_redis", lambda s: {"configured": False, "reachable": None})
    monkeypatch.setattr(preflight, "_check_object_store", lambda s: dict(store_check))
    monkeypatch.setattr(preflight, "_check_ollama",
                        lambda s: {"reachable": True, "model_present": True})
    monkeypatch.setattr(preflight, "_dependency_problems", lambda *a, **k: [])


QUOTA = {"configured": True, "reachable": True, "writeable": False,
         "error": "ClientError", "error_code": "QuotaExceeded", "http_status": 403}


def test_a_required_store_still_blocks_on_quota(monkeypatch):
    _patch(monkeypatch, QUOTA, _settings(required=True))
    report = preflight.preflight_report()
    assert report["status"] == "invalid"
    assert any("quota exhausted" in p for p in report["problems"])


def test_a_run_that_does_not_need_the_store_is_not_blocked_by_it(monkeypatch):
    _patch(monkeypatch, QUOTA, _settings(required=False))
    report = preflight.preflight_report()
    assert report["status"] == "ok", report["problems"]
    assert report["object_store_required"] is False
    # Visible, not hidden: the operator still sees the quota in the same report.
    assert report["checks"]["object_store"]["error_code"] == "QuotaExceeded"
    assert report["checks"]["object_store"]["blocking"] is False


def test_the_flag_does_not_hide_other_problems(monkeypatch):
    _patch(monkeypatch, QUOTA, _settings(required=False))
    monkeypatch.setattr(preflight, "_check_ollama", lambda s: {"reachable": True, "model_present": False})
    report = preflight.preflight_report()
    assert report["status"] == "invalid"
    assert any("model not present" in p for p in report["problems"])


def test_the_default_is_still_required():
    assert Settings().object_store_required is True
