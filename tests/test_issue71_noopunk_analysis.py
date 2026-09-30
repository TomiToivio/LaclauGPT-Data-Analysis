"""Issue LaclauGPT#71 — the NooPunk AI26 analysis node artifacts.

`main` is AI26 Phase 2 only, so the risk this file guards is not "does the runbook
read well" but four concrete failure modes:

1. **An interactive workstation quietly becoming an analysis node.** If a schedule
   appears for NooPunk, it stops being the on-demand test surface and starts
   competing with Laskin for the shared queue. That is the failure this change
   exists to prevent, so it is asserted directly.
2. **Cloud inference arriving without being asked.** A default that can reach
   `gemma4:31b-cloud` is an unasked cost and an undeclared provider change
   mid-corpus.
3. **The two nodes drifting into two systems.** NooPunk must share project id,
   storage roles and the distributed backend with Laskin, and differ *only* in
   machine class and execution mode.
4. **The runbook promising controls that do not exist**, or carrying a secret.

Run: python -m pytest tests/test_issue71_noopunk_analysis.py
"""

from __future__ import annotations

import re
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NOOPUNK_RUNBOOK = ROOT / "docs" / "AI26_NOOPUNK_ANALYSIS.md"
NOOPUNK_MACHINE = ROOT / "config" / "machines" / "noopunk.yaml"
NOOPUNK_SCRIPT = ROOT / "scripts" / "run_ai26_noopunk_analysis.sh"
LASKIN_SCRIPT = ROOT / "scripts" / "run_ai26_laskin_analysis.sh"
LASKIN_MACHINE = ROOT / "config" / "machines" / "laskin.yaml"
EXECUTION_DIR = ROOT / "config" / "execution"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


SECRET_PATTERNS = (
    r"mongodb(\+srv)?://[^\s\"']*:[^\s\"']*@",
    r"redis://[^\s\"']*:[^\s\"']*@",
    r"AKIA[0-9A-Z]{16}",
    r"(?i)password\s*=\s*[^\s\"']+",
)





def _run_wrapper(args, env_file, cwd):
    """Execute the wrapper with a minimal environment (its guard rails are the feature)."""

    env = {
        "PATH": "/usr/bin:/bin",
        "LACLAUGPT_ENV_FILE": str(env_file),
        "LACLAUGPT_PRIVATE_CONFIG_DIR": str(cwd),
    }
    return subprocess.run(
        ["bash", str(NOOPUNK_SCRIPT), *args],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=60,
    )


def _write_env(tmp_path):
    path = tmp_path / "noopunk.env"
    path.write_text(
        "LACLAUGPT_RUN_ID=ai26-noopunk-test\n"
        "LACLAUGPT_MONGODB_URI=mongodb://localhost:27017/\n"
        "LACLAUGPT_REDIS_URL=redis://localhost:6379/0\n"
        "LACLAUGPT_S3_BUCKET=test-bucket\n"
        "LACLAUGPT_LLM_ENDPOINT=http://127.0.0.1:11434\n"
    )
    return path

"""See the module docstring for what each group guards."""

def test_artifact_runbook_machine_config_and_script_exist(tmp_path=None) -> None:
    for path in (NOOPUNK_RUNBOOK, NOOPUNK_MACHINE, NOOPUNK_SCRIPT):
        assert path.exists(), f"{path.name} is missing"

def test_artifact_script_is_executable(tmp_path=None) -> None:
    assert NOOPUNK_SCRIPT.stat().st_mode & stat.S_IXUSR

def test_artifact_runbook_references_the_script_and_machine_config(tmp_path=None) -> None:
    text = _text(NOOPUNK_RUNBOOK)
    assert "scripts/run_ai26_noopunk_analysis.sh" in text
    assert "config/machines/noopunk.yaml" in text

def test_artifact_machine_template_names_the_node_and_its_class(tmp_path=None) -> None:
    text = _text(NOOPUNK_MACHINE)
    assert "machine: noopunk" in text
    assert "machine_class: laptop" in text

"""See the module docstring for what each group guards."""

"""NooPunk must not become an unattended analysis node."""

def test_schedule_no_execution_layer_exists_for_noopunk(tmp_path=None) -> None:
    schedules = [p.name for p in EXECUTION_DIR.glob("*noopunk*")]
    assert schedules == [], (
        f"a NooPunk execution/schedule layer appeared: {schedules}; "
        "analysis on this node is user-activated, not periodic"
    )

