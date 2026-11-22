"""Regression contracts for the AI26 Laskin text-only cron runner (#499-#501)."""
from __future__ import annotations

from pathlib import Path

from laclaugpt_data_analysis import deploy_drift

ROOT = Path(__file__).resolve().parents[1]


def test_cron_scopes_strict_gate_to_analysis_checkout():
    wrapper = (ROOT / "scripts/run_ai26_laskin.sh").read_text(encoding="utf-8")
    assert 'deploy_drift --strict --path "$ROOT_DIR" --quiet' in wrapper
    assert 'deploy_drift --strict --quiet' not in wrapper
    # Preserve visibility of sibling drift without making it a deployment dependency.
    assert 'deploy_drift --quiet || log "WARNING:' in wrapper


def test_text_only_cron_never_requires_s3_or_media_staging():
    wrapper = (ROOT / "scripts/run_ai26_laskin.sh").read_text(encoding="utf-8")
    assert 'export LACLAUGPT_OBJECT_BACKEND=local' in wrapper
    assert 'export LACLAUGPT_OBJECT_STORE_REQUIRED=0' in wrapper
    assert ': "${LACLAUGPT_S3_BUCKET:?' not in wrapper
    assert 'export LACLAUGPT_DATA_BACKEND=${LACLAUGPT_DATA_BACKEND:-mongodb}' in wrapper
    assert 'export LACLAUGPT_CACHE_BACKEND=${LACLAUGPT_CACHE_BACKEND:-redis}' in wrapper


def test_strict_deployment_error_names_checkout_and_remedy(tmp_path, capsys):
    path = tmp_path / "not-a-checkout"
    path.mkdir()
    assert deploy_drift.main(["--strict", "--path", str(path), "--no-fetch"]) == 2
    # --strict --no-fetch is invalid; the operator gets an explicit usage error.
    assert "strict mode requires" in capsys.readouterr().err


def test_help_distinguishes_strict_from_warning_mode():
    help_text = deploy_drift.build_parser().format_help()
    assert "strict rejects unsafe" in help_text
