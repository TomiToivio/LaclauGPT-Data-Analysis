from __future__ import annotations

from pathlib import Path


def test_laskin_wrapper_auto_refreezes_stale_manifest() -> None:
    script = Path("scripts/run_ai26_laskin.sh").read_text(encoding="utf-8")

    assert "AI26 manifest stale; re-freezing before scheduled analysis" in script
    assert "laclaugpt-freeze-ai26" in script
    assert '--public-git-sha "$RUNTIME_GIT"' in script
    assert 'if [[ "$MANIFEST_TREE" != "$RUNTIME_TREE" || "$MANIFEST_GIT" != "$RUNTIME_GIT" ]]' in script


def test_laskin_wrapper_refreezes_under_worker_lock() -> None:
    script = Path("scripts/run_ai26_laskin.sh").read_text(encoding="utf-8")

    lock_pos = script.index('exec 9>"$LOCK_FILE"')
    refreeze_pos = script.index("AI26 manifest stale; re-freezing before scheduled analysis")
    worker_pos = script.index('"$ROOT_DIR/.venv/bin/laclaugpt-analysis-worker"')

    assert lock_pos < refreeze_pos < worker_pos


def test_laskin_wrapper_preserves_private_overlay_and_public_codebook() -> None:
    script = Path("scripts/run_ai26_laskin.sh").read_text(encoding="utf-8")

    assert "LACLAUGPT_AI26_PUBLIC_CODEBOOK" in script
    assert "LACLAUGPT_AI26_PRIVATE_OVERLAY" in script
    assert 'FREEZE_ARGS+=(--private-overlay "$PRIVATE_OVERLAY")' in script