def test_schedule_machine_config_declares_cron_disabled(tmp_path=None) -> None:
    text = _text(NOOPUNK_MACHINE)
    assert re.search(r"^\s*cron:\s*false", text, re.MULTILINE), (
        "the NooPunk machine layer must declare cron: false"
    )

def test_schedule_runbook_states_there_is_no_cron_entry(tmp_path=None) -> None:
    text = " ".join(_text(NOOPUNK_RUNBOOK).split()).lower()
    assert "no cron entry" in text
    assert "user activated" in text or "user-activated" in text

def test_schedule_script_has_no_scheduler_or_loop(tmp_path=None) -> None:
    """A bounded batch, not a perpetual worker."""
    text = _text(NOOPUNK_SCRIPT)
    for forbidden in ("while true", "systemd", "crontab", "sleep 60"):
        assert forbidden not in text, f"the NooPunk wrapper contains {forbidden!r}"

def test_schedule_machine_config_sets_a_small_default_batch(tmp_path=None) -> None:
    text = _text(NOOPUNK_MACHINE)
    match = re.search(r"max_tasks_per_run:\s*(\d+)", text)
    assert match, "no bounded batch size declared"
    assert int(match.group(1)) < 10, (
        "the NooPunk default batch should be smaller than Laskin's, so a test "
        "session does not drain the shared queue"
    )

"""See the module docstring for what each group guards."""

"""Cloud inference must be explicit, announced, and never a fallback."""

def test_model_local_is_the_default_model(tmp_path=None) -> None:
    text = _text(NOOPUNK_SCRIPT)
    assert "gemma4:e2b" in text
    assert re.search(r'MODEL="\$\{LACLAUGPT_LLM_MODEL:-gemma4:e2b\}"', text), (
        "the default model branch must be the local gemma4:e2b"
    )

def test_model_cloud_model_is_named_and_announced(tmp_path=None) -> None:
    text = _text(NOOPUNK_SCRIPT)
    assert "gemma4:31b-cloud" in text
    assert "cloud model explicitly requested" in text

def test_model_cloud_fallback_is_disabled_on_both_paths(tmp_path=None) -> None:
    text = _text(NOOPUNK_SCRIPT)
    assert "LLM_ALLOW_CLOUD_FALLBACK=0" in text

def test_model_an_unknown_model_is_rejected_rather_than_defaulted(tmp_path=None) -> None:
    text = _text(NOOPUNK_SCRIPT)
    assert "there is no default that reaches the cloud" in text

"""See the module docstring for what each group guards."""

"""Same system as Laskin; only machine class and execution differ."""

def test_identity_shared_identity_matches_the_laskin_worker(tmp_path=None) -> None:
    noopunk = _text(NOOPUNK_SCRIPT)
    shared = (
        "export LACLAUGPT_PROJECT_ID=ai26",
        "export LACLAUGPT_STORAGE=distributed",
        "export LACLAUGPT_DATA_BACKEND=mongodb",
        "export LACLAUGPT_CACHE_BACKEND=redis",
        "export LACLAUGPT_OBJECT_BACKEND=s3",
    )
    for fragment in shared:
        assert fragment in noopunk, f"the NooPunk worker diverged on {fragment!r}"
        assert fragment in _text(LASKIN_SCRIPT), (
            f"Laskin no longer exports {fragment!r}; revisit this parity test"
        )

def test_identity_machine_and_execution_differ_from_laskin(tmp_path=None) -> None:
    noopunk = _text(NOOPUNK_SCRIPT)
    laskin = _text(LASKIN_SCRIPT)
    assert "export LACLAUGPT_MACHINE=laptop" in noopunk
    assert "export LACLAUGPT_MACHINE=linux-server" in laskin
    assert "export LACLAUGPT_EXECUTION=interactive" in noopunk
    assert "export LACLAUGPT_EXECUTION=cron" in laskin

def test_identity_required_environment_is_the_same_surface_as_laskin(tmp_path=None) -> None:
    noopunk = _text(NOOPUNK_SCRIPT)
    for required in (
        "LACLAUGPT_RUN_ID",
        "LACLAUGPT_MONGODB_URI",
        "LACLAUGPT_REDIS_URL",
        "LACLAUGPT_S3_BUCKET",
        "LACLAUGPT_LLM_ENDPOINT",
    ):
        assert f"{required}:?required" in noopunk, (
            f"{required} must be required, not optional: a local substitute "
            "would fork the corpus"
        )

def test_identity_script_refuses_to_create_a_local_namespace(tmp_path=None) -> None:
    text = _text(NOOPUNK_SCRIPT)
    for invented in ("noopunk__", "LACLAUGPT_MONGODB_DATABASE=noopunk"):
        assert invented not in text

