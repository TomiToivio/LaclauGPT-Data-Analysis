"""Offline tests for debug/verbose mode and its redaction guarantees."""
from __future__ import annotations

import logging

import pytest

from laclaugpt_data_analysis.debug_mode import (
    DebugReport,
    bodies_allowed,
    configure_logging,
    debug_enabled,
    describe_environment,
    redact,
    sanitize_url,
    trace_enabled,
)


@pytest.fixture(autouse=True)
def _clean_mode_env(monkeypatch):
    monkeypatch.delenv("LACLAUGPT_DEBUG", raising=False)
    monkeypatch.delenv("LACLAUGPT_TRACE", raising=False)


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_debug_flag_accepts_documented_truthy_values(monkeypatch, value) -> None:
    monkeypatch.setenv("LACLAUGPT_DEBUG", value)
    assert debug_enabled()


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
def test_debug_flag_is_off_for_everything_else(monkeypatch, value) -> None:
    monkeypatch.setenv("LACLAUGPT_DEBUG", value)
    assert not debug_enabled()


def test_trace_implies_body_access_but_debug_alone_does_not(monkeypatch) -> None:
    assert not bodies_allowed()
    monkeypatch.setenv("LACLAUGPT_DEBUG", "1")
    assert debug_enabled()
    assert not trace_enabled()
    assert not bodies_allowed()  # debug alone must not dump research text

    monkeypatch.setenv("LACLAUGPT_TRACE", "1")
    assert trace_enabled()
    assert bodies_allowed()


def test_logging_level_follows_debug_mode(monkeypatch) -> None:
    assert configure_logging() == logging.INFO
    monkeypatch.setenv("LACLAUGPT_DEBUG", "1")
    assert configure_logging() == logging.DEBUG


# --- redaction -------------------------------------------------------------


def test_redact_removes_uri_credentials() -> None:
    out = redact("mongodb://alice:hunter2@db.example.invalid:27017/laclaugpt")
    assert "hunter2" not in out
    assert "alice" not in out
    assert "db.example.invalid" in out  # host is diagnostic-relevant


def test_redact_removes_redis_and_s3_credentials() -> None:
    out = redact("redis://default:s3cr3t@redis.example.invalid:6379/0")
    assert "s3cr3t" not in out
    assert "redis.example.invalid" in out


def test_redact_handles_key_value_forms() -> None:
    for text in (
        "LACLAUGPT_S3_SECRET_ACCESS_KEY=abc123def456",
        "password: swordfish",
        "api_key=sk-abcdefghijklmnopqrstuvwx",
        "Authorization: Bearer abcdef1234567890",
    ):
        out = redact(text)
        assert "abc123def456" not in out
        assert "swordfish" not in out
        assert "sk-abcdefghijklmnopqrstuvwx" not in out
        assert "abcdef1234567890" not in out


def test_redact_removes_cloud_key_shapes() -> None:
    assert "AKIAIOSFODNN7EXAMPLE" not in redact("key AKIAIOSFODNN7EXAMPLE here")
    assert "ghp_" not in redact("token ghp_" + "a" * 30)


def test_redact_is_safe_for_non_strings() -> None:
    assert "hunter2" not in redact({"uri": "mongodb://u:hunter2@h/db"})
    assert redact(None) == "None"
    assert redact(12345) == "12345"


def test_sanitize_url_drops_userinfo_and_secret_query_params() -> None:
    out = sanitize_url("https://user:pw@host.invalid/path?token=abc&ok=1")
    assert "pw" not in out
    assert "abc" not in out
    assert "host.invalid" in out
    assert "ok=1" in out


def test_sanitize_url_handles_empty() -> None:
    assert sanitize_url("") == ""


# --- report ----------------------------------------------------------------


def test_disabled_report_records_nothing() -> None:
    report = DebugReport(enabled=False)
    report.emit("anything", value="x")
    assert report.events == []
    assert report.summary()["debug"] is False


def test_enabled_report_records_sanitized_events() -> None:
    report = DebugReport(enabled=True)
    report.emit("connect", url="mongodb://u:hunter2@host.invalid/db")
    name, payload = report.events[0]
    assert name == "connect"
    assert "hunter2" not in str(payload)
    assert "host.invalid" in payload["url"]


def test_report_withholds_bodies_unless_trace_enabled(monkeypatch) -> None:
    report = DebugReport(enabled=True)
    report.emit("prompt", prompt="SECRET RESEARCH TEXT " * 10)
    assert "SECRET RESEARCH TEXT" not in str(report.events)
    assert "withheld" in report.events[0][1]["prompt"]

    monkeypatch.setenv("LACLAUGPT_TRACE", "1")
    traced = DebugReport(enabled=True)
    traced.emit("prompt", prompt="visible in trace")
    assert "visible in trace" in traced.events[0][1]["prompt"]


def test_report_redacts_credential_named_keys() -> None:
    report = DebugReport(enabled=True)
    report.emit("cfg", token="abc", password="def", api_key="ghi", harmless="keep")
    payload = report.events[0][1]
    assert payload["token"] == "<redacted>"
    assert payload["password"] == "<redacted>"
    assert payload["api_key"] == "<redacted>"
    assert payload["harmless"] == "keep"


def test_report_is_bounded() -> None:
    report = DebugReport(enabled=True, max_events=3)
    for index in range(10):
        report.emit("e", index=index)
    assert len(report.events) == 3


def test_report_stage_context_manager_records_duration_and_failure() -> None:
    report = DebugReport(enabled=True)
    with report.stage("multimodal_frame"):
        pass
    names = [name for name, _ in report.events]
    assert names == ["multimodal_frame.start", "multimodal_frame.end"]
    assert "elapsed_seconds" in report.events[1][1]

    with pytest.raises(RuntimeError):
        with report.stage("discourse"):
            raise RuntimeError("boom")
    assert report.events[-1][0] == "discourse.error"
    assert report.events[-1][1]["failure_class"] == "RuntimeError"


def test_summary_reports_names_not_payloads() -> None:
    report = DebugReport(enabled=True)
    report.emit("a", secret_value="x")
    summary = report.summary()
    assert summary["events"] == ["a"]
    assert "secret_value" not in str(summary)


# --- environment -----------------------------------------------------------


def test_describe_environment_is_credential_free(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_PROJECT_ID", "ai26")
    monkeypatch.setenv("LACLAUGPT_MACHINE", "linux-server")
    monkeypatch.setenv("LACLAUGPT_EXECUTION", "cron")
    monkeypatch.setenv("LACLAUGPT_LLM_MODE", "local-ollama")
    monkeypatch.setenv("LACLAUGPT_LLM_MODEL", "gemma4:12b")
    monkeypatch.setenv("LACLAUGPT_LLM_ENDPOINT", "http://127.0.0.1:11500")
    monkeypatch.setenv("LACLAUGPT_MONGODB_URI", "mongodb://u:hunter2@host.invalid/db")

    described = describe_environment()

    assert described["project_id"] == "ai26"
    assert described["machine"] == "linux-server"
    assert described["execution"] == "cron"
    assert described["llm_model"] == "gemma4:12b"
    assert described["llm_endpoint"] == "http://127.0.0.1:11500"
    # The URI itself is never returned, only whether one is configured.
    assert described["mongodb_configured"] is True
    assert "hunter2" not in str(described)
