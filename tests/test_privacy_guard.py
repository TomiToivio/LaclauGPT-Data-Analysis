"""Privacy/publication guard tests (issue #2).

These tests verify the repository-level publication rules: ignored private
paths, ignored data/config artefacts and a public-tree hygiene scan. All
fixtures are synthetic.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# The two Mapbox token prefixes ("p" and "s"), kept as separate letters so this
# guard does not need to spell a literal token prefix inside its own source.
_TOKEN_PREFIX_LETTERS = ("p", "s")


def _is_ignored(relpath: str) -> bool:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", relpath],
        cwd=REPO_ROOT,
    )
    return proc.returncode == 0


def test_private_codebook_directory_is_ignored():
    assert _is_ignored("codebooks/private/anything.md")
    assert _is_ignored("codebooks/private/nested/study_codebook.md")


def test_public_and_example_codebooks_are_tracked():
    assert not _is_ignored("codebooks/public/seed_ai_formations.md")
    assert not _is_ignored("codebooks/examples/synthetic_example.md")
    assert not _is_ignored("codebooks/README.md")


def test_research_data_and_config_patterns_are_ignored():
    for path in (
        "var/data/corpus.sqlite3",
        "artifacts/export.jsonl",
        ".env",
        "config.private.toml",
        "secrets.json",
        "credentials.json",
    ):
        assert _is_ignored(path), f"{path} must stay ignored"


def test_no_real_codebook_material_in_public_tree():
    """Diary-grounded legacy codebooks must never enter the public tree."""
    public_codebooks = list((REPO_ROOT / "codebooks" / "public").rglob("*.md"))
    forbidden_markers = ("research diary", "diary rows", "entities.xlsx")
    for codebook in public_codebooks:
        text = codebook.read_text(encoding="utf-8").lower()
        for marker in forbidden_markers:
            assert marker not in text, f"{codebook.name} contains private-source marker {marker!r}"


def test_public_codebooks_declare_synthetic_or_public_grounding():
    public_codebooks = list((REPO_ROOT / "codebooks" / "public").rglob("*.md"))
    assert public_codebooks, "public codebooks must exist"
    for codebook in public_codebooks:
        text = codebook.read_text(encoding="utf-8").lower()
        assert ("paper" in text or "synthetic" in text or "exploratory" in text), (
            f"{codebook.name} does not declare its grounding"
        )


def _mapbox_token_pattern() -> re.Pattern[str]:
    """Match a Mapbox access-token literal without writing one into this file.

    Mapbox tokens are ``pk.`` (public) or ``sk.`` (secret) followed by the
    base64url of a JSON payload, so the body always begins with ``eyJ``. Both
    prefixes are one of the ``_TOKEN_PREFIX_LETTERS`` followed by a literal
    ``k`` and a dot. Fragments are assembled at runtime so this guard's own
    source cannot match its own pattern, and no real token is stored here.
    """
    lead = "[" + "".join(_TOKEN_PREFIX_LETTERS) + "]" + "k"
    payload_lead = "e" + "y" + "J"
    return re.compile(rf"\b{lead}\.{payload_lead}[A-Za-z0-9_-]{{20,}}")


def _tracked_text_files() -> list[Path]:
    raw = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    return [REPO_ROOT / item.decode("utf-8") for item in raw if item]


def test_no_mapbox_token_literal_in_tracked_files() -> None:
    """No tracked text file may contain a Mapbox token literal.

    Credentials must come from the environment or private configuration only.
    The check is deliberately shape-based rather than keyword-based: the
    historical incident this guards against (secret-scanning alert #1) sat in a
    file whose only hint was a ``geocoder.mapbox(...)`` call. A token pasted into
    a differently worded file, a notebook, a JSON fixture or a Markdown note
    would have gone unnoticed by a "must contain the word mapbox" filter, and a
    ``*.py``-only glob would have missed every other file type.

    This scans every tracked text file at HEAD.
    """
    pattern = _mapbox_token_pattern()
    offenders: list[str] = []
    for path in _tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if pattern.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "tracked files contain a hard-coded Mapbox token: "
        + ", ".join(offenders)
        + ". Move it to LACLAUGPT_MAPBOX_API_KEY / private configuration and "
        "rotate the exposed credential."
    )


def test_mapbox_token_guard_detects_a_realistic_literal() -> None:
    """The guard must actually fire; a silently-passing scan proves nothing."""
    pattern = _mapbox_token_pattern()
    synthetic = "key = '" + "pk" + "." + "eyJ" + "a" * 40 + "'"
    assert pattern.search(synthetic), "guard no longer detects a token literal"
    assert not pattern.search("key = os.getenv('LACLAUGPT_MAPBOX_API_KEY')")
    assert not pattern.search(".env.example:LACLAUGPT_MAPBOX_API_KEY=your_mapbox_api_key_here")


def test_no_concrete_csc_project_ids_or_scratch_paths_in_tracked_text():
    """Public files must use placeholders for site-specific CSC deployment identifiers."""
    project_id = re.compile(r"\bproject_[0-9]{4,}\b", re.IGNORECASE)
    scratch_path = re.compile(r"/scratch/project_[0-9]+(?:/|\b)", re.IGNORECASE)
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    for raw in tracked:
        if not raw:
            continue
        path = REPO_ROOT / raw.decode("utf-8")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(REPO_ROOT)
        assert project_id.search(text) is None, f"{rel} contains a concrete CSC project identifier"
        assert scratch_path.search(text) is None, f"{rel} contains a concrete CSC scratch path"