"""See the module docstring for what each group guards."""

def test_runbook_runbook_states_the_resource_policy(tmp_path=None) -> None:
    text = " ".join(_text(NOOPUNK_RUNBOOK).split()).lower()
    assert "off by default" in text
    assert "always on" in text

def test_runbook_runbook_documents_both_model_modes(tmp_path=None) -> None:
    text = _text(NOOPUNK_RUNBOOK)
    assert "gemma4:e2b" in text
    assert "gemma4:31b-cloud" in text
    assert "--model cloud" in text
    assert "--model local" in text

def test_runbook_runbook_states_cloud_is_never_implicit(tmp_path=None) -> None:
    text = " ".join(_text(NOOPUNK_RUNBOOK).split()).lower()
    assert "cloud is never implicit" in text

def test_runbook_runbook_documents_dry_run_and_bounded_batch(tmp_path=None) -> None:
    text = _text(NOOPUNK_RUNBOOK)
    assert "--dry-run" in text
    assert "--max-tasks" in text

def test_runbook_runbook_states_that_laskin_stays_the_always_on_node(tmp_path=None) -> None:
    text = " ".join(_text(NOOPUNK_RUNBOOK).split()).lower()
    assert "laskin" in text and "always-on" in text
    assert "noopunk does not run analysis by default" in text or \
        "does not run analysis by" in text

def test_runbook_runbook_keeps_secrets_out(tmp_path=None) -> None:
    text = _text(NOOPUNK_RUNBOOK)
    assert "LaclauGPT-Private" in text
    assert "No hostname, port, URI, bucket name, account, credential" in text

"""See the module docstring for what each group guards."""


def test_secrets_public_artifacts_contain_no_credential(tmp_path=None) -> None:
    for path in (NOOPUNK_RUNBOOK, NOOPUNK_MACHINE, NOOPUNK_SCRIPT):
        text = _text(path)
        for pattern in SECRET_PATTERNS:
            assert re.search(pattern, text) is None, (
                f"{path.name} may contain a credential"
            )

def test_secrets_machine_template_has_no_absolute_private_path(tmp_path=None) -> None:
    text = _text(NOOPUNK_MACHINE)
    for prefix in ("/home/", "/Users/", "/mnt/", "/private/"):
        assert prefix not in text, f"the machine template hard-codes {prefix}"

    """See the module docstring for what each group guards."""

    """Execute the wrapper: its guard rails are the feature."""

    def test_behaviour_test_dry_run_defaults_to_the_local_model(tmp_path) -> None:
        result = _run_wrapper(["--dry-run"], _write_env(tmp_path), tmp_path)
        assert result.returncode == 0, result.stderr
        assert "model=gemma4:e2b" in result.stdout
        assert "mode=local" in result.stdout
        assert "no work claimed" in result.stdout

    def test_behaviour_test_dry_run_cloud_is_announced_and_selected(tmp_path) -> None:
        result = _run_wrapper(["--model", "cloud", "--dry-run"], _write_env(tmp_path), tmp_path)
        assert result.returncode == 0, result.stderr
        assert "gemma4:31b-cloud" in result.stdout
        assert "explicitly requested" in result.stderr

    def test_behaviour_test_an_unknown_model_is_refused(tmp_path) -> None:
        result = _run_wrapper(["--model", "gemma4:31b-cloud", "--dry-run"],
                           _write_env(tmp_path), tmp_path)
        assert result.returncode != 0
        assert "must be local or cloud" in result.stderr

    def test_behaviour_test_zero_batch_is_refused(tmp_path) -> None:
        result = _run_wrapper(["--max-tasks", "0", "--dry-run"], _write_env(tmp_path), tmp_path)
        assert result.returncode != 0
        assert "at least 1" in result.stderr

    def test_behaviour_test_non_numeric_batch_is_refused(tmp_path) -> None:
        result = _run_wrapper(["--max-tasks", "abc", "--dry-run"], _write_env(tmp_path), tmp_path)
        assert result.returncode != 0
        assert "positive integer" in result.stderr

    def test_behaviour_missing_env_file_fails_closed(tmp_path) -> None:
        result = _run_wrapper(["--dry-run"], tmp_path / "nope.env", tmp_path)
        assert result.returncode != 0
        assert "missing env file" in result.stderr

    def test_behaviour_test_unknown_argument_is_refused(tmp_path) -> None:
        result = _run_wrapper(["--force", "--dry-run"], _write_env(tmp_path), tmp_path)
        assert result.returncode != 0
        assert "unknown argument" in result.stderr
