"""Issue #503: all AI26 Laskin entry points must distinguish a skipped tick from success."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_both_laskin_entrypoints_return_three_when_lock_held():
    for name in ("run_ai26_laskin.sh", "run_ai26_laskin_analysis.sh"):
        script = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        lock_branch = script.split("if ! flock -n 9; then", 1)[1].split("\nfi", 1)[0]
        assert "exit 3" in lock_branch, name
        assert "exit 0" not in lock_branch, name
        assert "date -Is" in lock_branch or 'log "' in lock_branch, name
        assert "status=already_running" in lock_branch, name


def test_legacy_entrypoint_does_not_reintroduce_s3_for_text_only_ai26():
    script = (ROOT / "scripts/run_ai26_laskin_analysis.sh").read_text(encoding="utf-8")
    assert 'export LACLAUGPT_OBJECT_BACKEND=local' in script
    assert 'export LACLAUGPT_OBJECT_STORE_REQUIRED=0' in script
    assert 'LACLAUGPT_S3_BUCKET:?' not in script
    assert 'export LACLAUGPT_DATA_BACKEND=mongodb' in script
    assert 'export LACLAUGPT_CACHE_BACKEND=redis' in script
